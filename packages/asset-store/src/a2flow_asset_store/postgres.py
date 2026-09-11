"""Explicit PostgreSQL initialization, immutable import and bounded snapshots."""
from contextlib import contextmanager
import hashlib
import json

from .records import AssetError, MAX_ASSETS, MAX_BYTES, canonical, digest
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
                for state in desired.serving:
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
                    for state in desired.serving:
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
        for state in desired.serving:
            if canonical(states.get((state["kind"], state["key"]))) != canonical(state):
                raise AssetError("READBACK_SERVING_MISMATCH")
