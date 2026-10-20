#!/usr/bin/env python3
"""Generate a new installation's private configuration; no databases or services."""
from __future__ import annotations

import argparse
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import runpy
import secrets
import shutil
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ("gateway", "bootstrap", "management", "accounts", "bside", "runtime", "execution", "content", "management-agent", "scheduler")


def write(path: Path, value: object, mode: int = 0o600) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, dict) else str(value)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(text + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--admin-user", required=True)
    parser.add_argument("--admin-password-file", type=Path)
    parser.add_argument("--model-key-file", type=Path)
    parser.add_argument("--prefix", default="a2flow_selfhost")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--registration-enabled", action="store_true")
    parser.add_argument("--trusted-edge-ip", action="append", default=[])
    args = parser.parse_args()
    trusted_edges = [str(ipaddress.ip_address(value)) for value in args.trusted_edge_ip]
    target = args.directory.expanduser().absolute()
    resolved = target.resolve()
    origin = urlsplit(args.origin)
    if (origin.scheme not in {"https", "http"} or not origin.hostname or origin.username or origin.password
            or origin.path or origin.query or origin.fragment
            or (origin.scheme == "http" and origin.hostname not in {"127.0.0.1", "localhost", "::1"})):
        raise ValueError("Use an exact HTTPS origin, or HTTP localhost for local development")
    if resolved == ROOT or ROOT in resolved.parents or target.exists():
        raise ValueError("Choose a new private directory outside the repository")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,24}", args.prefix) or not 1024 <= args.port <= 65535:
        raise ValueError("Invalid installation prefix or port")
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,32}", args.admin_user):
        raise ValueError("Admin name must be 3-32 letters, digits, underscore or hyphen")
    if not shutil.which("openssl"):
        raise ValueError("openssl is required for private mTLS certificates")
    password = args.admin_password_file.read_text().rstrip("\r\n") if args.admin_password_file else getpass.getpass("New administrator password: ")
    key = args.model_key_file.read_text().strip() if args.model_key_file else getpass.getpass("DeepSeek model API key: ")
    if not 8 <= len(password) <= 256 or not key or len(key) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise ValueError("Password must be 8-256 characters; model key must be nonempty printable ASCII")
    target.mkdir(mode=0o700, parents=True)
    for service in SERVICES:
        (target / service).mkdir(mode=0o700)
    gateway_config = (ROOT / "deploy/selfhost/nginx.conf").read_text()
    if trusted_edges:
        directives = "    real_ip_header X-A2Flow-Client-IP;\n" + "".join(f"    set_real_ip_from {value};\n" for value in trusted_edges)
        gateway_config = gateway_config.replace("    server_name _;\n", "    server_name _;\n" + directives)
    write(target / "gateway" / "nginx.conf", gateway_config)
    ca = target / "certificate-authority"
    ca.mkdir(mode=0o700)
    def openssl(*arguments: str) -> None:
        subprocess.run(["openssl", *arguments], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    openssl("req", "-x509", "-newkey", "rsa:3072", "-nodes", "-days", "3650", "-subj", "/CN=A2Flow Selfhost Private CA", "-keyout", str(ca / "ca-key.pem"), "-out", str(ca / "ca.pem"))
    for kind, usage in (("server", "serverAuth"), ("client", "clientAuth")):
        write(ca / f"{kind}.ext", f"basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage={usage}\nsubjectAltName=IP:127.0.0.1,DNS:localhost")
        openssl("req", "-newkey", "rsa:3072", "-nodes", "-subj", f"/CN=A2Flow {kind}", "-keyout", str(ca / f"{kind}-key.pem"), "-out", str(ca / f"{kind}.csr"))
        openssl("x509", "-req", "-days", "365", "-in", str(ca / f"{kind}.csr"), "-CA", str(ca / "ca.pem"), "-CAkey", str(ca / "ca-key.pem"), "-CAcreateserial", "-extfile", str(ca / f"{kind}.ext"), "-out", str(ca / f"{kind}.pem"))
    for path in ca.iterdir():
        path.chmod(0o600)
    certificate_roles = {"management": ("server", "client"), "execution": ("server", "client"),
                         "bside": ("client",), "runtime": ("client",),
                         "management-agent": ("client",), "content": ("server",)}
    for service, roles in certificate_roles.items():
        filenames = ["ca.pem", *(name for role in roles for name in (role + ".pem", role + "-key.pem"))]
        for filename in filenames:
            write(target / service / filename, (ca / filename).read_text())
    names = {kind: args.prefix + "_" + kind for kind in ("bootstrap", "management", "prt", "online", "content", "reader", "accounts")}
    passwords = {kind: secrets.token_urlsafe(36) for kind in names}
    pepper, token, installation = (secrets.token_urlsafe(36) for _ in range(3))
    hash_password = runpy.run_path(str(ROOT / "services/b-side-api/src/a2flow_bside/auth.py"))["hash_password"]
    password_hash = hash_password(password, pepper=pepper)
    del password
    def dsn(kind: str, role: str | None = None) -> str:
        role = role or kind
        return f"host=/run/postgresql dbname={names[kind]} user={names[role]} password={passwords[role]}"
    auth = {"A2FLOW_AUTH_TRUSTED_PROXIES": "127.0.0.1,::1", "A2FLOW_REGISTRATION_ENABLED": str(args.registration_enabled).lower()}
    base = {"A2FLOW_ENVIRONMENT": "PRT", "A2FLOW_DATABASE_NAME": names["prt"], "A2FLOW_DATABASE_USER": names["prt"], "A2FLOW_POSTGRES_PASSWORD_FILE": "/run/selfhost/postgres_password", "A2FLOW_ASSET_NAMESPACE": "a2flow-selfhost", "A2FLOW_USER_ID": "1", "A2FLOW_DEEPSEEK_KEY_FILE": "/run/selfhost/model_key", "A2FLOW_PEPPER_FILE": "/run/selfhost/pepper", "A2FLOW_INTERNAL_TOKEN_FILE": "/run/selfhost/internal_token"}
    rpc = {"A2FLOW_ENGINE_RPC_TARGET": "127.0.0.1:8794", "A2FLOW_ENGINE_RPC_MODE": "MTLS", "A2FLOW_ENGINE_RPC_CA_FILE": "/run/selfhost/ca.pem", "A2FLOW_ENGINE_RPC_CERT_FILE": "/run/selfhost/client.pem", "A2FLOW_ENGINE_RPC_KEY_FILE": "/run/selfhost/client-key.pem"}
    for service in ("accounts", "bside", "runtime"):
        service_secrets = {"postgres_password": passwords["prt"], "pepper": pepper}
        if service != "accounts":
            service_secrets.update(internal_token=token, model_key=key)
        for filename, value in service_secrets.items():
            write(target / service / filename, value, 0o400)
    bside = {**base, **rpc, **auth, "A2FLOW_LISTEN_PORT": "8785", "A2FLOW_BSIDE_DATABASE_NAME": names["prt"], "A2FLOW_BSIDE_ENVIRONMENT": "PRT", "A2FLOW_BSIDE_ASSET_NAMESPACE": "a2flow-selfhost", "A2FLOW_BSIDE_VALIDATOR_FACTORY": "deploy.assets:bundle_validator", "A2FLOW_BSIDE_BROWSER_ORIGIN": args.origin, "A2FLOW_BSIDE_BROWSER_ORIGINS": args.origin, "A2FLOW_BSIDE_SESSION_SECONDS": "7200", "A2FLOW_BSIDE_RUNTIME_URL": "http://127.0.0.1:8782", "A2FLOW_EMPLOYEE_STATIC_DIRECTORY": "/opt/a2flow/static/employee"}
    configs = {"bside": bside, "runtime": {**base, **rpc, "A2FLOW_LISTEN_PORT": "8782"}, "accounts": {**base, **auth, "A2FLOW_LISTEN_PORT": "8780", "A2FLOW_MANAGEMENT_PASSWORD_PEPPER_FILE": "/run/selfhost/pepper", "A2FLOW_MANAGEMENT_BROWSER_ORIGINS": args.origin}}
    def tls(prefix: str) -> dict[str, str]:
        return {prefix + "_RPC_MODE": "MTLS", prefix + "_CERT_FILE": "/run/selfhost/server.pem", prefix + "_KEY_FILE": "/run/selfhost/server-key.pem", prefix + "_CLIENT_CA_FILE": "/run/selfhost/ca.pem"}
    targets = {"content": {"PRT": {"host": "127.0.0.1", "port": 8795, "trustCertFile": "/run/selfhost/ca.pem", "clientCertFile": "/run/selfhost/client.pem", "clientKeyFile": "/run/selfhost/client-key.pem"}}}
    write(target / "execution" / "targets.json", targets)
    write(target / "execution" / "management.dsn", dsn("management", "reader"))
    write(target / "execution" / "assets.dsn", dsn("prt", "reader"))
    write(target / "content" / "content.dsn", dsn("content"))
    configs["execution"] = {**tls("A2FLOW_CAPABILITY"), "A2FLOW_CAPABILITY_BIND": "127.0.0.1:8794", "A2FLOW_CAPABILITY_DSN_FILE": "/run/selfhost/management.dsn", "A2FLOW_CAPABILITY_DATABASE": names["management"], "A2FLOW_CAPABILITY_ENVIRONMENT": "PRT", "A2FLOW_CAPABILITY_TARGETS_FILE": "/run/selfhost/targets.json", "A2FLOW_RUNTIME_ASSET_DSN_FILE": "/run/selfhost/assets.dsn", "A2FLOW_RUNTIME_ASSET_DATABASE": names["prt"], "A2FLOW_RUNTIME_ASSET_NAMESPACE": "a2flow-selfhost"}
    configs["content"] = {**tls("A2FLOW_CONTENT"), "A2FLOW_CONTENT_BIND": "127.0.0.1:8795", "A2FLOW_CONTENT_DSN_FILE": "/run/selfhost/content.dsn", "A2FLOW_CONTENT_DATABASE": names["content"], "A2FLOW_CONTENT_ENVIRONMENT": "PRT"}
    write(target / "management-agent" / "agent.dsn", dsn("prt"))
    write(target / "management-agent" / "model_key", key, 0o400)
    configs["management-agent"] = {**rpc, "A2FLOW_ENGINE_RPC_TARGET": "127.0.0.1:8793", "A2FLOW_MANAGEMENT_AGENT_POSTGRES_DSN_FILE": "/run/selfhost/agent.dsn", "A2FLOW_MANAGEMENT_AGENT_BIND": "127.0.0.1:50055"}
    configs["scheduler"] = {"A2FLOW_SCHEDULER_DATABASE_URL": dsn("prt"), "A2FLOW_SCHEDULER_REDIS_URL": "redis://127.0.0.1:6379/0", "A2FLOW_SCHEDULER_STREAM_NAMESPACE": args.prefix, "A2FLOW_SCHEDULER_BSIDE_URL": "http://127.0.0.1:8785", "A2FLOW_SCHEDULER_INTERNAL_TOKEN": token}
    for service, environment in configs.items():
        write(target / service / "config.json", {"environment": environment})
    suffix = "?socketFactory=org.newsclub.net.unix.AFUNIXSocketFactory%24FactoryArg&socketFactoryArg=/run/postgresql/.s.PGSQL.5432&sslmode=disable"
    java = {"A2FLOW_AUTH_TRUSTED_PROXIES": "127.0.0.1,::1", "A2FLOW_ENVIRONMENT": "PRT", "A2FLOW_MANAGEMENT_NAMESPACE": "a2flow-management", "A2FLOW_MANAGEMENT_JDBC_URL": "jdbc:postgresql://localhost/" + names["management"] + suffix, "A2FLOW_MANAGEMENT_DB_USER": names["management"], "A2FLOW_MANAGEMENT_DB_PASSWORD": passwords["management"], "A2FLOW_MANAGEMENT_DB_POOL_SIZE": "3", "A2FLOW_ACCOUNT_JDBC_URL": "jdbc:postgresql://localhost/" + names["prt"] + suffix, "A2FLOW_ACCOUNT_DB_USER": names["accounts"], "A2FLOW_ACCOUNT_DB_PASSWORD": passwords["accounts"], "A2FLOW_ACCOUNT_DB_POOL_SIZE": "2", "A2FLOW_MANAGEMENT_CONFIG": "/run/selfhost/management.json", "A2FLOW_MANAGEMENT_PORT": "8790", "A2FLOW_MANAGEMENT_STATIC_DIR": "/opt/management-static", "A2FLOW_MANAGEMENT_BROWSER_ORIGINS": args.origin, "A2FLOW_ACCOUNT_LOGIN_ORIGIN": "http://127.0.0.1:8780", "A2FLOW_RUNTIME_RPC_MODE": "MTLS", "A2FLOW_RUNTIME_RPC_PORT": "8793", "A2FLOW_RUNTIME_RPC_CERT_FILE": "/run/selfhost/server.pem", "A2FLOW_RUNTIME_RPC_KEY_FILE": "/run/selfhost/server-key.pem", "A2FLOW_RUNTIME_RPC_ENGINE_CA_FILE": "/run/selfhost/ca.pem", "A2FLOW_MANAGEMENT_AGENT_TARGET": "127.0.0.1:50055"}
    targets["a2ui-execution"] = {"PRT": {**targets["content"]["PRT"], "port": 8794}}
    java["A2FLOW_CAPABILITY_GRPC_TARGETS_JSON"] = json.dumps(targets, separators=(",", ":"))
    for kind in ("prt", "online"):
        java.update({f"A2FLOW_PUBLICATION_{kind.upper()}_{field}": value for field, value in {"DATABASE": names[kind], "JDBC_URL": "jdbc:postgresql://localhost/" + names[kind] + suffix, "USER": names[kind], "PASSWORD": passwords[kind], "NAMESPACE": "a2flow-selfhost"}.items()})
    if any("'" in value or "\n" in value for value in java.values()):
        raise ValueError("Invalid shell environment value")
    write(target / "management" / "java.env", "".join(f"{name}='{value}'\n" for name, value in java.items()))
    write(target / "management" / "management.json", {"workspaceRoot": "/tmp/skill-projection", "workspaceChangeGuard": {}, "pages": {"HADES_SKILL_FACTORY": {"specialists": [{"id": "101", "name": "通用数字员工", "digitalEmployeeId": "101"}], "businessDomains": [{"value": "general", "label": "通用业务"}], "capabilityDomains": [{"value": "general", "label": "通用能力"}]}}})
    write(target / "bootstrap" / "config.json", {"environment": {}, "installation": installation, "names": names, "passwords": passwords, "admin": {"username": args.admin_user, "hash": password_hash}, "pepper": pepper})
    # PostgreSQL drops to its image UID; this exact file mount is readable there.
    # Its parent remains owner-only; app secret copies remain 0400 and UID-bound.
    write(target / "postgres_password", passwords["bootstrap"], 0o444)
    write(target / "compose.env", f"COMPOSE_PROJECT_NAME={args.prefix}\nA2FLOW_PRIVATE={target}\nA2FLOW_DB_PREFIX={args.prefix}\nA2FLOW_APP_UID={os.getuid()}\nA2FLOW_APP_GID={os.getgid()}\nA2FLOW_HTTP_PORT={args.port}\nA2FLOW_IMAGE_TAG=local")
    print("Private configuration prepared; no database or service was changed.")
    print("Compose env: " + str(target / "compose.env"))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit("Configuration failed: " + type(error).__name__ + ". Preserve any partial directory; do not reuse it.") from None
