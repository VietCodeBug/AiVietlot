from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import utc_now, validate_draw
from .source import LATEST_URL, SourceError


def audit_records(records: list[dict], issues: list[dict] | None = None, *, source_latest: int | None = None) -> dict:
    ids = {r.get("draw_id") for r in records if type(r.get("draw_id")) is int and r["draw_id"] > 0}
    latest = max(ids, default=0)
    upper = max(latest, source_latest or 0)
    missing = sorted(set(range(1, upper + 1)) - ids)
    invalid = []
    seen_dates = set()
    seen_ids = set()
    valid_rows = []
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    for row in records:
        try:
            validate_draw(row, today=today)
            if row["draw_id"] in seen_ids:
                raise ValueError("Duplicate draw id")
            if row["draw_date"] in seen_dates:
                raise ValueError("Ngày quay trùng")
            seen_ids.add(row["draw_id"])
            seen_dates.add(row["draw_date"])
            valid_rows.append(row)
        except (KeyError, TypeError, ValueError) as exc:
            invalid.append({"draw_id": row.get("draw_id"), "message": str(exc)})
    conflicts = [i for i in issues or [] if i.get("kind") in {"conflict", "date_conflict"}]
    ordered = sorted(valid_rows, key=lambda r: r["draw_id"])
    chronology_errors = [b["draw_id"] for a, b in zip(ordered, ordered[1:]) if a["draw_date"] >= b["draw_date"]]
    source_bound_errors = [latest] if source_latest is not None and latest > source_latest else []
    clean = bool(ids) and not (missing or invalid or conflicts or chronology_errors or source_bound_errors)
    return {"checked_at": utc_now(), "total_draws": len(records),
            "first_draw_id": min(ids, default=None), "latest_draw_id": latest or None,
            "first_date": ordered[0]["draw_date"] if ordered else None,
            "latest_date": ordered[-1]["draw_date"] if ordered else None,
            "source_latest_draw_id": source_latest,
            "missing_draw_ids": missing, "invalid_records": invalid,
            "chronology_errors": chronology_errors,
            "source_bound_errors": source_bound_errors,
            "conflict_count": len(conflicts), "issue_count": len(issues or []),
            "coverage": "complete_through_observed_source" if source_latest and clean else "contiguous_local_range" if clean else "incomplete_or_has_issues",
            "verification_counts": {v: sum(r.get("verification_status") == v for r in records)
                                    for v in ["official", "secondary", "cross_checked"]}}


def write_json(path: str | Path | None, data: dict) -> None:
    if path is not None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(target)


def collect(repo, source, *, mode: str, max_pages: int | None = None,
            checkpoint: str | None = None, progress=print) -> dict:
    """Resume from durable DB facts and navigate actual observed source links."""
    run_id = None
    result = {"run_id": None, "mode": mode, "new_rows": 0, "duplicate_rows": 0,
              "error_count": 0, "pages_fetched": 0, "pending_results": 0}
    rows = {}
    source_latest = None
    fetched = set()

    def consume(url):
        page = source.fetch(url)
        fetched.add(page.url)
        result["pages_fetched"] += 1
        result["pending_results"] += page.pending
        for issue in page.issues:
            repo.record_issue(run_id, issue["kind"], issue["message"], issue["payload"], issue.get("draw_id"))
            result["error_count"] += 1
        counts = repo.ingest_batch(page.records, run_id)
        for key in ("new_rows", "duplicate_rows", "error_count"):
            result[key] += counts[key]
        # Fetch persisted rows after a conflict; never let incoming conflicting
        # facts influence gap navigation or the reported database range.
        if counts["error_count"]:
            rows.clear()
            rows.update({r["draw_id"]: r for r in repo.list_draws()})
        else:
            for record in page.records:
                rows.setdefault(record["draw_id"], record)
        if page.records:
            progress(f"Trang {result['pages_fetched']}: #{min(r['draw_id'] for r in page.records):05d}–#{max(r['draw_id'] for r in page.records):05d}; thêm {counts['new_rows']}, trùng {counts['duplicate_rows']}, lỗi {counts['error_count']}")
        write_json(checkpoint, {**result, "updated_at": utc_now(), "next_url": page.older_url,
                                "latest_source_draw_id": source_latest, "latest_database_draw_id": max(rows, default=None)})
        return page

    try:
        run_id = repo.start_run(mode)
        result["run_id"] = run_id
        rows.update({r["draw_id"]: r for r in repo.list_draws()})
        latest_page = consume(LATEST_URL)
        source_latest = max((r["draw_id"] for r in latest_page.records), default=None)
        if not latest_page.records and latest_page.issues:
            raise SourceError("Không có kỳ hợp lệ trên trang nguồn")
        if source_latest is None:
            if latest_page.pending:
                progress("Nguồn đang cập nhật kết quả; sẽ thử lại ở lần sync sau")
            else:
                raise SourceError("Không tìm thấy kết quả Mega hoàn chỉnh")
        blocked = set()
        while source_latest and (max_pages is None or result["pages_fetched"] < max_pages):
            missing = sorted(set(range(1, source_latest + 1)) - rows.keys() - blocked, reverse=True)
            if not missing:
                break
            target = missing[0]
            newer = sorted(i for i in rows if i > target)
            if not newer:
                raise SourceError(f"Không có liên kết đã xác minh để tìm kỳ #{target:05d}")
            url = source.navigation_url(rows[newer[0]]) if hasattr(source, "navigation_url") else rows[newer[0]]["source_url"]
            # The latest page already includes this anchor; its oldest observed
            # link is the next page without wasting another duplicate request.
            if url in latest_page.date_urls.values() and target < min(r["draw_id"] for r in latest_page.records):
                url = latest_page.older_url or url
            previous_count = len(rows)
            while url and url not in fetched and (max_pages is None or result["pages_fetched"] < max_pages):
                page = consume(url)
                if target in rows or (page.records and min(r["draw_id"] for r in page.records) <= target):
                    break
                url = page.older_url
            if target not in rows and len(rows) == previous_count:
                blocked.add(target)
                repo.record_issue(run_id, "missing", f"Nguồn không trả kỳ #{target:05d}", {"source_url": url}, target)
                result["error_count"] += 1
            # Reaching the limit is a resumable partial backfill, not success.
            if max_pages and result["pages_fetched"] >= max_pages:
                break
        records = repo.list_draws()
        report = audit_records(records, repo.list_issues(), source_latest=source_latest)
        integrity_errors = (len(report["invalid_records"]) + len(report["chronology_errors"])
                            + report["conflict_count"] + len(report["source_bound_errors"]))
        result.update({"latest_draw_id": report["latest_draw_id"], "source_latest_draw_id": source_latest,
                       "total_draws": report["total_draws"], "missing_draw_ids": report["missing_draw_ids"],
                       "coverage": report["coverage"], "integrity_error_count": integrity_errors})
        status = ("failed" if result["error_count"] or integrity_errors else "partial"
                  if report["missing_draw_ids"] or source_latest is None else "succeeded")
        result["status"] = status
        repo.finish_run(run_id, status=status, new_rows=result["new_rows"], duplicate_rows=result["duplicate_rows"],
                        error_count=result["error_count"], latest_draw_id=result["latest_draw_id"], meta=result)
        write_json(checkpoint, {**result, "updated_at": utc_now()})
        return result
    except Exception as exc:
        result["error_count"] += 1
        result["status"] = "failed"
        # Only our own sanitized source/storage exceptions reach the CLI.
        result["failure_type"] = type(exc).__name__
        if run_id is not None:
            try:
                repo.finish_run(run_id, status="failed", new_rows=result["new_rows"], duplicate_rows=result["duplicate_rows"],
                                error_count=result["error_count"], latest_draw_id=max(rows, default=None), meta=result)
            except Exception:
                result["run_finalization_failed"] = True
        try:
            write_json(checkpoint, {**result, "updated_at": utc_now()})
        except OSError:
            pass
        raise
