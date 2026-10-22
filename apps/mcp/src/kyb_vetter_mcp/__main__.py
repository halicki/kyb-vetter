"""Entry points.

``python -m kyb_vetter_mcp``       stdio transport (Claude Desktop, MCP Inspector); stdout is the protocol
``python -m kyb_vetter_mcp http``  Streamable HTTP on 0.0.0.0:$PORT (Cloud Run)
"""

import logging
import os
import sys

from kyb_vetter_core.config import get_settings
from kyb_vetter_mcp.server import build_server


def main(argv: list[str]) -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    if argv[1:] == ["http"]:
        import uvicorn

        from kyb_vetter_mcp.http import build_http_app

        port = int(os.environ.get("PORT", "8080"))
        uvicorn.run(build_http_app(settings), host="0.0.0.0", port=port)  # noqa: S104 - container binds all interfaces
        return
    build_server(settings).run(transport="stdio")


if __name__ == "__main__":
    main(sys.argv)
