#!/usr/bin/env python3
"""Exercise account protection only in an explicitly empty, local probe database.

Requires --dsn-file (owner-only) and --allow-disposable-database. No model calls,
production users or external HTTP endpoints are used. The database is not dropped;
only this process's newly created random schema is removed after the exercise.
"""
from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import dataclasses
import io
import ipaddress
import json
import logging
import multiprocessing
import os
from pathlib import Path
import re
import stat
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
for source in (ROOT, ROOT / 'services/b-side-api/src', ROOT / 'packages/contracts/src'):
    sys.path.insert(0, str(source))

import httpx
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from a2flow_bside import auth
from a2flow_bside.account_guard import (
    AccountGuardConfig, AccountGuardError, AdmissionPolicy, PostgresAccountGuard,
    client_address,
)
from a2flow_bside.app import create_app
from a2flow_bside.repositories import SessionsRepository, UsersRepository
from deploy.accounts.app import AccountAuthentication, create_app as create_management_app

PEPPER = 'synthetic-probe-pepper-not-for-deployment'
ORIGIN = 'http://127.0.0.1:18439'
HEADERS = {'Origin': ORIGIN, 'X-A2Flow-Client-IP': '198.51.100.20'}
CONFIG = AccountGuardConfig(trusted_proxies=('127.0.0.1',))


class ProbeConfigurationError(ValueError):
    """Safe operator guidance containing no supplied DSN values."""


def connect(dsn: str, schema: str):
    return psycopg.connect(dsn, row_factory=dict_row, connect_timeout=5,
        options=f'-c search_path={schema},pg_catalog -c statement_timeout=10000 -c lock_timeout=5000')


def guard(dsn: str, schema: str, config: AccountGuardConfig = CONFIG) -> PostgresAccountGuard:
    return PostgresAccountGuard(lambda: connect(dsn, schema), pepper=PEPPER,
                                environment='PRT', config=config)


def scope(address: str = '198.51.100.20') -> dict:
    return {'client': ('127.0.0.1', 1234),
            'headers': [(b'x-a2flow-client-ip', address.encode('ascii'))]}


def concurrent_attempt(arguments: tuple[str, str, int]) -> str:
    dsn, schema, index = arguments
    config = dataclasses.replace(CONFIG, login=AdmissionPolicy(60, 7, 100, 100))
    try:
        guard(dsn, schema, config).admit('login', 'probe-' + str(index), scope())
        return 'admitted'
    except AccountGuardError as error:
        return error.code


def reset_attempts(dsn: str, schema: str) -> None:
    with connect(dsn, schema) as connection:
        connection.execute('TRUNCATE account_auth_attempts')


def attempt_count(dsn: str, schema: str) -> int:
    with connect(dsn, schema) as connection:
        return connection.execute('SELECT count(*) AS n FROM account_auth_attempts').fetchone()['n']


def bside_application(dsn: str, schema: str, admission: PostgresAccountGuard):
    connection = lambda: connect(dsn, schema)
    # Only auth routes are called; unrelated product dependencies stay unconfigured.
    return create_app(users=UsersRepository(connection), sessions=SessionsRepository(connection),
        conversations=None, messages=None, schedules=None, notifications=None,
        run_ownership=None, runtime_client=None, chat_runner=None, workflow_catalog=lambda _: [],
        pepper=PEPPER, browser_origin=ORIGIN, environment='PRT', session_seconds=7200,
        account_guard=admission)


def management_application(dsn: str, schema: str, admission: PostgresAccountGuard):
    connection = lambda: connect(dsn, schema)
    return create_management_app(AccountAuthentication(users=UsersRepository(connection),
        sessions=SessionsRepository(connection), pepper=PEPPER, environment='PRT',
        origins=[ORIGIN], account_guard=admission))


def http_client(application):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=application,
        client=('127.0.0.1', 1001)), base_url='http://127.0.0.1')


async def http_exercise(dsn: str, schema: str) -> None:
    config = dataclasses.replace(CONFIG, login=AdmissionPolicy(60, 100, 100, 3))
    async with http_client(bside_application(dsn, schema, guard(dsn, schema, config))) as bclient, \
            http_client(management_application(dsn, schema, guard(dsn, schema, config))) as mclient:
        body = {'username': 'synthetic-admin', 'password': 'synthetic-initial-password'}
        response = await bclient.post('/api/auth/register', json=body, headers=HEADERS)
        assert response.status_code == 200, 'Synthetic registration failed'
        identity = int(response.json()['userId'])
        assert (await bclient.get('/api/auth/session')).status_code == 200
        assert (await bclient.post('/api/auth/logout', headers=HEADERS)).status_code == 200
        assert (await bclient.get('/api/auth/session')).status_code == 401
        assert (await bclient.post('/api/auth/login', json=body, headers=HEADERS)).status_code == 200
        assert (await mclient.post('/login', data=body, headers=HEADERS)).status_code == 303
        reset_attempts(dsn, schema)
        bad_origin = {**HEADERS, 'Origin': 'http://untrusted.invalid'}
        assert (await bclient.post('/api/auth/login', json=body, headers=bad_origin)).status_code == 403
        assert (await mclient.post('/login', data=body, headers=bad_origin)).status_code == 401
        assert attempt_count(dsn, schema) == 0
        wrong = {**body, 'password': 'synthetic-wrong-password'}
        assert (await bclient.post('/api/auth/login', json=wrong, headers=HEADERS)).status_code == 401
        assert (await mclient.post('/login', data=wrong, headers=HEADERS)).status_code == 401
        assert (await bclient.post('/api/auth/login', json=wrong, headers=HEADERS)).status_code == 401
        # Neither host may invoke password verification after admission rejects.
        import deploy.accounts.app as management_module
        original_b, original_m = auth.verify_password, management_module.verify_password
        def unexpected_hash(*args, **kwargs):
            raise AssertionError('Denied attempt invoked password verification')
        auth.verify_password = management_module.verify_password = unexpected_hash
        try:
            for client, path, values in ((bclient, '/api/auth/login', {'json': body}),
                                         (mclient, '/login', {'data': body})):
                response = await client.post(path, headers=HEADERS, **values)
                assert response.status_code == 429 and int(response.headers['Retry-After']) > 0
        finally:
            auth.verify_password, management_module.verify_password = original_b, original_m
        assert attempt_count(dsn, schema) == 3
        reset_attempts(dsn, schema)
        for headers in ({'Origin': ORIGIN}, {**HEADERS, 'X-A2Flow-Client-IP': 'invalid'}):
            assert (await bclient.post('/api/auth/login', json=body, headers=headers)).status_code == 400
            assert (await mclient.post('/login', data=body, headers=headers)).status_code == 400
        assert attempt_count(dsn, schema) == 0

        # Exercise the documented operator transaction on this synthetic account only.
        # This role change provisions the synthetic fixture, not part of password recovery.
        with connect(dsn, schema) as connection:
            connection.execute("UPDATE users SET role='ADMIN' WHERE user_id=%s", (identity,))
        new_password = 'synthetic-recovered-password'
        new_hash = auth.hash_password(new_password, pepper=PEPPER)
        with connect(dsn, schema) as connection:
            row = connection.execute('SELECT user_id,username,role FROM users WHERE user_id=%s FOR UPDATE',
                                     (identity,)).fetchone()
            assert row['username'] == body['username'] and row['role'] == 'ADMIN'
            updated = connection.execute('UPDATE users SET password_hash=%s WHERE user_id=%s RETURNING user_id',
                                         (new_hash, identity)).fetchall()
            assert len(updated) == 1
            connection.execute('DELETE FROM sessions WHERE user_id=%s', (identity,))
        assert (await bclient.get('/api/auth/session')).status_code == 401
        # GET /login redirects authenticated M sessions; revoked sessions show the form.
        assert (await mclient.get('/login')).status_code == 200
        assert (await bclient.post('/api/auth/login', json=body, headers=HEADERS)).status_code == 401
        recovered = {**body, 'password': new_password}
        assert (await bclient.post('/api/auth/login', json=recovered, headers=HEADERS)).status_code == 200
        assert (await mclient.post('/login', data=recovered, headers=HEADERS)).status_code == 303
        assert (await bclient.post('/api/auth/logout', headers=HEADERS)).status_code == 200
        assert (await mclient.post('/logout', headers=HEADERS)).status_code == 303
        reset_attempts(dsn, schema)

    disabled = dataclasses.replace(CONFIG, registration_enabled=False)
    async with http_client(bside_application(dsn, schema, guard(dsn, schema, disabled))) as client:
        response = await client.post('/api/auth/register', json=body, headers=HEADERS)
        assert response.status_code == 403 and response.json()['error']['code'] == 'REGISTRATION_DISABLED'
    limited = guard(dsn, schema, dataclasses.replace(CONFIG, register=AdmissionPolicy(3600, 2, 2, 2)))
    limited.admit('register', 'first', scope()); limited.admit('register', 'second', scope())
    try:
        limited.admit('register', 'third', scope())
        raise AssertionError('Registration quota bypass')
    except AccountGuardError as error:
        assert error.status == 429
    def unavailable():
        raise RuntimeError('SENSITIVE_SENTINEL_NEVER_LOG')
    broken = PostgresAccountGuard(unavailable, pepper=PEPPER, environment='PRT', config=CONFIG)
    capture = io.StringIO(); handler = logging.StreamHandler(capture)
    logger = logging.getLogger('a2flow_bside.account_guard'); logger.addHandler(handler)
    try:
        for application, path, values in (
            (bside_application(dsn, schema, broken), '/api/auth/login', {'json': body}),
            (management_application(dsn, schema, broken), '/login', {'data': body}),
        ):
            async with http_client(application) as client:
                response = await client.post(path, headers=HEADERS, **values)
                assert response.status_code == 503 and len(response.headers['X-Request-ID']) == 32
                assert response.headers['X-Request-ID'] in capture.getvalue()
        assert 'SENSITIVE_SENTINEL' not in capture.getvalue()
    finally:
        logger.removeHandler(handler)


def verify(dsn: str, schema: str) -> None:
    guard(dsn, schema).check_ready()
    with concurrent.futures.ProcessPoolExecutor(max_workers=4,
            mp_context=multiprocessing.get_context('spawn')) as executor:
        outcomes = list(executor.map(concurrent_attempt, [(dsn, schema, i) for i in range(32)]))
    assert outcomes.count('admitted') == 7 and outcomes.count('AUTH_RATE_LIMITED') == 25
    assert attempt_count(dsn, schema) == 7
    reset_attempts(dsn, schema)
    config = dataclasses.replace(CONFIG, login=AdmissionPolicy(60, 100, 100, 2))
    guard(dsn, schema, config).admit('login', 'name', scope('198.51.100.1'))
    guard(dsn, schema, config).admit('login', 'NAME', scope('198.51.100.2'))
    try:
        guard(dsn, schema, config).admit('login', 'name', scope('198.51.100.3'))
        raise AssertionError('Username quota bypass')
    except AccountGuardError as error:
        assert error.status == 429
    with connect(dsn, schema) as connection:
        row = connection.execute('SELECT address_key,username_key FROM account_auth_attempts LIMIT 1').fetchone()
        assert len(row['address_key']) == len(row['username_key']) == 64
        connection.execute("UPDATE account_auth_attempts SET created_at=clock_timestamp()-interval '61 seconds'")
    guard(dsn, schema, config).admit('login', 'name', scope())
    assert attempt_count(dsn, schema) == 1
    reset_attempts(dsn, schema)
    assert client_address({'client': ('198.51.100.4', 1), 'headers': [(b'x-a2flow-client-ip', b'1.1.1.1')]},
                          ('127.0.0.1',)) == '198.51.100.4'
    for headers in ([], [(b'x-a2flow-client-ip', b'invalid')],
                    [(b'x-a2flow-client-ip', b'1.1.1.1, 2.2.2.2')],
                    [(b'x-a2flow-client-ip', b'1.1.1.1')] * 2):
        try:
            client_address({'client': ('127.0.0.1', 1), 'headers': headers}, ('127.0.0.1',))
            raise AssertionError('Malformed trusted proxy header accepted')
        except AccountGuardError as error:
            assert error.status == 400
    asyncio.run(http_exercise(dsn, schema))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsn-file', type=Path, required=True)
    parser.add_argument('--allow-disposable-database', action='store_true', required=True)
    args = parser.parse_args()
    if sys.flags.optimize:
        raise ProbeConfigurationError('Assertions must remain enabled')
    descriptor = os.open(args.dsn_file, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ProbeConfigurationError('DSN file must be a regular owner-only file owned by this user')
        dsn = stream.read(16385).strip()
    if not dsn or len(dsn) > 16384:
        raise ProbeConfigurationError('Invalid DSN file size')
    fields = conninfo_to_dict(dsn)
    database = fields.get('dbname', '')
    host = fields.get('host', '')
    if not re.fullmatch(r'a2flow_auth_probe_[a-z0-9_]{1,32}', database):
        raise ProbeConfigurationError('Only an explicit a2flow_auth_probe_* database is allowed')
    if (not host or 'service' in fields or 'hostaddr' in fields or ',' in host
            or os.environ.get('PGSERVICE') or os.environ.get('PGHOSTADDR')):
        raise ProbeConfigurationError('Explicit local connection without service/hostaddr/multihost is required')
    if not host.startswith('/') and host != 'localhost':
        if not ipaddress.ip_address(host).is_loopback:
            raise ProbeConfigurationError('Only loopback or a local Unix socket is allowed')
    schema = 'auth_probe_' + uuid.uuid4().hex
    created = False
    try:
        with psycopg.connect(dsn, connect_timeout=5) as connection:
            actual = connection.execute('SELECT current_database()').fetchone()[0]
            if actual != database:
                raise ProbeConfigurationError('Connected database differs from explicit probe name')
            exists = connection.execute("SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema' "
                "AND c.relkind IN ('r','p','v','m','f','S') LIMIT 1").fetchone()
            if exists:
                raise ProbeConfigurationError('Probe database must be empty; no existing application objects are permitted')
            connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        created = True
        with connect(dsn, schema) as connection:
            connection.execute((ROOT/'services/b-side-api/src/a2flow_bside/account_guard.sql').read_text())
            # Only account DDL, no business tables or seed data.
            connection.execute("CREATE TABLE users (id bigserial PRIMARY KEY,user_id bigint UNIQUE NOT NULL,"
                "username text UNIQUE NOT NULL,password_hash text NOT NULL,role text NOT NULL DEFAULT 'USER')")
            connection.execute("CREATE TABLE sessions (token_sha256 text PRIMARY KEY,user_id bigint NOT NULL "
                "REFERENCES users(user_id),expires_at timestamptz NOT NULL)")
        verify(dsn, schema)
    finally:
        if created:
            with psycopg.connect(dsn, connect_timeout=5) as connection:
                connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
    print(json.dumps({'result': 'PASS', 'crossProcessAttempts': 32, 'admitted': 7,
        'rateLimited': 25, 'sharedMBQuota': True, 'proxyBoundary': 'passed',
        'registrationAndLogin': 'passed', 'syntheticPasswordRecovery': 'passed',
        'oldSessionsRevoked': True, 'safeFailureCorrelation': 'passed',
        'probeSchemaRemoved': True, 'existingAccountsTouched': False}))


if __name__ == '__main__':
    try:
        main()
    except ProbeConfigurationError as error:
        print('Account guard probe refused: ' + str(error), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as error:
        # Exception detail may include DSN or SQL; never print it or a traceback.
        print('Account guard probe failed: ' + type(error).__name__, file=sys.stderr)
        raise SystemExit(1) from None
