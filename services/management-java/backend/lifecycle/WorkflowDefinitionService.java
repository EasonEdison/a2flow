package dev.a2flow.management.lifecycle;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.access.AssetAction;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.access.AssetCreationTransactionService;
import dev.a2flow.management.access.AssetPermissionDeniedException;
import dev.a2flow.management.lifecycle.domain.WorkflowCreateResult;
import dev.a2flow.management.lifecycle.domain.WorkflowDefinitionView;
import dev.a2flow.management.lifecycle.domain.WorkflowDraftPayloadView;
import dev.a2flow.management.lifecycle.domain.WorkflowDraftUpdateResult;
import dev.a2flow.management.lifecycle.domain.WorkflowListItemView;
import dev.a2flow.management.lifecycle.domain.WorkflowListPageView;
import dev.a2flow.management.lifecycle.domain.WorkflowReleaseSourceView;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowCompiledPlanBuilder;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphAggregate;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphAggregateParser;
import dev.a2flow.management.release.AssetReleaseEditGuard;
import dev.a2flow.management.release.AssetReleasePointerQueryService;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseDigestUtils;
import dev.a2flow.management.release.ReleaseModels.AssetReleaseProjection;
import dev.a2flow.management.storage.db.entity.WorkflowDefinitionDO;
import dev.a2flow.management.storage.db.repository.WorkflowDefinitionRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * Workflow 定义控制面 Service。
 *
 * <p>负责 Workflow 稳定资产的全生命周期管理：创建（workflowCode 后端生成，specialistCode 绑定并
 * 通过 KConf 受控专员事实校验）、基础信息更新、草稿读写（含乐观并发 CAS）。所有 mutation 操作
 * 在调用 Repository 前强校验 OWNER/ADMIN 权限；只读操作允许 VIEWER。
 *
 * <p>updateWorkflowDraft 在 CAS 前把完整草稿解析为强类型聚合，并委托
 * WorkflowSpecialistSkillSelector 对每个 Skill 节点执行当前存在性以及店长全量/普通专员关系重验；
 * Skill 引用不检查操作者的 Skill VIEW，任一节点失败即拒绝保存，不降级/不 fallback。
 *
 * <p>上游：sellerdata RPC handler（§3.7 实现后接入）。
 * <p>下游：WorkflowDefinitionRepository / AssetCreationTransactionService /
 *         AssetAuthorizationService / WorkflowSpecialistSkillSelector。
 * <p>不负责：Skill 列表查询（§3.5）、发布 Adapter（§3.6）、
 *          运行态表（workflow_run/workflow_run_item）、前端视图组装。
 */
@Service
@Slf4j
public class WorkflowDefinitionService {

    private static final String WORKFLOW_CODE_PREFIX = "wf_";
    private static final String UUID_SEPARATOR = "-";
    private static final String EMPTY = "";
    private static final int INITIAL_DRAFT_REVISION = 1;
    private static final int INITIAL_DRAFT_CONTRACT_VERSION =
            WorkflowGraphAggregateParser.SNAPSHOT_CONTRACT_VERSION_V2;
    private static final int MAX_WORKFLOW_PAGE_SIZE = 100;
    private static final int WORKFLOW_SCAN_PAGE_SIZE = 100;
    private static final int NOT_DELETED = 0;

    private static final String DRAFT_FIELD_SNAPSHOT_CONTRACT_VERSION = "snapshotContractVersion";
    private static final String DRAFT_FIELD_WORKFLOW_CODE = "workflowCode";
    private static final String DRAFT_FIELD_METADATA = "metadata";
    private static final String DRAFT_FIELD_NODES = "nodes";
    private static final String DRAFT_FIELD_EDGES = "edges";
    private static final String DRAFT_FIELD_SUMMARY_CONFIG = "summaryConfig";
    private static final String DRAFT_FIELD_PROMPT = "prompt";
    private static final String DRAFT_FIELD_HANDLING_SUGGESTIONS = "handlingSuggestions";
    private static final String ERROR_WORKFLOW_NOT_FOUND = "Workflow不存在";
    private static final String ERROR_DISPLAY_NAME_REQUIRED = "Workflow显示名不能为空";
    private static final String ERROR_SPECIALIST_CODE_REQUIRED = "specialistCode不能为空";
    private static final String ERROR_SPECIALIST_NOT_ALLOWED = "specialistCode未在受控专员列表中";
    private static final String ERROR_CODE_SPECIALIST_NOT_ALLOWED = "WORKFLOW_SPECIALIST_NOT_ALLOWED";
    private static final String ERROR_CODE_WORKFLOW_NOT_FOUND = "WORKFLOW_NOT_FOUND";
    private static final String ERROR_CODE_DISPLAY_NAME_REQUIRED = "WORKFLOW_DISPLAY_NAME_REQUIRED";
    private static final String ERROR_CODE_SPECIALIST_CODE_REQUIRED = "WORKFLOW_SPECIALIST_CODE_REQUIRED";
    private static final String ERROR_CODE_DRAFT_PAYLOAD_REQUIRED = "WORKFLOW_DRAFT_PAYLOAD_REQUIRED";
    private static final String ERROR_CODE_DRAFT_WORKFLOW_CODE_MISMATCH =
            "WORKFLOW_DRAFT_WORKFLOW_CODE_MISMATCH";
    private static final String ERROR_CODE_LIST_LIMIT_INVALID = "WORKFLOW_LIST_LIMIT_INVALID";
    private static final String ERROR_CODE_LIST_LIMIT_EXCEEDED = "WORKFLOW_LIST_LIMIT_EXCEEDED";
    private static final String FIELD_SPECIALIST_CODE = "specialistCode";
    private static final String FIELD_SPECIALIST_ID = "id";
    private static final String FIELD_DISPLAY_NAME = "displayName";
    private static final String FIELD_WORKFLOW_CODE = "workflowCode";
    private static final String FIELD_DRAFT_PAYLOAD_JSON = "draftPayloadJson";
    private static final String FIELD_LIST_LIMIT = "limit";
    private static final String ERROR_CODE_LIST_PAGE_TOKEN_INVALID = "WORKFLOW_LIST_PAGE_TOKEN_INVALID";
    private static final String FIELD_LIST_PAGE_TOKEN = "pageToken";
    private static final String PAGE_TOKEN_SEPARATOR = ":";
    private static final String ERROR_DRAFT_PAYLOAD_REQUIRED = "草稿内容不能为空";
    private static final String ERROR_DRAFT_WORKFLOW_CODE_MISMATCH =
            "草稿内嵌workflowCode与路径参数不一致";

    @Resource
    private WorkflowDefinitionRepository workflowDefinitionRepository;

    @Resource
    private AssetCreationTransactionService assetCreationTransactionService;

    @Resource
    private AssetAuthorizationService assetAuthorizationService;

    @Resource
    private SkillFactoryPageConfigService pageConfigService;

    @Resource
    private WorkflowSpecialistSkillSelector workflowSpecialistSkillSelector;

    @Resource
    private AssetReleaseEditGuard assetReleaseEditGuard;

    @Resource
    private AssetReleasePointerQueryService assetReleasePointerQueryService;

    /**
     * 创建 Workflow。
     *
     * <p>workflowCode 由后端稳定生成（UUID 去横线加前缀），不接受客户端传入；specialistCode
     * 复用 Skill 的 SkillFactoryPageConfigService 受控解析器校验并规范化为同一专员 ID。
     *
     * @param operator      操作者 userName
     * @param displayName   显示名（不能为空）
     * @param description   描述（可为空）
     * @param specialistCode Skill 共用专员配置中的稳定 ID
     * @return 创建后的稳定 workflowCode、初始 revision/digest 与 createdAt
     */
    public WorkflowCreateResult createWorkflow(
            String operator, String displayName, String description, String specialistCode) {
        if (StringUtils.isBlank(displayName)) {
            throw new WorkflowControlPlaneException(
                    ERROR_CODE_DISPLAY_NAME_REQUIRED, ERROR_DISPLAY_NAME_REQUIRED,
                    null, FIELD_DISPLAY_NAME);
        }
        if (StringUtils.isBlank(specialistCode)) {
            throw new WorkflowControlPlaneException(
                    ERROR_CODE_SPECIALIST_CODE_REQUIRED, ERROR_SPECIALIST_CODE_REQUIRED,
                    null, FIELD_SPECIALIST_CODE);
        }
        String resolvedSpecialistCode = resolveSpecialistCode(specialistCode);

        String workflowCode = generateWorkflowCode();
        String initialDraftPayloadJson = buildInitialDraftPayloadJson(workflowCode);
        String initialDraftDigest = ReleaseDigestUtils.sha256(initialDraftPayloadJson);
        long now = System.currentTimeMillis();

        WorkflowDefinitionDO workflowDO = new WorkflowDefinitionDO()
                .setWorkflowCode(workflowCode)
                .setSpecialistCode(resolvedSpecialistCode)
                .setDisplayName(displayName)
                .setDescription(StringUtils.trimToNull(description))
                .setDraftContractVersion(INITIAL_DRAFT_CONTRACT_VERSION)
                .setDraftRevision((long) INITIAL_DRAFT_REVISION)
                .setDraftDigest(initialDraftDigest)
                .setDraftPayloadJson(initialDraftPayloadJson)
                .setCreatedBy(operator)
                .setUpdatedBy(operator)
                .setDeleted(NOT_DELETED)
                .setCreateTime(now)
                .setUpdateTime(now);

        WorkflowDefinitionDO created = assetCreationTransactionService
                .createWorkflow(operator, workflowDO, null);
        log.info("Workflow创建完成, workflowCode:{}, specialistCode:{}, operator:{}",
                created.getWorkflowCode(), created.getSpecialistCode(), operator);
        return new WorkflowCreateResult()
                .setWorkflowCode(created.getWorkflowCode())
                .setDraftRevision(created.getDraftRevision())
                .setDraftDigest(created.getDraftDigest())
                .setCreatedAt(created.getCreateTime());
    }

    /**
     * 查询单个 Workflow 元数据（不含完整草稿 payload）。
     * VIEWER 可读。
     */
    public WorkflowDefinitionView getWorkflow(String operator, String workflowCode) {
        assetAuthorizationService.requirePermission(
                operator, ReleaseAssetType.ORCHESTRATION_CONFIG, workflowCode, AssetAction.VIEW);
        WorkflowDefinitionDO workflowDO = requireWorkflow(workflowCode);
        log.info("Workflow元数据查询完成, workflowCode:{}, operator:{}", workflowCode, operator);
        return toView(operator, workflowDO);
    }

    /**
     * 使用 (updateTime,id) keyset 查询 Workflow 列表，不接受 offset。
     * 返回 common-v2 共享发布状态中真实存在的 PRT/ONLINE 环境指针。
     */
    public WorkflowListPageView getWorkflowList(
            String operator, String specialistCode, String pageToken, int limit) {
        assetAuthorizationService.requireTrustedOperator(operator);
        validatePageLimit(limit);
        PageCursor cursor = decodePageToken(pageToken);
        List<WorkflowListItemView> items = new ArrayList<>();
        WorkflowDefinitionDO lastScanned = null;
        boolean hasMore = false;
        while (items.size() < limit) {
            List<WorkflowDefinitionDO> page = workflowDefinitionRepository.list(
                    StringUtils.trimToNull(specialistCode),
                    cursor.updateTime, cursor.id, WORKFLOW_SCAN_PAGE_SIZE);
            if (page.isEmpty()) {
                break;
            }
            for (WorkflowDefinitionDO workflow : page) {
                lastScanned = workflow;
                cursor = new PageCursor(workflow.getUpdateTime(), workflow.getId());
                if (!canView(operator, workflow.getWorkflowCode())) {
                    continue;
                }
                items.add(toListItem(operator, workflow));
                if (items.size() == limit) {
                    break;
                }
            }
            if (items.size() == limit) {
                hasMore = !workflowDefinitionRepository.list(
                        StringUtils.trimToNull(specialistCode),
                        cursor.updateTime, cursor.id, 1).isEmpty();
                break;
            }
            if (page.size() < WORKFLOW_SCAN_PAGE_SIZE) {
                break;
            }
        }
        String nextPageToken = hasMore && lastScanned != null
                ? encodePageToken(lastScanned.getUpdateTime(), lastScanned.getId()) : null;
        log.info("Workflow keyset列表查询完成, specialistCode:{}, limit:{}, resultCount:{}, hasMore:{}, operator:{}",
                specialistCode, limit, items.size(), hasMore, operator);
        return new WorkflowListPageView().setItems(items).setNextPageToken(nextPageToken);
    }

    /**
     * 更新 Workflow 基础信息（displayName / description）。
     * 绝不修改 workflowCode / specialistCode；需要 OWNER 或 ADMIN 权限。
     *
     * @return 更新后的 WorkflowDefinitionView
     */
    public WorkflowDefinitionView updateWorkflowBasicInfo(
            String operator, String workflowCode, String displayName, String description) {
        assetAuthorizationService.requirePermission(
                operator, ReleaseAssetType.ORCHESTRATION_CONFIG, workflowCode, AssetAction.EDIT);
        WorkflowDefinitionDO current = requireWorkflow(workflowCode);
        assetReleaseEditGuard.requireEditableChange(
                ReleaseAssetType.ORCHESTRATION_CONFIG, workflowCode,
                "UPDATE_WORKFLOW_BASIC_INFO", operator);
        String newDisplayName = StringUtils.defaultIfBlank(displayName, current.getDisplayName());
        String newDescription = description != null
                ? StringUtils.trimToNull(description) : current.getDescription();
        long now = System.currentTimeMillis();
        int rows = workflowDefinitionRepository.updateBasicInfo(
                workflowCode, newDisplayName, newDescription, operator, now);
        if (rows == 0) {
            log.warn("Workflow基础信息更新无命中行, workflowCode:{}, operator:{}", workflowCode, operator);
            throw workflowNotFound(workflowCode);
        }
        WorkflowDefinitionDO updated = requireWorkflow(workflowCode);
        log.info("Workflow基础信息更新完成, workflowCode:{}, operator:{}", workflowCode, operator);
        return toView(operator, updated);
    }

    /**
     * 获取 Workflow 完整草稿 payload。
     * VIEWER 可读。
     */
    public WorkflowDraftPayloadView getWorkflowDraftPayload(String operator, String workflowCode) {
        assetAuthorizationService.requirePermission(
                operator, ReleaseAssetType.ORCHESTRATION_CONFIG, workflowCode, AssetAction.VIEW);
        WorkflowDefinitionDO workflowDO = requireWorkflow(workflowCode);
        log.info("Workflow草稿payload查询完成, workflowCode:{}, draftRevision:{}, operator:{}",
                workflowCode, workflowDO.getDraftRevision(), operator);
        return new WorkflowDraftPayloadView()
                .setWorkflowCode(workflowCode)
                .setDraftPayloadJson(workflowDO.getDraftPayloadJson())
                .setDraftRevision(workflowDO.getDraftRevision())
                .setDraftDigest(workflowDO.getDraftDigest());
    }

    /**
     * 为公共发布 Adapter 读取完整 Workflow 草稿事实。
     *
     * <p>本方法只接受共享发布控制面注入的可信 operator，并执行 VIEW 权限校验；返回值包含编译和
     * 冻结所需的定义元数据与完整草稿，但不读取发布版本、环境指针或运行态表。
     */
    public WorkflowReleaseSourceView getWorkflowReleaseSource(String operator, String workflowCode) {
        assetAuthorizationService.requirePermission(
                operator, ReleaseAssetType.ORCHESTRATION_CONFIG, workflowCode, AssetAction.VIEW);
        WorkflowDefinitionDO workflowDO = requireWorkflow(workflowCode);
        log.info("Workflow发布源读取完成, workflowCode:{}, draftRevision:{}, operator:{}",
                workflowCode, workflowDO.getDraftRevision(), operator);
        return toReleaseSourceView(workflowDO);
    }

    /** 发布入口对已解析冻结 graph 执行同一权限与专员关系重验。 */
    public void validateReleaseSkillReferences(
            String operator, String workflowCode, WorkflowGraphAggregate aggregate) {
        assetAuthorizationService.requirePermission(
                operator, ReleaseAssetType.ORCHESTRATION_CONFIG, workflowCode, AssetAction.VIEW);
        workflowSpecialistSkillSelector.validateSkillReferences(
                operator, workflowCode, AssetAction.PUBLISH, aggregate);
    }

    /** 只读快照对已解析 graph 执行 VIEW 权限和当前 Skill 关系重验。 */
    public void validateViewSkillReferences(
            String operator, String workflowCode, WorkflowGraphAggregate aggregate) {
        workflowSpecialistSkillSelector.validateSkillReferences(
                operator, workflowCode, AssetAction.VIEW, aggregate);
    }

    /** 编辑期预览对已解析 graph 执行 EDIT 权限和当前 Skill 关系重验。 */
    public void validatePreviewSkillReferences(
            String operator, String workflowCode, WorkflowGraphAggregate aggregate) {
        workflowSpecialistSkillSelector.validateSkillReferences(
                operator, workflowCode, AssetAction.EDIT, aggregate);
    }

    /**
     * 把公共历史版本中的完整 Workflow graph 恢复为新的可编辑草稿。
     *
     * <p>恢复前重新执行 EDIT 权限、强类型解析、稳定 workflowCode 和 Skill 专员关系校验，再使用当前
     * revision 做 CAS 并递增草稿版本。该操作不读取或修改 PRT/ONLINE 指针，也不执行 Workflow。
     */
    public WorkflowDraftUpdateResult restoreReleasedDraft(
            String operator, String workflowCode, String draftPayloadJson) {
        assetAuthorizationService.requirePermission(
                operator, ReleaseAssetType.ORCHESTRATION_CONFIG, workflowCode, AssetAction.EDIT);
        WorkflowDefinitionDO current = requireWorkflow(workflowCode);
        log.info("Workflow历史版本恢复草稿开始, workflowCode:{}, currentRevision:{}, operator:{}",
                workflowCode, current.getDraftRevision(), operator);
        return updateWorkflowDraftInternal(
                operator, workflowCode, draftPayloadJson, current.getDraftRevision());
    }

    /**
     * CAS 更新 Workflow 草稿。
     *
     * <p>执行顺序：
     * 1. OWNER/ADMIN 权限校验
     * 2. 解析并校验 draftPayloadJson 基础结构（snapshotContractVersion 必须为 2）
     * 3. 对每个 SKILL 节点重验 Skill 存在、当前 operator 可见且属于 Workflow.specialistCode；
     *    任一节点失败则抛 WorkflowSkillReferenceValidationException，草稿不落库
     * 4. 计算 SHA-256 draftDigest
     * 5. 调用 Repository CAS；版本冲突抛 WorkflowDraftConflictException（HTTP 409 语义）
     *
     * @param operator              操作者 userName
     * @param workflowCode          目标 workflowCode
     * @param draftPayloadJson      客户端提交的完整聚合草稿 JSON
     * @param expectedDraftRevision 客户端持有的当前版本号
     * @return 更新成功后的新 revision 和新 digest
     * @throws WorkflowDraftConflictException             版本冲突
     * @throws WorkflowSkillReferenceValidationException Skill 不存在、不可见或不属于绑定专员
     */
    public WorkflowDraftUpdateResult updateWorkflowDraft(
            String operator, String workflowCode,
            String draftPayloadJson, long expectedDraftRevision) {
        assetAuthorizationService.requirePermission(
                operator, ReleaseAssetType.ORCHESTRATION_CONFIG, workflowCode, AssetAction.EDIT);
        assetReleaseEditGuard.requireEditableChange(
                ReleaseAssetType.ORCHESTRATION_CONFIG, workflowCode,
                "UPDATE_WORKFLOW_DRAFT", operator);
        return updateWorkflowDraftInternal(
                operator, workflowCode, draftPayloadJson, expectedDraftRevision);
    }

    /**
     * 执行 Workflow 草稿的完整校验和 CAS 写入。
     *
     * <p>常规编辑入口先执行 ACTIVE change 门禁再调用本方法；common-v2 创建历史恢复变更时，
     * ACTIVE change 尚未写入共享状态，因此由已持有资产锁且已完成 EDIT 鉴权的 restore 入口直接调用。
     * 两条路径都必须经过身份、Skill 关系和完整图编译校验，禁止保存 partial compiled plan。
     */
    private WorkflowDraftUpdateResult updateWorkflowDraftInternal(
            String operator, String workflowCode,
            String draftPayloadJson, long expectedDraftRevision) {

        if (StringUtils.isBlank(draftPayloadJson)) {
            throw new WorkflowControlPlaneException(
                    ERROR_CODE_DRAFT_PAYLOAD_REQUIRED, ERROR_DRAFT_PAYLOAD_REQUIRED,
                    workflowCode, FIELD_DRAFT_PAYLOAD_JSON);
        }

        WorkflowGraphAggregate aggregate = WorkflowGraphAggregateParser.parse(draftPayloadJson);
        validateDraftWorkflowCode(aggregate.getWorkflowCode(), workflowCode);

        workflowSpecialistSkillSelector.validateSkillReferences(
                operator, workflowCode, AssetAction.EDIT, aggregate);
        WorkflowCompiledPlanBuilder.build(aggregate);

        String canonicalDraftPayloadJson = WorkflowGraphAggregateParser.serialize(aggregate);
        String newDigest = ReleaseDigestUtils.sha256(canonicalDraftPayloadJson);
        long now = System.currentTimeMillis();

        boolean updated = workflowDefinitionRepository.compareAndSetDraft(
                workflowCode, canonicalDraftPayloadJson, newDigest,
                aggregate.getSnapshotContractVersion(), operator, now, expectedDraftRevision);
        if (!updated) {
            log.info("Workflow草稿CAS版本冲突, workflowCode:{}, expectedRevision:{}",
                    workflowCode, expectedDraftRevision);
            throw new WorkflowDraftConflictException(workflowCode, expectedDraftRevision);
        }

        long newRevision = expectedDraftRevision + 1;
        log.info("Workflow草稿CAS更新成功, workflowCode:{}, newRevision:{}", workflowCode, newRevision);
        return new WorkflowDraftUpdateResult()
                .setWorkflowCode(workflowCode)
                .setDraftRevision(newRevision)
                .setDraftDigest(newDigest);
    }

    private boolean canView(String operator, String workflowCode) {
        try {
            assetAuthorizationService.requirePermission(
                    operator, ReleaseAssetType.ORCHESTRATION_CONFIG, workflowCode, AssetAction.VIEW);
            return true;
        } catch (AssetPermissionDeniedException exception) {
            log.info("Workflow列表过滤当前操作者不可见资产, workflowCode:{}, operator:{}",
                    workflowCode, operator);
            return false;
        }
    }

    /**
     * 复用 Skill 控制面的受控专员解析器，把请求值规范化为唯一稳定 ID。
     *
     * <p>Workflow 只允许绑定一个专员；多值、未知 ID 或配置中缺失的 ID 都以稳定领域错误失败关闭，
     * 不读取 roleCode alias，也不维护第二份 Workflow 专员配置。
     */
    private String resolveSpecialistCode(String specialistCode) {
        try {
            List<Map<String, Object>> configured = pageConfigService.resolveSpecialists(specialistCode);
            String requestedId = StringUtils.trim(specialistCode);
            if (configured.size() != 1) {
                throw specialistNotAllowed(specialistCode, null);
            }
            String resolvedId = StringUtils.trimToNull(
                    String.valueOf(configured.get(0).get(FIELD_SPECIALIST_ID)));
            if (!StringUtils.equals(requestedId, resolvedId)) {
                throw specialistNotAllowed(specialistCode, null);
            }
            return resolvedId;
        } catch (IllegalArgumentException exception) {
            throw specialistNotAllowed(specialistCode, exception);
        }
    }

    private WorkflowControlPlaneException specialistNotAllowed(
            String specialistCode, RuntimeException cause) {
        log.warn("Workflow创建 specialistCode 未在Skill共用受控专员列表中, specialistCode:{}",
                specialistCode);
        if (cause == null) {
            return new WorkflowControlPlaneException(
                    ERROR_CODE_SPECIALIST_NOT_ALLOWED, ERROR_SPECIALIST_NOT_ALLOWED,
                    null, FIELD_SPECIALIST_CODE);
        }
        return new WorkflowControlPlaneException(
                ERROR_CODE_SPECIALIST_NOT_ALLOWED, ERROR_SPECIALIST_NOT_ALLOWED,
                null, FIELD_SPECIALIST_CODE, cause);
    }

    private void validatePageLimit(int limit) {
        if (limit <= 0) {
            throw new WorkflowControlPlaneException(
                    ERROR_CODE_LIST_LIMIT_INVALID, "Workflow列表limit必须为正数",
                    null, FIELD_LIST_LIMIT);
        }
        if (limit > MAX_WORKFLOW_PAGE_SIZE) {
            throw new WorkflowControlPlaneException(
                    ERROR_CODE_LIST_LIMIT_EXCEEDED, "Workflow列表limit超过服务端上限",
                    null, FIELD_LIST_LIMIT);
        }
    }

    private PageCursor decodePageToken(String pageToken) {
        if (StringUtils.isBlank(pageToken)) {
            return new PageCursor(null, null);
        }
        try {
            String decoded = new String(Base64.getUrlDecoder().decode(pageToken), StandardCharsets.UTF_8);
            String[] parts = decoded.split(PAGE_TOKEN_SEPARATOR, -1);
            if (parts.length != 2) {
                throw new IllegalArgumentException();
            }
            return new PageCursor(Long.valueOf(parts[0]), Long.valueOf(parts[1]));
        } catch (RuntimeException exception) {
            throw new WorkflowControlPlaneException(
                    ERROR_CODE_LIST_PAGE_TOKEN_INVALID, "Workflow列表pageToken非法",
                    null, FIELD_LIST_PAGE_TOKEN);
        }
    }

    private String encodePageToken(Long updateTime, Long id) {
        String raw = updateTime + PAGE_TOKEN_SEPARATOR + id;
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(raw.getBytes(StandardCharsets.UTF_8));
    }

    private WorkflowListItemView toListItem(String operator, WorkflowDefinitionDO workflow) {
        AssetReleaseProjection projection = assetReleasePointerQueryService.projection(
                operator, ReleaseAssetType.ORCHESTRATION_CONFIG, workflow.getWorkflowCode());
        return new WorkflowListItemView()
                .setWorkflow(toView(workflow, projection.getStatus()))
                .setEnvironmentPointers(projection.getEnvironmentPointers());
    }

    private static final class PageCursor {
        private final Long updateTime;
        private final Long id;

        private PageCursor(Long updateTime, Long id) {
            this.updateTime = updateTime;
            this.id = id;
        }
    }

    private WorkflowDefinitionDO requireWorkflow(String workflowCode) {
        WorkflowDefinitionDO workflowDO = workflowDefinitionRepository.findByWorkflowCode(workflowCode);
        if (workflowDO == null) {
            throw workflowNotFound(workflowCode);
        }
        return workflowDO;
    }

    private WorkflowControlPlaneException workflowNotFound(String workflowCode) {
        return new WorkflowControlPlaneException(
                ERROR_CODE_WORKFLOW_NOT_FOUND, ERROR_WORKFLOW_NOT_FOUND,
                workflowCode, FIELD_WORKFLOW_CODE);
    }

    /**
     * 校验草稿 JSON 内嵌 workflowCode 与路径参数完全一致。
     *
     * <p>防止客户端提交内嵌 workflowCode 与路径 workflowCode 不一致的草稿，避免
     * 编译器、发布 Adapter 读取时遭遇 workflowCode 数据污染。
     * 日志只记录路径参数和内嵌字段类型，不泄露 payload 原始内容。
     */
    private void validateDraftWorkflowCode(String embeddedWorkflowCode, String workflowCode) {
        if (!StringUtils.equals(workflowCode, embeddedWorkflowCode)) {
            log.warn("Workflow草稿内嵌workflowCode与路径参数不一致, pathWorkflowCode:{}, embeddedWorkflowCode:{}",
                    workflowCode, embeddedWorkflowCode);
            throw new WorkflowControlPlaneException(
                    ERROR_CODE_DRAFT_WORKFLOW_CODE_MISMATCH,
                    ERROR_DRAFT_WORKFLOW_CODE_MISMATCH,
                    workflowCode, DRAFT_FIELD_WORKFLOW_CODE);
        }
    }

    private String generateWorkflowCode() {
        return WORKFLOW_CODE_PREFIX
                + UUID.randomUUID().toString().replace(UUID_SEPARATOR, EMPTY);
    }

    private String buildInitialDraftPayloadJson(String workflowCode) {
        Map<String, Object> draft = new LinkedHashMap<>();
        draft.put(DRAFT_FIELD_SNAPSHOT_CONTRACT_VERSION, INITIAL_DRAFT_CONTRACT_VERSION);
        draft.put(DRAFT_FIELD_WORKFLOW_CODE, workflowCode);
        draft.put(DRAFT_FIELD_METADATA, new LinkedHashMap<>());
        draft.put(DRAFT_FIELD_NODES, new ArrayList<>());
        draft.put(DRAFT_FIELD_EDGES, new ArrayList<>());
        Map<String, Object> summaryConfig = new LinkedHashMap<>();
        summaryConfig.put(DRAFT_FIELD_PROMPT, EMPTY);
        summaryConfig.put(DRAFT_FIELD_HANDLING_SUGGESTIONS, new ArrayList<>());
        draft.put(DRAFT_FIELD_SUMMARY_CONFIG, summaryConfig);
        return JsonSupport.toJSON(draft);
    }

    private WorkflowReleaseSourceView toReleaseSourceView(WorkflowDefinitionDO workflowDO) {
        return new WorkflowReleaseSourceView()
                .setWorkflowCode(workflowDO.getWorkflowCode())
                .setSpecialistCode(workflowDO.getSpecialistCode())
                .setDisplayName(workflowDO.getDisplayName())
                .setDescription(workflowDO.getDescription())
                .setDraftRevision(workflowDO.getDraftRevision())
                .setDraftDigest(workflowDO.getDraftDigest())
                .setDraftContractVersion(workflowDO.getDraftContractVersion())
                .setDraftPayloadJson(workflowDO.getDraftPayloadJson());
    }

    private WorkflowDefinitionView toView(String operator, WorkflowDefinitionDO workflowDO) {
        AssetReleaseProjection projection = assetReleasePointerQueryService.projection(
                operator, ReleaseAssetType.ORCHESTRATION_CONFIG, workflowDO.getWorkflowCode());
        return toView(workflowDO, projection.getStatus());
    }

    private WorkflowDefinitionView toView(WorkflowDefinitionDO workflowDO, String releaseStatus) {
        return new WorkflowDefinitionView()
                .setWorkflowCode(workflowDO.getWorkflowCode())
                .setSpecialistCode(workflowDO.getSpecialistCode())
                .setDisplayName(workflowDO.getDisplayName())
                .setDescription(workflowDO.getDescription())
                .setStatus(releaseStatus)
                .setDraftRevision(workflowDO.getDraftRevision())
                .setDraftDigest(workflowDO.getDraftDigest())
                .setDraftContractVersion(workflowDO.getDraftContractVersion())
                .setCreatedBy(workflowDO.getCreatedBy())
                .setUpdatedBy(workflowDO.getUpdatedBy())
                .setCreateTime(workflowDO.getCreateTime())
                .setUpdateTime(workflowDO.getUpdateTime());
    }
}
