package dev.a2flow.management.lifecycle;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.lifecycle.domain.SkillDraftMetadata;
import dev.a2flow.management.storage.db.repository.SkillFactoryWorkspaceRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 面向 Adviser Intelligent Lab 的草稿元数据查询服务。
 *
 * <p>该类只负责统一 method 参数的结构校验和 Repository 查询分支选择，返回 Skill code 及中英文名。
 * 它不读取发布状态、环境指针、文件系统或 KConf。</p>
 */
@Service
@Slf4j
public class SkillFactorySkillMetadataService {

    private static final String PARAM_SKILL_CODES = "skillCodes";
    private static final String QUERY_MODE_ALL = "all";
    private static final String QUERY_MODE_CODES = "codes";
    private static final int SKILL_METADATA_BATCH_LIMIT = 200;

    @Resource
    private SkillFactoryWorkspaceRepository workspaceRepository;

    /**
     * 查询当前非删除且工作区身份有效的草稿元数据；未传 skillCodes 时查询全部可见草稿。
     */
    public List<SkillDraftMetadata> query(Map<String, String> params) {
        String skillCodesJson = params == null ? null : params.get(PARAM_SKILL_CODES);
        if (StringUtils.isBlank(skillCodesJson)) {
            List<SkillDraftMetadata> result = workspaceRepository.listDraftMetadata();
            log.info("SkillFactory查询Skill轻量元数据完成, queryMode:{}, count:{}", QUERY_MODE_ALL, result.size());
            return result;
        }
        List<String> skillCodes = parseSkillCodes(skillCodesJson);
        List<SkillDraftMetadata> result = workspaceRepository.findDraftMetadataBySkillCodes(skillCodes);
        log.info("SkillFactory批量查询Skill轻量元数据完成, queryMode:{}, requestedCount:{}, resultCount:{}",
                QUERY_MODE_CODES, skillCodes.size(), result.size());
        return result;
    }

    private List<String> parseSkillCodes(String skillCodesJson) {
        Object parsed = JsonSupport.fromJSON(skillCodesJson, Object.class);
        if (!(parsed instanceof List<?>)) {
            throw new IllegalArgumentException("skillCodes must be a JSON array");
        }
        List<?> values = (List<?>) parsed;
        if (values.size() > SKILL_METADATA_BATCH_LIMIT) {
            throw new IllegalArgumentException("skillCodes batch size exceeds limit");
        }
        List<String> result = new ArrayList<>();
        for (Object value : values) {
            if (!(value instanceof String) || StringUtils.isBlank((String) value)) {
                throw new IllegalArgumentException("skillCodes must contain non-blank strings");
            }
            String skillCode = StringUtils.trim((String) value);
            if (!result.contains(skillCode)) {
                result.add(skillCode);
            }
        }
        return result;
    }
}
