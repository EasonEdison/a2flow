package dev.a2flow.management.storage.db;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;
import javax.sql.DataSource;

import dev.a2flow.management.access.AccountSessionDataSource;
import dev.a2flow.management.access.DatabaseSessionIdentityResolver;
import org.postgresql.ds.PGSimpleDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;
import org.springframework.jdbc.core.JdbcTemplate;

/** Two local-only fresh databases: auth queries never touch the management database. */
public final class AccountSessionDataSourceJdbcTest {
    public static void main(String[] args) throws Exception {
        if (args.length != 3 || !localTestUrl(args[0], "account_split_management")
                || !localTestUrl(args[1], "account_split_auth")) {
            throw new IllegalArgumentException("Requires two isolated account_split databases");
        }
        PGSimpleDataSource authAdmin = new PGSimpleDataSource();
        authAdmin.setUrl(args[1]); authAdmin.setUser(args[2]);
        JdbcTemplate auth = new JdbcTemplate(authAdmin);
        auth.execute("CREATE TABLE users (user_id bigint PRIMARY KEY, role text NOT NULL)");
        auth.execute("CREATE TABLE sessions (token_sha256 text PRIMARY KEY, user_id bigint REFERENCES users(user_id), expires_at timestamptz NOT NULL)");
        String token = "a".repeat(43);
        String digest = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                .digest(token.getBytes(StandardCharsets.US_ASCII)));
        auth.update("INSERT INTO users VALUES (?, 'ADMIN')", Long.MAX_VALUE);
        auth.update("INSERT INTO sessions VALUES (?, ?, CURRENT_TIMESTAMP + INTERVAL '1 hour')", digest, Long.MAX_VALUE);
        HikariHolder holder = new HikariHolder();
        try (AnnotationConfigApplicationContext context = new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(new MapPropertySource("test", Map.of(
                    "A2FLOW_MANAGEMENT_JDBC_URL", args[0], "A2FLOW_MANAGEMENT_DB_USER", args[2],
                    "A2FLOW_MANAGEMENT_DB_PASSWORD", "isolated-test-only",
                    "A2FLOW_ACCOUNT_JDBC_URL", args[1], "A2FLOW_ACCOUNT_DB_USER", args[2],
                    "A2FLOW_ACCOUNT_DB_PASSWORD", "isolated-test-only")));
            context.register(ManagementDatabaseConfiguration.class, AccountSessionDataSource.class,
                    DatabaseSessionIdentityResolver.class);
            context.refresh();
            DataSource management = context.getBean(DataSource.class);
            JdbcTemplate main = new JdbcTemplate(management);
            main.execute("CREATE TABLE management_probe (value integer)");
            main.update("INSERT INTO management_probe VALUES (1)");
            if (main.queryForObject("SELECT to_regclass('users') IS NOT NULL", Boolean.class)) {
                throw new AssertionError("Account schema leaked into management database");
            }
            AccountSessionDataSource accounts = context.getBean(AccountSessionDataSource.class);
            holder.pool = (com.zaxxer.hikari.HikariDataSource) accounts.dataSource();
            JdbcTemplate reader = new JdbcTemplate(accounts.dataSource());
            if (args[0].startsWith("jdbc:postgresql://localhost/")) {
                if (!main.queryForObject("SELECT inet_server_addr() IS NULL", Boolean.class)
                        || !reader.queryForObject("SELECT inet_server_addr() IS NULL", Boolean.class)) {
                    throw new AssertionError("Expected Unix sockets for both database connections");
                }
                System.out.println("UNIX_SOCKET_PASS: management and account connections have no TCP server address");
            }
            if (!"on".equals(reader.queryForObject("SHOW default_transaction_read_only", String.class))) {
                throw new AssertionError("Account connection must be server-side read-only");
            }
            try {
                reader.update("UPDATE users SET role='USER'");
                throw new AssertionError("Account pool allowed a write");
            } catch (org.springframework.dao.DataAccessException expected) {
                if (!(expected.getRootCause() instanceof java.sql.SQLException sql)
                        || !"25006".equals(sql.getSQLState())) throw expected;
            }
            DatabaseSessionIdentityResolver resolver = context.getBean(DatabaseSessionIdentityResolver.class);
            if (resolver.resolve(token).userId() != Long.MAX_VALUE || !resolver.resolve(token).isAdministrator()) {
                throw new AssertionError("Account identity changed");
            }
            auth.update("UPDATE users SET role='USER'");
            if (resolver.resolve(token).isAdministrator()) throw new AssertionError("Stale role");
            auth.update("UPDATE users SET role='UNKNOWN'"); expectDenied(() -> resolver.resolve(token));
            auth.update("UPDATE users SET role='ADMIN'");
            auth.update("UPDATE sessions SET expires_at=CURRENT_TIMESTAMP - INTERVAL '1 second'");
            expectDenied(() -> resolver.resolve(token));
            auth.update("DELETE FROM sessions"); expectDenied(() -> resolver.resolve(token));
            expectDenied(() -> resolver.resolve("b".repeat(43)));
            expectDenied(() -> resolver.resolve("invalid"));
            try (AccountSessionDataSource shared = new AccountSessionDataSource(management, new StandardEnvironment())) {
                if (shared.dataSource() != management) throw new AssertionError("Shared mode changed");
            }
            main.update("INSERT INTO management_probe VALUES (2)");
            StandardEnvironment partial = new StandardEnvironment();
            partial.getPropertySources().addFirst(new MapPropertySource("partial", Map.of("A2FLOW_ACCOUNT_DB_USER", args[2])));
            try {
                new AccountSessionDataSource(management, partial);
                throw new AssertionError("Partial auth configuration silently fell back");
            } catch (IllegalStateException expected) {
                if (!expected.getMessage().startsWith("Partial account")) throw expected;
            }
        }
        if (!holder.pool.isClosed()) throw new AssertionError("Owned account pool leaked on shutdown");
        System.out.println("ACCOUNT_SPLIT_PASS: separate DB, Spring injection, readonly writes rejected, signed64, roles, expired/revoked/invalid sessions, shared mode, fail closed, pool shutdown");
    }

    private static void expectDenied(Runnable action) {
        try { action.run(); throw new AssertionError("Session should be rejected"); }
        catch (SecurityException expected) { /* Existing authentication contract. */ }
    }
    private static boolean localTestUrl(String url, String database) {
        return url.matches("jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/" + database)
                || url.matches("jdbc:postgresql://localhost/" + database
                    + "\\?socketFactory=org\\.newsclub\\.net\\.unix\\.AFUNIXSocketFactory%24FactoryArg"
                    + "&socketFactoryArg=[^&]+&sslmode=disable");
    }
    private static final class HikariHolder { private com.zaxxer.hikari.HikariDataSource pool; }
}
