import kyb_vetter_mcp
from kyb_vetter_core.config import Settings


def test_package_imports_and_sees_core() -> None:
    assert kyb_vetter_mcp.__version__
    assert Settings().project_name
