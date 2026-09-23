package dev.a2flow.management.lifecycle;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.access.AssetAction;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.lifecycle.domain.SkillDraft;
import dev.a2flow.management.lifecycle.domain.WorkflowSkillCandidateView;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphAggregate;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowNode;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowSkillNode;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.storage.db.entity.WorkflowDefinitionDO;
import dev.a2flow.management.storage.db.repository.SkillFactoryWorkspaceRepository;
import dev.a2flow.management.storage.db.repository.WorkflowDefinitionRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * Workflow 绑定专员下的 Skill 候选与引用重验服务。
 *
 * <p>候选查询先读取 Workflow 稳定定义获得不可变 specialistCode，再复用 Skill 当前草稿仓储和
 * 当前版本专员关系服务。店长（stable id=1）可以引用任意现存 Skill，其他专员只能引用同专员
 * Skill；Skill 引用不要求操作者拥有该 Skill 的 VIEW 权限，也不授予 Skill 编辑权限。草稿保存、
 * compiledPlan 预览及公共发布 Build/Publish Adapter 复用 {@link #validateSkillReferences}，
 * 逐节点重新读取当前事实并失败关闭。
 *
 * <p>上游：WorkflowDefinitionService、后续 Workflow 控制面 RPC 和 WorkflowReleaseAssetAdapter。
 * <p>下游：WorkflowDefinitionRepository、SkillFactoryWorkspaceRepository、
 * SkillFactorySpecialistRelationService、AssetAuthorizationService。
 * <p>不负责：复制 Skill 内容、保存 Skill 版本或包、PINNED/TRACK 策略、发布状态机、运行态执行。
 */
@Service
@Slf4j
public class WorkflowSpecialistSkillSelector {

    private static final String ERROR_CODE_CANDIDATE_LIMIT_EXCEEDED =
            "WORKFLOW_SKILL_CANDIDATE_LIMIT_EXCEEDED";
    private static final String ERROR_CODE_SKILL_NOT_FOUND = "WORKFLOW_SKILL_NOT_FOUND";
    private static final String ERROR_CODE_SKILL_NOT_BELONG = "SKILL_NOT_BELONG_TO_SPECIALIST";
    private static final String ERROR_CODE_WORKFLOW_NOT_FOUND = "WORKFLOW_NOT_FOUND";
    private static final String ERROR_CODE_SPECIALIST_CODE_REQUIRED = "WORKFLOW_SPECIALIST_CODE_REQUIRED";
    private static final String ERROR_WORKFLOW_NOT_FOUND = "Workflow不存在";
    private static final String ERROR_SPECIALIST_CODE_REQUIRED = "Workflow绑定specialistCode不能为空";
    private static final String ERROR_SKILL_NOT_FOUND = "Workflow引用的Skill不存在";
    private static final String ERROR_SKILL_NOT_BELONG = "Workflow引用的Skill不属于绑定专员";
    private static final String ERROR_CANDIDATE_QUERY_LIMIT_EXCEEDED =
            "Workflow候选Skill查询超过服务端有界扫描上限";
    private static final String FIELD_PATH_CANDIDATES = "skills";
    private static final String FIELD_PATH_WORKFLOW_CODE = "workflowCode";
    private static final String FIELD_PATH_SPECIALIST_CODE = "specialistCode";
    private static final String FIELD_PATH_NODES_PREFIX = "nodes[";
    private static final String FIELD_PATH_SKILL_CODE_SUFFIX = "].skillCode";
    private static final String STORE_MANAGER_SPECIALIST_CODE = "1";
    private static final int SKILL_DRAFT_PAGE_SIZE = 100;
    private static final int MAX_SKILL_DRAFT_SCAN_PAGES = 100;
    private static final int MAX_SKILL_CANDIDATE_COUNT = 1000;

    @Resource
    private WorkflowDefinitionRepository workflowDefinitionRepository;

    @Resource
    private SkillFactoryWorkspaceRepository skillFactoryWorkspaceRepository;

    @Resource
    private SkillFactorySpecialistRelationService specialistRelationService;

    @Resource
    private AssetAuthorizationService assetAuthorizationService;

    /**
     * 查询指定 Workflow 当前可选择的 Skill。
     *
     * <p>查询不接受客户端 specialistCode，而是从 workflow_definition 读取绑定值。入口只校验
     * Workflow VIEW 权限；店长返回全部现存 Skill，其他专员按当前版本所属专员关系过滤。
     */
    public List<WorkflowSkillCandidateView> getSkillsForWorkflow(String operator, String workflowCode) {
        assetAuthorizationService.requirePermission(
                operator, ReleaseAssetType.ORCHESTRATION_CONFIG, workflowCode, AssetAction.VIEW);
        WorkflowDefinitionDO workflow = requireWorkflow(workflowCode);
        String specialistCode = requireSpecialistCode(workflowCode, workflow.getSpecialistCode());
        Map<String, WorkflowSkillCandidateView> candidatesBySkillCode = new LinkedHashMap<>();
        Long cursorUpdateTime = null;
        Long cursorId = null;
        int scannedPages = 0;
        while (true) {
            if (scannedPages >= MAX_SKILL_DRAFT_SCAN_PAGES) {
                throw candidateLimitExceeded(workflowCode);
            }
            scannedPages++;
            List<SkillDraft> page = skillFactoryWorkspaceRepository.listDraftPage(
                    cursorUpdateTime, cursorId, SKILL_DRAFT_PAGE_SIZE);
            // 店长无需关系查询；其他专员按当前扫描页批量读取精确草稿版本的所属关系。
            Map<Long, List<String>> specialistIds = isStoreManager(specialistCode)
                    ? Collections.emptyMap() : specialistRelationService.specialistIdsByDrafts(page);
            for (SkillDraft skillDraft : page) {
                if (!isStoreManager(specialistCode)
                        && !specialistIds.getOrDefault(skillDraft.getId(), Collections.emptyList())
                                .contains(specialistCode)) {
                    continue;
                }
                candidatesBySkillCode.putIfAbsent(skillDraft.getSkillCode(), toCandidate(skillDraft));
                if (candidatesBySkillCode.size() > MAX_SKILL_CANDIDATE_COUNT) {
                    throw candidateLimitExceeded(workflowCode);
                }
            }
            if (page.size() < SKILL_DRAFT_PAGE_SIZE) {
                break;
            }
            SkillDraft last = page.get(page.size() - 1);
            cursorUpdateTime = last.getUpdateTime();
            cursorId = last.getId();
            if (scannedPages == MAX_SKILL_DRAFT_SCAN_PAGES) {
                List<SkillDraft> overflow = skillFactoryWorkspaceRepository.listDraftPage(
                        cursorUpdateTime, cursorId, 1);
                if (overflow.isEmpty()) {
                    break;
                }
                throw candidateLimitExceeded(workflowCode);
            }
        }
        List<WorkflowSkillCandidateView> candidates = new ArrayList<>(candidatesBySkillCode.values());
        candidates.sort(Comparator.comparing(WorkflowSkillCandidateView::getSkillCode));
        log.info("Workflow Skill候选查询完成, workflowCode:{}, specialistCode:{}, managerMode:{}, "
                        + "operator:{}, count:{}",
                workflowCode, specialistCode, isStoreManager(specialistCode), operator, candidates.size());
        return candidates;
    }

    /**
     * 对强类型 Workflow 草稿中的全部 Skill 引用执行保存及发布共用重验。
     *
     * <p>每次调用都重新读取 Skill 当前存在性，并按店长全量或普通专员关系规则重验，不信任候选
     * 查询结果，不使用草稿或 latest 发布事实降级。任一节点失败即抛类型化异常，调用方不得
     * 持久化或创建 Build；被引用 Skill 的操作者 VIEW 权限不属于本规则。
     */
    public void validateSkillReferences(String operator, String workflowCode,
            AssetAction workflowAction, WorkflowGraphAggregate aggregate) {
        assetAuthorizationService.requirePermission(
                operator, ReleaseAssetType.ORCHESTRATION_CONFIG, workflowCode, workflowAction);
        WorkflowDefinitionDO workflow = requireWorkflow(workflowCode);
        String specialistCode = requireSpecialistCode(workflowCode, workflow.getSpecialistCode());
        List<WorkflowNode> nodes = aggregate.getNodes();
        for (int index = 0; index < nodes.size(); index++) {
            WorkflowNode node = nodes.get(index);
            if (!(node instanceof WorkflowSkillNode)) {
                continue;
            }
            WorkflowSkillNode skillNode = (WorkflowSkillNode) node;
            validateSkillReference(specialistCode, skillNode, index);
        }
        log.info("Workflow草稿Skill引用重验通过, workflowCode:{}, specialistCode:{}, operator:{}",
                aggregate.getWorkflowCode(), specialistCode, operator);
    }

    private void validateSkillReference(String specialistCode, WorkflowSkillNode skillNode, int nodeIndex) {
        String skillCode = skillNode.getSkillCode();
        String fieldPath = FIELD_PATH_NODES_PREFIX + nodeIndex + FIELD_PATH_SKILL_CODE_SUFFIX;
        SkillDraft skillDraft = skillFactoryWorkspaceRepository.findDraftBySkillCode(skillCode);
        if (skillDraft == null) {
            log.warn("Workflow引用Skill不存在, nodeCode:{}, skillCode:{}, specialistCode:{}",
                    skillNode.getNodeCode(), skillCode, specialistCode);
            throw validationFailure(ERROR_CODE_SKILL_NOT_FOUND, ERROR_SKILL_NOT_FOUND,
                    skillNode, specialistCode, fieldPath);
        }
        if (!isEligibleForWorkflowSpecialist(specialistCode, skillDraft)) {
            log.warn("Workflow引用Skill专员关系重验失败, nodeCode:{}, skillCode:{}, specialistCode:{}",
                    skillNode.getNodeCode(), skillCode, specialistCode);
            throw validationFailure(ERROR_CODE_SKILL_NOT_BELONG, ERROR_SKILL_NOT_BELONG,
                    skillNode, specialistCode, fieldPath);
        }
    }

    /**
     * 按 Workflow 稳定专员身份判断 Skill 是否可被引用。
     * 店长直接命中，普通专员只读取当前版本受控关系；不读取操作者 Skill 权限或历史发布事实。
     */
    private boolean isEligibleForWorkflowSpecialist(String specialistCode, SkillDraft skillDraft) {
        return isStoreManager(specialistCode)
                || specialistRelationService.specialistIds(skillDraft).contains(specialistCode);
    }

    private boolean isStoreManager(String specialistCode) {
        return STORE_MANAGER_SPECIALIST_CODE.equals(specialistCode);
    }

    private WorkflowControlPlaneException candidateLimitExceeded(String workflowCode) {
        log.warn("Workflow候选Skill查询超过完整响应上限, workflowCode:{}, maxCandidateCount:{}",
                workflowCode, MAX_SKILL_CANDIDATE_COUNT);
        return new WorkflowControlPlaneException(
                ERROR_CODE_CANDIDATE_LIMIT_EXCEEDED, ERROR_CANDIDATE_QUERY_LIMIT_EXCEEDED,
                workflowCode, FIELD_PATH_CANDIDATES);
    }

    private WorkflowSkillReferenceValidationException validationFailure(String errorCode,
            String message, WorkflowSkillNode skillNode, String specialistCode, String fieldPath) {
        return new WorkflowSkillReferenceValidationException(errorCode, message,
                skillNode.getNodeCode(), skillNode.getSkillCode(), specialistCode, fieldPath);
    }

    private WorkflowDefinitionDO requireWorkflow(String workflowCode) {
        WorkflowDefinitionDO workflow = workflowDefinitionRepository.findByWorkflowCode(workflowCode);
        if (workflow == null) {
            throw new WorkflowControlPlaneException(
                    ERROR_CODE_WORKFLOW_NOT_FOUND, ERROR_WORKFLOW_NOT_FOUND,
                    workflowCode, FIELD_PATH_WORKFLOW_CODE);
        }
        return workflow;
    }

    private String requireSpecialistCode(String workflowCode, String specialistCode) {
        if (StringUtils.isBlank(specialistCode)) {
            throw new WorkflowControlPlaneException(
                    ERROR_CODE_SPECIALIST_CODE_REQUIRED, ERROR_SPECIALIST_CODE_REQUIRED,
                    workflowCode, FIELD_PATH_SPECIALIST_CODE);
        }
        return specialistCode;
    }

    private WorkflowSkillCandidateView toCandidate(SkillDraft skillDraft) {
        return new WorkflowSkillCandidateView()
                .setSkillCode(skillDraft.getSkillCode())
                .setDisplayName(StringUtils.defaultIfBlank(
                        skillDraft.getSkillNameCn(), skillDraft.getSkillNameEn()))
                .setDescription(skillDraft.getSkillDescription())
                .setStatus(skillDraft.getStatus());
    }
}
