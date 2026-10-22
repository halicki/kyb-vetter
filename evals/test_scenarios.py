import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from mcp.types import TextContent

if TYPE_CHECKING:
    from collections.abc import Callable

    import respx
    from mcp import Client

SCENARIOS = sorted((Path(__file__).parent / "scenarios").glob("*.json"))

pytestmark = pytest.mark.eval


def _set_path(data: dict[str, Any], dotted: str, value: Any) -> None:
    *parents, last = dotted.split(".")
    for key in parents:
        data = data[key]
    data[last] = value


def _get_path(data: Any, dotted: str) -> Any:
    for key in dotted.split("."):
        data = data[int(key)] if isinstance(data, list) else data[key]
    return data


@pytest.mark.parametrize("scenario_path", SCENARIOS, ids=[p.stem for p in SCENARIOS])
async def test_scenario(
    scenario_path: Path,
    mcp_client: Callable[[], Client],
    mock_api: respx.MockRouter,
    fixture_json: Callable[[str], Any],
) -> None:
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    for mock in scenario["mocks"]:
        body = fixture_json(mock["fixture"]) if "fixture" in mock else mock.get("json")
        for path, value in mock.get("patch", {}).items():
            _set_path(body, path, value)
        mock_api.get(mock["url"]).respond(mock.get("status", 200), json=body)

    async with mcp_client() as client:
        result = await client.call_tool(scenario["tool"], scenario["arguments"])

    expect = scenario["expect"]
    assert result.is_error is expect.get("is_error", False), result.content
    text = (
        result.content[0].text
        if result.content and isinstance(result.content[0], TextContent)
        else ""
    )
    if "error_contains" in expect:
        assert expect["error_contains"].lower() in text.lower()
    if "structured" in expect:
        data = result.structured_content
        assert data is not None
        for path, value in expect["structured"].items():
            assert _get_path(data, path) == value, path
    if "warnings" in expect:
        assert result.structured_content is not None
        assert [w["code"] for w in result.structured_content["warnings"]] == expect["warnings"]
    for forbidden in expect.get("forbidden_substrings", []):
        assert forbidden not in text
