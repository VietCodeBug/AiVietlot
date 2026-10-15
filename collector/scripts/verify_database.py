"""Verify data/RLS and duplicate RPC behavior without persistent test changes.

Every permission probe and RPC test uses existing rows and a transaction which
is rolled back. No fake draw facts are created, and no credentials are printed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid

from dotenv import load_dotenv
import psycopg
from psycopg.types.json import Jsonb

from migrate import ROOT, connection_options


class CheckFailure(RuntimeError):
    pass


class RollbackProbe(Exception):
    pass


TABLES = ("mega645_draws", "ingestion_runs", "ingestion_issues", "ingestion_batches")


def denied(connection, role: str, query: str) -> None:
    try:
        with connection.transaction():
            # role and query are fixed program constants, never external input.
            connection.execute(f"set local role {role}")
            connection.execute(query)
            raise CheckFailure(f"Role {role} unexpectedly allowed a restricted operation")
    except psycopg.errors.InsufficientPrivilege:
        return


def verify(connection, *, rpc: bool = True) -> dict:
    report = {"status": "verified", "checks": []}
    rls = dict(connection.execute("""
        select c.relname, c.relrowsecurity from pg_class c
        join pg_namespace n on n.oid=c.relnamespace
        where n.nspname='public' and c.relname=any(%s)
    """, (list(TABLES),)).fetchall())
    if set(rls) != set(TABLES) or not all(rls.values()):
        raise CheckFailure("Collector tables are missing or row level security is disabled")
    report["checks"].append("all_collector_tables_have_rls")

    for role in ("anon", "authenticated"):
        with connection.transaction():
            connection.execute(f"set local role {role}")
            public_count = connection.execute("select count(*) from public.mega645_draws").fetchone()[0]
        if public_count <= 0:
            raise CheckFailure("Public draw access returned no collected facts")
        for query in (
            "insert into public.mega645_draws select * from public.mega645_draws where false",
            "update public.mega645_draws set n1=n1 where false",
            "delete from public.mega645_draws where false",
        ):
            denied(connection, role, query)
        for table in TABLES[1:]:
            denied(connection, role, f"select count(*) from public.{table}")
            denied(connection, role, f"delete from public.{table} where false")
        denied(connection, role, "select public.ingest_mega645_batch('[]'::jsonb,null,null)")
        report["checks"].append(f"{role}_reads_draws_but_cannot_write_or_read_private_logs")

    with connection.transaction():
        connection.execute("set local role service_role")
        for table in TABLES:
            connection.execute(f"select count(*) from public.{table}").fetchone()
    report["checks"].append("service_role_reads_admin_tables")

    count, first_id, latest_id, first_date, latest_date = connection.execute("""
        select count(*),min(draw_id),max(draw_id),min(draw_date),max(draw_date)
        from public.mega645_draws
    """).fetchone()
    if count <= 0:
        raise CheckFailure("No draws have been collected")
    missing = connection.execute("""
        select count(*) from generate_series(1,%s) g(draw_id)
        where not exists(select 1 from public.mega645_draws d where d.draw_id=g.draw_id)
    """, (latest_id,)).fetchone()[0]
    invalid = connection.execute("""
        select count(*) from public.mega645_draws where not (
            1<=n1 and n1<n2 and n2<n3 and n3<n4 and n4<n5 and n5<n6 and n6<=45)
            or draw_date > (now() at time zone 'Asia/Ho_Chi_Minh')::date
    """).fetchone()[0]
    chronology = connection.execute("""
        select count(*) from (
            select draw_date,lag(draw_date) over(order by draw_id) previous
            from public.mega645_draws
        ) d where draw_date<=previous
    """).fetchone()[0]
    if missing or invalid or chronology:
        raise CheckFailure("Collected draw range has missing, invalid, future, or out of order facts")
    report.update({"total_draws": count, "first_draw_id": first_id, "latest_draw_id": latest_id,
        "first_date": first_date.isoformat(), "latest_date": latest_date.isoformat(),
        "missing_draw_count": missing, "invalid_draw_count": invalid, "chronology_error_count": chronology})
    report["checks"].append("collected_draw_range_is_contiguous_and_valid")

    if rpc:
        # Actual facts are fed back through the real PostgreSQL function. The
        # ephemeral run/cache are rolled back with all probes, never published.
        sample = [row[0] for row in connection.execute("""
            select to_jsonb(d) from public.mega645_draws d order by draw_id desc limit 3
        """).fetchall()]
        sample_ids = [record["draw_id"] for record in sample]
        expected = {"new_rows": 0, "duplicate_rows": len(sample), "error_count": 0}
        conflict_expected = {"new_rows": 0, "duplicate_rows": 0, "error_count": 1}
        run_id, request_id = uuid.uuid4(), uuid.uuid4()
        try:
            with connection.transaction():
                connection.execute("set local role service_role")
                connection.execute("insert into public.ingestion_runs(id,mode) values(%s,'verification')", (run_id,))
                query = "select public.ingest_mega645_batch(%s,%s,%s)"
                first = connection.execute(query, (Jsonb(sample), run_id, request_id)).fetchone()[0]
                replay = connection.execute(query, (Jsonb(sample), run_id, request_id)).fetchone()[0]
                repeat = connection.execute(query, (Jsonb(sample), run_id, uuid.uuid4())).fetchone()[0]
                if first != expected or replay != expected or repeat != expected:
                    raise CheckFailure("Duplicate RPC or request replay returned unexpected counters")
                if connection.execute("select count(*) from public.ingestion_issues where run_id=%s", (run_id,)).fetchone()[0]:
                    raise CheckFailure("Duplicate RPC unexpectedly created an ingestion issue")
                if connection.execute("select count(*) from public.ingestion_batches where run_id=%s", (run_id,)).fetchone()[0] != 2:
                    raise CheckFailure("RPC request replay was not idempotent")

                # A conflicting, otherwise valid candidate is only observable
                # inside this rolled-back transaction. The public fact remains
                # unchanged, and replay must not create a second conflict issue.
                candidate = dict(sample[0])
                current_numbers = [candidate[f"n{i}"] for i in range(1, 7)]
                alternative = list(range(1, 7)) if current_numbers != list(range(1, 7)) else list(range(2, 8))
                candidate.update({f"n{i}": value for i, value in enumerate(alternative, 1)})
                candidate["verification_probe"] = "rolled-back conflict test"
                conflict_request = uuid.uuid4()
                conflict = connection.execute(query, (Jsonb([candidate]), run_id, conflict_request)).fetchone()[0]
                conflict_replay = connection.execute(query, (Jsonb([candidate]), run_id, conflict_request)).fetchone()[0]
                if conflict != conflict_expected or conflict_replay != conflict_expected:
                    raise CheckFailure("Conflicting RPC candidate or replay returned unexpected counters")
                issues = connection.execute("""
                    select kind,draw_id,payload->'incoming'->>'verification_probe'
                    from public.ingestion_issues where run_id=%s
                """, (run_id,)).fetchall()
                if issues != [("conflict", candidate["draw_id"], "rolled-back conflict test")]:
                    raise CheckFailure("Conflict was not recorded exactly once on request replay")
                if connection.execute("select count(*) from public.ingestion_batches where run_id=%s", (run_id,)).fetchone()[0] != 3:
                    raise CheckFailure("Conflict request replay added another batch entry")

                # Direct admin writes must also obey the ordered-number CHECK.
                try:
                    with connection.transaction():
                        connection.execute("update public.mega645_draws set n1=n2 where draw_id=%s", (candidate["draw_id"],))
                        raise CheckFailure("Database allowed a duplicate/invalid number sequence")
                except psycopg.errors.CheckViolation:
                    pass
                current = [row[0] for row in connection.execute("""
                    select to_jsonb(d) from public.mega645_draws d
                    where draw_id=any(%s) order by draw_id desc
                """, (sample_ids,)).fetchall()]
                if current != sample:
                    raise CheckFailure("Duplicate/conflicting RPC or constraint probe changed facts or provenance")
                raise RollbackProbe()
        except RollbackProbe:
            pass
        report["checks"].append("existing_draw_duplicates_and_request_replay_are_idempotent")
        report["checks"].append("conflicting_draw_is_logged_once_and_never_overwrites_facts")
        report["checks"].append("database_constraint_rejects_invalid_number_sequence")
        report["rpc_test"] = {**expected, "test_changes_rolled_back": True}
        report["conflict_test"] = {**conflict_expected, "issue_count": 1,
            "stored_facts_unchanged": True, "test_changes_rolled_back": True}
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify Mega 6/45 database integrity and public read-only access")
    parser.add_argument("--env-file", default=ROOT / ".env")
    parser.add_argument("--skip-rpc", action="store_true", help="Skip rolled-back duplicate RPC probe")
    parser.add_argument("--output", type=Path, help="Save the sanitized verification report as JSON")
    args = parser.parse_args(argv)
    load_dotenv(args.env_file, encoding="utf-8-sig", override=False)
    try:
        with psycopg.connect(**connection_options(), autocommit=True) as connection:
            report = verify(connection, rpc=not args.skip_rpc)
    except (CheckFailure, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        return 1
    except psycopg.Error as error:
        code = error.sqlstate
        safe_code = code if code and len(code) == 5 and code.isalnum() else None
        print(json.dumps({"status": "database_error", "sqlstate": safe_code}))
        return 1
    if args.output is not None:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.output.with_suffix(args.output.suffix + ".tmp")
            temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            temporary.replace(args.output)
        except OSError:
            print(json.dumps({"status": "output_error", "error": "Could not save verification report"}))
            return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
