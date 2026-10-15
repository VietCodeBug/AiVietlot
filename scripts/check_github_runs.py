"""Read public GitHub CI status without accessing credentials."""
import json
import requests

response = requests.get("https://api.github.com/repos/VietCodeBug/AiVietlot/actions/runs",
    params={"per_page": 8}, timeout=20)
response.raise_for_status()
print(json.dumps([{"name": run["name"], "status": run["status"],
    "conclusion": run["conclusion"], "url": run["html_url"],
    "head": run["head_sha"][:7]} for run in response.json().get("workflow_runs", [])], indent=2))
