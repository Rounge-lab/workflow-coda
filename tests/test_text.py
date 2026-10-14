"""Tests for the shared text rules."""

import pytest

from workflow_coda.text import has_visible_text


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", False),
        ("   ", False),
        ("\t\n ", False),
        ("x", True),
        ("  provenance  ", True),
        ("0", True),
    ],
)
def test_has_visible_text(text: str, expected: bool) -> None:
    # The shared predicate behind the component gates, the layout
    # model's VisibleText validator, and the theme's font rule.
    assert has_visible_text(text) is expected
