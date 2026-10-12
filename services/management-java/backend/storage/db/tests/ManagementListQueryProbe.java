import java.util.List;
import java.util.ArrayList;
import java.lang.reflect.Field;
import org.apache.ibatis.executor.Executor;
import org.apache.ibatis.mapping.MappedStatement;
import org.apache.ibatis.session.RowBounds;
import org.apache.ibatis.session.ResultHandler;
import org.apache.ibatis.plugin.Intercepts;
import org.apache.ibatis.plugin.Signature;
import org.apache.ibatis.plugin.Interceptor;
import org.apache.ibatis.plugin.Invocation;
import dev.a2flow.management.model.CapabilityActionDraft;
import dev.a2flow.management.lifecycle.CapabilityActionClassificationRelationService;
import dev.a2flow.management.storage.db.repository.EntityRelationRepository;
import dev.a2flow.management.storage.db.mapper.EntityRelationMapper;
import dev.a2flow.management.storage.db.mapper.CapabilityActionDraftMapper;
import dev.a2flow.management.storage.db.repository.CapabilityActionDraftRepository;
import java.util.Map;
import org.postgresql.ds.PGSimpleDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.core.io.ClassPathResource;
import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import dev.a2flow.management.storage.db.migration.ExplicitManagementMigration;
import dev.a2flow.management.storage.db.mapper.SkillListMapper;
import dev.a2flow.management.lifecycle.domain.SkillListQuery;
import dev.a2flow.management.lifecycle.domain.SkillListItem;
import dev.a2flow.management.lifecycle.domain.ComponentListQuery;
import dev.a2flow.management.storage.db.mapper.ComponentListMapper;
import dev.a2flow.management.storage.db.mapper.AssetReleaseStateMapper;
import dev.a2flow.management.storage.db.repository.AssetReleaseStateRepository;
import dev.a2flow.management.storage.db.repository.AssetReleaseRecordStore;
import dev.a2flow.management.release.ReleaseAssetType;

/** 本次整改的隔离数据库探针，不连接任何业务数据库。 */
public final class ManagementListQueryProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 2 || !args[0].matches("jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/management_query_test")) {
            throw new IllegalArgumentException("Requires a disposable loopback management_query_test database");
        }
        var source = new PGSimpleDataSource();
        source.setURL(args[0]);
        source.setUser(args[1]);
        try (var connection = source.getConnection()) { ExplicitManagementMigration.apply(connection); }
        var jdbc = new JdbcTemplate(source);
        jdbc.execute("TRUNCATE skill_draft, skill_asset_release_state, entity_relation, "
                + "skill_capability_action_draft, skill_component_registry RESTART IDENTITY");
        jdbc.execute("""
            INSERT INTO skill_draft(id,skill_code,workspace_id,skill_name_cn,skill_name_en,
                skill_description,business_domain,capability_domain,owner,version,status,update_time,create_time)
            SELECT n,'probe-'||n,'probe-'||n,'演示'||n,'demo-'||n,'description',
                'general','read','owner',1,'DRAFT',1000,1000 FROM generate_series(1,125) n;
            INSERT INTO skill_asset_release_state(asset_type,asset_key,revision,state_json)
            SELECT 'SKILL','probe-'||n,1,jsonb_build_object('versions','[]'::jsonb,
                'activeChange',jsonb_build_object('status',CASE WHEN n % 2 = 0 THEN 'ACTIVE' ELSE 'SEALED' END),
                'environments',CASE WHEN n % 5 = 0 THEN '{"ONLINE":{"sourceId":"live"}}'::jsonb
                ELSE '{}'::jsonb END)::text FROM generate_series(1,125) n;
            INSERT INTO entity_relation(namespace,source_entity_type,source_entity_id,source_version,
                relation_type,target_entity_id,target_entity_code,snapshot_json,sort_no)
            VALUES ('SKILL_FACTORY','SKILL','1',1,'SKILL_BELONGS_TO_SPECIALIST','reader','阅读专员','{}',1),
                   ('SKILL_FACTORY','SKILL','1',1,'SKILL_BELONGS_TO_SPECIALIST','second','第二专员','{}',2),
                   ('SKILL_FACTORY','SKILL','1',2,'SKILL_BELONGS_TO_SPECIALIST','stale','旧版本','{}',1),
                   ('OTHER','SKILL','2',1,'SKILL_BELONGS_TO_SPECIALIST','reader','越界','{}',1);
            """);
        var configuration = new MybatisConfiguration();
        configuration.setMapUnderscoreToCamelCase(true);
        configuration.addMapper(SkillListMapper.class);
        configuration.addMapper(ComponentListMapper.class);
        configuration.addMapper(AssetReleaseStateMapper.class);
        configuration.addMapper(EntityRelationMapper.class);
        configuration.addMapper(CapabilityActionDraftMapper.class);
        var counter = new QueryCounter();
        configuration.addInterceptor(counter);
        var builder = new MybatisSqlSessionFactoryBean();
        builder.setDataSource(source);
        builder.setConfiguration(configuration);
        builder.setMapperLocations(new ClassPathResource("storage/db/mapper/SkillListMapper.xml"),
                new ClassPathResource("storage/db/mapper/ComponentListMapper.xml"));
        var session = new SqlSessionTemplate(builder.getObject());
        var mapper = session.getMapper(SkillListMapper.class);
        var all = SkillListQuery.from(Map.of());
        check(mapper.count(all).getTotal() == 125, "超过100条的total");
        check(mapper.count(all).getEditingCount() == 62, "编辑状态计数");
        check(mapper.count(all).getOnlineCount() == 25, "线上状态计数");
        List<SkillListItem> first = mapper.selectPage(all);
        check(first.size() == 20 && first.get(0).getSkillCode().equals("probe-125"), "稳定排序/分页");
        var last = mapper.selectPage(SkillListQuery.from(Map.of("page","7")));
        check(last.size() == 5 && last.get(4).getSkillCode().equals("probe-1"), "100条以后的页");
        var bySpecialist = SkillListQuery.from(Map.of("keyword","阅读专员"));
        check(mapper.count(bySpecialist).getTotal() == 1, "旧记录专员搜索");
        check(mapper.selectPage(bySpecialist).get(0).getSpecialistId().equals("reader,second"), "多关系不放大行");
        check(mapper.count(SkillListQuery.from(Map.of("specialistId","reader"))).getTotal() == 1, "专员过滤");
        check(mapper.count(SkillListQuery.from(Map.of("specialistId","stale"))).getTotal() == 0, "版本隔离");
        check(mapper.count(SkillListQuery.from(Map.of("keyword","%"))).getTotal() == 0, "关键词非通配符");
        var online = mapper.count(SkillListQuery.from(Map.of("status","ONLINE")));
        check(online.getTotal() == 25 && online.getEditingCount() == 62, "状态筛选不污染状态计数");
        jdbc.execute("UPDATE skill_draft SET workspace_id='_internal' WHERE id=125");
        check(mapper.count(all).getTotal() == 124, "隐藏非法身份");
        jdbc.execute("DELETE FROM skill_asset_release_state WHERE asset_key='probe-1'");
        check(mapper.count(all).getInvalidStateCount() == 1, "缺失发布状态不静默伪造");
        check(mapper.selectPage(SkillListQuery.from(Map.of("page","9999"))).isEmpty(), "越界页");
        try { SkillListQuery.from(Map.of("pageSize","101")); throw new AssertionError("页大小上限"); }
        catch (IllegalArgumentException expected) { }
        verifyCapabilityBatch(jdbc, session, counter);
        verifyCapabilitySearch(jdbc, session);
        verifyComponentPage(jdbc, session);
        verifyReleaseScan(jdbc, session, counter);
        System.out.println("PASS: PostgreSQL/MyBatis 125-row paging, search, counters, relation isolation; 6 relation queries for 125 capabilities");
    }
    private static void verifyReleaseScan(JdbcTemplate jdbc, SqlSessionTemplate session,
            QueryCounter counter) throws Exception {
        jdbc.execute("""
            INSERT INTO skill_asset_release_state(asset_type,asset_key,revision,state_json)
            SELECT 'COMPONENT','scan-'||lpad(n::text,3,'0'),1,
                jsonb_build_object('assetType','COMPONENT','assetKey','scan-'||lpad(n::text,3,'0'),
                'builds','[]'::jsonb,'versions','[]'::jsonb,'deployments','[]'::jsonb)::text
            FROM generate_series(1,225) n;
            """);
        var repository = new AssetReleaseStateRepository();
        inject(repository, "assetReleaseStateMapper", session.getMapper(AssetReleaseStateMapper.class));
        inject(repository, "recordStore", new AssetReleaseRecordStore());
        counter.maxRows = 0;
        int previous = counter.count;
        List<String> keys = new ArrayList<>();
        repository.scanByAssetType(ReleaseAssetType.COMPONENT, state -> keys.add(state.getAssetKey()));
        check(keys.size() == 225 && new java.util.HashSet<>(keys).size() == 225, "发布扫描完整无重复");
        check(counter.count - previous == 3 && counter.maxRows == 100, "没有插件也必须实际分三页");
        System.out.println("PASS: release scan 225 rows, 3 SQL queries, max 100 rows per query");
    }
    private static void verifyComponentPage(JdbcTemplate jdbc, SqlSessionTemplate session) {
        jdbc.execute("""
            INSERT INTO skill_component_registry(id,asset_type,component_name,component_name_cn,
                dsl_type,protocol_version,owner,scene,enabled,update_time,official_demo_json,runtime_config_json)
            SELECT n,'A2UI_ATOM','probe-'||n,'组件'||n,'A2UI',1,'owner','scene',n%2,1000,
                repeat('x',10000),repeat('y',10000) FROM generate_series(1,125) n;
            INSERT INTO skill_component_registry(id,asset_type,component_name,dsl_type,enabled,update_time)
            VALUES (126,'CARD_COMPONENT','other','CARD_CONTAINER',1,2000);
            """);
        var mapper = session.getMapper(ComponentListMapper.class);
        var query = ComponentListQuery.from(Map.of("assetType","a2ui_atom"), false);
        check(mapper.count(query) == 125, "组件类型筛选与总数");
        var first = mapper.selectPage(query);
        check(first.size() == 20 && first.get(0).getId() == 125L, "组件真实分页与稳定排序");
        check(first.get(0).isEnabled() && !first.get(1).isEnabled(), "组件布尔映射");
        var last = mapper.selectPage(ComponentListQuery.from(Map.of("assetType","A2UI_ATOM","page","7"), false));
        check(last.size() == 5 && last.get(4).getId() == 1L, "组件超过100条不丢失");
        check(mapper.count(ComponentListQuery.from(Map.of("assetType","A2UI_ATOM"), true)) == 63,
                "组件启用筛选在分页前");
        var search = ComponentListQuery.from(Map.of("keyword","组件1", "pageSize","5"), false);
        check(mapper.count(search) == 37 && mapper.selectPage(search).size() == 5, "组件中文搜索再分页");
        check(mapper.count(ComponentListQuery.from(Map.of("dslType","card_container"), false)) == 1,
                "组件协议筛选规范化");
        check(mapper.count(ComponentListQuery.from(Map.of("keyword","%' OR 1=1 --"), false)) == 0,
                "组件关键词参数化");
        check(mapper.count(ComponentListQuery.from(Map.of("keyword","%"), false)) == 126,
                "组件保留原LIKE语义");
        check(mapper.selectPage(ComponentListQuery.from(Map.of("page","99"), false)).isEmpty(), "组件越界页");
        for (String invalid : List.of("0", "-1", "101", "x")) {
            try {
                ComponentListQuery.from(Map.of("pageSize", invalid), false);
                throw new AssertionError("组件非法pageSize未拒绝");
            } catch (IllegalArgumentException expected) { }
        }
        String serialized = com.alibaba.fastjson2.JSON.toJSONString(first);
        check(!serialized.contains("officialDemo") && !serialized.contains("runtimeConfig"), "摘要不泄漏大字段");
        System.out.println("PASS: component 125-row paging, filters, bounded page size, lean payload");
    }
    private static void verifyCapabilityBatch(JdbcTemplate jdbc, SqlSessionTemplate session,
            QueryCounter counter) throws Exception {
        jdbc.execute("""
            INSERT INTO entity_relation(namespace,source_entity_type,source_entity_id,source_version,
                relation_type,target_entity_id,target_entity_code,snapshot_json,sort_no)
            VALUES
              ('SKILL_FACTORY','CAPABILITY_ACTION','cap-1',1,'CAPABILITY_ACTION_BELONGS_TO_SPECIALIST',
                'a','a','{"specialistName":"甲"}',1),
              ('SKILL_FACTORY','CAPABILITY_ACTION','cap-1',1,'CAPABILITY_ACTION_BELONGS_TO_SPECIALIST',
                'b','b','{"specialistName":"乙"}',2),
              ('SKILL_FACTORY','CAPABILITY_ACTION','cap-1',2,'CAPABILITY_ACTION_BELONGS_TO_SPECIALIST',
                'stale','stale','{"specialistName":"旧版本"}',1),
              ('OTHER','CAPABILITY_ACTION','cap-1',1,'CAPABILITY_ACTION_BELONGS_TO_SPECIALIST',
                'other','other','{"specialistName":"越界"}',1);
            """);
        var repository = new EntityRelationRepository();
        inject(repository, "entityRelationMapper", session.getMapper(EntityRelationMapper.class));
        var service = new CapabilityActionClassificationRelationService();
        inject(service, "entityRelationRepository", repository);
        List<CapabilityActionDraft> drafts = new ArrayList<>();
        for (int index = 1; index <= 125; index++) {
            drafts.add(new CapabilityActionDraft().setDraftId("cap-" + index).setRevision(1));
        }
        counter.count = 0;
        service.projectAll(drafts);
        check(counter.count == 6, "批次查询应为3 * ceil(125/100)，不能逐条查询");
        check(drafts.get(0).getSpecialistId().equals("a,b"), "批量关系顺序及隔离");
        check(drafts.get(1).getSpecialistId().isEmpty(), "无关系不伪造分类");
        for (CapabilityActionDraft draft : drafts) {
            service.matches(draft, "", "", "a");
        }
        check(counter.count == 6, "空分类筛选不能再次访问DB");
        check(service.project(new CapabilityActionDraft().setDraftId("cap-1").setRevision(1))
                .getSpecialistName().equals(drafts.get(0).getSpecialistName()), "单条与批量口径一致");
        counter.count = 0;
        service.projectAll(List.of());
        check(counter.count == 0, "空列表不访问DB");
    }

    private static void inject(Object target, String fieldName, Object value) throws Exception {
        Field field = target.getClass().getDeclaredField(fieldName);
        field.setAccessible(true);
        field.set(target, value);
    }

    private static void verifyCapabilitySearch(JdbcTemplate jdbc, SqlSessionTemplate session) throws Exception {
        jdbc.execute("""
            INSERT INTO skill_capability_action_draft(draft_id,action_code,name_cn,revision,
                draft_json,validation_json,update_time,deleted)
            VALUES ('draft-one','Read.One','阅读',1,'{}','{}',1000,0),
                   ('draft-two','Read.Two','查询 100%_字面值',1,'{}','{}',1000,0),
                   ('draft-deleted','Read.Deleted','已删除',1,'{}','{}',1000,1);
            """);
        var repository = new CapabilityActionDraftRepository();
        inject(repository, "capabilityActionDraftMapper", session.getMapper(CapabilityActionDraftMapper.class));
        check(repository.list("read.").size() == 2, "SQL大小写搜索与删除过滤");
        check(repository.list("阅读").get(0).getDraftId().equals("draft-one"), "中文搜索");
        check(repository.list("%_").size() == 1, "百分号下划线按字面量匹配");
        check(repository.list("' OR TRUE --").isEmpty(), "参数绑定不能注入SQL");
        check(repository.list("").get(0).getDraftId().equals("draft-two"), "同更新时间稳定排序");
    }

    @Intercepts(@Signature(type = Executor.class, method = "query",
            args = {MappedStatement.class, Object.class, RowBounds.class, ResultHandler.class}))
    public static final class QueryCounter implements Interceptor {
        int count;
        int maxRows;
        @Override
        public Object intercept(Invocation invocation) throws Throwable {
            count++;
            Object result = invocation.proceed();
            if (result instanceof List<?> rows) maxRows = Math.max(maxRows, rows.size());
            return result;
        }
    }

    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
}
