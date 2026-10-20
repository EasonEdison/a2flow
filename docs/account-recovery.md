# Operator account recovery

A2Flow stores password hashes, not recoverable passwords. M and B share the same
account and session tables but use separate browser cookies. There is no Web
password-reset or email-recovery flow in this release. The procedure below is an
explicit operator maintenance action, not a self-service API or a bootstrap mode.

## Preconditions and boundaries

- Identify the installation and the existing administrator's exact `user_id` and
  username through a read-only account query. The recovery transaction must find
  that same existing `ADMIN`; it never creates users or changes roles/identities.
- Restrict the public login/registration endpoints for a maintenance window before
  starting. Prevent concurrent account login while the hash and sessions change.
  Keep PostgreSQL, the gateway namespace and required local mounts available.
- Take a protected, restorable database backup and preserve the current private
  configuration. Password hashes, peppers and database credentials are sensitive;
  do not attach dumps, terminal transcripts or private files to an issue or Git.
- Use the installation's **current** password pepper and the repository's
  `a2flow_bside.auth.hash_password`. Do not regenerate the private directory,
  change the pepper, edit the initial bootstrap hash, or rerun initialization to
  recover a password. Bootstrap intentionally does not overwrite existing hashes.
- Lost private configuration or pepper requires recovery from its protected
  installation backup first. A database hash cannot reconstruct the missing
  password or pepper. This guide does not claim an automatic recovery mechanism
  when that backup is unavailable.

## Self-hosted operator transaction

Use the same reviewed image/source revision as the installation. From its repository
root, open an interactive Python session in a disposable accounts container with
its existing protected mounts. This does not run the accounts launcher or expose a
new HTTP service:

```sh
SELFHOST_ENV="$HOME/.a2flow/selfhost-one/compose.env"
docker compose --env-file "$SELFHOST_ENV" -f deploy/selfhost/compose.yaml \
  run --rm --no-deps --entrypoint python accounts
```

At the Python prompt, paste this complete `exec` block. Credentials are read from
existing mounts; the new password is entered twice without terminal echo. Never
substitute a password in the command line or copy a hash into SQL manually.

```python
exec('''
import getpass
import json
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from a2flow_bside.auth import hash_password

env = json.loads(Path("/run/selfhost/config.json").read_text())["environment"]
user_id = int(input("Existing administrator user_id: "))
username = input("Existing administrator username: ")
password = getpass.getpass("New administrator password: ")
repeat = getpass.getpass("Repeat new password: ")
if password != repeat or not 12 <= len(password) <= 128:
    raise ValueError("Passwords must match and contain 12-128 characters")
pepper = Path(env["A2FLOW_MANAGEMENT_PASSWORD_PEPPER_FILE"]).read_text().strip()
encoded = hash_password(password, pepper=pepper)
with psycopg.connect(
    host="/run/postgresql", dbname=env["A2FLOW_DATABASE_NAME"],
    user=env["A2FLOW_DATABASE_USER"],
    password=Path(env["A2FLOW_POSTGRES_PASSWORD_FILE"]).read_text().strip(),
    row_factory=dict_row, connect_timeout=5,
    options="-c statement_timeout=10000 -c lock_timeout=5000",
) as connection:
    row = connection.execute(
        "SELECT user_id,username,role FROM users WHERE user_id=%s FOR UPDATE",
        (user_id,),
    ).fetchone()
    if row is None or row["username"] != username or row["role"] != "ADMIN":
        raise ValueError("Exact existing administrator was not found; no change committed")
    changed = connection.execute(
        "UPDATE users SET password_hash=%s WHERE user_id=%s RETURNING user_id",
        (encoded, user_id),
    ).fetchall()
    if len(changed) != 1:
        raise ValueError("Expected exactly one administrator; no change committed")
    connection.execute("DELETE FROM sessions WHERE user_id=%s", (user_id,))
del password, repeat, encoded, pepper
print("Updated exactly one administrator and revoked that account's M/B sessions.")
''')
```

Exit Python to remove the disposable container. Resume the account endpoints and
verify both M and B through their normal HTTPS login pages: the old password and
old sessions must fail, the new password must succeed, and the same user identity
and role must remain. Existing workflows, assets and content are not reset.

Admission budgets remain in force after recovery. Respect `Retry-After`; do not
truncate the guard table, disable the guard, or clear all users' sessions to make
an acceptance request pass. If the transaction fails before commit, PostgreSQL
rolls back both changes. If the terminal disconnects around commit, inspect the
saved account/session facts and use a normal login to resolve uncertainty before
attempting another change; do not assume it rolled back.

For other deployment layouts, adapt only the protected connection and pepper-file
paths after inspection. The same single-account transaction and verification
requirements apply. Do not execute against a remembered database or username.

## Reproducible isolated exercise

[`scripts/verify_account_guard.py`](../scripts/verify_account_guard.py) exercises
this transaction using a synthetic account, proving old M/B sessions are revoked,
the old password fails, and the new password works. It also checks shared admission
limits and the trusted-proxy boundary. It is not a production password-reset tool.

Prepare a **new empty local PostgreSQL database** named `a2flow_auth_probe_<suffix>`.
Give its DSN to the script through a regular file owned by the current user with
mode `0600`, outside Git. Use a loopback address or local Unix socket; never use an
installation's account database. The script refuses other names, nonlocal hosts,
symlinks, permissive DSN files and databases with existing application objects.
It creates one random schema and removes only that schema in `finally`; it does
not drop databases, change existing users or call external HTTP/model services.

In a disposable Python 3.11+ environment, install the repository's HTTP dependencies
plus the database/client dependencies used by this probe:

```sh
python -m pip install -r services/b-side-api/requirements-http.txt
python -m pip install 'psycopg[binary]==3.3.6' 'SQLAlchemy==2.0.54' \
  'pydantic==2.13.5' 'croniter==6.0.0' 'httpx==0.28.1'
python scripts/verify_account_guard.py \
  --dsn-file "$HOME/.a2flow/account-probe.dsn" --allow-disposable-database
```

A passing JSON result reports `syntheticPasswordRecovery: "passed"` and
`probeSchemaRemoved: true`. Do not run with Python optimization (`-O`), which would
disable assertion checks; the script rejects it. A killed process can leave its
random schema behind. Inspect the dedicated disposable database before explicitly
cleaning it; the next run refuses a nonempty database instead of deleting it.

This synthetic exercise does not establish production backup restorability,
public-proxy correctness or a disaster-recovery SLA. Those remain separate operator
checks for each installation.
