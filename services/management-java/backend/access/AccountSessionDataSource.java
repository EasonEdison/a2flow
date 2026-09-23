package dev.a2flow.management.access;

import javax.sql.DataSource;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

/** Account queries may use a separate existing account database; never manages its schema. */
@Component
public final class AccountSessionDataSource implements AutoCloseable {
    private static final String URL = "A2FLOW_ACCOUNT_JDBC_URL";
    private static final String USER = "A2FLOW_ACCOUNT_DB_USER";
    private static final String PASSWORD_PROPERTY = "A2FLOW_ACCOUNT_DB_PASSWORD";
    private static final String POOL_SIZE = "A2FLOW_ACCOUNT_DB_POOL_SIZE";
    private final DataSource dataSource;
    private final HikariDataSource ownedPool;

    public AccountSessionDataSource(DataSource managementDataSource, Environment environment) {
        if (environment.getProperty(URL) == null) {
            if (environment.getProperty(USER) != null || environment.getProperty(PASSWORD_PROPERTY) != null
                    || environment.getProperty(POOL_SIZE) != null) {
                throw new IllegalStateException("Partial account database configuration: " + URL + " is required");
            }
            // Existing isolated tests may intentionally host both schemas in one database.
            dataSource = managementDataSource;
            ownedPool = null;
            return;
        }
        String url = required(environment, URL);
        if (!url.startsWith("jdbc:postgresql:")) {
            throw new IllegalArgumentException(URL + " must use PostgreSQL");
        }
        int size = environment.getProperty(POOL_SIZE, Integer.class, 2);
        if (size < 1 || size > 8) throw new IllegalArgumentException(POOL_SIZE + " must be between 1 and 8");
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(url);
        config.setUsername(required(environment, USER));
        config.setPassword(required(environment, PASSWORD_PROPERTY));
        config.setMaximumPoolSize(size);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(10_000);
        config.setPoolName("a2flow-account-readonly");
        config.setReadOnly(true);
        // PostgreSQL JDBC's readOnly flag alone need not protect auto-commit statements.
        config.setConnectionInitSql("SET default_transaction_read_only = on");
        ownedPool = new HikariDataSource(config);
        dataSource = ownedPool;
    }

    public DataSource dataSource() { return dataSource; }

    @Override public void close() {
        if (ownedPool != null) ownedPool.close();
    }

    private static String required(Environment environment, String key) {
        String value = environment.getProperty(key);
        if (value == null || value.isBlank()) throw new IllegalStateException("Missing required configuration: " + key);
        return value;
    }
}
