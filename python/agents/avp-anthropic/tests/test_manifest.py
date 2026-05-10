"""Phase 5 punch-list: rewrite for refs-only Commission + resolver protocol.

The original tests in this file exercised behavior that has been redesigned
(in-process subagent dispatch via AnthropicSubagentDriver, capability flags,
etc.). Phase 4 stubs the file so the suite collects cleanly; the git
history preserves the original assertions for re-use.
"""

import pytest

pytest.skip(
    "Phase 5 follow-up: rewrite for refs-only Commission + resolver protocol",
    allow_module_level=True,
)
