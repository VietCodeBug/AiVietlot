"""Read-only comparison of real database records with an independent website."""
import json
import os
from datetime import date
from pathlib import Path
import sys

from dotenv import load_dotenv

from mega_collector.models import utc_now
from mega_collector.source import MinhNgocSource, SourceError, parse_vietmy
from mega_collector.storage import StorageError, SupabaseRepository


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(encoding="utf-8-sig")
    repo = SupabaseRepository(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])
    try:
        rows = {r["draw_id"]: r for r in repo.list_draws()}
        latest = max(rows)
        requested = sorted({1, latest // 2, latest - 4, latest})
        source = MinhNgocSource()
        results = []
        for draw_id in requested:
            if draw_id not in rows:
                results.append({"draw_id": draw_id, "status": "missing_in_database"})
                continue
            stored = rows[draw_id]
            day = date.fromisoformat(stored["draw_date"]).strftime("%d-%m-%Y")
            url = f"https://xosovietmy.vn/xs-mega-ngay-{day}.html"
            record = parse_vietmy(source._read_html(url), url)[0]
            fields = ["draw_id", "draw_date", *[f"n{i}" for i in range(1, 7)]]
            matched = all(stored[k] == record[k] for k in fields)
            results.append({"draw_id": draw_id, "draw_date": stored["draw_date"],
                            "database_numbers": [stored[f"n{i}"] for i in range(1, 7)],
                            "second_source_numbers": [record[f"n{i}"] for i in range(1, 7)],
                            "status": "matched" if matched else "conflict", "independent_url": url,
                            "original_url": stored["source_url"]})
        report = {"checked_at": utc_now(), "sample_count": len(results), "results": results,
                  "all_matched": all(r["status"] == "matched" for r in results),
                  "note": "Both sources are secondary; sample checks do not officially verify the entire dataset."}
        Path("artifacts").mkdir(exist_ok=True)
        Path("artifacts/crosschecks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["all_matched"] else 1
    except (SourceError, StorageError, KeyError):
        print("Independent source verification failed; no database facts changed")
        return 2
    finally:
        repo.close()


if __name__ == "__main__":
    raise SystemExit(main())
