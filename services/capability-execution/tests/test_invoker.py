import hashlib
import json

import pytest

from a2flow_capability.invoker import indexed_identity
from a2flow_capability.releases import ReleaseError


def test_inventory_is_only_a_stable_identity_index() -> None:
    raw = json.dumps(
        {
            "kind": "ABILITY",
            "key": "content.project.create",
            "definition": {
                "runtimeProfile": "a2flow.java-rpc.v1",
                "assetKey": "draft-1",
                "sourceId": "stale-version-never-used",
                "sourceDigest": "stale-digest",
            },
        }
    ).encode()
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    assert indexed_identity(raw, digest, "content.project.create") == "draft-1"
    with pytest.raises(ReleaseError, match="IDENTITY"):
        indexed_identity(raw, digest, "another.action")
    with pytest.raises(ReleaseError, match="DIGEST"):
        indexed_identity(raw, "sha256:bad", "content.project.create")


def test_non_published_profile_is_rejected() -> None:
    raw = json.dumps(
        {"kind": "ABILITY", "key": "content.project.create", "definition": {"assetKey": "draft-1"}}
    ).encode()
    with pytest.raises(ReleaseError, match="PROFILE"):
        indexed_identity(raw, "sha256:" + hashlib.sha256(raw).hexdigest(), "content.project.create")
