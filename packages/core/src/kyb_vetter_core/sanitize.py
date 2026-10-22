"""Sanitisation of free text coming from public registers.

Register data (company names, addresses, legal forms) is untrusted input to
the language model. We cannot make it harmless, but we can bound it: remove
control and invisible characters that could hide instructions or break
rendering, collapse whitespace, and cap the length so a single field cannot
flood the context (ADR-0012).
"""

import re
import unicodedata

DEFAULT_MAX_LEN = 300
ELLIPSIS = "…"

_INVISIBLE = frozenset({"​", "‌", "‍", "⁠", "﻿"})
_WHITESPACE = re.compile(r"\s+")


_ASCII_WHITESPACE = frozenset(" \t\n\r\x0b\x0c")


def _is_dropped(char: str) -> bool:
    if char in _INVISIBLE:
        return True
    category = unicodedata.category(char)
    if category == "Cc":
        return char not in _ASCII_WHITESPACE  # keeps TAB/LF/CR, drops NEL and other controls
    return category in {"Cf", "Co", "Cn"}


def clean_text(value: str | None, *, max_len: int = DEFAULT_MAX_LEN) -> str | None:
    """Strip control/invisible characters, normalise whitespace and truncate.

    Returns ``None`` for ``None`` and for text that is empty after cleaning.
    """
    if value is None:
        return None
    kept = "".join(c for c in value if not _is_dropped(c))
    text = _WHITESPACE.sub(" ", kept).strip()
    if not text:
        return None
    if len(text) > max_len:
        text = text[: max_len - 1] + ELLIPSIS
    return text
