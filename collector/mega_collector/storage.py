"""Durable storage with immutable draw facts and idempotent REST ingestion."""

from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests


class StorageError(RuntimeError):
    """Database error whose message contains no credentials or response body."""


DRAW_FIELDS = (
    "draw_id", "draw_date", "n1", "n2", "n3", "n4", "n5", "n6",
    "source_name", "source_url", "fetched_at", "verification_status",
)
FACT_FIELDS = ("draw_date", "n1", "n2", "n3", "n4", "n5", "n6")
RUN_FIELDS = {"status", "new_rows", "duplicate_rows", "error_count", "latest_draw_id", "meta"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("Record must be an object")
    clean = {key: record.get(key) for key in DRAW_FIELDS}
    if type(clean["draw_id"]) is not int or not 0 < clean["draw_id"] <= 2147483647:
        raise ValueError("draw_id must be a positive PostgreSQL integer")
    value = clean["draw_date"]
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("draw_date must be an ISO date")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError("draw_date must be a valid ISO date") from None
    numbers = [clean[f"n{index}"] for index in range(1, 7)]
    if any(type(number) is not int for number in numbers):
        raise ValueError("Numbers must be integers")
    if not (1 <= numbers[0] and numbers[-1] <= 45) or any(
        left >= right for left, right in zip(numbers, numbers[1:])
    ):
        raise ValueError("Numbers must be six distinct ascending integers in 1..45")
    for key in ("source_name", "source_url"):
        if not isinstance(clean[key], str) or not clean[key].strip():
            raise ValueError(f"{key} is required")
    if not isinstance(clean["verification_status"], str) or clean["verification_status"] not in {
        "official", "secondary", "cross_checked",
    }:
        raise ValueError("Invalid verification_status")
    if not isinstance(clean["fetched_at"], str):
        raise ValueError("fetched_at must be an ISO timestamp with timezone")
    try:
        timestamp = datetime.fromisoformat(clean["fetched_at"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError
    except ValueError:
        raise ValueError("fetched_at must be an ISO timestamp with timezone") from None
    clean["fetched_at"] = timestamp.astimezone(timezone.utc).isoformat()
    return clean


def _validate_finish(fields: dict[str, Any]) -> dict[str, Any]:
    if set(fields) - RUN_FIELDS:
        raise ValueError("Unsupported ingestion run fields")
    for key in ("new_rows", "duplicate_rows", "error_count"):
        if key in fields and (type(fields[key]) is not int or fields[key] < 0):
            raise ValueError(f"{key} must be a non-negative integer")
    if "meta" in fields and not isinstance(fields["meta"], dict):
        raise ValueError("meta must be an object")
    return {"status": "succeeded", **fields, "finished_at": _utc_now()}


class SupabaseRepository:
    """REST repository; every retried write is idempotent.

    New sb_secret keys belong only in ``apikey``, never in Authorization Bearer.
    """

    def __init__(self, url: str, key: str, session: requests.Session | None = None,
                 *, timeout: float = 30, retry_attempts: int = 4, page_size: int = 1000) -> None:
        parsed = urlsplit(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or (
            parsed.username or parsed.password or parsed.query or parsed.fragment
        ):
            raise ValueError("SUPABASE_URL must be a plain HTTP(S) project URL")
        if not key.strip():
            raise ValueError("A Supabase API key is required")
        if retry_attempts < 1 or timeout <= 0 or not 1 <= page_size <= 1000:
            raise ValueError("Invalid repository timeout, retry count, or page size")
        self._url = url.strip().rstrip("/") + "/rest/v1"
        self._session = session if session is not None else requests.Session()
        self._headers = {"apikey": key.strip(), "Content-Type": "application/json"}
        if not key.strip().startswith("sb_"):
            self._headers["Authorization"] = f"Bearer {key.strip()}"
        self._timeout, self._retry_attempts, self._page_size = timeout, retry_attempts, page_size

    def _request(self, method: str, endpoint: str, *, params: dict[str, Any] | None = None,
                 body: Any = None, prefer: str | None = None) -> Any:
        headers = dict(self._headers)
        if prefer:
            headers["Prefer"] = prefer
        for attempt in range(self._retry_attempts):
            try:
                response = self._session.request(method, self._url + "/" + endpoint,
                    headers=headers, params=params, json=body, timeout=self._timeout)
            except (requests.RequestException, TimeoutError):
                if attempt + 1 == self._retry_attempts:
                    raise StorageError("Supabase connection failed after retries") from None
                time.sleep(min(0.5 * 2**attempt, 4))
                continue
            if response.status_code in {408, 429, 500, 502, 503, 504} and attempt + 1 < self._retry_attempts:
                retry_after = response.headers.get("Retry-After", "")
                delay = min(float(retry_after), 10) if retry_after.isdecimal() else min(0.5 * 2**attempt, 4)
                time.sleep(delay)
                continue
            if not 200 <= response.status_code < 300:
                raise StorageError(f"Supabase request failed (HTTP {response.status_code})")
            if response.status_code == 204 or not response.content:
                return None
            try:
                return response.json()
            except ValueError:
                raise StorageError("Supabase returned an invalid JSON response") from None
        raise StorageError("Supabase connection failed after retries")

    def _list(self, table: str, order: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        while True:
            page = self._request("GET", table, params={
                "select": "*", "order": order, "limit": self._page_size, "offset": len(rows),
            })
            if not isinstance(page, list) or any(not isinstance(row, dict) for row in page):
                raise StorageError("Supabase returned an invalid row list")
            if not page:
                return rows
            # A Supabase server can enforce a lower limit, so stop only on empty.
            rows.extend(page)

    def list_draws(self) -> list[dict[str, Any]]:
        return self._list("mega645_draws", "draw_id.asc")

    def all_rows(self) -> list[dict[str, Any]]:
        return self.list_draws()

    def list_issues(self) -> list[dict[str, Any]]:
        return self._list("ingestion_issues", "created_at.asc,id.asc")

    def start_run(self, mode: str) -> str:
        run_id = str(uuid.uuid4())
        self._request("POST", "ingestion_runs", params={"on_conflict": "id"},
            body={"id": run_id, "mode": mode, "status": "running", "started_at": _utc_now()},
            prefer="resolution=ignore-duplicates,return=minimal")
        return run_id

    def finish_run(self, run_id: str, **fields: Any) -> None:
        self._request("PATCH", "ingestion_runs", params={"id": f"eq.{uuid.UUID(run_id)}"},
            body=_validate_finish(fields), prefer="return=minimal")

    def record_issue(self, run_id: str | None, kind: str, message: str,
                     payload: Any, draw_id: int | None = None) -> None:
        self._request("POST", "ingestion_issues", params={"on_conflict": "id"}, body={
            "id": str(uuid.uuid4()), "run_id": run_id, "kind": kind,
            "message": message, "payload": payload, "draw_id": draw_id,
        }, prefer="resolution=ignore-duplicates,return=minimal")

    def ingest_batch(self, records: list[dict[str, Any]], run_id: str) -> dict[str, int]:
        if not isinstance(records, list) or len(records) > 1000:
            raise ValueError("A batch must be a list of at most 1000 records")
        result = self._request("POST", "rpc/ingest_mega645_batch", body={
            "p_records": records, "p_run_id": str(uuid.UUID(run_id)), "p_request_id": str(uuid.uuid4()),
        })
        keys = ("new_rows", "duplicate_rows", "error_count")
        if not isinstance(result, dict) or any(type(result.get(key)) is not int or result[key] < 0 for key in keys):
            raise StorageError("Supabase returned invalid ingestion counters")
        return {key: result[key] for key in keys}

    def close(self) -> None:
        self._session.close()


_SQLITE_SCHEMA = """
create table if not exists mega645_draws (
    draw_id integer primary key check(draw_id > 0 and draw_id <= 2147483647),
    draw_date text not null unique,
    n1 integer not null, n2 integer not null, n3 integer not null,
    n4 integer not null, n5 integer not null, n6 integer not null,
    source_name text not null check(length(source_name) > 0),
    source_url text not null check(length(source_url) > 0), fetched_at text not null,
    verification_status text not null check(verification_status in ('official','secondary','cross_checked')),
    created_at text not null, updated_at text not null,
    check(1 <= n1 and n1 < n2 and n2 < n3 and n3 < n4 and n4 < n5 and n5 < n6 and n6 <= 45)
);
create table if not exists ingestion_runs (
    id text primary key, mode text not null, status text not null default 'running',
    started_at text not null, finished_at text,
    new_rows integer not null default 0 check(new_rows >= 0),
    duplicate_rows integer not null default 0 check(duplicate_rows >= 0),
    error_count integer not null default 0 check(error_count >= 0),
    latest_draw_id integer, meta text not null default '{}'
);
create table if not exists ingestion_issues (
    id text primary key, run_id text references ingestion_runs(id),
    kind text not null, message text not null, payload text not null,
    draw_id integer, created_at text not null
);
create index if not exists ingestion_issues_run_idx on ingestion_issues(run_id, created_at);
"""


class SQLiteRepository:
    """Explicit durable offline backend with the same no-overwrite semantics."""

    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(path), timeout=30)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("pragma foreign_keys = on")
        self._connection.execute("pragma journal_mode = wal")
        self._connection.executescript(_SQLITE_SCHEMA)

    def list_draws(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._connection.execute("select * from mega645_draws order by draw_id")]

    def all_rows(self) -> list[dict[str, Any]]:
        return self.list_draws()

    def list_issues(self) -> list[dict[str, Any]]:
        result = []
        for row in self._connection.execute("select * from ingestion_issues order by created_at, id"):
            item = dict(row)
            item["payload"] = json.loads(item["payload"])
            result.append(item)
        return result

    def start_run(self, mode: str) -> str:
        run_id = str(uuid.uuid4())
        with self._connection:
            self._connection.execute("insert into ingestion_runs(id,mode,status,started_at) values(?,?,?,?)",
                (run_id, mode, "running", _utc_now()))
        return run_id

    def finish_run(self, run_id: str, **fields: Any) -> None:
        update = _validate_finish(fields)
        if "meta" in update:
            update["meta"] = json.dumps(update["meta"], ensure_ascii=False)
        columns = ",".join(f"{key}=?" for key in update)
        with self._connection:
            cursor = self._connection.execute(f"update ingestion_runs set {columns} where id=?",
                (*update.values(), run_id))
            if cursor.rowcount != 1:
                raise StorageError("Ingestion run does not exist")

    def _insert_issue(self, run_id: str | None, kind: str, message: str,
                      payload: Any, draw_id: int | None = None) -> None:
        self._connection.execute(
            "insert into ingestion_issues(id,run_id,kind,message,payload,draw_id,created_at) values(?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), run_id, kind, message, json.dumps(payload, ensure_ascii=False), draw_id, _utc_now()))

    def record_issue(self, run_id: str | None, kind: str, message: str,
                     payload: Any, draw_id: int | None = None) -> None:
        with self._connection:
            self._insert_issue(run_id, kind, message, payload, draw_id)

    def ingest_batch(self, records: list[dict[str, Any]], run_id: str) -> dict[str, int]:
        if not isinstance(records, list) or len(records) > 1000:
            raise ValueError("A batch must be a list of at most 1000 records")
        counters = {"new_rows": 0, "duplicate_rows": 0, "error_count": 0}
        with self._connection:
            # Obtain the write lock before checking IDs/dates in separate connections.
            self._connection.execute("begin immediate")
            if self._connection.execute("select id from ingestion_runs where id=?", (run_id,)).fetchone() is None:
                raise StorageError("Ingestion run does not exist")
            for record in records:
                try:
                    candidate = _validate_record(record)
                except ValueError as error:
                    draw_id = record.get("draw_id") if isinstance(record, dict) else None
                    self._insert_issue(run_id, "invalid", str(error), record,
                        draw_id if type(draw_id) is int and 0 < draw_id <= 2147483647 else None)
                    counters["error_count"] += 1
                    continue
                existing = self._connection.execute("select * from mega645_draws where draw_id=?",
                    (candidate["draw_id"],)).fetchone()
                if existing is not None:
                    if all(existing[key] == candidate[key] for key in FACT_FIELDS):
                        counters["duplicate_rows"] += 1
                    else:
                        self._insert_issue(run_id, "conflict", "Existing draw id has different date or numbers",
                            {"incoming": record, "existing": dict(existing)}, candidate["draw_id"])
                        counters["error_count"] += 1
                    continue
                existing = self._connection.execute("select * from mega645_draws where draw_date=?",
                    (candidate["draw_date"],)).fetchone()
                if existing is not None:
                    self._insert_issue(run_id, "date_conflict", "Existing draw date belongs to another draw id",
                        {"incoming": record, "existing": dict(existing)}, candidate["draw_id"])
                    counters["error_count"] += 1
                    continue
                stamp = _utc_now()
                values = [candidate[key] for key in DRAW_FIELDS] + [stamp, stamp]
                self._connection.execute("insert into mega645_draws(" + ",".join(DRAW_FIELDS)
                    + ",created_at,updated_at) values(" + ",".join("?" for _ in values) + ")", values)
                counters["new_rows"] += 1
        return counters

    def close(self) -> None:
        self._connection.close()
