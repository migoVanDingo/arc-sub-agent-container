"""Test fixtures.

Sub-agent packages should be testable WITHOUT importing arc. The fixtures
here provide the minimum shape of `arc.subagent_api` that a unit test needs:

  - StubBuildContext: a SubAgentBuildContext-like object with the right
    attribute shape, no real arc dependency

If you've checked out arc next to your sub-agent (`pip install -e ../arc`),
you can also import the real classes from `arc.subagent_api`. These stubs
let you test in CI without that.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest


# ── Stub build context ─────────────────────────────────────────────────────
# Mirrors the attribute shape arc passes. SubAgentBuildContext is minimal
# in v0.1 (arc_home reserved for future use).

@dataclass(frozen=True)
class StubBuildContext:
    arc_home: Path = field(default_factory=lambda: Path("/tmp/.arc"))


@pytest.fixture
def build_ctx() -> StubBuildContext:
    return StubBuildContext()
