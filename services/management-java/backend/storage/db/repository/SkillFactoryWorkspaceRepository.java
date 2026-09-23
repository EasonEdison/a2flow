package dev.a2flow.management.storage.db.repository;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Repository;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import dev.a2flow.management.config.SkillFactoryConfigReader;
import dev.a2flow.management.lifecycle.domain.SkillDraft;
import dev.a2flow.management.lifecycle.domain.SkillDraftMetadata;
import dev.a2flow.management.storage.db.entity.SkillFactoryWorkspaceDO;
import dev.a2flow.management.storage.db.mapper.SkillFactoryWorkspaceMapper;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 工作区 Repository。
 *
 * <p>该类负责两类 sellerdata 边界内动作：一是把 workspaceId 转成受控本地路径；
 * 二是通过 Mapper 读写真实 `skill_draft` 元数据。它不承担 adviser 的绑定审批或发布审批，
 * 也不保存 Skill 文件正文。
 */
@Repository
@Slf4j
public class SkillFactoryWorkspaceRepository {

    private static final String DEFAULT_SKILL_CODE = "live-plan-create-skill";
    private static final String DEFAULT_CREATE_SOURCE = "CHAT_CREATE";
    private static final String DEFAULT_DRAFT_STATUS = "DEVELOPING";
    private static final String DEFAULT_OWNER = "system";
    private static final String DEFAULT_VERSION_TEXT = "v1";
    private static final String PATH_SEPARATOR = "/";
    private static final String PATH_PARENT = "..";
    private static final String VERSION_PREFIX = "v";
    private static final String EMPTY = "";
    private static final String SYSTEM_WORKSPACE_DIR_PREFIX = "_";
    private static final String ERROR_WORKSPACE_ID_INVALID = "workspaceId is invalid";
    private static final String ERROR_WORKSPACE_NOT_FOUND = "workspace does not exist";
    private static final String ERROR_LANG_BRIDGE_SKILL_ID_INVALID = "langBridgeSkillId is invalid";
    private static final String ERROR_LANG_BRIDGE_SKILL_ID_CONFLICT = "langBridgeSkillId conflicts with saved value";
    private static final String ERROR_UPDATE_LANG_BRIDGE_SKILL_ID_FAILED = "update langBridgeSkillId failed";
    private static final String ERROR_DRAFT_PAGE_CURSOR_NOT_ADVANCED = "skill draft page cursor did not advance";
    private static final String ERROR_DRAFT_PAGE_LIMIT_INVALID = "skill draft page limit must be positive";
    private static final String ERROR_DRAFT_PAGE_CURSOR_INVALID =
            "skill draft page cursor fields must both be null or non-null";
    private static final String ERROR_DRAFT_PAGE_IDENTITY_INVALID =
            "skill draft page contains invalid stable identity";
    private static final String LIMIT_ONE = "LIMIT 1";
    private static final String LIMIT_PREFIX = "LIMIT ";

    private static final String PARAM_SKILL_CODE = "skillCode";
    private static final String PARAM_SKILL_NAME_CN = "skillNameCn";
    private static final String PARAM_SKILL_NAME_EN = "skillNameEn";
    private static final String PARAM_SKILL_DESCRIPTION = "skillDescription";
    private static final String PARAM_BUSINESS_DOMAIN = "businessDomain";
    private static final String PARAM_CAPABILITY_DOMAIN = "capabilityDomain";
    private static final String PARAM_CREATE_SOURCE = "createSource";
    private static final String PARAM_SOURCE_ZIP_URL = "sourceZipUrl";
    private static final String PARAM_VERSION = "version";
    private static final String PARAM_OWNER = "owner";

    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_SKILL_NAME_CN = "skillNameCn";
    private static final String FIELD_SKILL_NAME_EN = "skillNameEn";
    private static final String FIELD_SKILL_DESCRIPTION = "skillDescription";
    private static final String FIELD_BUSINESS_DOMAIN = "businessDomain";
    private static final String FIELD_CAPABILITY_DOMAIN = "capabilityDomain";
    private static final String FIELD_CREATE_SOURCE = "createSource";
    private static final String FIELD_SOURCE_ZIP_URL = "sourceZipUrl";
    private static final String FIELD_VERSION = "version";
    private static final String FIELD_LANG_BRIDGE_SKILL_ID = "langBridgeSkillId";
    private static final String FIELD_STATUS = "status";
    private static final String FIELD_OWNER = "owner";
    private static final String FIELD_CREATOR = "creator";
    private static final String FIELD_MODIFIER = "modifier";
    private static final String FIELD_EXT_JSON = "extJson";
    private static final String FIELD_ATTRIBUTE = "attribute";

    private static final int DEFAULT_VERSION = 1;
    private static final int NOT_DELETED = 0;
    private static final int DRAFT_LIST_LIMIT = 100;
    private static final int SKILL_METADATA_BATCH_LIMIT = 200;

    private static final long ZERO_ID = 0L;

    @Resource
    private SkillFactoryWorkspaceMapper workspaceMapper;

    @Resource
    private SkillFactoryConfigReader skillFactoryConfigReader;

    /**
     * 返回 SkillFactory 本地工作区根目录。
     */
    public Path workspaceRoot() {
        return skillFactoryConfigReader.getHadesSkillFactoryWorkspaceRoot();
    }

    /**
     * 根据 workspaceId 计算受控本地目录，并阻断路径穿越。
     */
    public Path resolveWorkspace(String workspaceId) {
        if (StringUtils.isBlank(workspaceId) || workspaceId.contains(PATH_SEPARATOR)
                || workspaceId.contains(PATH_PARENT)) {
            log.warn("SkillFactory工作区ID非法, workspaceId:{}", workspaceId);
            throw new IllegalArgumentException(ERROR_WORKSPACE_ID_INVALID);
        }
        Path workspaceRoot = workspaceRoot();
        Path workspace = workspaceRoot.resolve(workspaceId).normalize();
        if (!workspace.startsWith(workspaceRoot)) {
            log.warn("SkillFactory工作区越界, workspaceId:{}, workspacePath:{}", workspaceId, workspace);
            throw new IllegalArgumentException(ERROR_WORKSPACE_ID_INVALID);
        }
        return workspace;
    }

    /**
     * 创建 SkillFactory 工作区基础目录，并返回工作区领域摘要。
     */
    public SkillDraft createWorkspace(String workspaceId, List<?> files) throws IOException {
        Path workspace = resolveWorkspace(workspaceId);
        createDirectories(workspaceId, workspace);
        return workspace(workspaceId, files);
    }

    /**
     * 基于本地 workspace 扫描结果组装工作区领域对象。
     */
    public SkillDraft workspace(String workspaceId, List<?> files) throws IOException {
        Path workspace = resolveWorkspace(workspaceId);
        if (!Files.exists(workspace)) {
            log.warn("SkillFactory工作区不存在，无法组装领域对象, workspaceId:{}, workspacePath:{}",
                    workspaceId, workspace);
            throw new IllegalArgumentException(ERROR_WORKSPACE_NOT_FOUND);
        }
        return new SkillDraft()
                .setWorkspaceId(workspaceId)
                .setWorkspaceRoot(normalize(workspaceRoot()))
                .setWorkspacePath(normalize(workspaceRoot().relativize(workspace)))
                .setFileCount(files.size());
    }

    /**
     * 查询指定 workspaceId 对应的草稿元数据。
     */
    public SkillDraft findDraftByWorkspaceId(String workspaceId) {
        return toDomain(findDraftByWorkspaceIdDb(workspaceId));
    }

    private SkillFactoryWorkspaceDO findDraftByWorkspaceIdDb(String workspaceId) {
        SkillFactoryWorkspaceDO draft = selectDraftByWorkspaceIdDb(workspaceId);
        if (draft == null) {
            log.info("SkillFactory查询工作区草稿元数据DB未命中, workspaceId:{}", workspaceId);
            return null;
        }
        SkillFactoryWorkspaceDO runtimeDraft = fillRuntimeWorkspaceFieldsQuietly(copyDraft(draft));
        if (!isVisibleDraft(runtimeDraft)) {
            log.warn("SkillFactory查询工作区草稿元数据DB命中非法身份，按未命中处理, "
                            + "workspaceId:{}, skillCode:{}",
                    runtimeDraft.getWorkspaceId(), runtimeDraft.getSkillCode());
            return null;
        }
        log.info("SkillFactory查询工作区草稿元数据命中DB, workspaceId:{}, skillCode:{}",
                runtimeDraft.getWorkspaceId(), runtimeDraft.getSkillCode());
        return runtimeDraft;
    }

    /**
     * 按 Skill code 查询最新草稿元数据。
     */
    public SkillDraft findDraftBySkillCode(String skillCode) {
        return toDomain(findDraftBySkillCodeDb(skillCode));
    }

    private SkillFactoryWorkspaceDO findDraftBySkillCodeDb(String skillCode) {
        SkillFactoryWorkspaceDO draft = selectDraftBySkillCodeDb(skillCode);
        if (draft == null) {
            log.info("SkillFactory查询Skill草稿详情DB未命中, skillCode:{}", skillCode);
            return null;
        }
        SkillFactoryWorkspaceDO runtimeDraft = fillRuntimeWorkspaceFieldsQuietly(copyDraft(draft));
        if (!isVisibleDraft(runtimeDraft)) {
            log.warn("SkillFactory查询Skill草稿详情DB命中非法身份，按未命中处理, "
                            + "skillCode:{}, workspaceId:{}",
                    runtimeDraft.getSkillCode(), runtimeDraft.getWorkspaceId());
            return null;
        }
        log.info("SkillFactory查询Skill草稿详情命中DB, skillCode:{}, workspaceId:{}",
                runtimeDraft.getSkillCode(), runtimeDraft.getWorkspaceId());
        return runtimeDraft;
    }

    /**
     * 判断 Skill code 是否已被注册，供注册入口做唯一性校验。
     */
    public boolean draftExistsBySkillCode(String skillCode) {
        if (StringUtils.isBlank(skillCode)) {
            return false;
        }
        return draftExistsBySkillCodeDb(skillCode);
    }

    private boolean draftExistsBySkillCodeDb(String skillCode) {
        LambdaQueryWrapper<SkillFactoryWorkspaceDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillFactoryWorkspaceDO::getDeleted, NOT_DELETED)
                .and(query -> query.eq(SkillFactoryWorkspaceDO::getSkillCode, skillCode)
                        .or()
                        .eq(SkillFactoryWorkspaceDO::getWorkspaceId, skillCode));
        long count = countDb(wrapper);
        boolean exists = count > 0;
        log.info("SkillFactory检查Skill code是否重复DB完成, skillCode:{}, exists:{}, count:{}",
                skillCode, exists, count);
        return exists;
    }

    /**
     * 判断 Skill 中文名是否已被其他草稿占用。
     */
    public boolean draftExistsBySkillNameCn(String skillNameCn, String excludedSkillCode) {
        if (StringUtils.isBlank(skillNameCn)) {
            return false;
        }
        return draftExistsBySkillNameCnDb(skillNameCn, excludedSkillCode);
    }

    private boolean draftExistsBySkillNameCnDb(String skillNameCn, String excludedSkillCode) {
        LambdaQueryWrapper<SkillFactoryWorkspaceDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillFactoryWorkspaceDO::getDeleted, NOT_DELETED)
                .eq(SkillFactoryWorkspaceDO::getSkillNameCn, skillNameCn);
        if (StringUtils.isNotBlank(excludedSkillCode)) {
            wrapper.ne(SkillFactoryWorkspaceDO::getSkillCode, excludedSkillCode);
        }
        long count = countDb(wrapper);
        boolean exists = count > 0;
        log.info("SkillFactory检查Skill中文名是否重复DB完成, skillNameCn:{}, excludedSkillCode:{}, "
                        + "exists:{}, count:{}",
                skillNameCn, excludedSkillCode, exists, count);
        return exists;
    }

    /**
     * 更新 Skill 基础信息，不改变 Skill code、workspaceId、专员、负责人或 workspace 目录。
     */
    public SkillDraft updateSkillBasicInfo(String skillCode, String skillNameCn,
            String skillDescription, String businessDomain, String capabilityDomain, String operator) {
        return toDomain(updateSkillBasicInfoDb(
                skillCode, skillNameCn, skillDescription, businessDomain, capabilityDomain, operator));
    }

    /**
     * 回写 LangBridge Skill 稳定 ID。
     *
     * <p>该字段只允许从空值写入，或幂等写入相同值；已存在不同 ID 时拒绝覆盖，避免重试把同一个
     * SkillFactory Skill 指向另一条 LangBridge Skill。
     */
    public SkillDraft updateLangBridgeSkillId(String skillCode, long langBridgeSkillId) {
        if (langBridgeSkillId <= 0) {
            throw new IllegalArgumentException(ERROR_LANG_BRIDGE_SKILL_ID_INVALID);
        }
        return toDomain(updateLangBridgeSkillIdDb(skillCode, langBridgeSkillId));
    }

    private SkillFactoryWorkspaceDO updateLangBridgeSkillIdDb(String skillCode, long langBridgeSkillId) {
        long now = System.currentTimeMillis();
        LambdaUpdateWrapper<SkillFactoryWorkspaceDO> wrapper = new LambdaUpdateWrapper<>();
        wrapper.eq(SkillFactoryWorkspaceDO::getSkillCode, skillCode)
                .eq(SkillFactoryWorkspaceDO::getDeleted, NOT_DELETED)
                .and(condition -> condition.isNull(SkillFactoryWorkspaceDO::getLangBridgeSkillId)
                        .or().le(SkillFactoryWorkspaceDO::getLangBridgeSkillId, ZERO_ID)
                        .or().eq(SkillFactoryWorkspaceDO::getLangBridgeSkillId, langBridgeSkillId))
                .set(SkillFactoryWorkspaceDO::getLangBridgeSkillId, langBridgeSkillId)
                .set(SkillFactoryWorkspaceDO::getUpdateTime, now);
        int rows = workspaceMapper.update(null, wrapper);
        if (rows <= 0) {
            SkillFactoryWorkspaceDO existing = selectDraftBySkillCodeDb(skillCode);
            checkedLangBridgeSkillIdDraft(existing, skillCode, langBridgeSkillId);
            log.warn("SkillFactory回写LangBridge Skill ID到DB失败, skillCode:{}", skillCode);
            throw new IllegalStateException(ERROR_UPDATE_LANG_BRIDGE_SKILL_ID_FAILED);
        }
        log.info("SkillFactory回写LangBridge Skill ID到DB完成, skillCode:{}, langBridgeSkillId:{}",
                skillCode, langBridgeSkillId);
        return copyDraft(fillRuntimeWorkspaceFieldsQuietly(selectDraftBySkillCodeDb(skillCode)));
    }

    private SkillFactoryWorkspaceDO checkedLangBridgeSkillIdDraft(SkillFactoryWorkspaceDO existing,
            String skillCode, long langBridgeSkillId) {
        if (existing == null) {
            throw new IllegalArgumentException(ERROR_WORKSPACE_NOT_FOUND);
        }
        if (existing.getLangBridgeSkillId() != null && existing.getLangBridgeSkillId() > 0
                && existing.getLangBridgeSkillId() != langBridgeSkillId) {
            log.warn("SkillFactory拒绝覆盖不同的LangBridge Skill ID, skillCode:{}, savedId:{}, requestId:{}",
                    skillCode, existing.getLangBridgeSkillId(), langBridgeSkillId);
            throw new IllegalStateException(ERROR_LANG_BRIDGE_SKILL_ID_CONFLICT);
        }
        return copyDraft(existing).setLangBridgeSkillId(langBridgeSkillId);
    }

    private SkillFactoryWorkspaceDO updateSkillBasicInfoDb(String skillCode, String skillNameCn,
            String skillDescription, String businessDomain, String capabilityDomain, String operator) {
        SkillFactoryWorkspaceDO existingDraft = selectDraftBySkillCodeDb(skillCode);
        if (existingDraft == null) {
            log.warn("SkillFactory更新Skill基础信息DB失败，草稿不存在, skillCode:{}, operator:{}",
                    skillCode, operator);
            return null;
        }
        long now = System.currentTimeMillis();
        SkillFactoryWorkspaceDO updatedDraft = copyDraft(existingDraft)
                .setSkillNameCn(skillNameCn)
                .setModifier(StringUtils.defaultIfBlank(operator, existingDraft.getModifier()))
                .setUpdateTime(now);
        if (skillDescription != null) {
            updatedDraft.setSkillDescription(skillDescription);
        }
        if (businessDomain != null) {
            updatedDraft.setBusinessDomain(businessDomain);
        }
        if (capabilityDomain != null) {
            updatedDraft.setCapabilityDomain(capabilityDomain);
        }
        int rows = workspaceMapper.updateById(updatedDraft);
        if (rows <= 0) {
            log.warn("SkillFactory更新Skill基础信息DB失败，updateById未影响行, skillCode:{}, draftId:{}, "
                            + "operator:{}",
                    skillCode, updatedDraft.getId(), operator);
            throw new IllegalStateException("update skill draft basic info failed");
        }
        SkillFactoryWorkspaceDO runtimeDraft = fillRuntimeWorkspaceFieldsQuietly(updatedDraft);
        log.info("SkillFactory更新Skill基础信息DB完成, skillCode:{}, workspaceId:{}, operator:{}, "
                        + "businessDomain:{}, capabilityDomain:{}, descriptionLength:{}",
                skillCode, runtimeDraft.getWorkspaceId(), operator,
                runtimeDraft.getBusinessDomain(), runtimeDraft.getCapabilityDomain(),
                StringUtils.length(runtimeDraft.getSkillDescription()));
        return copyDraft(runtimeDraft);
    }

    /**
     * 查询 Skill 草稿列表，供 M 端 workbench 首屏加载。
     */
    public List<SkillDraft> listDrafts(String keyword, String businessDomain, String capabilityDomain) {
        return listDraftsDb(keyword, businessDomain, capabilityDomain).stream()
                .map(this::toDomain)
                .collect(Collectors.toList());
    }

    /**
     * 按 Skill code 批量查询展示元数据。
     *
     * <p>查询只经过 {@code skill_draft}，由数据库过滤逻辑删除记录，再由 Repository 严格过滤
     * {@code workspaceId == skillCode} 的稳定身份。这里不补读文件系统，也不读取发布状态或环境指针。
     */
    public List<SkillDraftMetadata> findDraftMetadataBySkillCodes(List<String> skillCodes) {
        if (skillCodes == null || skillCodes.isEmpty()) {
            return new ArrayList<>();
        }
        if (skillCodes.size() > SKILL_METADATA_BATCH_LIMIT) {
            throw new IllegalArgumentException("skill metadata batch size exceeds limit");
        }
        LambdaQueryWrapper<SkillFactoryWorkspaceDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillFactoryWorkspaceDO::getDeleted, NOT_DELETED)
                .in(SkillFactoryWorkspaceDO::getSkillCode, skillCodes)
                .orderByDesc(SkillFactoryWorkspaceDO::getUpdateTime);
        return toMetadataList(workspaceMapper.selectList(wrapper));
    }

    /**
     * 查询全部可见草稿的轻量展示元数据，供 Adviser 的 Skill 搜索和筛选使用。
     *
     * <p>只读取身份校验和展示所需字段，不复用工作台列表的 100 条上限，避免遗漏搜索和筛选项。
     * 保持逻辑删除、稳定身份过滤和按 code 去重，不读取发布状态或环境指针。
     */
    public List<SkillDraftMetadata> listDraftMetadata() {
        LambdaQueryWrapper<SkillFactoryWorkspaceDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.select(SkillFactoryWorkspaceDO::getSkillCode, SkillFactoryWorkspaceDO::getSkillNameCn,
                        SkillFactoryWorkspaceDO::getSkillNameEn, SkillFactoryWorkspaceDO::getWorkspaceId,
                        SkillFactoryWorkspaceDO::getDeleted)
                .eq(SkillFactoryWorkspaceDO::getDeleted, NOT_DELETED)
                .orderByDesc(SkillFactoryWorkspaceDO::getUpdateTime);
        return toMetadataList(workspaceMapper.selectList(wrapper));
    }

    private List<SkillDraftMetadata> toMetadataList(List<SkillFactoryWorkspaceDO> drafts) {
        Map<String, SkillDraftMetadata> metadata = new LinkedHashMap<>();
        if (drafts == null) {
            return new ArrayList<>();
        }
        for (SkillFactoryWorkspaceDO draft : drafts) {
            if (draft == null || !Integer.valueOf(NOT_DELETED).equals(draft.getDeleted())
                    || !isVisibleDraft(draft)) {
                continue;
            }
            metadata.putIfAbsent(draft.getSkillCode(), new SkillDraftMetadata()
                    .setSkillCode(draft.getSkillCode())
                    .setSkillNameCn(draft.getSkillNameCn())
                    .setSkillNameEn(draft.getSkillNameEn()));
        }
        return new ArrayList<>(metadata.values());
    }

    private List<SkillFactoryWorkspaceDO> listDraftsDb(String keyword, String businessDomain,
            String capabilityDomain) {
        String normalizedKeyword = StringUtils.trimToEmpty(keyword);
        String normalizedBusinessDomain = StringUtils.trimToEmpty(businessDomain);
        String normalizedCapabilityDomain = StringUtils.trimToEmpty(capabilityDomain);
        LambdaQueryWrapper<SkillFactoryWorkspaceDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillFactoryWorkspaceDO::getDeleted, NOT_DELETED);
        if (StringUtils.isNotBlank(normalizedKeyword)) {
            wrapper.and(query -> query.like(SkillFactoryWorkspaceDO::getSkillCode, normalizedKeyword)
                    .or()
                    .like(SkillFactoryWorkspaceDO::getSkillNameCn, normalizedKeyword)
                    .or()
                    .like(SkillFactoryWorkspaceDO::getSkillNameEn, normalizedKeyword)
                    .or()
                    .like(SkillFactoryWorkspaceDO::getSkillDescription, normalizedKeyword)
                    .or()
                    .like(SkillFactoryWorkspaceDO::getBusinessDomain, normalizedKeyword)
                    .or()
                    .like(SkillFactoryWorkspaceDO::getCapabilityDomain, normalizedKeyword)
                    .or()
                    .like(SkillFactoryWorkspaceDO::getOwner, normalizedKeyword));
        }
        if (StringUtils.isNotBlank(normalizedBusinessDomain)) {
            wrapper.eq(SkillFactoryWorkspaceDO::getBusinessDomain, normalizedBusinessDomain);
        }
        if (StringUtils.isNotBlank(normalizedCapabilityDomain)) {
            wrapper.eq(SkillFactoryWorkspaceDO::getCapabilityDomain, normalizedCapabilityDomain);
        }
        wrapper.orderByDesc(SkillFactoryWorkspaceDO::getUpdateTime)
                .last(LIMIT_PREFIX + DRAFT_LIST_LIMIT);
        List<SkillFactoryWorkspaceDO> drafts = workspaceMapper.selectList(wrapper);
        List<SkillFactoryWorkspaceDO> result = uniqueDraftsBySkillCode(
                (drafts == null ? new ArrayList<SkillFactoryWorkspaceDO>() : drafts)
                .stream()
                .map(this::copyDraft)
                .map(this::fillRuntimeWorkspaceFieldsQuietly)
                .filter(this::isVisibleDraft)
                .collect(Collectors.toList()));
        log.info("SkillFactory查询Skill草稿列表DB完成, keyword:{}, businessDomain:{}, capabilityDomain:{}, "
                        + "dbCount:{}, resultCount:{}",
                normalizedKeyword, normalizedBusinessDomain, normalizedCapabilityDomain,
                drafts == null ? 0 : drafts.size(), result.size());
        return result;
    }

    /**
     * 按稳定游标分页查询全部 Skill 草稿，供需要完整遍历的后端控制面使用。
     *
     * <p>按 updateTime、id 倒序推进；同一游标之后只返回更旧记录，避免 offset 在并发更新时重复或漏读。
     * Repository 仅负责分页数据访问和领域转换，调用方负责跨页业务筛选与去重。
     */
    public List<SkillDraft> listDraftPage(Long cursorUpdateTime, Long cursorId, int limit) {
        if (limit <= 0) {
            throw new IllegalArgumentException(ERROR_DRAFT_PAGE_LIMIT_INVALID);
        }
        if ((cursorUpdateTime == null) != (cursorId == null)) {
            throw new IllegalArgumentException(ERROR_DRAFT_PAGE_CURSOR_INVALID);
        }
        LambdaQueryWrapper<SkillFactoryWorkspaceDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillFactoryWorkspaceDO::getDeleted, NOT_DELETED);
        if (cursorUpdateTime != null) {
            wrapper.and(query -> query.lt(SkillFactoryWorkspaceDO::getUpdateTime, cursorUpdateTime)
                    .or(nested -> nested.eq(SkillFactoryWorkspaceDO::getUpdateTime, cursorUpdateTime)
                            .lt(SkillFactoryWorkspaceDO::getId, cursorId)));
        }
        wrapper.orderByDesc(SkillFactoryWorkspaceDO::getUpdateTime)
                .orderByDesc(SkillFactoryWorkspaceDO::getId)
                .last(LIMIT_PREFIX + limit);
        List<SkillFactoryWorkspaceDO> drafts = workspaceMapper.selectList(wrapper);
        List<SkillFactoryWorkspaceDO> normalized = (drafts == null
                ? new ArrayList<SkillFactoryWorkspaceDO>() : drafts).stream()
                .map(this::copyDraft)
                .peek(this::requireStableDraftIdentity)
                .collect(Collectors.toList());
        assertPageCursorAdvanced(cursorUpdateTime, cursorId, normalized);
        log.info("SkillFactory分页查询Skill草稿DB完成, cursorUpdateTime:{}, cursorId:{}, limit:{}, "
                        + "dbCount:{}, resultCount:{}",
                cursorUpdateTime, cursorId, limit, drafts == null ? 0 : drafts.size(), normalized.size());
        return normalized.stream().map(this::toDomain).collect(Collectors.toList());
    }

    private void requireStableDraftIdentity(SkillFactoryWorkspaceDO draft) {
        if (!isVisibleDraft(draft)) {
            log.error("SkillFactory分页查询发现非法Skill稳定身份, draftId:{}", draft == null ? null : draft.getId());
            throw new IllegalStateException(ERROR_DRAFT_PAGE_IDENTITY_INVALID);
        }
    }

    private void assertPageCursorAdvanced(Long cursorUpdateTime, Long cursorId,
            List<SkillFactoryWorkspaceDO> drafts) {
        if (drafts.isEmpty()) {
            return;
        }
        SkillFactoryWorkspaceDO last = drafts.get(drafts.size() - 1);
        Long nextUpdateTime = last.getUpdateTime();
        Long nextId = last.getId();
        boolean advanced = nextUpdateTime != null && nextId != null
                && (cursorUpdateTime == null || nextUpdateTime < cursorUpdateTime
                || nextUpdateTime.equals(cursorUpdateTime) && nextId < cursorId);
        if (!advanced) {
            log.error("SkillFactory草稿分页游标未推进, cursorUpdateTime:{}, cursorId:{}, "
                            + "nextUpdateTime:{}, nextId:{}",
                    cursorUpdateTime, cursorId, nextUpdateTime, nextId);
            throw new IllegalStateException(ERROR_DRAFT_PAGE_CURSOR_NOT_ADVANCED);
        }
    }

    /**
     * 根据当前本地 workspace 扫描结果插入或更新 `skill_draft`。
     */
    public SkillDraft upsertDraftMetadata(String workspaceId, Path workspace, String fileTreeDigest,
            int fileCount, Map<String, String> params, String operator) {
        SkillFactoryWorkspaceDO draft =
                upsertDraftMetadataDb(workspaceId, workspace, fileTreeDigest, fileCount, params, operator);
        SkillDraft result = toDomain(draft);
        result.setFileCount(fileCount);
        return result;
    }

    private SkillFactoryWorkspaceDO upsertDraftMetadataDb(String workspaceId, Path workspace, String fileTreeDigest,
            int fileCount, Map<String, String> params, String operator) {
        SkillFactoryWorkspaceDO existingDraft = selectDraftByWorkspaceIdDb(workspaceId);
        SkillFactoryWorkspaceDO draft = buildDraft(workspaceId, workspace, fileTreeDigest, params, operator,
                existingDraft);
        SkillFactoryWorkspaceDO runtimeDraft = fillRuntimeWorkspaceFields(draft, workspace, fileCount);
        if (existingDraft == null || existingDraft.getId() == null) {
            int rows = workspaceMapper.insert(runtimeDraft);
            if (rows <= 0) {
                log.warn("SkillFactory草稿元数据DB插入失败, workspaceId:{}, skillCode:{}, operator:{}",
                        workspaceId, runtimeDraft.getSkillCode(), operator);
                throw new IllegalStateException("insert skill draft metadata failed");
            }
            log.info("SkillFactory草稿元数据已插入DB, workspaceId:{}, skillCode:{}, draftId:{}, "
                            + "fileTreeDigest:{}",
                    workspaceId, runtimeDraft.getSkillCode(), runtimeDraft.getId(), fileTreeDigest);
            return copyDraft(runtimeDraft);
        }
        runtimeDraft.setId(existingDraft.getId())
                .setCreateTime(existingDraft.getCreateTime());
        int rows = workspaceMapper.updateById(runtimeDraft);
        if (rows <= 0) {
            log.warn("SkillFactory草稿元数据DB更新失败, workspaceId:{}, skillCode:{}, draftId:{}, operator:{}",
                    workspaceId, runtimeDraft.getSkillCode(), runtimeDraft.getId(), operator);
            throw new IllegalStateException("update skill draft metadata failed");
        }
        log.info("SkillFactory草稿元数据已更新DB, workspaceId:{}, skillCode:{}, draftId:{}, fileTreeDigest:{}",
                workspaceId, runtimeDraft.getSkillCode(), runtimeDraft.getId(), fileTreeDigest);
        return copyDraft(runtimeDraft);
    }

    private void createDirectories(String workspaceId, Path workspace) throws IOException {
        Files.createDirectories(workspace.getParent());
        Files.createDirectory(workspace);
        log.info("SkillFactory工作区目录已创建, workspaceId:{}, workspacePath:{}", workspaceId, workspace);
    }

    private SkillFactoryWorkspaceDO selectDraftByWorkspaceIdDb(String workspaceId) {
        if (StringUtils.isBlank(workspaceId)) {
            return null;
        }
        LambdaQueryWrapper<SkillFactoryWorkspaceDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillFactoryWorkspaceDO::getWorkspaceId, workspaceId)
                .eq(SkillFactoryWorkspaceDO::getDeleted, NOT_DELETED)
                .orderByDesc(SkillFactoryWorkspaceDO::getUpdateTime)
                .last(LIMIT_ONE);
        return workspaceMapper.selectOne(wrapper);
    }

    private SkillFactoryWorkspaceDO selectDraftBySkillCodeDb(String skillCode) {
        if (StringUtils.isBlank(skillCode)) {
            return null;
        }
        LambdaQueryWrapper<SkillFactoryWorkspaceDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillFactoryWorkspaceDO::getSkillCode, skillCode)
                .eq(SkillFactoryWorkspaceDO::getDeleted, NOT_DELETED)
                .orderByDesc(SkillFactoryWorkspaceDO::getUpdateTime)
                .last(LIMIT_ONE);
        return workspaceMapper.selectOne(wrapper);
    }

    private long countDb(LambdaQueryWrapper<SkillFactoryWorkspaceDO> wrapper) {
        Number count = workspaceMapper.selectCount(wrapper);
        return count == null ? 0L : count.longValue();
    }

    private SkillFactoryWorkspaceDO buildDraft(String workspaceId, Path workspace, String fileTreeDigest,
            Map<String, String> params, String operator, SkillFactoryWorkspaceDO existing) {
        long now = System.currentTimeMillis();
        SkillFactoryWorkspaceDO effectiveExisting = identityConsistentExisting(workspaceId, existing);
        String skillCode = firstNonBlank(value(params, PARAM_SKILL_CODE), workspaceId, DEFAULT_SKILL_CODE);
        if (!StringUtils.equals(skillCode, workspaceId)) {
            log.warn("SkillFactory草稿元数据发现Skill code和workspaceId不一致，按workspaceId修正, "
                            + "workspaceId:{}, requestSkillCode:{}",
                    workspaceId, skillCode);
            skillCode = workspaceId;
        }
        SkillFactoryWorkspaceDO draft = new SkillFactoryWorkspaceDO()
                .setSkillCode(skillCode)
                .setCreateSource(firstNonBlank(value(params, PARAM_CREATE_SOURCE),
                        value(effectiveExisting, FIELD_CREATE_SOURCE), DEFAULT_CREATE_SOURCE))
                .setWorkspaceId(workspaceId)
                .setWorkspacePath(normalize(workspaceRoot().relativize(workspace)))
                .setFileTreeDigest(StringUtils.defaultString(fileTreeDigest))
                .setSourceZipUrl(firstNonBlank(value(params, PARAM_SOURCE_ZIP_URL),
                        value(effectiveExisting, FIELD_SOURCE_ZIP_URL), EMPTY))
                .setVersion(parseVersion(firstNonBlank(value(params, PARAM_VERSION),
                        value(effectiveExisting, FIELD_VERSION), DEFAULT_VERSION_TEXT)))
                .setLangBridgeSkillId(number(value(effectiveExisting, FIELD_LANG_BRIDGE_SKILL_ID)))
                .setStatus(firstNonBlank(value(effectiveExisting, FIELD_STATUS), DEFAULT_DRAFT_STATUS))
                .setOwner(firstNonBlank(value(params, PARAM_OWNER), operator, value(effectiveExisting, FIELD_OWNER),
                        DEFAULT_OWNER))
                .setCreator(firstNonBlank(value(effectiveExisting, FIELD_CREATOR), operator, DEFAULT_OWNER))
                .setModifier(firstNonBlank(operator, value(effectiveExisting, FIELD_MODIFIER), DEFAULT_OWNER))
                .setExtJson(SkillFactoryJsonColumnSupport.nullable(
                        value(effectiveExisting, FIELD_EXT_JSON), FIELD_EXT_JSON))
                .setAttribute(SkillFactoryJsonColumnSupport.nullable(
                        value(effectiveExisting, FIELD_ATTRIBUTE), FIELD_ATTRIBUTE))
                .setDeleted(NOT_DELETED)
                .setUpdateTime(now);
        draft.setSkillNameCn(firstNonBlank(value(params, PARAM_SKILL_NAME_CN),
                value(effectiveExisting, FIELD_SKILL_NAME_CN), draft.getSkillCode()));
        draft.setSkillNameEn(firstNonBlank(value(params, PARAM_SKILL_NAME_EN),
                value(effectiveExisting, FIELD_SKILL_NAME_EN), draft.getSkillCode()));
        if (params != null && params.containsKey(PARAM_SKILL_DESCRIPTION)) {
            draft.setSkillDescription(value(params, PARAM_SKILL_DESCRIPTION));
        } else {
            draft.setSkillDescription(value(effectiveExisting, FIELD_SKILL_DESCRIPTION));
        }
        draft.setBusinessDomain(firstNonBlank(value(params, PARAM_BUSINESS_DOMAIN),
                value(effectiveExisting, FIELD_BUSINESS_DOMAIN)));
        draft.setCapabilityDomain(firstNonBlank(value(params, PARAM_CAPABILITY_DOMAIN),
                value(effectiveExisting, FIELD_CAPABILITY_DOMAIN)));
        if (effectiveExisting == null || effectiveExisting.getCreateTime() == null) {
            draft.setCreateTime(now);
        } else {
            draft.setCreateTime(effectiveExisting.getCreateTime());
        }
        return draft;
    }

    private SkillFactoryWorkspaceDO fillRuntimeWorkspaceFields(SkillFactoryWorkspaceDO draft, Path workspace,
            int fileCount) {
        return draft.setWorkspacePath(normalize(workspaceRoot().relativize(workspace)));
    }

    private SkillFactoryWorkspaceDO fillRuntimeWorkspaceFieldsQuietly(SkillFactoryWorkspaceDO draft) {
        if (draft == null) {
            return null;
        }
        if (StringUtils.isBlank(draft.getWorkspaceId())) {
            log.warn("SkillFactory草稿缺少workspaceId，无法回填运行时workspace字段, skillCode:{}",
                    draft.getSkillCode());
            return draft;
        }
        try {
            Path workspace = resolveWorkspace(draft.getWorkspaceId());
            return fillRuntimeWorkspaceFields(draft, workspace, countWorkspaceFilesQuietly(workspace));
        } catch (IllegalArgumentException e) {
            log.warn("SkillFactory草稿workspaceId非法，跳过运行时目录回填, workspaceId:{}, skillCode:{}, "
                            + "error:{}",
                    draft.getWorkspaceId(), draft.getSkillCode(), e.getMessage());
            return draft;
        }
    }

    private boolean isSystemWorkspaceName(String workspaceName) {
        return StringUtils.startsWith(workspaceName, SYSTEM_WORKSPACE_DIR_PREFIX);
    }

    private boolean isVisibleDraft(SkillFactoryWorkspaceDO draft) {
        if (draft == null) {
            return false;
        }
        if (StringUtils.isBlank(draft.getWorkspaceId()) || StringUtils.isBlank(draft.getSkillCode())) {
            log.warn("SkillFactory跳过缺少身份字段的草稿, workspaceId:{}, skillCode:{}",
                    draft.getWorkspaceId(), draft.getSkillCode());
            return false;
        }
        if (isSystemWorkspaceName(draft.getWorkspaceId()) || isSystemWorkspaceName(draft.getSkillCode())) {
            return false;
        }
        if (!StringUtils.equals(draft.getWorkspaceId(), draft.getSkillCode())) {
            log.warn("SkillFactory跳过身份不一致的草稿, workspaceId:{}, skillCode:{}",
                    draft.getWorkspaceId(), draft.getSkillCode());
            return false;
        }
        return true;
    }

    private SkillFactoryWorkspaceDO identityConsistentExisting(String workspaceId, SkillFactoryWorkspaceDO existing) {
        if (existing == null) {
            return null;
        }
        if (StringUtils.equals(workspaceId, existing.getWorkspaceId())
                && StringUtils.equals(workspaceId, existing.getSkillCode())) {
            return existing;
        }
        log.warn("SkillFactory丢弃旧草稿中的非法身份字段, workspaceId:{}, existingWorkspaceId:{}, "
                        + "existingSkillCode:{}",
                workspaceId, existing.getWorkspaceId(), existing.getSkillCode());
        return null;
    }

    private List<SkillFactoryWorkspaceDO> uniqueDraftsBySkillCode(List<SkillFactoryWorkspaceDO> drafts) {
        Map<String, SkillFactoryWorkspaceDO> uniqueDrafts = new LinkedHashMap<>();
        for (SkillFactoryWorkspaceDO draft : drafts) {
            SkillFactoryWorkspaceDO previous = uniqueDrafts.putIfAbsent(draft.getSkillCode(), draft);
            if (previous != null) {
                log.warn("SkillFactory列表发现重复Skill code，保留第一条并丢弃后续草稿, "
                                + "skillCode:{}, keptWorkspaceId:{}, droppedWorkspaceId:{}",
                        draft.getSkillCode(), previous.getWorkspaceId(), draft.getWorkspaceId());
            }
        }
        return new ArrayList<>(uniqueDrafts.values());
    }

    private int countWorkspaceFilesQuietly(Path workspace) {
        if (workspace == null || !Files.exists(workspace)) {
            return 0;
        }
        try (Stream<Path> paths = Files.walk(workspace)) {
            return (int) paths.filter(Files::isRegularFile).count();
        } catch (IOException e) {
            log.warn("SkillFactory统计workspace文件数失败, workspace:{}, error={}", workspace, e.getMessage());
            return 0;
        }
    }

    private SkillFactoryWorkspaceDO copyDraft(SkillFactoryWorkspaceDO draft) {
        if (draft == null) {
            return null;
        }
        return new SkillFactoryWorkspaceDO()
                .setId(draft.getId())
                .setSkillCode(draft.getSkillCode())
                .setSkillNameCn(draft.getSkillNameCn())
                .setSkillNameEn(draft.getSkillNameEn())
                .setSkillDescription(draft.getSkillDescription())
                .setBusinessDomain(draft.getBusinessDomain())
                .setCapabilityDomain(draft.getCapabilityDomain())
                .setCreateSource(draft.getCreateSource())
                .setWorkspaceId(draft.getWorkspaceId())
                .setWorkspacePath(draft.getWorkspacePath())
                .setFileTreeDigest(draft.getFileTreeDigest())
                .setSourceZipUrl(draft.getSourceZipUrl())
                .setVersion(draft.getVersion())
                .setLangBridgeSkillId(draft.getLangBridgeSkillId())
                .setStatus(draft.getStatus())
                .setOwner(draft.getOwner())
                .setCreator(draft.getCreator())
                .setModifier(draft.getModifier())
                .setExtJson(draft.getExtJson())
                .setAttribute(draft.getAttribute())
                .setDeleted(draft.getDeleted())
                .setCreateTime(draft.getCreateTime())
                .setUpdateTime(draft.getUpdateTime());
    }

    /**
     * 把数据库对象转换成 lifecycle 领域对象，并补齐文件系统运行态摘要。
     */
    private SkillDraft toDomain(SkillFactoryWorkspaceDO draft) {
        if (draft == null) {
            return null;
        }
        int fileCount = 0;
        if (StringUtils.isNotBlank(draft.getWorkspaceId())) {
            try {
                fileCount = countWorkspaceFilesQuietly(resolveWorkspace(draft.getWorkspaceId()));
            } catch (IllegalArgumentException e) {
                log.warn("SkillFactory草稿转换领域对象时workspaceId非法, skillCode:{}, workspaceId:{}",
                        draft.getSkillCode(), draft.getWorkspaceId());
            }
        }
        return new SkillDraft()
                .setId(draft.getId())
                .setSkillCode(draft.getSkillCode())
                .setSkillNameCn(draft.getSkillNameCn())
                .setSkillNameEn(draft.getSkillNameEn())
                .setSkillDescription(draft.getSkillDescription())
                .setBusinessDomain(draft.getBusinessDomain())
                .setCapabilityDomain(draft.getCapabilityDomain())
                .setCreateSource(draft.getCreateSource())
                .setWorkspaceId(draft.getWorkspaceId())
                .setWorkspaceRoot(normalize(workspaceRoot()))
                .setWorkspacePath(draft.getWorkspacePath())
                .setFileTreeDigest(draft.getFileTreeDigest())
                .setSourceZipUrl(draft.getSourceZipUrl())
                .setVersion(draft.getVersion())
                .setLangBridgeSkillId(draft.getLangBridgeSkillId())
                .setStatus(draft.getStatus())
                .setOwner(draft.getOwner())
                .setCreator(draft.getCreator())
                .setModifier(draft.getModifier())
                .setExtJson(draft.getExtJson())
                .setAttribute(draft.getAttribute())
                .setFileCount(fileCount)
                .setCreateTime(draft.getCreateTime())
                .setUpdateTime(draft.getUpdateTime());
    }

    private String value(Map<String, String> params, String key) {
        return params == null ? EMPTY : StringUtils.defaultString(params.get(key));
    }

    private String value(SkillFactoryWorkspaceDO draft, String field) {
        if (draft == null) {
            return EMPTY;
        }
        switch (field) {
            case FIELD_SKILL_CODE:
                return draft.getSkillCode();
            case FIELD_SKILL_NAME_CN:
                return draft.getSkillNameCn();
            case FIELD_SKILL_NAME_EN:
                return draft.getSkillNameEn();
            case FIELD_SKILL_DESCRIPTION:
                return draft.getSkillDescription();
            case FIELD_BUSINESS_DOMAIN:
                return draft.getBusinessDomain();
            case FIELD_CAPABILITY_DOMAIN:
                return draft.getCapabilityDomain();
            case FIELD_CREATE_SOURCE:
                return draft.getCreateSource();
            case FIELD_SOURCE_ZIP_URL:
                return draft.getSourceZipUrl();
            case FIELD_VERSION:
                return draft.getVersion() == null ? EMPTY : String.valueOf(draft.getVersion());
            case FIELD_LANG_BRIDGE_SKILL_ID:
                return draft.getLangBridgeSkillId() == null ? EMPTY : String.valueOf(draft.getLangBridgeSkillId());
            case FIELD_STATUS:
                return draft.getStatus();
            case FIELD_OWNER:
                return draft.getOwner();
            case FIELD_CREATOR:
                return draft.getCreator();
            case FIELD_MODIFIER:
                return draft.getModifier();
            case FIELD_EXT_JSON:
                return draft.getExtJson();
            case FIELD_ATTRIBUTE:
                return draft.getAttribute();
            default:
                return EMPTY;
        }
    }

    private String firstNonBlank(String... values) {
        for (String value : values) {
            if (StringUtils.isNotBlank(value)) {
                return value;
            }
        }
        return EMPTY;
    }

    private Integer parseVersion(String versionText) {
        String normalized = StringUtils.removeStartIgnoreCase(StringUtils.defaultString(versionText), VERSION_PREFIX);
        if (!StringUtils.isNumeric(normalized)) {
            return DEFAULT_VERSION;
        }
        return Integer.parseInt(normalized);
    }

    private Long number(String value) {
        if (!StringUtils.isNumeric(value)) {
            return ZERO_ID;
        }
        return Long.parseLong(value);
    }

    private String normalize(Path path) {
        return path.normalize().toString().replace('\\', '/');
    }
}
