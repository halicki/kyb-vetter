"""Run the MCP server over stdio: ``python -m kyb_vetter_mcp``.

Logging goes to stderr; stdout belongs to the protocol.
"""

import logging
import sys

from kyb_vetter_core.config import get_settings
from kyb_vetter_mcp.server import build_server


def main() -> None:
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    build_server(get_settings()).run(transport="stdio")


if __name__ == "__main__":
    main()
