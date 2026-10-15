from datetime import date, timedelta
import json

import pytest

from mega_collector.engine import audit_records, collect
from mega_collector.source import LATEST_URL, Page
from mega_collector.storage import SQLiteRepository, StorageError


def draw(draw_id):
    day = date(2016, 7, 20) + timedelta(days=draw_id - 1)
    return {"draw_id": draw_id, "draw_date": day.isoformat(),
        "n1": 1, "n2": 2, "n3": 3, "n4": 4, "n5": 5, "n6": 6,
        "source_name": "fixture", "source_url": (
            "https://www.minhngoc.net.vn/ket-qua-xo-so/dien-toan-vietlott/mega-6x45/"
            + day.strftime("%d-%m-%Y") + ".html"),
        "fetched_at": "2026-10-14T00:00:00Z", "verification_status": "secondary"}


def page(ids, *, url=LATEST_URL, older=None, pending=0):
    records = [draw(draw_id) for draw_id in ids]
    return Page(url=url, records=records, older_url=older, pending=pending,
        date_urls={record["draw_date"]: record["source_url"] for record in records})


class Source:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def fetch(self, url):
        self.calls.append(url)
        assert url in self.pages, f"Unexpected source navigation: {url}"
        return self.pages[url]


@pytest.fixture
def repository():
    repo = SQLiteRepository(":memory:")
    yield repo
    repo.close()


def seed(repo, ids):
    run = repo.start_run("fixture")
    repo.ingest_batch([draw(draw_id) for draw_id in ids], run)
    repo.finish_run(run)
    return run


def test_synced_database_fetches_only_latest_page(repository):
    seed(repository, range(1, 7))
    source = Source({LATEST_URL: page([6, 5, 4], older=draw(4)["source_url"])})
    result = collect(repository, source, mode="sync", progress=lambda _: None)
    assert source.calls == [LATEST_URL]
    assert result["status"] == "succeeded"
    assert result["new_rows"] == 0
    assert result["duplicate_rows"] == 3


def test_backfill_follows_observed_link_and_fills_oldest_range(repository):
    older_url = draw(4)["source_url"]
    source = Source({LATEST_URL: page([6, 5, 4], older=older_url),
        older_url: page([4, 3, 2, 1], url=older_url)})
    result = collect(repository, source, mode="backfill", progress=lambda _: None)
    assert source.calls == [LATEST_URL, older_url]
    assert result["status"] == "succeeded"
    assert result["new_rows"] == 6
    assert result["duplicate_rows"] == 1
    assert result["missing_draw_ids"] == []


def test_middle_gap_uses_nearest_persisted_newer_anchor(repository):
    seed(repository, [1, 2, 4, 5, 6])
    anchor = draw(4)["source_url"]
    source = Source({LATEST_URL: page([6, 5]), anchor: page([4, 3, 2], url=anchor)})
    result = collect(repository, source, mode="sync", progress=lambda _: None)
    assert source.calls == [LATEST_URL, anchor]
    assert result["new_rows"] == 1
    assert result["status"] == "succeeded"


def test_page_limit_is_partial_and_resumable(repository):
    source = Source({LATEST_URL: page([6, 5, 4], older=draw(4)["source_url"])})
    result = collect(repository, source, mode="backfill", max_pages=1, progress=lambda _: None)
    assert result["status"] == "partial"
    assert result["missing_draw_ids"] == [1, 2, 3]
    assert result["error_count"] == 0


def test_source_gap_is_reported_without_repeat_request_loop(repository):
    seed(repository, [1, 2, 4, 5, 6])
    anchor = draw(4)["source_url"]
    source = Source({LATEST_URL: page([6, 5]), anchor: page([4], url=anchor)})
    result = collect(repository, source, mode="sync", progress=lambda _: None)
    assert source.calls == [LATEST_URL, anchor]
    assert result["status"] == "failed"
    assert result["missing_draw_ids"] == [3]
    assert repository.list_issues()[0]["kind"] == "missing"


def test_historical_conflict_cannot_turn_into_success_on_next_sync(repository):
    run = seed(repository, range(1, 7))
    repository.record_issue(run, "conflict", "Previously observed mismatch", {"draw_id": 3}, 3)
    result = collect(repository, Source({LATEST_URL: page([6, 5])}), mode="sync", progress=lambda _: None)
    assert result["status"] == "failed"
    assert result["integrity_error_count"] == 1
    assert result["coverage"] == "incomplete_or_has_issues"


def test_unobserved_latest_pending_range_is_partial(repository):
    seed(repository, range(1, 7))
    result = collect(repository, Source({LATEST_URL: page([], pending=1)}), mode="sync", progress=lambda _: None)
    assert result["status"] == "partial"
    assert result["source_latest_draw_id"] is None


def test_initial_database_read_failure_finalizes_started_run(repository, monkeypatch):
    def fail():
        raise StorageError("Read failed")
    monkeypatch.setattr(repository, "list_draws", fail)
    with pytest.raises(StorageError, match="Read failed"):
        collect(repository, Source({}), mode="sync", progress=lambda _: None)
    row = repository._connection.execute("select status,error_count,finished_at from ingestion_runs").fetchone()
    assert row["status"] == "failed"
    assert row["error_count"] == 1
    assert row["finished_at"] is not None


def test_audit_rejects_future_facts_duplicate_ids_and_stale_source_bound():
    future = draw(1)
    future["draw_date"] = (date.today() + timedelta(days=2)).isoformat()
    report = audit_records([future], source_latest=1)
    assert report["invalid_records"]
    assert report["coverage"] == "incomplete_or_has_issues"
    report = audit_records([draw(1), draw(1)], source_latest=1)
    assert report["invalid_records"]
    report = audit_records([draw(1), draw(2)], source_latest=1)
    assert report["source_bound_errors"] == [2]
    assert report["coverage"] == "incomplete_or_has_issues"


def test_audit_reports_invalid_id_without_crashing():
    broken = draw(1)
    broken.pop("draw_id")
    assert audit_records([broken])["invalid_records"]


def test_cli_returns_failure_for_historical_integrity_conflict(repository, tmp_path, monkeypatch):
    from mega_collector import cli
    run = seed(repository, range(1, 7))
    repository.record_issue(run, "conflict", "Previously observed mismatch", {}, 3)
    monkeypatch.setattr(cli, "repository", lambda _: repository)
    monkeypatch.setattr(cli, "MinhNgocSource", lambda **_: Source({LATEST_URL: page([6, 5])}))
    assert cli.main(["--env-file", str(tmp_path / "missing.env"), "sync",
        "--checkpoint", str(tmp_path / "checkpoint.json")]) == 5


def test_summary_compresses_large_gap_list_without_changing_artifact_data(capsys, monkeypatch):
    from mega_collector.cli import summary
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    data = {"missing_draw_ids": [*range(1, 1501), 1575]}
    summary(data)
    printed = json.loads(capsys.readouterr().out)
    assert printed["missing_draw_ranges"] == ["1-1500", "1575"]
    assert printed["missing_draw_count"] == 1501
    assert "missing_draw_ids" not in printed
    assert len(data["missing_draw_ids"]) == 1501
