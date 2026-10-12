import java.util.Map;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.jdbc.core.JdbcTemplate;

import dev.a2flow.management.lifecycle.domain.ManagementPageQuery;
import dev.a2flow.management.storage.db.migration.ExplicitManagementMigration;
import dev.a2flow.management.storage.db.repository.ApplicationListRepository;
import dev.a2flow.management.storage.db.repository.CapabilityListRepository;

/** Disposable PostgreSQL contract probe; refuses non-loopback/non-fixture databases. */
public final class ManagementPaginationJdbcProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 2 || !args[0].equals(
                "jdbc:postgresql://127.0.0.1:15489/management_query_test")) {
            throw new IllegalArgumentException("requires isolated management_query_test on loopback 15489");
        }
        try (HikariDataSource source = new HikariDataSource()) {
            source.setJdbcUrl(args[0]);
            source.setUsername(args[1]);
            String password = System.getenv("A2FLOW_QUERY_PROBE_PASSWORD");
            if (password == null || password.isBlank()) {
                throw new IllegalArgumentException("fixture password environment variable is required");
            }
            source.setPassword(password);
            source.setMaximumPoolSize(1);
            source.setMinimumIdle(0);
            try (var connection = source.getConnection()) {
                ExplicitManagementMigration.apply(connection);
            }
            JdbcTemplate jdbc = new JdbcTemplate(source);
            jdbc.execute("TRUNCATE skill_capability_action_draft, skill_component_registry, "
                    + "skill_asset_release_state, entity_relation RESTART IDENTITY");
            jdbc.execute("""
                INSERT INTO skill_capability_action_draft(draft_id,action_code,name_cn,source_type,
                    side_effect_level,revision,draft_json,deleted,update_time)
                SELECT 'cap-'||n,'action-'||n,'能力'||n,'API_CENTER','READ',2,
                    jsonb_build_object('basicInfo',jsonb_build_object('description','摘要'||n))::text,
                    0,1000 FROM generate_series(1,125) n;
                INSERT INTO entity_relation(namespace,source_entity_type,source_entity_id,source_version,
                    relation_type,target_entity_id,sort_no)
                SELECT 'SKILL_FACTORY','CAPABILITY_ACTION','cap-'||n,2,
                    'CAPABILITY_ACTION_BELONGS_TO_SPECIALIST','reader',1 FROM generate_series(1,125) n;
                INSERT INTO entity_relation(namespace,source_entity_type,source_entity_id,source_version,
                    relation_type,target_entity_id,sort_no)
                VALUES ('SKILL_FACTORY','CAPABILITY_ACTION','cap-125',1,
                    'CAPABILITY_ACTION_BELONGS_TO_BUSINESS_DOMAIN','stale',10),
                    ('SKILL_FACTORY','CAPABILITY_ACTION','cap-125',2,
                    'CAPABILITY_ACTION_BELONGS_TO_BUSINESS_DOMAIN','old',1),
                    ('SKILL_FACTORY','CAPABILITY_ACTION','cap-125',2,
                    'CAPABILITY_ACTION_BELONGS_TO_BUSINESS_DOMAIN','current',2);
                INSERT INTO skill_asset_release_state(asset_type,asset_key,revision,state_json,deleted)
                VALUES ('CAPABILITY_ACTION','cap-125',1,
                    '{"activeChange":{"status":"ACTIVE"},"environments":{"ONLINE":{"version":1}},"builds":[],"versions":[]}',0),
                    ('CAPABILITY_ACTION','cap-124',1,
                    '{"environments":{},"builds":[{"status":"SEALED"}],"versions":[]}',0),
                    ('CAPABILITY_ACTION','cap-123',1,
                    '{"environments":{},"builds":[{"recordRef":"fixture-build"}],"versions":[]}',0),
                    ('RELEASE_RECORD','fixture-build',1,
                    jsonb_build_object('recordJson',jsonb_build_object('payload',
                        jsonb_build_object('status','SEALED'))::text)::text,0);
                INSERT INTO skill_component_registry(asset_type,component_name,component_name_cn,
                    runtime_config_json,update_time)
                SELECT 'A2UI_APPLICATION','app-'||n,'应用'||n,
                    jsonb_build_object('appCode','app-'||n,'nameCn','应用'||n)::text,1000
                FROM generate_series(1,125) n;
                INSERT INTO skill_asset_release_state(asset_type,asset_key,revision,state_json,deleted)
                VALUES ('A2UI_APPLICATION','app-125',1,
                    '{"environments":{"ONLINE":{"version":1}},"builds":[],"versions":[]}',0),
                    ('A2UI_APPLICATION','app-124',1,
                    '{"environments":{"PRT":{"version":1}},"builds":[],"versions":[]}',0);
                """);
            CapabilityListRepository capabilities = new CapabilityListRepository(source);
            var first = capabilities.list(Map.of(), new ManagementPageQuery(1, 20));
            check(first.total() == 125 && first.list().size() == 20, "capability total/page");
            check(first.list().get(0).draftId().equals("cap-125"), "stable capability tie order");
            check(capabilities.list(Map.of(), new ManagementPageQuery(7, 20)).list().size() == 5,
                    "capability tail page");
            check(capabilities.list(Map.of("keyword", "cap-1"), new ManagementPageQuery(1, 20)).total() == 37,
                    "keyword before limit");
            check(capabilities.list(Map.of("businessDomain", "current"),
                    new ManagementPageQuery(1, 20)).total() == 1, "last relation wins");
            check(capabilities.list(Map.of("businessDomain", "old"),
                    new ManagementPageQuery(1, 20)).total() == 0, "old relation not selected");
            check(capabilities.list(Map.of("businessDomain", "stale"),
                    new ManagementPageQuery(1, 20)).total() == 0, "stale revision not selected");
            check(capabilities.list(Map.of("specialistId", "reader"),
                    new ManagementPageQuery(1, 20)).total() == 125, "specialist before limit");
            check(capabilities.list(Map.of("publishStatus", "ONLINE"),
                    new ManagementPageQuery(1, 20)).total() == 1, "capability online");
            check(capabilities.list(Map.of("publishStatus", "EDITING"),
                    new ManagementPageQuery(1, 20)).total() == 123,
                    "editing excludes inline and referenced build status");
            check(capabilities.list(Map.of("keyword", "' OR TRUE --"),
                    new ManagementPageQuery(1, 20)).total() == 0, "bound keyword");
            ApplicationListRepository applications = new ApplicationListRepository(source);
            check(applications.list(Map.of(), new ManagementPageQuery(1, 20)).total() == 125,
                    "application total");
            check(applications.list(Map.of(), new ManagementPageQuery(7, 20)).list().size() == 5,
                    "application tail page");
            check(applications.list(Map.of("status", "ONLINE"),
                    new ManagementPageQuery(1, 20)).total() == 1, "application online");
            check(applications.list(Map.of("status", "PRT"),
                    new ManagementPageQuery(1, 20)).total() == 1, "application prt");
            check(applications.list(Map.of("status", "DRAFT"),
                    new ManagementPageQuery(1, 20)).total() == 123, "application draft");
            check(applications.list(Map.of("keyword", "app-1"),
                    new ManagementPageQuery(1, 20)).total() == 37, "application keyword before limit");
            System.out.println("PASS 125 capability + 125 Application SQL paging/filter cases");
        }
    }

    private static void check(boolean condition, String name) {
        if (!condition) throw new AssertionError(name);
    }
}
