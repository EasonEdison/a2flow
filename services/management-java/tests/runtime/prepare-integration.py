"""Initialize only freshly-created integration DBs and private synthetic credentials."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import sys
import psycopg
from a2flow_asset_store import PostgresAssetRepository
from deploy.assets import bundle_validator


def main():
    directory = Path(sys.argv[1]).resolve()
    if not directory.name.startswith("a2flow-chat-integration."):
        raise ValueError("Dedicated integration directory required")
    namespace = "chat-rpc-integration"
    validator = bundle_validator()
    destinations = {}
    for env in ("PRT", "ONLINE"):
        database = "chat_rpc_" + env.lower()
        dsn = f"host=127.0.0.1 port=56502 dbname={database}"
        PostgresAssetRepository(dsn, environment=env, database=database, validator=validator).setup()
        with psycopg.connect(dsn) as connection:
            connection.execute(Path(os.environ["INTEGRATION_JAVA_ROOT"], "publication-bridge/migrations/V001__publication_receipts.sql").read_text())
        destinations[env] = dsn
    token = secrets.token_urlsafe(32)
    bridge_token = secrets.token_urlsafe(40)
    user_id = 9223372036854775807
    with psycopg.connect("host=127.0.0.1 port=56502 dbname=chat_rpc_management") as connection:
        connection.execute("CREATE TABLE users (user_id bigint PRIMARY KEY, role text NOT NULL)")
        connection.execute("CREATE TABLE sessions (token_sha256 text PRIMARY KEY, user_id bigint REFERENCES users(user_id), expires_at timestamptz NOT NULL)")
        connection.execute("INSERT INTO users VALUES (%s, 'ADMIN')", (user_id,))
        connection.execute("INSERT INTO sessions VALUES (%s, %s, CURRENT_TIMESTAMP + INTERVAL '8 hours')", (hashlib.sha256(token.encode()).hexdigest(), user_id))
    env = {
        "A2FLOW_MANAGEMENT_NAMESPACE": namespace,
        "A2FLOW_PUBLICATION_BRIDGE_TOKEN": bridge_token,
        "A2FLOW_PUBLICATION_VALIDATOR_FACTORY": "deploy.assets:bundle_validator",
        "A2FLOW_PUBLICATION_BRIDGE_PORT": "18892",
        "A2FLOW_PUBLICATION_BRIDGE_URL": "http://127.0.0.1:18892",
        "M_ORIGIN": "http://127.0.0.1:18890",
        "M_COOKIE": "a2flow_management_session=" + token,
        "M_SESSION_COOKIE": "a2flow_management_session=" + token,
        "M_USER_ID": str(user_id),
        "RPC_DESCRIPTOR_FILE": str(directory / "business-descriptor.base64"),
        "RPC_TARGET_KEY": "integration-business",
        "RPC_SERVICE_NAME": "integration.business.v1.Business",
        "RPC_METHOD_NAME": "Invoke",
        "M_AUTHORING_OUTPUT": str(directory / "authored-assets.json"),
        "OUTPUT_FILE": str(directory / "authored-assets.json"),
        "RUNTIME_ENV_FILE": str(directory / "runtime-env.json"),
    }
    for environment in destinations:
        env[f"A2FLOW_PUBLICATION_{environment}_DSN"] = destinations[environment]
        env[f"A2FLOW_PUBLICATION_{environment}_DATABASE"] = "chat_rpc_" + environment.lower()
        env[f"A2FLOW_PUBLICATION_{environment}_NAMESPACE"] = namespace
    write_private(directory / "environment.sh", "".join("export " + key + "=" + shlex.quote(value) + "\n" for key, value in env.items()))
    write_private(directory / "runtime-env.json", json.dumps({
        "prtDsn": destinations["PRT"], "onlineDsn": destinations["ONLINE"], "namespace": namespace,
        "rpcTarget": "127.0.0.1:18893", "userId": str(user_id),
    }, ensure_ascii=False, indent=2))


def write_private(path, value):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        stream.write(value)


if __name__ == "__main__":
    main()
