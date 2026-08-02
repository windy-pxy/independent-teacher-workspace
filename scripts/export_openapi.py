import json
from pathlib import Path

from teacher_workspace.main import app

destination = Path("packages/api-client/openapi.json")
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(
    json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(f"Exported OpenAPI schema to {destination}")
