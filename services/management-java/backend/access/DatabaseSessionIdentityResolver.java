package dev.a2flow.management.access;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

/** 复用 M/B 账号登录写入的 users/sessions，不创建账号，不签发另一套登录凭据。 */
@Component
public class DatabaseSessionIdentityResolver {
    private final JdbcTemplate jdbc;

    @Autowired
    public DatabaseSessionIdentityResolver(AccountSessionDataSource accounts) {
        this(accounts.dataSource());
    }

    public DatabaseSessionIdentityResolver(DataSource dataSource) {
        this.jdbc = new JdbcTemplate(dataSource);
    }

    public Principal resolve(String token) {
        if (token == null || !token.matches("[A-Za-z0-9_-]{43}")) {
            throw new SecurityException("ACCOUNT_AUTHENTICATION_REQUIRED");
        }
        String digest;
        try {
            digest = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(token.getBytes(StandardCharsets.US_ASCII)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 unavailable", impossible);
        }
        var principals = jdbc.query("""
                SELECT u.user_id, u.role FROM sessions s JOIN users u ON u.user_id = s.user_id
                WHERE s.token_sha256 = ? AND s.expires_at > CURRENT_TIMESTAMP
                """, (row, index) -> new Principal(row.getLong("user_id"), row.getString("role")), digest);
        if (principals.size() != 1 || !principals.get(0).validRole()) {
            throw new SecurityException("ACCOUNT_AUTHENTICATION_REQUIRED");
        }
        return principals.get(0);
    }

    public record Principal(long userId, String role) {
        public boolean validRole() { return "ADMIN".equals(role) || "USER".equals(role); }
        public boolean isAdministrator() { return "ADMIN".equals(role); }
    }
}
