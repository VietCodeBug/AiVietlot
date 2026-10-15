"""Send only frontend publishable settings to the linked Vercel project via CMD stdin."""
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

root = Path(__file__).resolve().parents[1]
settings = dotenv_values(root / "web" / ".env.local", encoding="utf-8-sig")
for name in ("VITE_SUPABASE_URL", "VITE_SUPABASE_PUBLISHABLE_KEY"):
    value = settings.get(name)
    if not value or value.startswith("sb_secret_"):
        raise SystemExit("Missing or unsafe frontend configuration")
    command = f"npx --yes vercel@64.1.0 env add {name} production,preview,development --yes --no-sensitive --force"
    result = subprocess.run(["cmd.exe", "/d", "/c", command], input=value,
        text=True, capture_output=True, cwd=root, encoding="utf-8", errors="replace")
    print((result.stdout + result.stderr).replace(value, "[public configuration value]"))
    if result.returncode:
        raise SystemExit(result.returncode)
