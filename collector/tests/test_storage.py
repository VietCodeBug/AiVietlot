from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import uuid
from unittest.mock import patch

import pytest
import requests

from mega_collector.storage import SQLiteRepository, StorageError, SupabaseRepository


def draw(**changes):
    return {
        "draw_id": 1, "draw_date": "2016-07-20",
        "n1": 2, "n2": 3, "n3": 5, "n4": 11, "n5": 17, "n6": 45,
        "source_name": "fixture", "source_url": "https://example.test/mega/1",
        "fetched_at": "2026-10-14T11:00:00Z", "verification_status": "secondary",
        **changes,
    }


def test_sqlite_persists_draws_and_never_overwrites(tmp_path):
    path = tmp_path / "draws.sqlite3"
    repository = SQLiteRepository(path)
    run = repository.start_run("backfill")
    assert repository.ingest_batch([draw()], run) == {
        "new_rows": 1, "duplicate_rows": 0, "error_count": 0,
    }
    first = repository.list_draws()[0]
    assert repository.ingest_batch([
        draw(source_name="other source", verification_status="official"),
        draw(n1=1),
        draw(draw_id=2),
        draw(draw_id=3, draw_date="2016-07-22", n6=46),
    ], run) == {"new_rows": 0, "duplicate_rows": 1, "error_count": 3}
    assert repository.list_draws() == [first]
    assert {issue["kind"] for issue in repository.list_issues()} == {"conflict", "date_conflict", "invalid"}
    repository.finish_run(run, new_rows=1, duplicate_rows=1, error_count=3,
        latest_draw_id=1, status="partial", meta={"source": "fixture"})
    repository.close()
    reopened = SQLiteRepository(path)
    assert reopened.list_draws() == [first]
    assert len(reopened.list_issues()) == 3
    with sqlite3.connect(path) as connection:
        row = connection.execute("select status,new_rows,error_count,meta from ingestion_runs where id=?", (run,)).fetchone()
        assert row[:3] == ("partial", 1, 3)
        assert json.loads(row[3]) == {"source": "fixture"}
    reopened.close()


@pytest.mark.parametrize("changes", [
    {"draw_id": True}, {"draw_id": 0}, {"draw_date": "2026-02-30"},
    {"n1": 0}, {"n2": 2}, {"n2": 2.5}, {"n6": 46},
    {"fetched_at": "2026-10-14T11:00:00"}, {"source_url": ""},
    {"verification_status": "made_up"}, {"verification_status": []},
])
def test_invalid_records_are_quarantined(changes):
    repository = SQLiteRepository(":memory:")
    run = repository.start_run("backfill")
    assert repository.ingest_batch([draw(**changes)], run)["error_count"] == 1
    assert repository.list_draws() == []
    assert repository.list_issues()[0]["kind"] == "invalid"
    repository.close()


def test_atomic_batches_and_concurrent_collectors(tmp_path):
    path = tmp_path / "parallel.sqlite3"
    repository = SQLiteRepository(path)
    run = repository.start_run("backfill")
    repository.close()

    def ingest():
        connection = SQLiteRepository(path)
        try:
            return connection.ingest_batch([draw()], run)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: ingest(), range(2)))
    assert sum(result["new_rows"] for result in results) == 1
    assert sum(result["duplicate_rows"] for result in results) == 1
    repository = SQLiteRepository(path)
    # Unknown run aborts the whole transaction before any draw can be persisted.
    with pytest.raises(StorageError):
        repository.ingest_batch([draw(draw_id=2, draw_date="2016-07-22")], str(uuid.uuid4()))
    assert len(repository.list_draws()) == 1
    repository.close()


class FakeResponse:
    def __init__(self, data=None, status=200, content=True):
        self.status_code = status
        self.headers = {}
        self.content = b"response" if content else b""
        self.data = data

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **options):
        self.calls.append((method, url, options))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    def close(self):
        pass


def test_supabase_key_headers_and_pagination_respect_server_limit():
    session = FakeSession([FakeResponse([{"draw_id": 1}]), FakeResponse([{"draw_id": 2}]), FakeResponse([])])
    repository = SupabaseRepository("https://example.supabase.co", "sb_secret_fake", session)
    assert repository.list_draws() == [{"draw_id": 1}, {"draw_id": 2}]
    assert [call[2]["params"]["offset"] for call in session.calls] == [0, 1, 2]
    assert session.calls[0][2]["headers"]["apikey"] == "sb_secret_fake"
    assert "Authorization" not in session.calls[0][2]["headers"]


def test_rpc_retry_retains_request_id_and_redacts_network_errors():
    session = FakeSession([requests.Timeout("credential leaked here"), FakeResponse({
        "new_rows": 1, "duplicate_rows": 0, "error_count": 0,
    })])
    repository = SupabaseRepository("https://example.supabase.co", "sb_secret_fake", session)
    with patch("mega_collector.storage.time.sleep"):
        assert repository.ingest_batch([draw()], str(uuid.uuid4()))["new_rows"] == 1
    assert session.calls[0][2]["json"] == session.calls[1][2]["json"]
    session = FakeSession([requests.Timeout("sb_secret_fake")])
    repository = SupabaseRepository("https://example.supabase.co", "sb_secret_fake", session, retry_attempts=1)
    with pytest.raises(StorageError) as error:
        repository.list_draws()
    assert "sb_secret_fake" not in str(error.value)


def test_http_error_body_never_leaks_credentials():
    session = FakeSession([FakeResponse({"error": "sb_secret_fake"}, status=401)])
    repository = SupabaseRepository("https://example.supabase.co", "sb_secret_fake", session)
    with pytest.raises(StorageError, match="HTTP 401") as error:
        repository.list_draws()
    assert "sb_secret_fake" not in str(error.value)
