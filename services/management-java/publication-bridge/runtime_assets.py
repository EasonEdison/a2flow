"""Persist complete Java publications into the environment-specific asset DB.

Java owns the effective publication pointer, including gray routing. These rows
are immutable runtime material; the RPC-aware reader checks that pointer before
selecting a retained version. No business API is called from publication.
"""
from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, TypedDict, cast

from a2flow_asset_store.java_runtime import PROFILE, application_abilities, validate_java_asset
from a2flow_asset_store.records import AssetError, canonical, digest

if TYPE_CHECKING:
    from bridge import Publisher


class RuntimePublication(TypedDict):
    kind: str
    key: str
    environment: str
    assetKey: str
    sourceId: str
    sourceDigest: str
    payloadDigest: str
    payloadJson: str
    requestId: str
    expectedServingDigest: str


def selection(publisher: Publisher, value: object) -> dict[str, str]:
    if type(value) is not dict or set(value) != {"kind", "key", "environment"}:
        raise AssetError("PUBLICATION_FIELDS_INVALID")
    if value["kind"] not in {"ABILITY", "APPLICATION"}:
        raise AssetError("UNSUPPORTED_JAVA_RUNTIME_ASSET")
    with publisher.transaction(value["environment"]) as (destination, connection, _):
        row = connection.execute("SELECT document FROM a2flow_asset_serving WHERE namespace=%s AND kind=%s AND asset_key=%s",
                                 (destination.namespace, value["kind"], value["key"])).fetchone()
        return {"servingDigest": digest(canonical(None if row is None else json.loads(bytes(row[0]))))}


def publish(publisher: Publisher, value: object) -> dict[str, object]:
    fields = set(RuntimePublication.__annotations__)
    if type(value) is not dict or set(value) != fields:
        raise AssetError("PUBLICATION_FIELDS_INVALID")
    if any(type(value[field]) is not str or not value[field] for field in fields):
        raise AssetError("PUBLICATION_FIELD_TYPE_INVALID")
    request = cast(RuntimePublication, value)
    kind, key = request["kind"], request["key"]
    definition = {"runtimeProfile": PROFILE, **{field: request[field] for field in
                  ("assetKey", "sourceId", "sourceDigest", "payloadDigest", "payloadJson")}}
    validate_java_asset(kind, key, definition)
    deps = ([{"kind": "ABILITY", "key": code} for code in sorted(application_abilities(definition, key))]
            if kind == "APPLICATION" else [])
    version = "java-" + hashlib.sha256(canonical([request["sourceId"], request["sourceDigest"]])).hexdigest()
    fingerprint = digest(canonical({k: v for k, v in request.items() if k != "expectedServingDigest"}))
    # Separate receipt namespace from package publication; caller request IDs
    # remain stable across retries and cannot alias another asset's operation.
    receipt_id = "runtime:" + hashlib.sha256(canonical([kind, key, request["requestId"]])).hexdigest()
    with publisher.transaction(request["environment"]) as (destination, connection, repository):
        ns = destination.namespace
        prior = connection.execute("SELECT request_digest,receipt FROM a2flow_management_publication_receipts WHERE namespace=%s AND request_id=%s",
                                   (ns, receipt_id)).fetchone()
        if prior is not None:
            if prior[0] != fingerprint:
                raise AssetError("REQUEST_ID_CONFLICT")
            receipt = json.loads(bytes(prior[1]))
            retained = connection.execute("SELECT document,digest FROM a2flow_asset_versions WHERE namespace=%s AND kind=%s AND asset_key=%s AND version_id=%s",
                                          (ns, kind, key, receipt["versionId"])).fetchone()
            if retained is None or retained[1] != receipt["contentDigest"] or digest(bytes(retained[0])) != retained[1]:
                raise AssetError("RECEIPT_READBACK_MISMATCH")
            return receipt
        prior_asset = connection.execute("SELECT document FROM a2flow_asset_versions WHERE namespace=%s AND kind=%s AND asset_key=%s LIMIT 1",
                                         (ns, kind, key)).fetchone()
        asset_id = (json.loads(bytes(prior_asset[0]))["assetId"] if prior_asset else
                    kind.lower() + "-" + hashlib.sha256(key.encode()).hexdigest())
        candidate = {"kind": kind, "key": key, "assetId": asset_id, "versionId": version,
                     "definition": definition, "dependencies": deps}
        candidate["contentDigest"] = digest(canonical(candidate))
        target = {"environment": destination.environment, "versionId": version,
                  "channel": "CURRENT" if destination.environment == "PRT" else "STABLE", "grayUserIds": []}
        result = repository.publish_candidate(ns, kind, key, candidate, target, request["expectedServingDigest"])
        if not result["published"]:
            raise AssetError("PUBLICATION_READBACK_MISMATCH")
        receipt = {"published": True, "kind": kind, "key": key, "environment": destination.environment,
                   "sourceId": request["sourceId"], "sourceDigest": request["sourceDigest"],
                   "versionId": version, "contentDigest": candidate["contentDigest"],
                   "servingDigest": result["servingDigest"], "requestId": request["requestId"]}
        connection.execute("INSERT INTO a2flow_management_publication_receipts(namespace,request_id,request_digest,receipt) VALUES(%s,%s,%s,%s)",
                           (ns, receipt_id, fingerprint, canonical(receipt)))
        return receipt
