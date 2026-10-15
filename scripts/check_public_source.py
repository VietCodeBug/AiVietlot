"""Verify staged source and compiled assets contain no backend credentials."""
from pathlib import Path
import subprocess
import sys
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
settings = dotenv_values(root / ".env", encoding="utf-8-sig")
secrets = [settings[name] for name in ("SUPABASE_SECRET_KEY", "PGPASSWORD") if settings.get(name)]
staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=root, text=True).splitlines()
forbidden = [name for name in staged if Path(name).name in {".env", ".env.local", "auth.json"} or "node_modules/" in name or "/.vercel/" in name or "/dist/" in name]
paths = [root / name for name in staged] + list((root / "web" / "dist").rglob("*.js"))
matches = [str(path.relative_to(root)) for path in paths if path.is_file() and any(secret in path.read_text(encoding="utf-8", errors="ignore") for secret in secrets)]
print({"staged_file_count": len(staged), "backend_secret_matches": matches, "forbidden_paths": forbidden})
sys.exit(bool(matches or forbidden))
