"""Resolve Java publications against retained, environment-local DB material.

The M release pointer is authoritative, including ONLINE user gray selection.
The Python serving index is only an inventory for these assets, not a second
release decision. Missing retained material is an error, never a draft fallback.
"""
from __future__ import annotations

from uuid import uuid4
from typing import Any, cast

from a2flow_asset_store import AssetReader
from a2flow_asset_store.java_runtime import is_java_asset
from a2flow_asset_store.records import Asset, AssetError, Bundle
from skillweave_contracts import TrustedContext

from .rpc_client import RpcClient


class RpcAssetReader(AssetReader):
    def __init__(self, repository: Any, namespace: str, rpc: RpcClient) -> None:
        super().__init__(repository, namespace)
        self.rpc = rpc

    def _resolve(self, bundle: Bundle, owner: TrustedContext, kind: str, key: str) -> tuple[Asset, str]:
        candidates = [asset for asset in bundle.assets
                      if asset.kind == kind and asset.key == key and is_java_asset(asset.definition)]
        if not candidates:
            return super()._resolve(bundle, owner, kind, key)
        request_id = "resolve:" + uuid4().hex
        if kind == "APPLICATION":
            release = self.rpc.describe(owner, key, request_id).release
            source_id, source_digest = release.source_id, release.digest
            environment = release.environment
        elif kind == "ABILITY":
            asset_keys = {cast(str, asset.definition["assetKey"]) for asset in candidates}
            if len(asset_keys) != 1:
                raise AssetError("JAVA_ASSET_IDENTITY_CONFLICT")
            ability = self.rpc.resolve(owner, next(iter(asset_keys)), request_id)
            source_id, source_digest = ability.source_id, ability.source_digest
            environment = ability.resolved_environment
        else:
            raise AssetError("UNSUPPORTED_JAVA_RUNTIME_ASSET")
        if environment != owner.environment:
            raise AssetError("ENVIRONMENT_MISMATCH")
        matches = [asset for asset in candidates
                   if asset.definition["sourceId"] == source_id
                   and asset.definition["sourceDigest"] == source_digest]
        if len(matches) != 1:
            raise AssetError("JAVA_PUBLISHED_MATERIAL_MISSING")
        # This metadata is not used for Skill version selection; only these two
        # Java asset kinds use the M-side resolver.
        return matches[0], "JAVA_PUBLISHED"
