"""Deploy a clean copy of tracked sources using the authenticated CMD Vercel CLI.

Keeping the upload independent of local Python environments and test directories
also makes the deployment input match the Git commit that was reviewed.
"""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
root = Path(__file__).resolve().parents[1]
target = Path(tempfile.mkdtemp(prefix="mega-lab-deploy-"))
files = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "HEAD", "--", "web"], cwd=root, text=True).splitlines()
for name in files:
    if Path(name).name.startswith(".env"):
        continue
    destination = target / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(subprocess.check_output(["git", "show", f"HEAD:{name}"], cwd=root))
(target / ".vercel").mkdir()
shutil.copy2(root / ".vercel" / "project.json", target / ".vercel" / "project.json")
shutil.copy2(root / ".vercelignore", target / ".vercelignore")
commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
report = {"directory": str(target), "source_commit": commit, "frontend_files": len(files)}
(root / "artifacts" / "deployment-source.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report), flush=True)
raise SystemExit(subprocess.call(["cmd.exe", "/d", "/c",
    "npx --yes vercel@64.1.0 deploy --prod --yes --scope phamhoainam1709s-projects"], cwd=target))
