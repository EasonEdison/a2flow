package dev.a2flow.management.storage.db.repository;

import java.util.List;
import java.util.Map;

import javax.sql.DataSource;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

import dev.a2flow.management.lifecycle.ManagementListPage;
import dev.a2flow.management.lifecycle.domain.ManagementPageQuery;

/** SQL-first management list; relation predicates use the current source revision. */
@Repository
public class CapabilityListRepository {
    private final NamedParameterJdbcTemplate jdbc;

    public CapabilityListRepository(DataSource dataSource) {
        this.jdbc = new NamedParameterJdbcTemplate(dataSource);
    }

    public ManagementListPage<Row> list(Map<String, String> filters, ManagementPageQuery page) {
        StringBuilder where = new StringBuilder(" WHERE d.deleted = 0"
                + " AND (nullif(trim(d.action_code),'') IS NOT NULL"
                + " OR nullif(trim(d.name_cn),'') IS NOT NULL)");
        MapSqlParameterSource args = new MapSqlParameterSource();
        String keyword = text(filters, "keyword");
        if (!keyword.isEmpty()) {
            where.append(" AND (strpos(lower(coalesce(d.draft_id,'')),lower(:keyword)) > 0"
                    + " OR strpos(lower(coalesce(d.action_code,'')),lower(:keyword)) > 0"
                    + " OR strpos(lower(coalesce(d.name_cn,'')),lower(:keyword)) > 0)");
            args.addValue("keyword", keyword);
        }
        relation(where, args, "businessDomain", "CAPABILITY_ACTION_BELONGS_TO_BUSINESS_DOMAIN", true, filters);
        relation(where, args, "capabilityDomain", "CAPABILITY_ACTION_BELONGS_TO_CAPABILITY_DOMAIN", true, filters);
        relation(where, args, "specialistId", "CAPABILITY_ACTION_BELONGS_TO_SPECIALIST", false, filters);
        String status = text(filters, "publishStatus");
        if (!status.isEmpty()) {
            if (!status.equals("ONLINE") && !status.equals("EDITING")) {
                throw new IllegalArgumentException("invalid publishStatus: " + status);
            }
            String online = "(s.state_json::jsonb #> '{environments,ONLINE}') IS NOT NULL";
            if (status.equals("ONLINE")) {
                where.append(" AND ").append(online);
            } else {
                // Same priority as AssetReleasePointerQueryService: ACTIVE or no online and UNPUBLISHED.
                where.append(" AND (s.state_json::jsonb #>> '{activeChange,status}' = 'ACTIVE'"
                        + " OR (NOT coalesce(" + online + ", false)"
                        + " AND (s.state_json::jsonb #> '{environments,PRT}') IS NULL"
                        + " AND nullif(s.state_json::jsonb #>> '{activeChange,status}','') IS NULL"
                        + " AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(coalesce(s.state_json::jsonb->'builds','[]'::jsonb)) b"
                        + " LEFT JOIN skill_asset_release_state record ON record.asset_type = 'RELEASE_RECORD'"
                        + " AND record.asset_key = b->>'recordRef' AND record.deleted = 0"
                        + " WHERE nullif(coalesce(b->>'status',"
                        + " ((record.state_json::jsonb->>'recordJson')::jsonb #>> '{payload,status}')),'') IS NOT NULL)"
                        + " AND jsonb_array_length(coalesce(s.state_json::jsonb->'versions','[]'::jsonb)) = 0))");
            }
        }
        String from = " FROM skill_capability_action_draft d"
                + " LEFT JOIN skill_asset_release_state s ON s.asset_type = 'CAPABILITY_ACTION'"
                + " AND s.asset_key = d.draft_id AND s.deleted = 0";
        long total = jdbc.queryForObject("SELECT count(*)" + from + where, args, Long.class);
        if (total == 0) return new ManagementListPage<>(List.of(), 0, page.page(), page.pageSize());
        args.addValue("limit", page.pageSize()).addValue("offset", page.offset());
        List<Row> rows = jdbc.query("SELECT d.draft_id,d.action_code,d.name_cn,d.source_type,"
                        + "d.side_effect_level,d.revision,d.update_time,"
                        + "d.draft_json::jsonb #>> '{basicInfo,description}' AS description"
                        + from + where + " ORDER BY d.update_time DESC,d.id DESC LIMIT :limit OFFSET :offset",
                args, (rs, index) -> new Row(rs.getString("draft_id"), rs.getString("action_code"),
                        rs.getString("name_cn"), rs.getString("description"), rs.getString("source_type"),
                        rs.getString("side_effect_level"), rs.getInt("revision"), rs.getLong("update_time")));
        return new ManagementListPage<>(rows, total, page.page(), page.pageSize());
    }

    private void relation(StringBuilder where, MapSqlParameterSource args, String key,
            String relationType, boolean lastWins, Map<String, String> filters) {
        String value = text(filters, key);
        if (value.isEmpty()) return;
        args.addValue(key, value).addValue(key + "Type", relationType);
        String predicate = "r.namespace = 'SKILL_FACTORY' AND r.source_entity_type = 'CAPABILITY_ACTION'"
                + " AND r.source_entity_id = d.draft_id AND r.source_version = d.revision"
                + " AND r.relation_type = :" + key + "Type";
        where.append(" AND EXISTS (SELECT 1 FROM entity_relation r WHERE ").append(predicate)
                .append(" AND r.target_entity_id = :").append(key);
        if (lastWins) {
            where.append(" AND r.id = (SELECT latest.id FROM entity_relation latest WHERE ")
                    .append(predicate.replace("r.", "latest."))
                    .append(" ORDER BY latest.sort_no DESC,latest.id DESC LIMIT 1)");
        }
        where.append(')');
    }

    private String text(Map<String, String> filters, String key) {
        return filters == null || filters.get(key) == null ? "" : filters.get(key).trim();
    }

    public record Row(String draftId, String actionCode, String nameCn, String description,
            String sourceType, String sideEffectLevel, int revision, long updateTime) { }
}
