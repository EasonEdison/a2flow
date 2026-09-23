package dev.a2flow.management.storage.db.migration;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.postgresql.ds.PGSimpleDataSource;
import dev.a2flow.management.storage.db.repository.PostgresSkillWorkspaceStore;

/** 显式运维入口；不是 Spring Bean，不在服务启动时执行。仅支持新独立实例 V001。 */
public final class ExplicitManagementMigration {
    public static final String RESOURCE = "storage/db/migration/V001__management_baseline.sql";
    private static final String HISTORY = "public.a2flow_java_management_schema_history";

    private ExplicitManagementMigration() { }

    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !"--apply-new-instance".equals(args[0])) {
            throw new IllegalArgumentException("必须显式传入 --apply-new-instance；不会自动迁移旧数据");
        }
        String url = required("A2FLOW_MANAGEMENT_JDBC_URL");
        if (!url.startsWith("jdbc:postgresql:")) {
            throw new IllegalArgumentException("仅支持 PostgreSQL JDBC 地址");
        }
        PGSimpleDataSource source = new PGSimpleDataSource();
        source.setURL(url);
        source.setUser(required("A2FLOW_MANAGEMENT_DB_USER"));
        source.setPassword(required("A2FLOW_MANAGEMENT_DB_PASSWORD"));
        try (Connection connection = source.getConnection()) {
            System.out.println(apply(connection));
        }
    }

    /** 独立迁移事务：失败整体回滚，已有未登记管理表一律拒绝接管。 */
    public static String apply(Connection connection) throws SQLException, IOException {
        if (!connection.getAutoCommit()) {
            throw new IllegalArgumentException("迁移要求独立自动提交连接，不能加入业务事务");
        }
        String sql = readSql();
        String checksum = PostgresSkillWorkspaceStore.sha256(sql.getBytes(StandardCharsets.UTF_8));
        List<String> tables = managedTables(sql);
        connection.setAutoCommit(false);
        try (Statement statement = connection.createStatement()) {
            statement.execute("SET LOCAL search_path = public");
            statement.execute("SELECT pg_advisory_xact_lock(72630499202101)");
            statement.execute("CREATE TABLE IF NOT EXISTS " + HISTORY + " ("
                    + "version INTEGER PRIMARY KEY, description TEXT NOT NULL, checksum TEXT NOT NULL, "
                    + "installed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)");
            try (ResultSet rows = statement.executeQuery("SELECT version, checksum FROM " + HISTORY)) {
                if (rows.next()) {
                    if (rows.getInt(1) != 1 || !checksum.equals(rows.getString(2)) || rows.next()) {
                        throw new SQLException("迁移历史版本或校验和不匹配；拒绝修改数据库");
                    }
                    for (String table : tables) {
                        if (!exists(connection, table)) {
                            throw new SQLException("已登记迁移缺少表：" + table);
                        }
                    }
                    connection.commit();
                    return "V001 已存在且校验一致，未重建表";
                }
            }
            for (String table : tables) {
                if (exists(connection, table)) {
                    throw new SQLException("检测到未登记的管理表，拒绝接管或覆盖：" + table);
                }
            }
            statement.execute(sql);
            try (PreparedStatement insert = connection.prepareStatement("INSERT INTO " + HISTORY
                    + " (version, description, checksum) VALUES (1, ?, ?)")) {
                insert.setString(1, "管理端新独立实例：11元数据表与2共享资产表");
                insert.setString(2, checksum);
                insert.executeUpdate();
            }
            connection.commit();
            return "V001 迁移完成并登记校验和；未创建或修改 users/sessions";
        } catch (SQLException | RuntimeException failure) {
            try {
                connection.rollback();
            } catch (SQLException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
            throw failure;
        } finally {
            connection.setAutoCommit(true);
        }
    }

    private static boolean exists(Connection connection, String table) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement("SELECT to_regclass(?) IS NOT NULL")) {
            statement.setString(1, "public." + table);
            try (ResultSet rows = statement.executeQuery()) {
                rows.next();
                return rows.getBoolean(1);
            }
        }
    }

    private static List<String> managedTables(String sql) {
        List<String> tables = new ArrayList<>();
        Matcher matcher = Pattern.compile("(?m)^CREATE TABLE ([a-z0-9_]+) ").matcher(sql);
        while (matcher.find()) {
            tables.add(matcher.group(1));
        }
        if (tables.size() != 13) {
            throw new IllegalStateException("V001 迁移资源表清单异常");
        }
        return tables;
    }

    private static String readSql() throws IOException {
        try (InputStream stream = ExplicitManagementMigration.class.getClassLoader().getResourceAsStream(RESOURCE)) {
            if (stream == null) {
                throw new IOException("缺少迁移资源：" + RESOURCE);
            }
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("缺少显式配置：" + key);
        }
        return value;
    }
}
