package dev.a2flow.management.release;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.access.AssetAction;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.lifecycle.WorkflowDefinitionService;
import dev.a2flow.management.lifecycle.domain.WorkflowReleaseSourceView;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowEdge;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowForkNode;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphAggregateParser;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowJoinNode;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowNode;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowRouterCandidate;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowRouterNode;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowSkillNode;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowSummaryNode;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.ReleaseModels.DependencyGateDetail;
import dev.a2flow.management.release.ReleaseModels.GateResult;
import dev.a2flow.management.release.ReleaseModels.PublishResult;
import dev.a2flow.management.release.ReleaseModels.ReleaseArtifact;
import dev.a2flow.management.release.ReleaseModels.ReleasePublishContext;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyPathNode;
import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyReleaseFailure;
import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyReleaseReport;
import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyValidationRequest;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;
import dev.a2flow.management.release.dependency.AssetDependencyReleaseValidator;
import dev.a2flow.management.release.dependency.AssetDependencyType;
import dev.a2flow.management.release.diff.ReleaseDiffContentType;
import dev.a2flow.management.release.diff.ReleaseDiffDocument;
import dev.a2flow.management.release.diff.ReleaseDiffEngine;
import dev.a2flow.management.release.diff.ReleaseDiffEntry;
import dev.a2flow.management.release.diff.ReleaseDiffQuery;
import dev.a2flow.management.release.diff.ReleaseDiffResource;

import lombok.extern.slf4j.Slf4j;

/**
 * Workflow 资产接入 common-v2 发布控制面的领域 Adapter。
 *
 * <p>上游共享发布服务提供可信 operator、目标环境与冻结来源，本类从 WorkflowDefinitionService 读取
 * 当前草稿，调用严格 parser/compiler 生成自包含快照，复用公共 Diff 和递归依赖准出，并把历史 graph
 * 通过 Service CAS 恢复为新草稿。下游公共控制面继续负责 Change、Build、Version、审批、历史和环境
 * 指针。本类不读 Skill 草稿/latest、不执行 Workflow、不创建私有版本表或私有 pointer。
 */
@Component
@Slf4j
public class WorkflowReleaseAssetAdapter extends AbstractReleaseAssetAdapter {

    private static final String SUMMARY_SPECIALIST_CODE = "specialistCode";
    private static final String SUMMARY_DISPLAY_NAME = "displayName";
    private static final String SUMMARY_DRAFT_REVISION = "draftRevision";
    private static final String SUMMARY_PAYLOAD_CONTRACT_VERSION = "payloadContractVersion";
    private static final String SUMMARY_WORKFLOW_SNAPSHOT_CONTRACT_VERSION =
            "workflowSnapshotContractVersion";
    private static final String SUMMARY_COMPILED_PLAN_CONTRACT_VERSION = "compiledPlanContractVersion";
    private static final String SUMMARY_COMPILED_PLAN_DIGEST = "compiledPlanDigest";
    private static final String SUMMARY_ASSET_KEY = "assetKey";
    private static final String SUMMARY_ENVIRONMENT = "environment";
    private static final String SUMMARY_SOURCE_TYPE = "sourceType";
    private static final String SUMMARY_SOURCE_VERSION = "sourceVersion";
    private static final String SUMMARY_DIGEST = "digest";

    private static final String RESOURCE_TYPE_NODE_ADDED = "NODE_ADDED";
    private static final String RESOURCE_TYPE_NODE_REMOVED = "NODE_REMOVED";
    private static final String RESOURCE_TYPE_NODE_MODIFIED = "NODE_MODIFIED";
    private static final String RESOURCE_TYPE_EDGE_ADDED = "EDGE_ADDED";
    private static final String RESOURCE_TYPE_EDGE_REMOVED = "EDGE_REMOVED";
    private static final String RESOURCE_TYPE_EDGE_MODIFIED = "EDGE_MODIFIED";
    private static final String RESOURCE_TYPE_SUMMARY_PROMPT_CHANGED = "SUMMARY_PROMPT_CHANGED";
    private static final String RESOURCE_TYPE_CONTRACT_VERSION = "CONTRACT_VERSION";
    private static final String PATH_NODE_PREFIX = "nodes/";
    private static final String PATH_EDGE_PREFIX = "edges/";
    private static final String PATH_SUMMARY = "summary/config.json";
    private static final String PATH_CONTRACT = "contracts/versions.json";
    private static final String PATH_SUFFIX = ".json";
    private static final String DETAIL_BEFORE = "before";
    private static final String DETAIL_AFTER = "after";
    private static final String DETAIL_NODE_CODE = "code";
    private static final String DETAIL_NODE_TYPE = "type";
    private static final String DETAIL_DISPLAY_NAME = "displayName";
    private static final String DETAIL_SKILL_CODE = "skillCode";
    private static final String DETAIL_NODE_PROMPT = "nodePrompt";
    private static final String DETAIL_QUICK_TRIGGER_MESSAGE = "quickTriggerMessage";
    private static final String DETAIL_ALLOW_SKIP = "allowSkip";
    private static final String DETAIL_ROUTER_PROMPT = "routerPrompt";
    private static final String DETAIL_ROUTER_CONTRACT_VERSION = "routerContractVersion";
    private static final String DETAIL_ROUTER_SCHEMA_DIGEST = "routerSchemaDigest";
    private static final String DETAIL_CANDIDATES = "candidates";
    private static final String DETAIL_MATCHING_NODE_CODE = "matchingNodeCode";
    private static final String DETAIL_JOIN_POLICY = "joinPolicy";
    private static final String DETAIL_MAX_PARALLELISM = "maxParallelism";
    private static final String DETAIL_EDGE_ID = "edgeId";
    private static final String DETAIL_EDGE_TYPE = "type";
    private static final String DETAIL_SOURCE_NODE_CODE = "source";
    private static final String DETAIL_TARGET_NODE_CODE = "target";
    private static final String DETAIL_ROUTE_KEY = "routeKey";
    private static final String DETAIL_BRANCH_KEY = "branchKey";
    private static final String DETAIL_BRANCH_ORDER = "branchOrder";
    private static final String DETAIL_DESCRIPTION = "description";
    private static final String DETAIL_PROMPT = "prompt";
    private static final String DETAIL_DETAIL_SUMMARY_PROMPT = "detailSummaryPrompt";
    private static final String DETAIL_PAYLOAD_CONTRACT_VERSION = "payloadContractVersion";
    private static final String DETAIL_WORKFLOW_SNAPSHOT_CONTRACT_VERSION =
            "workflowSnapshotContractVersion";
    private static final String DETAIL_COMPILED_PLAN_CONTRACT_VERSION = "compiledPlanContractVersion";

    private static final String GATE_WORKFLOW_COMPILED = "WORKFLOW_COMPILED";
    private static final String GATE_WORKFLOW_DEPENDENCIES = "WORKFLOW_DEPENDENCIES";
    private static final String LABEL_WORKFLOW_COMPILED = "Workflow强类型编译";
    private static final String LABEL_WORKFLOW_DEPENDENCIES = "Workflow递归依赖准出";
    private static final String MESSAGE_WORKFLOW_COMPILED = "Workflow graph与compiledPlan契约一致";
    private static final String MESSAGE_DEPENDENCIES_READY = "Workflow全部Skill递归依赖已在目标环境就绪";
    private static final String MESSAGE_SNAPSHOT_VALIDATED =
            "冻结Workflow发布快照已验证，环境指针由publish-center-common-v2推进";
    private static final String ERROR_TRUSTED_CONTEXT_REQUIRED = "Workflow发布操作缺少可信operator上下文";
    private static final String ERROR_SNAPSHOT_PAIR_IDENTITY_INVALID =
            "Workflow Diff快照assetKey不一致";
    private static final String ERROR_DEPENDENCY_NOT_READY = "DEPENDENCY_NOT_READY";
    private static final int DEPENDENCY_DETAILS_CONTRACT_VERSION = 1;

    @Resource
    private AssetAuthorizationService assetAuthorizationService;

    @Resource
    private WorkflowDefinitionService workflowDefinitionService;

    @Resource
    private WorkflowReleasePayloadAdapter payloadAdapter;

    @Resource
    private AssetDependencyReleaseValidator dependencyReleaseValidator;

    @Resource
    private ReleaseDiffEngine releaseDiffEngine;

    @Override
    public ReleaseAssetType assetType() {
        return ReleaseAssetType.ORCHESTRATION_CONFIG;
    }

    /** Workflow 定义创建即拥有完整草稿；common-v2 另行强制不存在历史 Version 才允许首个共享变更。 */
    @Override
    public boolean isInitialEditableChange(AssetSnapshot snapshot) {
        return true;
    }

    /** legacy 入口不具备可信身份，Workflow 必须失败关闭。 */
    @Override
    public AssetSnapshot currentSnapshot(String assetKey, Map<String, String> params) {
        throw new IllegalStateException(ERROR_TRUSTED_CONTEXT_REQUIRED);
    }

    /** 使用服务端可信 operator 读取、重验、编译并冻结当前 Workflow 快照。 */
    @Override
    public AssetSnapshot currentSnapshot(ReleaseOperationContext operationContext,
            String assetKey, Map<String, String> params) {
        requirePermission(operationContext.getOperator(), assetKey, AssetAction.VIEW);
        WorkflowReleaseSourceView source = workflowDefinitionService.getWorkflowReleaseSource(
                operationContext.getOperator(), assetKey);
        payloadAdapter.requireValidSource(source);
        workflowDefinitionService.validateViewSkillReferences(
                operationContext.getOperator(), assetKey,
                WorkflowGraphAggregateParser.parse(source.getDraftPayloadJson()));
        WorkflowReleasePayload payload = payloadAdapter.create(source);
        log.info("Workflow当前发布快照编译完成, workflowCode:{}, draftRevision:{}, operator:{}",
                assetKey, source.getDraftRevision(), operationContext.getOperator());
        return snapshot(assetKey, payload, summaryEntry(
                SUMMARY_SPECIALIST_CODE, source.getSpecialistCode(),
                SUMMARY_DISPLAY_NAME, source.getDisplayName(),
                SUMMARY_DRAFT_REVISION, source.getDraftRevision(),
                SUMMARY_PAYLOAD_CONTRACT_VERSION, payload.getPayloadContractVersion(),
                SUMMARY_WORKFLOW_SNAPSHOT_CONTRACT_VERSION,
                payload.getWorkflowSnapshotContractVersion(),
                SUMMARY_COMPILED_PLAN_CONTRACT_VERSION, payload.getCompiledPlanContractVersion(),
                SUMMARY_COMPILED_PLAN_DIGEST, payload.getCompiledPlanDigest()),
                payload.getCanonicalDigest(), StringUtils.EMPTY);
    }

    /** 真实发布在读取完整草稿前强制 PUBLISH，禁止通过 VIEW 快照入口绕过。 */
    @Override
    public AssetSnapshot currentPublishSnapshot(ReleaseOperationContext operationContext,
            String assetKey, Map<String, String> params) {
        requirePermission(operationContext.getOperator(), assetKey, AssetAction.PUBLISH);
        return currentSnapshot(operationContext, assetKey, params);
    }

    /** Workflow payload 在 currentSnapshot 已完整冻结，Build 阶段只做不可变校验。 */
    @Override
    public AssetSnapshot freezeBuildSnapshot(ReleaseOperationContext operationContext,
            String assetKey, AssetSnapshot current, Map<String, String> params) {
        requirePermission(operationContext.getOperator(), assetKey, AssetAction.PUBLISH);
        payloadAdapter.requirePayload(current, assetKey);
        return current;
    }

    /** legacy 门禁入口不具备可信 operator，必须失败关闭。 */
    @Override
    public List<GateResult> evaluateGates(String assetKey, ReleaseEnvironment environment,
            AssetSnapshot snapshot, Map<String, String> params) {
        throw new IllegalStateException(ERROR_TRUSTED_CONTEXT_REQUIRED);
    }

    /**
     * 发布前重验专员关系和 frozen payload，并委托公共 validator 递归检查目标环境依赖。
     */
    @Override
    public List<GateResult> evaluateGates(ReleaseOperationContext operationContext,
            String assetKey, ReleaseEnvironment environment, AssetSnapshot snapshot,
            Map<String, String> params) {
        requirePermission(operationContext.getOperator(), assetKey, AssetAction.PUBLISH);
        return evaluateWorkflowGates(
                operationContext, assetKey, environment, snapshot, params, false);
    }

    /** 编辑期门禁预览只允许具备 EDIT 权限的操作者，不复用发布授权入口。 */
    @Override
    public List<GateResult> evaluatePreviewGates(ReleaseOperationContext operationContext,
            String assetKey, ReleaseEnvironment environment, AssetSnapshot snapshot,
            ReleaseArtifact artifact, Map<String, String> params) {
        requirePermission(operationContext.getOperator(), assetKey, AssetAction.EDIT);
        return evaluateWorkflowGates(
                operationContext, assetKey, environment, snapshot, params, true);
    }

    private List<GateResult> evaluateWorkflowGates(ReleaseOperationContext operationContext,
            String assetKey, ReleaseEnvironment environment, AssetSnapshot snapshot,
            Map<String, String> params, boolean preview) {
        if (preview) {
            workflowDefinitionService.validatePreviewSkillReferences(
                    operationContext.getOperator(), assetKey,
                    payloadAdapter.requireWorkflowGraph(snapshot, assetKey));
        } else {
            workflowDefinitionService.validateReleaseSkillReferences(
                    operationContext.getOperator(), assetKey,
                    payloadAdapter.requireWorkflowGraph(snapshot, assetKey));
        }
        WorkflowReleasePayload payload = payloadAdapter.requirePayload(snapshot, assetKey);
        DependencyReleaseReport report = dependencyReleaseValidator.validate(
                new DependencyValidationRequest()
                        .setRootAssetType(ReleaseAssetType.ORCHESTRATION_CONFIG.name())
                        .setRootAssetKey(assetKey)
                        .setRequestedEnvironment(environment)
                        .setDependencies(skillDependencies(payload)));
        GateResult compiledGate = gate(GATE_WORKFLOW_COMPILED, LABEL_WORKFLOW_COMPILED,
                true, true, MESSAGE_WORKFLOW_COMPILED);
        GateResult dependencyGate = dependencyGate(report);
        log.info("Workflow发布门禁执行完成, workflowCode:{}, environment:{}, dependencyPassed:{}, "
                        + "failureCount:{}, operator:{}",
                assetKey, environment, report.getPassed(), report.getFailures().size(),
                operationContext.getOperator());
        return List.of(compiledGate, dependencyGate);
    }

    /** 带产物入口与快照门禁保持同一可信 operator 和递归依赖语义。 */
    @Override
    public List<GateResult> evaluateGates(ReleaseOperationContext operationContext,
            String assetKey, ReleaseEnvironment environment, AssetSnapshot snapshot,
            ReleaseArtifact artifact, Map<String, String> params) {
        return evaluateGates(operationContext, assetKey, environment, snapshot, params);
    }

    /** Workflow Diff 按 Node/Edge/Summary/ContractVersion 拆分，行级算法继续复用公共引擎。 */
    @Override
    public ReleaseDiffDocument diff(AssetSnapshot current, AssetSnapshot target, ReleaseDiffQuery query) {
        requireSameSnapshotIdentity(current, target);
        WorkflowReleasePayload currentPayload = payloadAdapter.requirePayload(current, current.getAssetKey());
        WorkflowReleasePayload targetPayload = payloadAdapter.requirePayload(target, target.getAssetKey());
        requireSameSpecialist(currentPayload, targetPayload);
        List<SemanticResource> currentResources = semanticResources(currentPayload);
        List<SemanticResource> targetResources = semanticResources(targetPayload);
        ReleaseDiffDocument document = releaseDiffEngine.compare(
                "当前内容", "目标版本", resources(currentResources), resources(targetResources), query);
        Map<String, SemanticResource> before = indexSemantics(currentResources);
        Map<String, SemanticResource> after = indexSemantics(targetResources);
        for (ReleaseDiffEntry entry : document.getEntries()) {
            SemanticResource beforeResource = before.get(
                    entry.getOldPath() == null ? entry.getPath() : entry.getOldPath());
            SemanticResource afterResource = after.get(entry.getPath());
            entry.setResourceType(diffResourceType(entry))
                    .setDetails(beforeAfterDetails(beforeResource, afterResource));
        }
        return document;
    }

    /** legacy 恢复入口不具备不可变可信上下文，Workflow 必须失败关闭。 */
    @Override
    public void restore(String userName, String assetKey, AssetSnapshot snapshot, Map<String, String> params) {
        throw new IllegalStateException(ERROR_TRUSTED_CONTEXT_REQUIRED);
    }

    /** 历史恢复只把冻结 graph 作为新草稿 CAS 写回，不修改公共环境指针。 */
    @Override
    public void restore(ReleaseOperationContext operationContext,
            String assetKey, AssetSnapshot snapshot, Map<String, String> params) {
        String operator = operationContext.getOperator();
        requirePermission(operator, assetKey, AssetAction.EDIT);
        WorkflowReleasePayload payload = payloadAdapter.requirePayload(snapshot, assetKey);
        String draftPayloadJson = WorkflowGraphAggregateParser.serialize(payload.getWorkflowGraph());
        workflowDefinitionService.restoreReleasedDraft(operator, assetKey, draftPayloadJson);
        log.info("Workflow历史版本已恢复为新草稿, workflowCode:{}, operator:{}", assetKey, operator);
    }

    /** legacy 发布入口携带可变 userName，Workflow 必须失败关闭。 */
    @Override
    public PublishResult deploy(ReleasePublishContext context) {
        throw new IllegalStateException(ERROR_TRUSTED_CONTEXT_REQUIRED);
    }

    /** 发布只信任不可变操作上下文，ReleasePublishContext.userName 不参与授权。 */
    @Override
    public PublishResult deploy(
            ReleaseOperationContext operationContext, ReleasePublishContext context) {
        String operator = operationContext.getOperator();
        requirePermission(operator, context.getAssetKey(), AssetAction.PUBLISH);
        WorkflowReleasePayload payload = payloadAdapter.requirePayload(
                context.getSnapshot(), context.getAssetKey());
        log.info("冻结Workflow发布快照已验证，环境指针由publish-center-common-v2推进, workflowCode:{}, "
                        + "environment:{}, sourceType:{}, sourceVersion:{}, requestId:{}, operator:{}",
                context.getAssetKey(), context.getEnvironment(), context.getSourceType(),
                context.getSourceVersion(), context.getRequestId(), operator);
        return succeeded(MESSAGE_SNAPSHOT_VALIDATED, summaryEntry(
                SUMMARY_ASSET_KEY, context.getAssetKey(),
                SUMMARY_ENVIRONMENT, context.getEnvironment().name(),
                SUMMARY_SOURCE_TYPE, context.getSourceType(),
                SUMMARY_SOURCE_VERSION, context.getSourceVersion(),
                SUMMARY_DIGEST, payload.getCanonicalDigest()));
    }

    private void requirePermission(String operator, String assetKey, AssetAction action) {
        assetAuthorizationService.requirePermission(
                operator, ReleaseAssetType.ORCHESTRATION_CONFIG, assetKey, action);
    }

    private void requireSameSnapshotIdentity(AssetSnapshot current, AssetSnapshot target) {
        String currentAssetKey = current == null ? null : current.getAssetKey();
        String targetAssetKey = target == null ? null : target.getAssetKey();
        if (StringUtils.isBlank(currentAssetKey)
                || !StringUtils.equals(currentAssetKey, targetAssetKey)) {
            throw new WorkflowReleasePayloadValidationException(
                    WorkflowReleasePayloadAdapter.ERROR_CODE_SNAPSHOT_IDENTITY_INVALID,
                    ERROR_SNAPSHOT_PAIR_IDENTITY_INVALID,
                    currentAssetKey,
                    "current.assetKey,target.assetKey");
        }
    }

    private void requireSameSpecialist(
            WorkflowReleasePayload current, WorkflowReleasePayload target) {
        if (!StringUtils.equals(current.getSpecialistCode(), target.getSpecialistCode())) {
            throw new WorkflowReleasePayloadValidationException(
                    WorkflowReleasePayloadAdapter.ERROR_CODE_SNAPSHOT_IDENTITY_INVALID,
                    "Workflow绑定专员不可变",
                    current.getWorkflowCode(),
                    SUMMARY_SPECIALIST_CODE);
        }
    }

    private List<AssetDependencyReference> skillDependencies(WorkflowReleasePayload payload) {
        return payloadAdapter.skillCodes(payload).stream()
                .map(skillCode -> new AssetDependencyReference()
                        .setAssetType(AssetDependencyType.SKILL)
                        .setAssetKey(skillCode))
                .toList();
    }

    private GateResult dependencyGate(DependencyReleaseReport report) {
        List<DependencyGateDetail> details = new ArrayList<>();
        report.getResolvedAssets().forEach(asset -> details.add(resolvedDependencyDetail(asset)));
        report.getFailures().forEach(failure -> details.add(failedDependencyDetail(report, failure)));
        if (Boolean.TRUE.equals(report.getPassed())) {
            return gate(GATE_WORKFLOW_DEPENDENCIES, LABEL_WORKFLOW_DEPENDENCIES,
                    true, true, MESSAGE_DEPENDENCIES_READY)
                    .setDependencyDetailsContractVersion(DEPENDENCY_DETAILS_CONTRACT_VERSION)
                    .setDependencyDetails(details);
        }
        DependencyReleaseFailure failure = report.getFailures().get(0);
        return gate(GATE_WORKFLOW_DEPENDENCIES, LABEL_WORKFLOW_DEPENDENCIES,
                false, true, failure.getMessage())
                .setErrorCode(ERROR_DEPENDENCY_NOT_READY + ":" + failure.getErrorCode().name())
                .setCauseCode(failure.getCauseCode())
                .setFieldPath(StringUtils.defaultIfBlank(
                        failure.getFieldPath(), dependencyFieldPath(failure.getPath())))
                .setDependencyPath(dependencyPath(failure.getPath()))
                .setDependencyDetailsContractVersion(DEPENDENCY_DETAILS_CONTRACT_VERSION)
                .setDependencyDetails(details);
    }

    private DependencyGateDetail resolvedDependencyDetail(ResolvedReleasedAsset asset) {
        return new DependencyGateDetail()
                .setStatus(GATE_PASSED)
                .setAssetType(asset.getAssetType() == null ? null : asset.getAssetType().name())
                .setAssetKey(asset.getAssetKey())
                .setRequestedEnvironment(asset.getRequestedEnvironment() == null
                        ? null : asset.getRequestedEnvironment().name())
                .setResolvedEnvironment(asset.getResolvedEnvironment() == null
                        ? null : asset.getResolvedEnvironment().name())
                .setSourceType(asset.getSourceType() == null ? null : asset.getSourceType().name())
                .setSourceId(asset.getSourceId())
                .setVersion(asset.getVersion())
                .setDigest(asset.getDigest())
                .setCandidate(asset.getCandidate())
                .setRouteReason(asset.getRouteReason() == null ? null : asset.getRouteReason().name())
                .setDependencyPath(dependencyPath(asset.getPath()));
    }

    private DependencyGateDetail failedDependencyDetail(
            DependencyReleaseReport report, DependencyReleaseFailure failure) {
        DependencyPathNode target = lastPathNode(failure.getPath());
        return new DependencyGateDetail()
                .setStatus(GATE_FAILED)
                .setAssetType(target == null ? null : target.getAssetType())
                .setAssetKey(target == null ? null : target.getAssetKey())
                .setRequestedEnvironment(report.getRequestedEnvironment() == null
                        ? null : report.getRequestedEnvironment().name())
                .setErrorCode(failure.getErrorCode() == null ? null : failure.getErrorCode().name())
                .setCauseType(failure.getCauseType())
                .setCauseCode(failure.getCauseCode())
                .setFieldPath(StringUtils.defaultIfBlank(
                        failure.getFieldPath(), dependencyFieldPath(failure.getPath())))
                .setMessage(failure.getMessage())
                .setDependencyPath(dependencyPath(failure.getPath()));
    }

    private DependencyPathNode lastPathNode(List<DependencyPathNode> path) {
        return path == null || path.isEmpty() ? null : path.get(path.size() - 1);
    }

    private List<String> dependencyPath(List<DependencyPathNode> path) {
        return path == null ? List.of() : path.stream()
                .map(this::dependencyPathNode)
                .toList();
    }

    private String dependencyFieldPath(List<DependencyPathNode> path) {
        if (path == null || path.size() < 2) {
            return "dependencies";
        }
        return "dependencies[assetKey=" + path.get(1).getAssetKey() + "]";
    }

    private String dependencyPathNode(DependencyPathNode node) {
        return node.getAssetType() + "/" + node.getAssetKey();
    }

    private List<SemanticResource> semanticResources(WorkflowReleasePayload payload) {
        List<SemanticResource> resources = new ArrayList<>();
        payload.getWorkflowGraph().getNodes().stream()
                .sorted(Comparator.comparing(WorkflowNode::getNodeCode))
                .forEach(node -> {
                    Map<String, Object> details = nodeDetails(node);
                    resources.add(resource(
                            PATH_NODE_PREFIX + node.getNodeCode() + PATH_SUFFIX,
                            node instanceof WorkflowSummaryNode ? details : node,
                            details));
                });
        payload.getWorkflowGraph().getEdges().stream()
                .sorted(Comparator.comparing(WorkflowEdge::getEdgeId))
                .forEach(edge -> resources.add(resource(
                        PATH_EDGE_PREFIX + edge.getEdgeId() + PATH_SUFFIX,
                        edge, edgeDetails(edge))));
        resources.add(resource(PATH_SUMMARY,
                payload.getWorkflowGraph().getSummaryConfig(), summaryConfigDetails(payload)));
        Map<String, Object> contracts = contractDetails(payload);
        resources.add(resource(PATH_CONTRACT, contracts, contracts));
        return resources;
    }

    /** 构造 Summary Diff 详情，缺失的可选详细提示词不伪造 null 字段。 */
    private Map<String, Object> summaryConfigDetails(WorkflowReleasePayload payload) {
        Map<String, Object> details = summaryEntry(
                DETAIL_PROMPT, payload.getWorkflowGraph().getSummaryConfig().getPrompt());
        String detailSummaryPrompt =
                payload.getWorkflowGraph().getSummaryConfig().getDetailSummaryPrompt();
        if (detailSummaryPrompt != null) {
            details.put(DETAIL_DETAIL_SUMMARY_PROMPT, detailSummaryPrompt);
        }
        return details;
    }

    private Map<String, Object> nodeDetails(WorkflowNode node) {
        Map<String, Object> details = summaryEntry(
                DETAIL_NODE_CODE, node.getNodeCode(),
                DETAIL_NODE_TYPE, node.getNodeType().name(),
                DETAIL_PROMPT, null,
                DETAIL_SKILL_CODE, null,
                DETAIL_NODE_PROMPT, null,
                DETAIL_QUICK_TRIGGER_MESSAGE, null,
                DETAIL_ALLOW_SKIP, null,
                DETAIL_ROUTER_PROMPT, null,
                DETAIL_ROUTER_CONTRACT_VERSION, null,
                DETAIL_ROUTER_SCHEMA_DIGEST, null,
                DETAIL_CANDIDATES, List.of(),
                DETAIL_MATCHING_NODE_CODE, null,
                DETAIL_JOIN_POLICY, null,
                DETAIL_MAX_PARALLELISM, null);
        if (node.getDisplayName() != null) {
            details.put(DETAIL_DISPLAY_NAME, node.getDisplayName());
        }
        if (node instanceof WorkflowSkillNode skillNode) {
            details.put(DETAIL_SKILL_CODE, skillNode.getSkillCode());
            details.put(DETAIL_NODE_PROMPT, skillNode.getNodePrompt());
            details.put(DETAIL_QUICK_TRIGGER_MESSAGE, skillNode.getQuickTriggerMessage());
            details.put(DETAIL_PROMPT, skillNode.getNodePrompt());
            details.put(DETAIL_ALLOW_SKIP, skillNode.getControlPolicy() == null
                    ? null : skillNode.getControlPolicy().getAllowSkip());
        } else if (node instanceof WorkflowRouterNode routerNode) {
            details.put(DETAIL_ROUTER_PROMPT, routerNode.getRouterPrompt());
            details.put(DETAIL_PROMPT, routerNode.getRouterPrompt());
            details.put(DETAIL_ROUTER_CONTRACT_VERSION, routerNode.getRouterContractVersion());
            details.put(DETAIL_ROUTER_SCHEMA_DIGEST, routerNode.getRouterSchemaDigest());
            details.put(DETAIL_CANDIDATES, routerCandidates(routerNode));
        } else if (node instanceof WorkflowForkNode forkNode) {
            details.put(DETAIL_MATCHING_NODE_CODE, forkNode.getMatchingNodeCode());
            details.put(DETAIL_JOIN_POLICY, forkNode.getJoinPolicy());
            details.put(DETAIL_MAX_PARALLELISM, forkNode.getMaxParallelism());
        } else if (node instanceof WorkflowJoinNode joinNode) {
            details.put(DETAIL_MATCHING_NODE_CODE, joinNode.getMatchingNodeCode());
            details.put(DETAIL_JOIN_POLICY, joinNode.getJoinPolicy());
        } else if (node instanceof WorkflowSummaryNode summaryNode) {
            details.remove(DETAIL_PROMPT);
            details.remove(DETAIL_NODE_PROMPT);
            details.remove(DETAIL_ROUTER_PROMPT);
            details.put(DETAIL_ALLOW_SKIP, summaryNode.isAllowSkip());
        } else {
            throw new IllegalStateException("Workflow节点类型与领域对象不一致: " + node.getNodeType());
        }
        return details;
    }

    private List<Map<String, Object>> routerCandidates(WorkflowRouterNode routerNode) {
        return routerNode.getCandidates().stream()
                .sorted(Comparator.comparing(WorkflowRouterCandidate::getRouteKey)
                        .thenComparing(WorkflowRouterCandidate::getTargetNodeCode))
                .map(candidate -> summaryEntry(
                        DETAIL_ROUTE_KEY, candidate.getRouteKey(),
                        DETAIL_DESCRIPTION, candidate.getDescription(),
                        DETAIL_TARGET_NODE_CODE, candidate.getTargetNodeCode()))
                .toList();
    }

    private Map<String, Object> edgeDetails(WorkflowEdge edge) {
        return summaryEntry(
                DETAIL_EDGE_ID, edge.getEdgeId(),
                DETAIL_EDGE_TYPE, edge.getEdgeType().name(),
                DETAIL_SOURCE_NODE_CODE, edge.getSourceNodeCode(),
                DETAIL_TARGET_NODE_CODE, edge.getTargetNodeCode(),
                DETAIL_ROUTE_KEY, edge.getRouteKey(),
                DETAIL_BRANCH_KEY, edge.getBranchKey(),
                DETAIL_BRANCH_ORDER, edge.getBranchOrder(),
                DETAIL_DESCRIPTION, edge.getDescription());
    }

    private Map<String, Object> contractDetails(WorkflowReleasePayload payload) {
        return summaryEntry(
                DETAIL_PAYLOAD_CONTRACT_VERSION, payload.getPayloadContractVersion(),
                DETAIL_WORKFLOW_SNAPSHOT_CONTRACT_VERSION,
                payload.getWorkflowSnapshotContractVersion(),
                DETAIL_COMPILED_PLAN_CONTRACT_VERSION,
                payload.getCompiledPlanContractVersion());
    }

    private SemanticResource resource(
            String path, Object value, Map<String, Object> details) {
        String content = JsonSupport.toJSON(value);
        return new SemanticResource(path, details,
                new ReleaseDiffResource()
                        .setPath(path)
                        .setContentType(ReleaseDiffContentType.JSON)
                        .setLanguage("json")
                        .setDigest(ReleaseDigestUtils.sha256(content))
                        .setSize((long) content.getBytes(StandardCharsets.UTF_8).length)
                        .setContent(content));
    }

    private List<ReleaseDiffResource> resources(List<SemanticResource> resources) {
        return resources.stream().map(SemanticResource::resource).toList();
    }

    private Map<String, SemanticResource> indexSemantics(List<SemanticResource> resources) {
        Map<String, SemanticResource> result = new LinkedHashMap<>();
        resources.forEach(resource -> result.put(resource.path(), resource));
        return result;
    }

    private Map<String, Object> beforeAfterDetails(
            SemanticResource before, SemanticResource after) {
        Map<String, Object> details = new LinkedHashMap<>();
        details.put(DETAIL_BEFORE, before == null
                ? null : new LinkedHashMap<>(before.details()));
        details.put(DETAIL_AFTER, after == null
                ? null : new LinkedHashMap<>(after.details()));
        return details;
    }

    private String diffResourceType(ReleaseDiffEntry entry) {
        String path = entry.getPath() == null ? entry.getOldPath() : entry.getPath();
        if (path.startsWith(PATH_NODE_PREFIX)) {
            return switch (entry.getChangeType()) {
                case ADDED -> RESOURCE_TYPE_NODE_ADDED;
                case DELETED -> RESOURCE_TYPE_NODE_REMOVED;
                default -> RESOURCE_TYPE_NODE_MODIFIED;
            };
        }
        if (path.startsWith(PATH_EDGE_PREFIX)) {
            return switch (entry.getChangeType()) {
                case ADDED -> RESOURCE_TYPE_EDGE_ADDED;
                case DELETED -> RESOURCE_TYPE_EDGE_REMOVED;
                default -> RESOURCE_TYPE_EDGE_MODIFIED;
            };
        }
        if (PATH_SUMMARY.equals(path)) {
            return RESOURCE_TYPE_SUMMARY_PROMPT_CHANGED;
        }
        if (PATH_CONTRACT.equals(path)) {
            return RESOURCE_TYPE_CONTRACT_VERSION;
        }
        throw new IllegalStateException("Workflow Diff资源路径不支持: " + path);
    }

    private record SemanticResource(
            String path, Map<String, Object> details, ReleaseDiffResource resource) {
    }
}
