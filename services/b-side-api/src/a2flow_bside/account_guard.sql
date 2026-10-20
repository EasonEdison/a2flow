-- Explicit migration, shared by M and B account admission. Never run at serving startup.
-- No passwords, session tokens, raw usernames or raw client addresses are stored.
CREATE TABLE IF NOT EXISTS account_auth_attempts (
    environment text NOT NULL CHECK (environment IN ('PRT', 'ONLINE')),
    action text NOT NULL CHECK (action IN ('login', 'register')),
    address_key text NOT NULL CHECK (address_key ~ '^[0-9a-f]{64}$'),
    username_key text NOT NULL CHECK (username_key ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS account_auth_attempts_window
    ON account_auth_attempts (environment, action, created_at);
