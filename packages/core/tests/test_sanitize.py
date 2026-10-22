import pytest

from kyb_vetter_core.sanitize import DEFAULT_MAX_LEN, clean_text


def test_none_passes_through() -> None:
    assert clean_text(None) is None


def test_plain_text_is_unchanged() -> None:
    assert clean_text("ORLEN SPÓŁKA AKCYJNA") == "ORLEN SPÓŁKA AKCYJNA"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("A\x00B\x07C\x1bD", "ABCD"),  # C0 controls
        ("A\x85B\x9fC", "ABC"),  # C1 controls
        ("A​B‌C‍D﻿E⁠F", "ABCDEF"),  # zero-width and BOM
        ("A‮B", "AB"),  # bidi override
    ],
)
def test_control_and_invisible_characters_are_removed(raw: str, expected: str) -> None:
    assert clean_text(raw) == expected


def test_whitespace_is_collapsed_and_trimmed() -> None:
    assert clean_text("  ul.\tChmielna \n\n 85/87 \r\n ") == "ul. Chmielna 85/87"


def test_long_text_is_truncated_with_ellipsis() -> None:
    result = clean_text("x" * 1000, max_len=20)
    assert result == "x" * 19 + "…"
    assert len(result) == 20


def test_default_limit_applies() -> None:
    result = clean_text("y" * (DEFAULT_MAX_LEN + 50))
    assert result is not None
    assert len(result) == DEFAULT_MAX_LEN


def test_empty_after_cleaning_becomes_none() -> None:
    assert clean_text(" ​ \x00 ") is None
