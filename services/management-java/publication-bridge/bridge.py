"""Loopback management-only bridge. Reuses asset validators; no Agent/model execution."""
import base64
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib
import io
import json
import os
import zipfile
from typing import TypedDict, cast
from collections.abc import Iterator

import psycopg
from a2flow_asset_store import PostgresAssetRepository, BundleValidator
from a2flow_asset_store.records import AssetError, canonical, digest
from a2flow_asset_store.validation import namespace, entries
from skillweave_contracts import JsonObject

MAX_BODY = 24 * 1024 * 1024


class SelectionRequest(TypedDict):
    key: str
    environment: str


class SelectionResponse(TypedDict):
    servingDigest: str


class PublicationRequest(SelectionRequest):
    sourceId: str
    sourceDigest: str
    snapshot: JsonObject
    requestId: str
    packageDigest: str
    packageBase64: str
    expectedServingDigest: str


class PublicationReceipt(TypedDict):
    published: bool
    assetKey: str
    environment: str
    packageDigest: str
    versionId: str
    contentDigest: str
    servingDigest: str
    requestId: str


class Dependency(TypedDict):
    kind: str
    key: str


def parse_request(value: object, *, publication: bool) -> SelectionRequest | PublicationRequest:
    fields = {"key", "environment"}
    if publication:
        fields |= {"sourceId", "sourceDigest", "snapshot", "requestId", "packageDigest",
                   "packageBase64", "expectedServingDigest"}
    if type(value) is not dict or set(value) != fields:
        raise AssetError("PUBLICATION_FIELDS_INVALID")
    for key in fields - {"snapshot"}:
        if type(value[key]) is not str or not value[key]:
            raise AssetError("PUBLICATION_FIELD_TYPE_INVALID")
    if publication and type(value["snapshot"]) is not dict:
        raise AssetError("FROZEN_SNAPSHOT_REQUIRED")
    return cast(PublicationRequest | SelectionRequest, value)


@dataclass(frozen=True)
class Destination:
    environment: str
    database: str
    dsn: str
    namespace: str


class BoundRepository(PostgresAssetRepository):
    """Reuse library transactions as savepoints under the receipt's outer transaction."""
    def __init__(self, destination: Destination, validator: BundleValidator, connection: psycopg.Connection) -> None:
        super().__init__(destination.dsn, environment=destination.environment,
                         database=destination.database, validator=validator)
        self.connection = connection

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        yield self.connection


def text(value: object, code: str, limit: int = 256) -> str:
    if type(value) is not str or not value or len(value) > limit:
        raise AssetError(code)
    return value


def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise AssetError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def material(request: PublicationRequest) -> JsonObject:
    """Translate archive transport only; package/path/media rules remain library-owned."""
    try:
        raw = base64.b64decode(request["packageBase64"], validate=True)
        if len(raw) > 16 * 1024 * 1024 or digest(raw) != request["packageDigest"]:
            raise AssetError("PACKAGE_DIGEST_OR_SIZE_INVALID")
        items, seen, total = [], set(), 0
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if len(archive.infolist()) > 256:
                raise AssetError("PACKAGE_ENTRY_LIMIT")
            prefix = request["key"] + "/"
            for item in archive.infolist():
                if not item.filename.startswith(prefix) or item.flag_bits & 1:
                    raise AssetError("PACKAGE_ROOT_OR_ENCRYPTION_INVALID")
                if item.is_dir():
                    continue
                path = item.filename[len(prefix):]
                if not path or path in seen or (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise AssetError("PACKAGE_PATH_DUPLICATE_OR_LINK")
                seen.add(path)
                if item.file_size > 4 * 1024 * 1024:
                    raise AssetError("PACKAGE_ENTRY_TOO_LARGE")
                with archive.open(item) as source:
                    content = source.read(4 * 1024 * 1024 + 1)
                total += len(content)
                if len(content) > 4 * 1024 * 1024 or total > 16 * 1024 * 1024:
                    raise AssetError("PACKAGE_EXPANSION_TOO_LARGE")
                media = next((mime for suffix, mime in ((".md", "text/markdown"), (".txt", "text/plain"),
                    (".json", "application/json"), (".yaml", "text/plain"), (".yml", "text/plain"),
                    (".py", "text/plain"), (".js", "text/plain")) if path.endswith(suffix)), "application/octet-stream")
                items.append({"handleId": "entry-" + hashlib.sha256(path.encode()).hexdigest(),
                              "logicalPath": path, "mediaType": media, "byteSize": len(content),
                              "contentDigest": digest(content),
                              "base64": base64.b64encode(content).decode("ascii")})
        items.sort(key=lambda value: (value["logicalPath"] != "SKILL.md", value["logicalPath"]))
        definition = {"entries": items, "requiredToolNames": []}
        entries(definition)
        return definition
    except AssetError:
        raise
    except Exception:
        raise AssetError("INVALID_SKILL_PACKAGE") from None


def dependencies(snapshot: JsonObject) -> list[Dependency]:
    """Explicit compatible mappings only; never drop unsupported component/action semantics."""
    if type(snapshot) is not dict:
        raise AssetError("FROZEN_SNAPSHOT_REQUIRED")
    result: list[Dependency] = []
    for field in ("componentBindings", "capabilityBindings"):
        values = snapshot.get(field)
        if type(values) is not list:
            raise AssetError("FROZEN_BINDING_LIST_REQUIRED")
        for binding in values:
            if type(binding) is not dict:
                raise AssetError("FROZEN_BINDING_INVALID")
            if field == "componentBindings":
                if binding.get("assetType") != "A2UI_APPLICATION":
                    raise AssetError("LEGACY_COMPONENT_RUNTIME_MAPPING_UNSUPPORTED")
                kind, key = "APPLICATION", binding.get("componentName")
            else:
                kind, key = "ABILITY", binding.get("capabilityCode")
            result.append({"kind": kind, "key": text(key, "RUNTIME_DEPENDENCY_KEY_REQUIRED")})
    if len({(dep["kind"], dep["key"]) for dep in result}) != len(result):
        raise AssetError("DUPLICATE_DEPENDENCY")
    return sorted(result, key=lambda dep: (dep["kind"], dep["key"]))


class Publisher:
    def __init__(self, destinations: dict[str, Destination], validator: BundleValidator) -> None:
        if set(destinations) != {"PRT", "ONLINE"}:
            raise AssetError("BOTH_ENVIRONMENT_DESTINATIONS_REQUIRED")
        if destinations["PRT"].database == destinations["ONLINE"].database:
            raise AssetError("SEPARATE_ENVIRONMENT_DATABASES_REQUIRED")
        self.destinations, self.validator = destinations, validator

    @contextmanager
    def transaction(self, environment: str) -> Iterator[tuple[Destination, psycopg.Connection, BoundRepository]]:
        destination = self.destinations.get(environment)
        if destination is None:
            raise AssetError("INVALID_ENVIRONMENT")
        namespace(destination.namespace)
        with psycopg.connect(destination.dsn, autocommit=True, connect_timeout=5,
                             options="-c statement_timeout=10000 -c lock_timeout=5000") as connection:
            with connection.transaction():
                if connection.execute("SELECT current_database()").fetchone() != (destination.database,):
                    raise AssetError("DATABASE_MISMATCH")
                if connection.execute("SELECT environment FROM a2flow_asset_environment WHERE singleton=TRUE").fetchall() != [(environment,)]:
                    raise AssetError("DATABASE_ENVIRONMENT_MISMATCH")
                lock = int.from_bytes(hashlib.sha256(destination.namespace.encode()).digest()[:8], "big", signed=True)
                connection.execute("SELECT pg_advisory_xact_lock(%s)", (lock,))
                yield destination, connection, BoundRepository(destination, self.validator, connection)

    @staticmethod
    def state(connection: psycopg.Connection, ns: str, key: str) -> JsonObject | None:
        row = connection.execute("SELECT document FROM a2flow_asset_serving WHERE namespace=%s AND kind='SKILL' AND asset_key=%s", (ns, key)).fetchone()
        return None if row is None else json.loads(bytes(row[0]))

    def selection(self, request: SelectionRequest) -> SelectionResponse:
        request = cast(SelectionRequest, parse_request(request, publication=False))
        key = text(request.get("key"), "SKILL_KEY_REQUIRED")
        with self.transaction(request.get("environment")) as (destination, connection, repository):
            document = repository._document(connection, destination.namespace)
            if document["assets"] or document["serving"]:
                self.validator.validate(document, expected_namespace=destination.namespace,
                                        expected_environment=destination.environment)
                repository._validate_serving_closure(document)
            return {"servingDigest": digest(canonical(self.state(connection, destination.namespace, key)))}

    @staticmethod
    def verify_retained(connection: psycopg.Connection, ns: str, key: str, version: str, expected: str) -> None:
        row = connection.execute("SELECT document,digest FROM a2flow_asset_versions WHERE namespace=%s AND kind='SKILL' AND asset_key=%s AND version_id=%s", (ns, key, version)).fetchone()
        if row is None or row[1] != expected or digest(bytes(row[0])) != expected:
            raise AssetError("RECEIPT_READBACK_MISMATCH")

    def publish(self, request: PublicationRequest) -> PublicationReceipt:
        request = cast(PublicationRequest, parse_request(request, publication=True))
        key = text(request["key"], "SKILL_KEY_REQUIRED")
        request_id = text(request["requestId"], "REQUEST_ID_REQUIRED")
        text(request["sourceId"], "SOURCE_ID_REQUIRED")
        text(request["sourceDigest"], "SOURCE_DIGEST_REQUIRED")
        fingerprint = digest(canonical({k: v for k, v in request.items() if k != "expectedServingDigest"}))
        definition = material(request)
        deps = dependencies(request["snapshot"])
        definition["requiredToolNames"] = sorted({"execute_ability" if dep["kind"] == "ABILITY" else "render_application" for dep in deps})
        version = "java-" + hashlib.sha256(canonical([request["sourceId"], request["sourceDigest"], request["packageDigest"]])).hexdigest()
        with self.transaction(request["environment"]) as (destination, connection, repository):
            ns = destination.namespace
            prior = connection.execute("SELECT request_digest,receipt FROM a2flow_management_publication_receipts WHERE namespace=%s AND request_id=%s", (ns, request_id)).fetchone()
            if prior:
                if prior[0] != fingerprint:
                    raise AssetError("REQUEST_ID_CONFLICT")
                receipt = json.loads(bytes(prior[1]))
                self.verify_retained(connection, ns, key, receipt["versionId"], receipt["contentDigest"])
                return receipt
            rows = connection.execute("SELECT document FROM a2flow_asset_versions WHERE namespace=%s AND kind='SKILL' AND asset_key=%s LIMIT 1", (ns, key)).fetchone()
            asset_id = json.loads(bytes(rows[0]))["assetId"] if rows else "skill-" + hashlib.sha256(key.encode()).hexdigest()
            candidate = {"kind": "SKILL", "key": key, "assetId": asset_id, "versionId": version,
                         "definition": definition, "dependencies": deps}
            candidate["contentDigest"] = digest(canonical(candidate))
            target = {"environment": destination.environment, "versionId": version,
                      "channel": "CURRENT" if destination.environment == "PRT" else "STABLE", "grayUserIds": []}
            result = repository.publish_candidate(ns, "SKILL", key, candidate, target, request["expectedServingDigest"])
            self.verify_retained(connection, ns, key, version, candidate["contentDigest"])
            if not result["published"]:
                raise AssetError("PUBLICATION_READBACK_MISMATCH")
            receipt: PublicationReceipt = {"published": True, "assetKey": key, "environment": destination.environment,
                       "packageDigest": request["packageDigest"], "versionId": version,
                       "contentDigest": candidate["contentDigest"], "servingDigest": result["servingDigest"],
                       "requestId": request_id}
            connection.execute("INSERT INTO a2flow_management_publication_receipts(namespace,request_id,request_digest,receipt) VALUES(%s,%s,%s,%s)", (ns, request_id, fingerprint, canonical(receipt)))
        return receipt


def handler(publisher: Publisher, token: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass  # No tokens, payloads or access headers in logs.

        def do_POST(self) -> None:
            try:
                if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                    self.send_error(401)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY or self.headers.get("Transfer-Encoding"):
                    raise AssetError("REQUEST_SIZE_INVALID")
                request = json.loads(self.rfile.read(length), object_pairs_hook=unique)
                if self.path == "/selection":
                    result = publisher.selection(cast(SelectionRequest, parse_request(request, publication=False)))
                elif self.path == "/publish":
                    result = publisher.publish(cast(PublicationRequest, parse_request(request, publication=True)))
                elif self.path == "/asset/selection":
                    from runtime_assets import selection
                    result = selection(publisher, request)
                elif self.path == "/asset/publish":
                    from runtime_assets import publish
                    result = publish(publisher, request)
                else:
                    raise AssetError("UNKNOWN_OPERATION")
                status = 200
            except AssetError as error:
                result, status = {"error": error.code}, 409
            except Exception:
                result, status = {"error": "PUBLICATION_FAILED_OUTCOME_REQUIRES_RETRY"}, 500
            data = canonical(result)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    return Handler


class BoundedHTTPServer(HTTPServer):
    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(45)
        return connection, address


def main() -> None:
    token = os.environ["A2FLOW_PUBLICATION_BRIDGE_TOKEN"]
    if len(token) < 32:
        raise ValueError("PUBLICATION_BRIDGE_TOKEN_INVALID")
    module, name = os.environ["A2FLOW_PUBLICATION_VALIDATOR_FACTORY"].split(":")
    validator = getattr(importlib.import_module(module), name)()
    destinations = {env: Destination(env, os.environ[f"A2FLOW_PUBLICATION_{env}_DATABASE"],
                                    os.environ[f"A2FLOW_PUBLICATION_{env}_DSN"],
                                    os.environ[f"A2FLOW_PUBLICATION_{env}_NAMESPACE"])
                    for env in ("PRT", "ONLINE")}
    server = BoundedHTTPServer(("127.0.0.1", int(os.environ.get("A2FLOW_PUBLICATION_BRIDGE_PORT", "8093"))),
                        handler(Publisher(destinations, validator), token))
    server.serve_forever()


if __name__ == "__main__":
    main()
