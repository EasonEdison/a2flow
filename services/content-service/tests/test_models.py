from uuid import uuid4

import pytest

from a2flow_content.errors import ContentError
from a2flow_content.models import (
    MAX_REVISION,
    Environment,
    ReadingPoint,
    SaveSourceCommand,
    TrustedContext,
    revision,
)


def test_trusted_context_accepts_full_signed_int64() -> None:
    assert TrustedContext(-(1 << 63), Environment.PRT, "min-user").user_id == -(1 << 63)
    assert TrustedContext(0, Environment.ONLINE, "zero-user").user_id == 0
    assert TrustedContext((1 << 63) - 1, Environment.PRT, "max-user").user_id == (1 << 63) - 1


def test_source_limit_uses_original_text_length() -> None:
    with pytest.raises(ContentError, match="INVALID_SOURCE_BODY"):
        SaveSourceCommand(uuid4(), "source", " " * 30_001, None)


def test_required_evidence_rejects_blank_text() -> None:
    with pytest.raises(ContentError, match="READING_EVIDENCE_REQUIRED"):
        ReadingPoint("p1", "claim", "   ", None, "explanation")


def test_revision_matches_wire_uint32() -> None:
    assert revision(MAX_REVISION, "REVISION") == MAX_REVISION
    with pytest.raises(ContentError, match="INVALID_REVISION"):
        revision(MAX_REVISION + 1, "REVISION")
