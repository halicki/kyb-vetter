"""Entry point: ``python -m kyb_vetter_api`` serves REST v1 on 0.0.0.0:$PORT (Cloud Run)."""

import logging
import os
import sys

import uvicorn

from kyb_vetter_api.app import build_app
from kyb_vetter_core.config import get_settings


def main() -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(build_app(get_settings()), host="0.0.0.0", port=port)  # noqa: S104 - container binds all interfaces


if __name__ == "__main__":
    main()
