import sys
from pathlib import Path

# Reuse the MCP app test fixtures (client, settings, mock_api, fixture_json) for scenario runs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "mcp"))

from tests.conftest import fixture_json, mcp_client, mock_api, settings  # noqa: F401
