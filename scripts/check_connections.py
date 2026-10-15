"""Connection diagnostics: never print keys, passwords, URIs, or exception text."""
import json
import os
import socket

import psycopg
import requests
from dotenv import load_dotenv

load_dotenv(encoding="utf-8-sig")
report = {}
url = os.environ.get("SUPABASE_URL", "").rstrip("/")
key = os.environ.get("SUPABASE_SECRET_KEY", "")
try:
    response = requests.get(url + "/rest/v1/mega645_draws", params={"select": "draw_id", "limit": "1"},
                            headers={"apikey": key}, timeout=20)
    body = response.json()
    report["rest"] = {"http_status": response.status_code,
                      "code": body.get("code") if isinstance(body, dict) else None,
                      "table_exists": response.status_code == 200}
except requests.RequestException:
    report["rest"] = {"error": "connection_failed"}
try:
    host = os.environ.get("PGHOST", "")
    report["postgres_dns_families"] = sorted({"IPv6" if x[0] == socket.AF_INET6 else "IPv4"
                                             for x in socket.getaddrinfo(host, 5432)})
    with psycopg.connect(host=host, port=os.environ.get("PGPORT", "5432"),
                         dbname=os.environ.get("PGDATABASE", "postgres"),
                         user=os.environ.get("PGUSER", "postgres"),
                         password=os.environ.get("PGPASSWORD", ""),
                         connect_timeout=10, sslmode="require") as conn:
        report["postgres"] = {"connected": conn.execute("select 1").fetchone()[0] == 1}
except Exception as exc:
    report["postgres"] = {"connected": False, "error_type": type(exc).__name__}
print(json.dumps(report, indent=2))
