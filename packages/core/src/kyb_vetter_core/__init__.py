"""Domain core for the counterparty verification platform.

All business logic lives here. The MCP server, REST API and worker are thin
adapters over this package and must not duplicate anything found here.
"""

from importlib.metadata import version

__version__ = version("kyb-vetter-core")

__all__ = ["__version__"]
