package dev.a2flow.management.storage.db.repository;

import java.util.List;
import java.util.Map;

import javax.sql.DataSource;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

import dev.a2flow.management.lifecycle.ManagementListPage;
import dev.a2flow.management.lifecycle.domain.ManagementPageQuery;

/** Application summary page. Only the selected page reads canonical source JSON for digest comparison. */
@Repository
public class ApplicationListRepository {
    private final NamedParameterJdbcTemplate jdbc;

    public ApplicationListRepository(DataSource dataSource) {
        this.jdbc = new NamedParameterJdbcTemplate(dataSource);
    }

    public ManagementListPage<Row> list(Map<String, String> filters, ManagementPageQuery page) {
        MapSqlParameterSource args = new MapSqlParameterSource();
        StringBuilder where = new StringBuilder(" WHERE a.asset_type = 'A2UI_APPLICATION'");
        String keyword = text(filters, "keyword");
        if (!keyword.isEmpty()) {
            where.append(" AND (a.component_name LIKE '%' || :keyword || '%'"
                    + " OR a.component_name_cn LIKE '%' || :keyword || '%'"
                    + " OR a.agent_ui_dsl LIKE '%' || :keyword || '%'"
                    + " OR a.owner LIKE '%' || :keyword || '%' OR a.scene LIKE '%' || :keyword || '%')");
            args.addValue("keyword", keyword);
        }
        String status = text(filters, "status");
        if (!status.isEmpty() && !status.equals("ALL")) {
            if (!List.of("DRAFT", "VALIDATED", "PRT", "ONLINE").contains(status)) {
                throw new IllegalArgumentException("invalid application status: " + status);
            }
            String online = "(s.state_json::jsonb #> '{environments,ONLINE}') IS NOT NULL";
            String prt = "(s.state_json::jsonb #> '{environments,PRT}') IS NOT NULL";
            switch (status) {
                case "ONLINE" -> where.append(" AND ").append(online);
                case "PRT" -> where.append(" AND NOT coalesce(").append(online)
                        .append(", false) AND ").append(prt);
                case "DRAFT" -> where.append(" AND NOT coalesce(").append(online)
                        .append(", false) AND NOT coalesce(").append(prt).append(", false)");
                default -> where.append(" AND false"); // VALIDATED is not a published list state.
            }
        }
        String from = " FROM skill_component_registry a LEFT JOIN skill_asset_release_state s"
                + " ON s.asset_type = 'A2UI_APPLICATION' AND s.asset_key = a.component_name"
                + " AND s.deleted = 0";
        long total = jdbc.queryForObject("SELECT count(*)" + from + where, args, Long.class);
        if (total == 0) return new ManagementListPage<>(List.of(), 0, page.page(), page.pageSize());
        args.addValue("limit", page.pageSize()).addValue("offset", page.offset());
        List<Row> rows = jdbc.query("SELECT a.id,a.component_name,a.component_name_cn,"
                        + "a.runtime_config_json,a.create_time,a.update_time" + from + where
                        + " ORDER BY a.update_time DESC,a.id DESC LIMIT :limit OFFSET :offset",
                args, (rs, index) -> new Row(rs.getLong("id"), rs.getString("component_name"),
                        rs.getString("component_name_cn"), rs.getString("runtime_config_json"),
                        rs.getLong("create_time"), rs.getLong("update_time")));
        return new ManagementListPage<>(rows, total, page.page(), page.pageSize());
    }

    private String text(Map<String, String> filters, String key) {
        return filters == null || filters.get(key) == null ? "" : filters.get(key).trim();
    }

    public record Row(long id, String appCode, String nameCn, String sourceJson,
            long createTime, long updateTime) { }
}
