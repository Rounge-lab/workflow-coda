"""Recognize markdown artifact-variable syntax.

This module only recognizes the syntax; resolution belongs to
``core.markdown``.
"""

import re
from typing import Final

MARKDOWN_VARIABLE_RE: Final[re.Pattern[str]] = re.compile(
    r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}"
)
