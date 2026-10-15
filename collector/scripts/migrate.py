"""Apply collector SQL using environment credentials; never print secrets.

Usage: python collector/scripts/migrate.py
Accepts DATABASE_URL (properly URL-encoded), or PGHOST/PGPORT/PGDATABASE/
PGUSER/PGPASSWORD. The latter avoids URI escaping mistakes in passwords.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

import psycopg
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]


def connection_options() -> dict[str, object]:
    options: dict[str, object] = {"sslmode": "require", "connect_timeout": 15}
    # Prefer explicit PG fields, which support passwords containing @, #, etc.
    if os.getenv("PGHOST"):
        options.update({
            "host": os.environ["PGHOST"],
            "port": os.getenv("PGPORT", "5432"),
            "dbname": os.getenv("PGDATABASE", "postgres"),
            "user": os.getenv("PGUSER", "postgres"),
        })
        if os.getenv("PGPASSWORD"):
            options["password"] = os.environ["PGPASSWORD"]
        else:
            raise ValueError("PGPASSWORD is required with PGHOST")
    elif os.getenv("DATABASE_URL"):
        options["conninfo"] = os.environ["DATABASE_URL"]
    else:
        raise ValueError("Set PGHOST and PGPASSWORD, or DATABASE_URL, in the local environment")
    return options


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply Mega 6/45 collector database migration")
    parser.add_argument("--sql", type=Path, default=ROOT / "supabase" / "migrations" / "001_collector.sql")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args(argv)
    load_dotenv(args.env_file, encoding="utf-8-sig", override=False)
    try:
        options = connection_options()
        sql = args.sql.read_text(encoding="utf-8-sig")
        # The SQL owns its BEGIN/COMMIT; no unrelated transaction is created.
        with psycopg.connect(**options, autocommit=True) as connection:
            connection.execute(sql, prepare=False)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    except OSError:
        print("Could not read the requested migration file", file=sys.stderr)
        return 2
    except psycopg.Error as error:
        # psycopg exception messages can repeat URI credentials, so emit SQLSTATE only.
        code = error.sqlstate
        label = f" (SQLSTATE {code})" if code and len(code) == 5 and code.isalnum() else ""
        print(f"Database migration failed{label}; check connection settings and database access", file=sys.stderr)
        return 1
    print("Collector database migration applied successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
