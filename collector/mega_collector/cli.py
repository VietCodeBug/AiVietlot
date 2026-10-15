from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .engine import audit_records, collect, write_json
from .models import DRAW_FIELDS
from .source import MinhNgocSource, SourceError
from .storage import SQLiteRepository, StorageError, SupabaseRepository


def positive(value: str) -> int:
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("Giá trị phải lớn hơn 0")
    return result


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Thu thập toàn bộ lịch sử Mega 6/45 với nguồn và audit rõ ràng")
    p.add_argument("--backend", choices=["supabase", "sqlite"], default="supabase", help="Database đích (mặc định Supabase)")
    p.add_argument("--database", default="data/mega645.sqlite3", help="Đường dẫn SQLite local")
    p.add_argument("--env-file", default=".env", help="File cấu hình bí mật local")
    sub = p.add_subparsers(dest="command", required=True)
    for name, help_text in [("backfill", "Nhập lịch sử, tiếp tục từ các kỳ còn thiếu trong DB"),
                            ("sync", "Lấy kỳ mới và lấp khoảng trống bằng liên kết đã quan sát")]:
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--max-pages", type=positive, default=30 if name == "sync" else None,
                         help="Giới hạn trang mỗi lần (sync mặc định 30); chạy lại để tiếp tục")
        cmd.add_argument("--checkpoint", default=f"artifacts/{name}.json", help="Bằng chứng tiến độ; resume dựa trên DB")
        cmd.add_argument("--delay", type=float, default=1.0, help="Khoảng nghỉ giữa request, tối thiểu 0.5 giây")
    audit = sub.add_parser("audit", help="Kiểm tra phạm vi mã kỳ, số thiếu, dữ liệu sai và mâu thuẫn")
    audit.add_argument("--output", help="Lưu báo cáo JSON")
    audit.add_argument("--check-source", action="store_true", help="Đọc nguồn thật để so sánh kỳ mới nhất")
    export = sub.add_parser("export", help="Xuất CSV UTF-8 có provenance")
    export.add_argument("--output", default="data/mega645.csv")
    imp = sub.add_parser("import-local", help="Nhập dữ liệu SQLite đã thu thập vào Supabase theo batch")
    imp.add_argument("--input", default="data/mega645.sqlite3")
    imp.add_argument("--batch-size", type=positive, default=200)
    return p


def repository(args):
    if args.backend == "sqlite":
        return SQLiteRepository(args.database)
    url, key = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SECRET_KEY", "")
    if not url or not key:
        raise ValueError("Cần SUPABASE_URL và SUPABASE_SECRET_KEY trong .env hoặc biến môi trường")
    return SupabaseRepository(url, key)


def summary(data: dict) -> None:
    display = dict(data)
    missing = data.get("missing_draw_ids", [])
    ranges = []
    if "missing_draw_ids" in display:
        for draw_id in sorted(set(missing)):
            if ranges and draw_id == ranges[-1][1] + 1:
                ranges[-1][1] = draw_id
            else:
                ranges.append([draw_id, draw_id])
        display.pop("missing_draw_ids")
        display["missing_draw_count"] = len(missing)
        display["missing_draw_ranges"] = [str(a) if a == b else f"{a}-{b}" for a, b in ranges]
    print(json.dumps(display, ensure_ascii=False, indent=2))
    filename = os.getenv("GITHUB_STEP_SUMMARY")
    if filename:
        lines = ["### Mega 6/45 collector", "", f"- Trạng thái: {data.get('status', data.get('coverage', 'audit'))}",
                 f"- Kỳ mới nhất DB: {data.get('latest_draw_id')}", f"- Tổng số kỳ: {data.get('total_draws')}",
                 f"- Dòng mới: {data.get('new_rows', 0)}; trùng: {data.get('duplicate_rows', 0)}; lỗi: {data.get('error_count', 0)}",
                 f"- Kỳ thiếu ({len(missing)}): {display.get('missing_draw_ranges', [])}", ""]
        with open(filename, "a", encoding="utf-8") as file:
            file.write("\n".join(lines))


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = parser().parse_args(argv)
    load_dotenv(args.env_file, encoding="utf-8-sig")
    repo = None
    try:
        repo = repository(args)
        if args.command in {"backfill", "sync"}:
            result = collect(repo, MinhNgocSource(delay=args.delay), mode=args.command,
                             max_pages=args.max_pages, checkpoint=args.checkpoint)
            if result["new_rows"] == 0 and result["status"] == "succeeded":
                print("Chưa có kỳ mới; DB đã khớp phạm vi nguồn đã quan sát")
            summary(result)
            return 5 if result["status"] == "failed" else 2 if result["status"] == "partial" else 0
        if args.command == "audit":
            source_latest = None
            if args.check_source:
                page = MinhNgocSource().fetch()
                if page.issues or (not page.records and not page.pending):
                    raise SourceError("Không thể xác định kỳ mới nhất từ nguồn")
                source_latest = max((r["draw_id"] for r in page.records), default=None)
            report = audit_records(repo.list_draws(), repo.list_issues(), source_latest=source_latest)
            if args.check_source:
                report["source_check_status"] = "observed" if source_latest is not None else "pending"
            write_json(args.output, report)
            summary(report)
            return 0 if report["coverage"] != "incomplete_or_has_issues" and (
                not args.check_source or source_latest is not None
            ) else 2
        if args.command == "export":
            rows = repo.list_draws()
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=DRAW_FIELDS, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
            print(f"Đã xuất {len(rows)} kỳ vào {path}")
            return 0
        if args.command == "import-local":
            if args.backend != "supabase":
                raise ValueError("import-local cần --backend supabase")
            if not Path(args.input).is_file():
                raise ValueError("Không tìm thấy SQLite đầu vào")
            if args.batch_size > 1000:
                raise ValueError("Batch tối đa 1000 kỳ")
            local = SQLiteRepository(args.input)
            try:
                records = local.list_draws()
            finally:
                local.close()
            run_id = repo.start_run("import-local")
            counts = {"new_rows": 0, "duplicate_rows": 0, "error_count": 0}
            try:
                for i in range(0, len(records), args.batch_size):
                    batch = repo.ingest_batch([{k: r[k] for k in DRAW_FIELDS} for r in records[i:i+args.batch_size]], run_id)
                    for key in counts:
                        counts[key] += batch[key]
                persisted = repo.list_draws()
                result = {**counts, "latest_draw_id": max((r["draw_id"] for r in persisted), default=None),
                          "total_draws": len(persisted), "status": "failed" if counts["error_count"] else "succeeded"}
                repo.finish_run(run_id, **counts, status=result["status"], latest_draw_id=result["latest_draw_id"])
            except StorageError:
                repo.finish_run(run_id, **{**counts, "error_count": counts["error_count"] + 1}, status="failed")
                raise
            summary(result)
            return 5 if counts["error_count"] else 0
    except SourceError as exc:
        summary({"status": "source_error", "error": str(exc), "error_count": 1})
        return 3
    except StorageError as exc:
        summary({"status": "database_error", "error": str(exc), "error_count": 1})
        return 4
    except (ValueError, OSError):
        summary({"status": "configuration_error", "error": "Kiểm tra cấu hình, quyền truy cập file và đường dẫn", "error_count": 1})
        return 1
    except Exception as exc:
        # Unexpected dependency/parser failures must not print request objects,
        # credentials, or untrusted exception strings in a public CI log.
        summary({"status": "internal_error", "failure_type": type(exc).__name__, "error_count": 1})
        return 6
    finally:
        if repo:
            repo.close()
    return 0
