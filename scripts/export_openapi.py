import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def build_openapi_schema() -> dict[str, Any]:
    """Generate the live OpenAPI 3.1.0 schema without requiring external DB/env secrets."""
    from src.infrastructure.config import Settings
    from src.presentation.api.app import create_app

    settings = Settings(
        app_env="development",
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="openapi-export-placeholder-key-at-least-32-chars!",
        log_level="WARNING",
    )
    app = create_app(settings)
    schema = app.openapi()
    app.state.engine.sync_engine.dispose()
    return schema


def main() -> None:
    output_path = _REPO_ROOT / "contracts" / "openapi.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = build_openapi_schema()
    output_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"Exported OpenAPI {schema.get('openapi')} schema to {output_path}")


if __name__ == "__main__":
    main()
