package dev.a2flow.management.storage.db;

import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.Objects;
import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean;
import dev.a2flow.management.storage.db.entity.WorkflowDefinitionDO;
import dev.a2flow.management.storage.db.mapper.WorkflowDefinitionMapper;
import dev.a2flow.management.storage.db.migration.ExplicitManagementMigration;
import org.apache.ibatis.session.SqlSessionFactory;
import org.mybatis.spring.SqlSessionTemplate;
import org.postgresql.ds.PGSimpleDataSource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 独立临时 PostgreSQL：生产 DDL 与真实 MyBatis SQL，不使用模拟数据库。 */
public final class ManagementSchemaMigrationJdbcTest {
    private static final String[] ENTITIES = {"AgentObservationEvent", "AssetReleaseState", "CapabilityActionDraft",
            "EntityRelation", "SkillAssetPrincipal", "SkillFactoryAuthoringEvent", "SkillFactoryAuthoringSession",
            "SkillFactoryAuthoringTurn", "SkillFactoryComponentAsset", "SkillFactoryWorkspace", "WorkflowDefinition"};

    public static void main(String[] args) throws Exception {
        if (args.length != 2 || !args[0].matches("jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/management_schema_test")) {
            throw new IllegalArgumentException("只允许独立本机 management_schema_test 数据库");
        }
        PGSimpleDataSource source = new PGSimpleDataSource();
        source.setURL(args[0]);
        source.setUser(args[1]);
        JdbcTemplate jdbc = new JdbcTemplate(source);
        // 未登记旧表碰撞必须整体回滚，既有表和行保持原样。
        jdbc.execute("CREATE TABLE skill_draft (marker text)");
        jdbc.update("INSERT INTO skill_draft VALUES ('preserved')");
        try (Connection connection = source.getConnection()) {
            expectSqlFailure(() -> ExplicitManagementMigration.apply(connection));
        }
        check("preserved".equals(jdbc.queryForObject("SELECT marker FROM skill_draft", String.class)), "既有行被改变");
        check(jdbc.queryForObject("SELECT to_regclass('a2flow_java_management_schema_history') IS NULL", Boolean.class),
                "失败迁移未回滚历史表");
        jdbc.execute("DROP TABLE skill_draft"); // 仅删除上面本测试创建的单列夹具。
        try (Connection connection = source.getConnection()) {
            System.out.println(ExplicitManagementMigration.apply(connection));
            System.out.println(ExplicitManagementMigration.apply(connection));
        }
        check(jdbc.queryForObject("SELECT count(*) FROM pg_tables WHERE schemaname='public'", Integer.class) == 14,
                "应为 13 张业务表加 1 张迁移历史表");
        check(jdbc.queryForObject("SELECT to_regclass('users') IS NULL AND to_regclass('sessions') IS NULL", Boolean.class),
                "迁移不应创建账号体系");
        MybatisConfiguration configuration = new MybatisConfiguration();
        configuration.setMapUnderscoreToCamelCase(true);
        for (String name : ENTITIES) configuration.addMapper(mapperClass(name));
        MybatisSqlSessionFactoryBean builder = new MybatisSqlSessionFactoryBean();
        builder.setDataSource(source);
        builder.setConfiguration(configuration);
        builder.setMapperLocations(new ClassPathResource("storage/db/mapper/WorkflowDefinitionMapper.xml"));
        SqlSessionFactory factory = builder.getObject();
        SqlSessionTemplate session = new SqlSessionTemplate(factory);
        for (String name : ENTITIES) roundTrip(session, name);
        WorkflowDefinitionMapper workflows = session.getMapper(WorkflowDefinitionMapper.class);
        WorkflowDefinitionDO first = workflow("workflow-a"), second = workflow("workflow-b");
        check(workflows.insertWorkflow(first) == 1 && first.getId() != null, "自定义 insert 主键回填失败");
        workflows.insertWorkflow(second);
        check(workflows.selectByWorkflowCode("workflow-a").getDraftRevision() == 1L, "自定义查询失败");
        var page = workflows.listByCondition("specialist", null, null, 1);
        check(page.size() == 1 && page.get(0).getId().equals(second.getId()), "同时间 keyset 排序失败");
        var next = workflows.listByCondition("specialist", 100L, second.getId(), 1);
        check(next.size() == 1 && next.get(0).getId().equals(first.getId()), "keyset 后页失败");
        check(workflows.listByCondition("other", null, null, 1).isEmpty(), "specialist 过滤失败");
        check(workflows.updateBasicInfo("workflow-a", "changed", "description", "operator", 101L) == 1, "更新基础信息失败");
        check(workflows.compareAndSetDraft("workflow-a", "{}", "digest", 1, "operator", 102L, 1L) == 1, "CAS失败");
        check(workflows.compareAndSetDraft("workflow-a", "{}", "stale", 1, "operator", 103L, 1L) == 0, "过期CAS未被拒绝");
        TransactionTemplate transaction = new TransactionTemplate(new DataSourceTransactionManager(source));
        transaction.executeWithoutResult(status -> {
            workflows.insertWorkflow(workflow("rolled-back"));
            check(jdbc.queryForObject("SELECT count(*) FROM workflow_definition WHERE workflow_code='rolled-back'", Integer.class) == 1,
                    "JDBC 和 MyBatis 未共用连接");
            status.setRollbackOnly();
        });
        check(workflows.selectByWorkflowCode("rolled-back") == null, "事务回滚失败");
        String checksum = jdbc.queryForObject("SELECT checksum FROM a2flow_java_management_schema_history", String.class);
        jdbc.update("UPDATE a2flow_java_management_schema_history SET checksum='tampered'");
        try (Connection connection = source.getConnection()) {
            expectSqlFailure(() -> ExplicitManagementMigration.apply(connection));
        }
        jdbc.update("UPDATE a2flow_java_management_schema_history SET checksum=?", checksum);
        System.out.println("PASS：13表迁移、重复执行、旧表保护、校验和拒绝、11类真实CRUD、Workflow分页/CAS、共享事务回滚");
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    private static void roundTrip(SqlSessionTemplate session, String name) throws Exception {
        Class<?> type = Class.forName("dev.a2flow.management.storage.db.entity." + name + "DO");
        Object entity = type.getConstructor().newInstance();
        for (Field field : type.getDeclaredFields()) {
            if (Modifier.isStatic(field.getModifiers()) || field.getName().equals("id")) continue;
            field.setAccessible(true);
            if (field.getType() == String.class) field.set(entity, "sample-" + field.getName());
            else if (field.getType() == Long.class) field.set(entity, 100L);
            else if (field.getType() == Integer.class) field.set(entity, field.getName().equals("deleted") ? 0 : 1);
            else throw new AssertionError("未覆盖字段类型: " + field);
        }
        BaseMapper mapper = (BaseMapper) session.getMapper(mapperClass(name));
        check(mapper.insert(entity) == 1, name + " insert");
        Field id = type.getDeclaredField("id"); id.setAccessible(true);
        Long key = (Long) id.get(entity);
        check(key != null, name + " generated id");
        Object loaded = mapper.selectById(key);
        for (Field field : type.getDeclaredFields()) {
            if (Modifier.isStatic(field.getModifiers())) continue;
            field.setAccessible(true);
            check(Objects.equals(field.get(entity), field.get(loaded)), name + "字段往返失败:" + field.getName());
        }
        check(mapper.updateById(entity) == 1, name + " update");
        check(mapper.deleteById(key) == 1 && mapper.selectById(key) == null, name + " delete");
    }

    private static Class<?> mapperClass(String name) throws ClassNotFoundException {
        return Class.forName("dev.a2flow.management.storage.db.mapper." + name + "Mapper");
    }
    private static WorkflowDefinitionDO workflow(String code) {
        return new WorkflowDefinitionDO().setWorkflowCode(code).setSpecialistCode("specialist")
                .setDraftRevision(1L).setDraftContractVersion(1).setDeleted(0).setUpdateTime(100L).setCreateTime(100L);
    }
    private static void check(boolean condition, String message) { if (!condition) throw new AssertionError(message); }
    private static void expectSqlFailure(SqlAction action) throws Exception {
        try { action.run(); } catch (SQLException expected) { return; }
        throw new AssertionError("应该拒绝迁移");
    }
    @FunctionalInterface private interface SqlAction { void run() throws Exception; }
}
