"""Write the API's OpenAPI schema, from which the frontend's TypeScript types are generated.

Usage (from backend/):  uv run python -m app.api.export_openapi ../frontend/openapi.json
"""

import json
import sys
from pathlib import Path

from app.api.main import create_app


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        raise SystemExit("usage: python -m app.api.export_openapi <output.json>")
    schema = create_app().openapi()
    # Sorted and newline-terminated, so CI can check the committed copy is current with git diff.
    Path(args[0]).write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
