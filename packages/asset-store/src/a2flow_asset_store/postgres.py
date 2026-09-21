"""Explicit PostgreSQL initialization, immutable import and bounded snapshots."""
from contextlib import contextmanager
import hashlib
import json
from skillweave_contracts.user_id import user_id_from_wire, user_id_to_wire

from .records import AssetError, KINDS, MAX_ASSETS, MAX_BYTES, canonical, digest
from .validation import environment, namespace

DDL = (
    "CREATE TABLE IF NOT EXISTS a2flow_asset_environment "
    "(singleton BOOLEAN PRIMARY KEY CHECK (singleton), environment TEXT NOT NULL "
    "CHECK (environment IN ('PRT','ONLINE')))",
    "CREATE TABLE IF NOT EXISTS a2flow_asset_versions "
    "(namespace TEXT NOT NULL, kind TEXT NOT NULL, asset_key TEXT NOT NULL, "
    "version_id TEXT NOT NULL, document BYTEA NOT NULL, digest TEXT NOT NULL, "
    "PRIMARY KEY(namespace,kind,asset_key,version_id))",
    "CREATE TABLE IF NOT EXISTS a2flow_asset_serving "
    "(namespace TEXT NOT NULL, kind TEXT NOT NULL, asset_key TEXT NOT NULL, "
    "document BYTEA NOT NULL, PRIMARY KEY(namespace,kind,asset_key))",
)


class PostgresAssetRepository:
    """One environment/database binding per instance, no implicit initialization."""
    def __init__(self, conninfo, *, environment, database, validator, connection_factory=None):
        self.environment = globals()["environment"](environment)
        if type(database) is not str or not database:
            raise AssetError("EXACT_DATABASE_REQUIRED")
        self.database, self.validator = database, validator
        self._conninfo, self._connect = conninfo, connection_factory

    @contextmanager
    def _connection(self):
        connection = None
        try:
            connect = self._connect
            if connect is None:
                import psycopg
                connect = psycopg.connect
            connection = connect(self._conninfo, autocommit=True, connect_timeout=5,
                options="-c statement_timeout=10000 -c lock_timeout=5000",
                application_name="a2flow-asset-store")
            row = connection.execute("SELECT current_database()").fetchone()
            if not row or row[0] != self.database:
                raise AssetError("DATABASE_MISMATCH")
            yield connection
        except AssetError:
            raise
        except Exception:
            raise AssetError("ASSET_DATABASE_ERROR") from None
        finally:
            if connection is not None:
                connection.close()

    def _check_environment(self, connection):
        rows = connection.execute(
            "SELECT environment FROM a2flow_asset_environment WHERE singleton=TRUE"
        ).fetchall()
        if rows != [(self.environment,)]:
            raise AssetError("DATABASE_ENVIRONMENT_MISMATCH")

    def setup(self):
        """Operator-only DDL; separate from seed and read calls."""
        with self._connection() as connection:
            with connection.transaction():
                connection.execute("SELECT pg_advisory_xact_lock(%s)", (78080301,))
                for statement in DDL:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO a2flow_asset_environment(singleton,environment) VALUES(TRUE,%s) "
                    "ON CONFLICT(singleton) DO NOTHING", (self.environment,))
                self._check_environment(connection)

    def _document(self, connection, ns):
        self._check_environment(connection)
        total = 0
        for table in ("a2flow_asset_versions", "a2flow_asset_serving"):
            # Table names are constant allowlisted literals, never operator/model input.
            count, size = connection.execute(
                "SELECT count(*),coalesce(sum(octet_length(document)),0) FROM " + table +
                " WHERE namespace=%s", (ns,)).fetchone()
            if count > MAX_ASSETS:
                raise AssetError("ASSET_LIMIT")
            total += size
        if total > MAX_BYTES:
            raise AssetError("BUNDLE_TOO_LARGE")
        rows = connection.execute(
            "SELECT kind,asset_key,version_id,document,digest FROM a2flow_asset_versions "
            "WHERE namespace=%s ORDER BY kind,asset_key,version_id", (ns,)).fetchall()
        assets = []
        for kind, key, version, raw, expected in rows:
            raw = bytes(raw)
            if digest(raw) != expected:
                raise AssetError("READBACK_DIGEST_MISMATCH")
            value = json.loads(raw)
            if canonical(value) != raw or (value["kind"], value["key"], value["versionId"]) != (kind, key, version):
                raise AssetError("READBACK_IDENTITY_MISMATCH")
            assets.append({**value, "contentDigest": expected})
        states = []
        for kind, key, raw in connection.execute(
            "SELECT kind,asset_key,document FROM a2flow_asset_serving WHERE namespace=%s "
            "ORDER BY kind,asset_key", (ns,)).fetchall():
            raw = bytes(raw)
            state = json.loads(raw)
            if canonical(state) != raw or (state["kind"], state["key"]) != (kind, key):
                raise AssetError("READBACK_IDENTITY_MISMATCH")
            states.append(state)
        return {"format": "AF-MVP-08-ASSETS-1", "namespace": ns,
                "environment": self.environment, "assets": assets, "serving": states}

    def check_publication_ready(self, ns):
        """Check an initialized destination; an empty namespace is publishable."""
        ns = namespace(ns)
        with self._connection() as connection:
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                document = self._document(connection, ns)
                if document["assets"] or document["serving"]:
                    self.validator.validate(
                        document, expected_namespace=ns,
                        expected_environment=self.environment)
                    self._validate_serving_closure(document)
                return {"ready": True, "empty": not document["assets"]}

    def read(self, ns):
        namespace(ns)
        with self._connection() as connection:
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                document = self._document(connection, ns)
                return self.validator.validate(document, expected_namespace=ns,
                                               expected_environment=self.environment)

    def import_bundle(self, document, *, expected_namespace, dry_run=True):
        """Validate before connection; atomic insert/no-op, never overwrite.

        A post-commit verification error is explicitly a potentially committed
        result, not an invitation to retry blindly.
        """
        ns = namespace(expected_namespace)
        desired = self.validator.validate(document, expected_namespace=ns,
                                          expected_environment=self.environment)
        inserts = []
        with self._connection() as connection:
            with connection.transaction():
                if dry_run:
                    connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                else:
                    lock = int.from_bytes(hashlib.sha256(ns.encode()).digest()[:8], "big", signed=True)
                    connection.execute("SELECT pg_advisory_xact_lock(%s)", (lock,))
                existing = self._document(connection, ns)
                old_assets = {(a["kind"], a["key"], a["versionId"]): a for a in existing["assets"]}
                old_states = {(s["kind"], s["key"]): s for s in existing["serving"]}
                for asset in desired.assets:
                    value = {**asset.document, "contentDigest": asset.content_digest}
                    old = old_assets.get(asset.identity)
                    if old is not None and canonical(old) != canonical(value):
                        raise AssetError("ASSET_CONFLICT")
                    if old is None:
                        inserts.append(asset.identity)
                    old_assets[asset.identity] = value
                for state in json.loads(desired.serving_data):
                    identity = state["kind"], state["key"]
                    old = old_states.get(identity)
                    if old is not None and canonical(old) != canonical(state):
                        raise AssetError("SERVING_CONFLICT")
                    old_states[identity] = state
                combined = {**existing, "assets": list(old_assets.values()),
                            "serving": list(old_states.values())}
                self.validator.validate(combined, expected_namespace=ns,
                                        expected_environment=self.environment)
                if not dry_run:
                    for asset in desired.assets:
                        if asset.identity in inserts:
                            connection.execute(
                                "INSERT INTO a2flow_asset_versions "
                                "(namespace,kind,asset_key,version_id,document,digest) VALUES(%s,%s,%s,%s,%s,%s)",
                                (ns, asset.kind, asset.key, asset.version_id, asset.data, asset.content_digest))
                    previous_keys = {(s["kind"], s["key"]) for s in existing["serving"]}
                    for state in json.loads(desired.serving_data):
                        if (state["kind"], state["key"]) not in previous_keys:
                            connection.execute(
                                "INSERT INTO a2flow_asset_serving(namespace,kind,asset_key,document) VALUES(%s,%s,%s,%s)",
                                (ns, state["kind"], state["key"], canonical(state)))
                    self._verify(connection, ns, desired)
        if not dry_run:
            try:
                with self._connection() as connection:
                    with connection.transaction():
                        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                        self._verify(connection, ns, desired)
            except AssetError:
                raise AssetError("POST_COMMIT_VERIFICATION_FAILED") from None
        return {"namespace": ns, "environment": self.environment,
                "status": ("WOULD_INSERT" if inserts else "NO_CHANGE") if dry_run else
                          ("INSERTED" if inserts else "NO_CHANGE"),
                "assets": [{"kind": a.kind, "key": a.key, "versionId": a.version_id,
                            "contentDigest": a.content_digest} for a in desired.assets]}

    @staticmethod
    def _asset_key(kind, key):
        if type(kind) is not str or kind not in KINDS:
            raise AssetError("UNKNOWN_ASSET_KIND")
        if type(key) is not str or not 1 <= len(key) <= 256:
            raise AssetError("INVALID_ASSET_KEY")
        return kind, key

    @staticmethod
    def _serving_digest(state):
        return digest(canonical(state))

    def publication_history(self, ns, kind, key):
        """Read retained immutable versions and the current serving CAS token."""
        ns = namespace(ns)
        kind, key = self._asset_key(kind, key)
        with self._connection() as connection:
            with connection.transaction():
                connection.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                document = self._document(connection, ns)
                versions = [
                    {"versionId": item["versionId"],
                     "assetId": item["assetId"],
                     "contentDigest": item["contentDigest"]}
                    for item in document["assets"]
                    if (item["kind"], item["key"]) == (kind, key)
                ]
                state = next((item for item in document["serving"]
                              if (item["kind"], item["key"]) == (kind, key)), None)
                if not versions or state is None:
                    raise AssetError("ASSET_NOT_FOUND")
                return {
                    "kind": kind, "key": key, "versions": versions,
                    "serving": {**state, "grayUserIds": [
                        user_id_to_wire(user_id_from_wire(user))
                        for user in state["grayUserIds"]]},
                    "servingDigest": self._serving_digest(state),
                }

    def retained_version(self, ns, kind, key, version_id):
        ns = namespace(ns)
        kind, key = self._asset_key(kind, key)
        if type(version_id) is not str or not 1 <= len(version_id) <= 256:
            raise AssetError("INVALID_VERSION_ID")
        with self._connection() as connection:
            with connection.transaction():
                connection.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                self._check_environment(connection)
                row = connection.execute(
                    "SELECT document,digest FROM a2flow_asset_versions "
                    "WHERE namespace=%s AND kind=%s AND asset_key=%s AND version_id=%s",
                    (ns, kind, key, version_id)).fetchone()
        if row is None:
            raise AssetError("VERSION_NOT_FOUND")
        raw, expected = bytes(row[0]), row[1]
        if digest(raw) != expected:
            raise AssetError("READBACK_DIGEST_MISMATCH")
        document = json.loads(raw)
        if canonical(document) != raw or (
                document.get("kind"), document.get("key"), document.get("versionId")) != (
                    kind, key, version_id):
            raise AssetError("READBACK_IDENTITY_MISMATCH")
        return {"kind": kind, "key": key, "versionId": version_id,
                "contentDigest": expected, "document": document}

    def publish_candidate(self, ns, kind, key, candidate, target,
                          expected_serving_digest):
        """Atomically retain one immutable candidate and select its target."""
        return self._change_serving(
            ns, kind, key, target["versionId"], target,
            expected_serving_digest, candidate=candidate, status="PUBLISHED")

    def check_candidate(self, ns, kind, key, candidate, target,
                        expected_serving_digest):
        """Validate the exact publication transaction without writing rows."""
        return self._change_serving(
            ns, kind, key, target["versionId"], target,
            expected_serving_digest, candidate=candidate, status="CHECKED", dry_run=True)

    def rollback_configuration(self, ns, kind, key, version_id, target,
                               expected_serving_digest):
        """Select a retained version; this never compensates business effects."""
        return self._change_serving(
            ns, kind, key, version_id, target, expected_serving_digest,
            candidate=None, status="ROLLED_BACK")

    def _change_serving(self, ns, kind, key, version_id, target,
                        expected_serving_digest, *, candidate, status, dry_run=False):
        ns = namespace(ns)
        kind, key = self._asset_key(kind, key)
        if (type(expected_serving_digest) is not str
                or not expected_serving_digest.startswith("sha256:")):
            raise AssetError("INVALID_SERVING_DIGEST")
        if type(target) is not dict or set(target) != {
                "environment", "versionId", "channel", "grayUserIds"}:
            raise AssetError("INVALID_PUBLICATION_TARGET")
        if target["environment"] != self.environment or target["versionId"] != version_id:
            raise AssetError("DESTINATION_MISMATCH")
        gray_users = target["grayUserIds"]
        if type(gray_users) is not list or len(gray_users) > 1024:
            raise AssetError("INVALID_GRAY_USERS")
        try:
            gray_users = [user_id_to_wire(user_id_from_wire(user)) for user in gray_users]
        except ValueError:
            raise AssetError("INVALID_GRAY_USERS") from None
        if len(gray_users) != len(set(gray_users)):
            raise AssetError("INVALID_GRAY_USERS")
        with self._connection() as connection:
            with connection.transaction():
                lock = int.from_bytes(
                    hashlib.sha256(ns.encode()).digest()[:8],
                    "big", signed=True)
                connection.execute("SELECT pg_advisory_xact_lock(%s)", (lock,))
                existing = self._document(connection, ns)
                states = {(item["kind"], item["key"]): item
                          for item in existing["serving"]}
                old_state = states.get((kind, key))
                empty_digest = self._serving_digest(None)
                if old_state is None:
                    if candidate is None:
                        raise AssetError("ASSET_NOT_FOUND")
                    if expected_serving_digest != empty_digest:
                        raise AssetError("STALE_SERVING_SELECTION")
                elif self._serving_digest(old_state) != expected_serving_digest:
                    raise AssetError("STALE_SERVING_SELECTION")

                assets = {(item["kind"], item["key"], item["versionId"]): item
                          for item in existing["assets"]}
                identity = kind, key, version_id
                if candidate is not None:
                    if (type(candidate) is not dict
                            or (candidate.get("kind"), candidate.get("key"),
                                candidate.get("versionId")) != identity):
                        raise AssetError("CANDIDATE_IDENTITY_MISMATCH")
                    old = assets.get(identity)
                    if old is not None and canonical(old) != canonical(candidate):
                        raise AssetError("ASSET_CONFLICT")
                    assets[identity] = candidate
                elif identity not in assets:
                    raise AssetError("VERSION_NOT_FOUND")

                if self.environment == "PRT":
                    if target["channel"] != "CURRENT" or gray_users:
                        raise AssetError("INVALID_PRT_TARGET")
                    next_state = {
                        "kind": kind, "key": key, "current": version_id,
                        "stable": None, "gray": None, "grayUserIds": [],
                    }
                else:
                    if old_state is None and target["channel"] == "GRAY":
                        raise AssetError("INVALID_ONLINE_TARGET")
                    if target["channel"] == "STABLE" and not gray_users:
                        next_state = {
                            "kind": kind, "key": key, "current": None,
                            "stable": version_id, "gray": None,
                            "grayUserIds": [],
                        }
                    elif target["channel"] == "GRAY" and gray_users:
                        next_state = {
                            "kind": kind, "key": key, "current": None,
                            "stable": old_state["stable"] if old_state else None, "gray": version_id,
                            "grayUserIds": gray_users,
                        }
                    else:
                        raise AssetError("INVALID_ONLINE_TARGET")
                states[(kind, key)] = next_state
                proposed = {
                    **existing, "assets": list(assets.values()),
                    "serving": list(states.values()),
                }
                desired = self.validator.validate(
                    proposed, expected_namespace=ns,
                    expected_environment=self.environment)
                self._validate_serving_closure(proposed)
                if dry_run:
                    return {"status": "PREPARED_NOT_PUBLISHED", "published": False,
                            "expectedServingDigest": expected_serving_digest}

                if candidate is not None and identity not in {
                        (item["kind"], item["key"], item["versionId"])
                        for item in existing["assets"]}:
                    raw = canonical({
                        field: value for field, value in candidate.items()
                        if field != "contentDigest"
                    })
                    if digest(raw) != candidate.get("contentDigest"):
                        raise AssetError("DIGEST_MISMATCH")
                    connection.execute(
                        "INSERT INTO a2flow_asset_versions "
                        "(namespace,kind,asset_key,version_id,document,digest) "
                        "VALUES(%s,%s,%s,%s,%s,%s)",
                        (ns, kind, key, version_id, raw,
                         candidate["contentDigest"]))
                if old_state is None:
                    result = connection.execute(
                        "INSERT INTO a2flow_asset_serving(namespace,kind,asset_key,document) "
                        "VALUES(%s,%s,%s,%s) ON CONFLICT(namespace,kind,asset_key) DO NOTHING",
                        (ns, kind, key, canonical(next_state)))
                else:
                    result = connection.execute(
                        "UPDATE a2flow_asset_serving SET document=%s "
                        "WHERE namespace=%s AND kind=%s AND asset_key=%s "
                        "AND document=%s",
                        (canonical(next_state), ns, kind, key,
                         canonical(old_state)))
                if getattr(result, "rowcount", 1) != 1:
                    raise AssetError("STALE_SERVING_SELECTION")
                self._verify(connection, ns, desired)
                self._validate_serving_closure(self._document(connection, ns))
        return {
            "status": status, "published": True,
            "businessCompensated": False,
            "kind": kind, "key": key, "versionId": version_id,
            "serving": next_state,
            "servingDigest": self._serving_digest(next_state),
        }

    def _validate_serving_closure(self, document):
        """Check selected Application ability pins for every routing cohort."""
        states = {(item["kind"], item["key"]): item
                  for item in document["serving"]}
        states = {key: {**state, "grayUserIds": [user_id_from_wire(user)
                   for user in state["grayUserIds"]]} for key, state in states.items()}
        assets = {(item["kind"], item["key"], item["versionId"]): item
                  for item in document["assets"]}
        users = {None}
        if self.environment == "ONLINE":
            users.update(user for state in states.values()
                         for user in state["grayUserIds"])

        def selected(state, user):
            if self.environment == "PRT":
                return state["current"]
            if user is not None and user in state["grayUserIds"]:
                return state["gray"]
            return state["stable"]

        for user in users:
            for (asset_kind, asset_key), state in states.items():
                if asset_kind != "APPLICATION":
                    continue
                application = assets[(
                    asset_kind, asset_key, selected(state, user))]
                for action in application["definition"]["actionPolicies"]:
                    ability_key, expected_version = (
                        action["abilityReleaseRef"].split("@"))
                    ability_state = states.get(("ABILITY", ability_key))
                    if (ability_state is None
                            or selected(ability_state, user)
                            != expected_version):
                        raise AssetError("SERVING_DEPENDENCY_MISMATCH")

    def _verify(self, connection, ns, desired):
        observed = self._document(connection, ns)
        self.validator.validate(observed, expected_namespace=ns,
                                expected_environment=self.environment)
        actual = {(a["kind"], a["key"], a["versionId"]): a for a in observed["assets"]}
        for asset in desired.assets:
            expected = {**asset.document, "contentDigest": asset.content_digest}
            if canonical(actual.get(asset.identity)) != canonical(expected):
                raise AssetError("READBACK_DIGEST_MISMATCH")
        states = {(s["kind"], s["key"]): s for s in observed["serving"]}
        for state in json.loads(desired.serving_data):
            if canonical(states.get((state["kind"], state["key"]))) != canonical(state):
                raise AssetError("READBACK_SERVING_MISMATCH")
