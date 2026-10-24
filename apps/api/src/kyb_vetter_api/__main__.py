"""Entry point: ``python -m kyb_vetter_api`` serves REST v1 on 0.0.0.0:$PORT (Cloud Run)."""

import os

import uvicorn

from kyb_vetter_api.app import build_app
from kyb_vetter_core.config import get_settings
from kyb_vetter_core.telemetry import configure_logging, configure_tracing


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    configure_tracing(settings, role="api")
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(build_app(settings), host="0.0.0.0", port=port)  # noqa: S104 - container binds all interfaces


if __name__ == "__main__":
    main()
