package dev.a2flow.management.aicoding;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Properties;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.eclipse.jgit.diff.DiffAlgorithm;
import org.eclipse.jgit.diff.DiffFormatter;
import org.eclipse.jgit.diff.EditList;
import org.eclipse.jgit.diff.RawText;
import org.eclipse.jgit.diff.RawTextComparator;
import org.springframework.stereotype.Component;

import com.google.common.collect.Lists;
import com.google.common.collect.Maps;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.aicoding.domain.SkillFactoryPatchApplyResult;
import dev.a2flow.management.aicoding.domain.SkillFactoryPatchMergePlan;
import dev.a2flow.management.aicoding.domain
        .SkillFactoryPreparedPatchChange;

import dev.a2flow.management.config.SkillFactoryConfigReader;
import dev.a2flow.management.config.WorkspaceChangeGuardConfig;
import dev.a2flow.management.event.AiCodingEventPayload;
import dev.a2flow.management.event.AiCodingEventPayloadCodec;
import dev.a2flow.management.event.AiCodingEventPayloadFactory;
import dev.a2flow.management.fileguard.WorkspaceModelContext;
import dev.a2flow.management.fileguard.WorkspaceSnapshot;
import dev.a2flow.management.fileguard.WorkspaceSnapshotDiff;
import dev.a2flow.management.fileguard.WorkspaceSnapshotService;
import dev.a2flow.management.lifecycle.domain.SkillDraft;
import dev.a2flow.management.observation.AgentObservationService;

import dev.a2flow.management.storage.db.entity.AgentObservationEventDO;

import dev.a2flow.management.storage.db.repository.SkillFactoryWorkspaceFileRepository;
import dev.a2flow.management.storage.db.repository.SkillFactoryWorkspaceRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory AI Coding 文件与 patch 服务。
 *
 * <p>该服务只负责 M 端 AI Coding 的受控 workspace 文件读取、patch 草稿暂存、审批门禁、
 * 确认应用和丢弃。`workspaceId` 等于 `skillCode`，只表示 Skill 工作区身份目录；AI Coding
 * 真正可读写的工程根固定为该身份目录下的 `preprod/current`。
 * 上游由 `AiCodingReActEngine` 调用，下游只写入 agent-service 管控的可编辑工程目录。它不负责
 * adviser 业务鉴权、SkillFactory lifecycle 方法分发、组件中心、包发布或 LangBridge/OpenClaw
 * 注册。依赖同步 Tool 把可信依赖、组件和业务能力说明返回给模型后，模型仍须通过本服务的普通
 * {@code propose_patch} 生成可审阅 Patch；本服务不查询资产目录、不执行组件渲染或业务能力调用。
 */
@Slf4j
@Component
public class SkillFactoryAiCodingService {

    private static final Pattern WORKSPACE_ID_PATTERN = Pattern.compile("[A-Za-z0-9._-]+");
    private static final String INTERNAL_STATE_DIR = ".skillfactory";
    private static final String PATCH_STORE_DIR = "patches";
    private static final String LEGACY_PATCH_STORE_DIR = "_patches";
    private static final String PREPROD_DIR = "preprod";
    private static final String CURRENT_DIR = "current";
    private static final String SKILL_MD_FILE = "SKILL.md";
    private static final String DRAFT_STATE_FILE = ".draft-state.properties";
    private static final String DRAFT_STATE_KEY_STATUS = "draftStatus";
    private static final String DRAFT_STATE_KEY_BASE_VERSION = "baseVersion";
    private static final String DRAFT_STATE_KEY_SEALED_VERSION = "sealedVersion";
    private static final String DRAFT_STATUS_EDITING = "EDITING";
    private static final String DRAFT_STATUS_SEALED = "SEALED";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_SESSION_ID = "sessionId";
    private static final String FIELD_MESSAGE = "message";
    private static final String FIELD_USER_NAME = "userName";
    private static final String FIELD_PATCH_ID = "patchId";
    private static final String FIELD_ACTION = "action";

    private static final String FIELD_DECISION = "decision";
    private static final String FIELD_DECISION_MESSAGE = "decisionMessage";
    private static final String FIELD_IDEMPOTENCY_KEY = "idempotencyKey";
    private static final String FIELD_WORKSPACE_ROOT = "workspaceRoot";
    private static final String FIELD_TRACE_ID = "traceId";
    private static final String FIELD_RUN_ID = "runId";
    private static final String FIELD_CONVERSATION_ID = "conversationId";
    private static final String FIELD_MESSAGE_ID = "messageId";
    private static final String FIELD_BIZ_KEY = "bizKey";
    private static final String FIELD_SURFACE_ID = "surfaceId";
    private static final String FIELD_SOURCE_COMPONENT_ID = "sourceComponentId";
    private static final String FIELD_ACTION_CODE = "actionCode";
    private static final String FIELD_ACTION_PARAMS = "actionParams";
    private static final String FIELD_REFERENCE_COMPONENT_CODES = "referenceComponentCodes";
    private static final String FIELD_COMPONENT_REFS = "componentRefs";
    private static final String FIELD_SKILL_NAME = "skillName";
    private static final String FIELD_ACCEPTANCE_CRITERIA = "acceptanceCriteria";
    private static final String FIELD_OPERATOR = "operator";
    private static final String FIELD_PATH = "path";
    private static final String FIELD_CHANGE_TYPE = "changeType";
    private static final String FIELD_CHANGED_FILES = "changedFiles";
    private static final String FIELD_SELECTED_FILE_PATHS = "selectedFilePaths";
    private static final String FIELD_APPLIED_FILES = "appliedFiles";
    private static final String FIELD_CONTENT = "content";
    private static final String FIELD_DIFF_PREVIEW = "diffPreview";
    private static final String FIELD_PATCH_STATUS = "patchStatus";
    private static final String FIELD_RISK_ITEMS = "riskItems";
    private static final String FIELD_SUMMARY = "summary";
    private static final String FIELD_BASE_FILE_TREE_DIGEST = "baseFileTreeDigest";
    private static final String FIELD_BASE_FILE_DIGEST_MAP = "baseFileDigestMap";
    private static final String FIELD_BASE_FILE_CONTENT_MAP = "baseFileContentMap";
    private static final String FIELD_FILE_TREE_DIGEST = "fileTreeDigest";
    private static final String FIELD_CONFLICT_FILES = "conflictFiles";
    private static final String FIELD_WORKSPACE_SNAPSHOT = "workspaceSnapshot";
    private static final String FIELD_PREVIOUS_FILE_TREE_DIGEST = "previousFileTreeDigest";
    private static final String FIELD_CURRENT_FILE_TREE_DIGEST = "currentFileTreeDigest";
    private static final String FIELD_DIFF = "diff";

    private static final String FIELD_CREATE_TIME = "createTime";
    private static final String FIELD_UPDATE_TIME = "updateTime";
    private static final String FIELD_MESSAGE_LENGTH = "messageLength";
    private static final String FIELD_KEYS = "keys";
    private static final String STATUS_PROPOSED = "PROPOSED";
    private static final String STATUS_APPLIED = "APPLIED";
    private static final String STATUS_DISCARDED = "DISCARDED";
    private static final String ERROR_PATCH_ALREADY_APPLIED = "patch already applied";
    private static final String ERROR_PATCH_ALREADY_DISCARDED = "patch already discarded";
    private static final String ERROR_PATCH_STATUS_UNSUPPORTED = "unsupported patch status: ";
    private static final String IDEMPOTENCY_HUMAN_DECISION_PREFIX = "patch-human-decision:";
    private static final String IDEMPOTENCY_PATCH_RESULT_PREFIX = "patch-command-result:";
    private static final String CHANGE_TYPE_ADD = "ADD";
    private static final String CHANGE_TYPE_MODIFY = "MODIFY";
    private static final String CHANGE_TYPE_DELETE = "DELETE";

    private static final String DEFAULT_CONFIRM_RISK_ITEM = "确认业务字段和前端组件协议后再应用 patch";
    private static final String MANAGED_DEPENDENCY_GUIDANCE_PATCH_RISK =
            "请确认 SKILL.md 受管依赖、组件和业务能力说明的具体 Diff 后再应用";

    private static final String DELETE_FILE_RISK_ITEM = "检测到删除文件变更，需人工确认后应用";
    private static final String BIZ_KEY_HADES_SKILL_FACTORY = "HADES_SKILL_FACTORY";
    private static final String TOOL_PROPOSE_PATCH = "propose_patch";
    private static final String AI_CODING_ACTION_CHAT = "CODING_CHAT";
    private static final String AI_CODING_ACTION_PROPOSE_PATCH = "PROPOSE_PATCH";
    private static final String AI_CODING_ACTION_CONFIRM_PATCH = "CODING_PATCH_CONFIRM";
    private static final String AI_CODING_ACTION_DISCARD_PATCH = "CODING_PATCH_DISCARD";
    private static final String RISK_LEVEL_MEDIUM = "MEDIUM";
    private static final String DECISION_APPROVE = "approve";
    private static final String DECISION_REJECT = "reject";
    private static final String OBS_TYPE_HUMAN_DECISION = "human_decision_observation";
    private static final String OBS_TYPE_COMMAND_RESULT = "command_result_observation";
    private static final String OBS_TYPE_UI_ACTION = "ui_action_observation";
    private static final String OBS_TYPE_WORKSPACE_SNAPSHOT = "workspace_snapshot_observation";
    private static final String OBS_TYPE_WORKSPACE_CHANGED = "workspace_changed_observation";

    private static final String OBS_SOURCE_CONFIRM_PATCH = "confirm_patch";
    private static final String OBS_SOURCE_DISCARD_PATCH = "discard_patch";
    private static final String OBS_SOURCE_AUTO_APPLY = "auto_apply";
    private static final String OBS_SOURCE_A2UI_ACTION = "a2ui_action";
    private static final String OBS_SOURCE_WORKSPACE_MODEL_CONTEXT = "workspace_model_context";
    private static final String OBS_SOURCE_WORKSPACE_CHANGE_GUARD = "workspace_change_guard";
    private static final String ERROR_CODE_PATCH_CONTENT_CONFLICT = "PATCH_CONTENT_CONFLICT";
    private static final String ERROR_PATCH_CONTENT_CONFLICT =
            "选中文件与 Patch 的内容状态存在冲突，未写入任何文件。请处理冲突后重新生成 Patch。";
    private static final String ERROR_WORKSPACE_MODEL_CONTEXT_FAILED =
            "failed to build current workspace model context";
    private static final String ERROR_WORKSPACE_IDENTITY_MISMATCH =
            "workspaceId must be equal to skillCode";
    private static final String ERROR_WORKSPACE_NOT_REGISTERED =
            "workspace is not registered";
    private static final String ERROR_WORKSPACE_DIRECTORY_MISSING =
            "registered workspace directory does not exist";
    private static final String DEFAULT_APPROVE_MESSAGE = "用户批准应用 AI Coding patch。";
    private static final String DEFAULT_REJECT_MESSAGE = "用户拒绝应用 AI Coding patch。";
    private static final String ACTION_CONFIRM_REQUIREMENT = "confirmRequirement";
    private static final String ACTION_SELECT_COMPONENT_REFS = "selectComponentRefs";
    private static final String ACTION_SUBMIT_MISSING_INFO = "submitMissingInfo";
    private static final String ACTION_CONFIRM_ACCEPTANCE_CRITERIA = "confirmAcceptanceCriteria";
    private static final String A2UI_VERSION = "v1.0";
    private static final String A2UI_SURFACE_PREFIX = "requirement_confirm_";
    private static final String A2UI_COMPONENT_REQUIREMENT_CONFIRM = "requirementConfirmButton";
    private static final String A2UI_COMPONENT_COMPONENT_SELECT = "componentRefSelector";
    private static final Set<String> AUTHORING_ACTION_WHITELIST = Set.of(
            ACTION_CONFIRM_REQUIREMENT,
            ACTION_SELECT_COMPONENT_REFS,
            ACTION_SUBMIT_MISSING_INFO,
            ACTION_CONFIRM_ACCEPTANCE_CRITERIA);
    private static final Pattern FORBIDDEN_ACTION_FIELD_PATTERN =
            Pattern.compile("(?i).*(url|rpc|sql|script|token|cookie|secret|password|sellerId|accessproxy).*");
    private static final int RECENT_OBSERVATION_LIMIT = 10;
    private static final int DIFF_PREVIEW_CONTEXT_LINES = 3;
    private static final String ERROR_DRAFT_SEALED = "current draft is sealed, create a new change first";
    private static final String ERROR_WORKSPACE_ROOT_UNAVAILABLE =
            "SkillFactory workspace root is unavailable";

    private final Path fallbackWorkspaceRoot;

    @Resource
    private AgentObservationService agentObservationService;
    @Resource
    private SkillFactoryConfigReader skillFactoryConfigReader;
    @Resource
    private AiCodingEventPayloadFactory aiCodingEventPayloadFactory;
    @Resource
    private AiCodingEventPayloadCodec aiCodingEventPayloadCodec;
    @Resource
    private WorkspaceSnapshotService workspaceSnapshotService;
    @Resource
    private SkillFactoryPatchMergeService skillFactoryPatchMergeService;
    @Resource
    private SkillFactoryWorkspaceRepository workspaceRepository;
    @Resource
    private SkillFactoryWorkspaceFileRepository workspaceFileRepository;
    @Resource
    private SkillFactoryManagedSkillDocumentService managedSkillDocumentService;
    /**
     * Spring 运行态构造入口。
     *
     * <p>workspace 必须在依赖注入完成后由 {@link SkillFactoryConfigReader} 统一解析，不能在构造阶段从一个
     * 尚未装配的空配置对象读取，否则服务启动时会因空路径失败。
     */
    public SkillFactoryAiCodingService() {
        this.fallbackWorkspaceRoot = null;
    }
    /**
     * 测试或独立调用使用的显式 workspace 构造入口。
     */
    public SkillFactoryAiCodingService(Path defaultWorkspaceRoot) {
        this.fallbackWorkspaceRoot = Objects.requireNonNull(defaultWorkspaceRoot,
                ERROR_WORKSPACE_ROOT_UNAVAILABLE).toAbsolutePath().normalize();
    }

    /**
     * 为 AI Coding chat 准备受控工作目录。
     *
     * <p>该方法要求 lifecycle 已经注册 workspace，并已经创建 `preprod/current` 可编辑目录。B 端
     * Chat RPC 不具备 M 端可信 KSN，因此这里只校验工作区身份和编辑状态；页面发送入口由
     * {@code ASSET_ACCESS_GET} 控制。Chat 只允许创建身份目录内的隐藏 Patch 控制目录，不能补建
     * workspace 身份或可编辑工程目录。
     */
    public Path prepareWorkingDir(Map<String, String> params) {
        SkillFactoryAiCodingContext context = buildContext(params);
        requireRegisteredWorkspace(context);
        requireDraftEditable(context, AI_CODING_ACTION_CHAT);
        try {
            Path identityDir = identityWorkspaceDir(context.workspaceId, context.workspaceRoot);
            Path workingDir = workingDir(context);
            Path patchesDir = patchesDir(context);
            Files.createDirectories(patchesDir);
            log.info("SkillFactoryAiCodingService准备AI Coding工作区完成, context={}, workspaceRoot={}, "
                            + "identityDir={}, workingDir={}, patchesDir={}",
                    contextSummary(context), context.workspaceRoot, identityDir, workingDir, patchesDir);
            return workingDir;
        } catch (IOException e) {
            log.error("SkillFactoryAiCodingService准备AI Coding工作区异常, context={}",
                    contextSummary(context), e);
            throw new IllegalStateException("prepare ai coding workspace failed: " + e.getMessage(), e);
        }
    }

    /**
     * 将模型提出的文件变更写入 patch 暂存区。
     *
     * <p>该方法是 `propose_patch` 工具的落点，只校验路径、生成 diff 预览和 patch JSON，
     * 不直接写 working 文件；操作者预览后显式应用或丢弃 patch。
     */
    public String proposePatch(Map<String, String> params, Map<String, Object> patchInput) {
        return proposePatchInternal(params, patchInput);
    }

    private String proposePatchInternal(Map<String, String> params, Map<String, Object> patchInput) {
        long startTime = System.currentTimeMillis();
        SkillFactoryAiCodingContext context = buildContext(params);
        Map<String, Object> safeInput = Objects.isNull(patchInput) ? Maps.newHashMap() : patchInput;

        try {
            requireRegisteredWorkspace(context);
            requireDraftEditable(context, AI_CODING_ACTION_PROPOSE_PATCH);
            Path workingDir = workingDir(context);
            Path patchesDir = patchesDir(context);
            Files.createDirectories(patchesDir);

            String patchId = buildPatchId(context.sessionId);
            List<Map<String, Object>> changedFiles = normalizeChangedFiles(safeInput, workingDir, context);
            validateManagedDependencyChange(workingDir, changedFiles);
            WorkspaceSnapshot baseSnapshot = workspaceSnapshotService.capture(workingDir);
            List<String> changedFilePaths = changedFilePaths(changedFiles);
            Map<String, String> baseFileDigestMap =
                    workspaceSnapshotService.fileDigestMapForPaths(baseSnapshot, changedFilePaths);
            Map<String, String> baseFileContentMap =
                    workspaceSnapshotService.fileContentMapForPaths(
                            workingDir, baseSnapshot, changedFilePaths);
            List<String> explicitRiskItems = normalizeExplicitRiskItems(safeInput.get(FIELD_RISK_ITEMS));

            List<String> riskItems = explicitRiskItems;
            Map<String, Object> patch = Maps.newHashMap();
            patch.put(FIELD_PATCH_ID, patchId);
            patch.put(FIELD_WORKSPACE_ID, context.workspaceId);
            patch.put(FIELD_SESSION_ID, context.sessionId);
            patch.put(FIELD_OPERATOR, context.userName);
            patch.put(FIELD_PATCH_STATUS, STATUS_PROPOSED);
            patch.put(FIELD_SUMMARY, StringUtils.defaultString(MapUtils.getString(safeInput, FIELD_SUMMARY)));
            patch.put(FIELD_BASE_FILE_TREE_DIGEST, baseSnapshot.getFileTreeDigest());
            patch.put(FIELD_BASE_FILE_DIGEST_MAP, baseFileDigestMap);
            patch.put(FIELD_BASE_FILE_CONTENT_MAP, baseFileContentMap);
            patch.put(FIELD_CHANGED_FILES, changedFiles);
            patch.put(FIELD_RISK_ITEMS, riskItems);

            patch.put(FIELD_TRACE_ID, context.traceId);
            patch.put(FIELD_CREATE_TIME, System.currentTimeMillis());

            writePatch(patchesDir, patchId, patch);

            AiCodingEventPayload payload = aiCodingEventPayloadFactory.patchProposed(context.workspaceId,
                    context.sessionId, patchId, context.traceId, patchEventView(patch, changedFiles));
            enrichAuthoringMeta(payload, context, null);

            return aiCodingEventPayloadCodec.toJson(payload);
        } catch (Exception e) {
            log.error("SkillFactoryAiCodingService propose_patch异常, context={}, inputKeys={}",
                    contextSummary(context), safeInput.keySet(), e);
            throw new IllegalStateException("propose patch failed: " + e.getMessage(), e);
        }
    }

    private boolean validateManagedDependencyChange(Path workingDir, List<Map<String, Object>> changedFiles)
            throws IOException {
        boolean managedGuidanceChanged = false;
        for (Map<String, Object> change : changedFiles) {
            String relativePath = MapUtils.getString(change, FIELD_PATH);
            if (!StringUtils.equalsIgnoreCase(SKILL_MD_FILE, relativePath)) {
                continue;
            }
            String oldContent = readIfExists(resolveWorkingPath(workingDir, relativePath));
            String changeType = MapUtils.getString(change, FIELD_CHANGE_TYPE);
            String newContent = CHANGE_TYPE_DELETE.equalsIgnoreCase(changeType)
                    ? StringUtils.EMPTY : MapUtils.getString(change, FIELD_CONTENT);
            managedGuidanceChanged |= managedSkillDocumentService
                    .validatePatchAndDetectManagedGuidanceChange(oldContent, newContent);
        }
        return managedGuidanceChanged;
    }

    /**
     * 用户确认后应用 patch。
     *
     * <p>该方法会先读取 patches 目录中的 patch 文件，逐个校验目标路径必须在
     * working 目录内，再执行 ADD/MODIFY/DELETE 并更新 patch 状态和文件树摘要。
     * 任意异常会返回失败结果，不做静默降级。
     */
    public SkillFactoryPatchApplyResult confirmPatch(Map<String, String> params) {
        long startTime = System.currentTimeMillis();
        log.info("SkillFactoryAiCodingService收到CODING_PATCH_CONFIRM请求, params={}", paramsSummary(params));
        Map<String, String> safeParams = Objects.isNull(params) ? Maps.newHashMap() : params;
        SkillFactoryAiCodingContext context = buildControlContext(safeParams);
        String workspaceId = context.workspaceId;
        String patchId = requireText(safeParams.get(FIELD_PATCH_ID), FIELD_PATCH_ID);
        Path workspaceRoot = context.workspaceRoot;
        try {
            requireRegisteredWorkspace(context);
            requireDraftEditable(context, AI_CODING_ACTION_CONFIRM_PATCH);
            Path workingDir = workingDir(workspaceId, workspaceRoot);
            Path patchFile = resolvePatchFile(context, patchId);
            Path patchRoot = patchesDir(workspaceId, workspaceRoot).toAbsolutePath().normalize();
            log.info("SkillFactoryAiCodingService准备确认patch, workspaceId={}, patchId={}, workingDir={}, "
                            + "patchFile={}, workspaceRoot={}",
                    workspaceId, patchId, workingDir, patchFile, workspaceRoot);
            if (!patchFile.toAbsolutePath().normalize().startsWith(patchRoot) || !Files.exists(patchFile)) {
                log.info("SkillFactoryAiCodingService确认patch失败，patch文件不存在或越界, "
                                + "workspaceId={}, patchId={}, patchRoot={}",
                        workspaceId, patchId, patchRoot);
                return SkillFactoryPatchApplyResult.fail(workspaceId, patchId, "patch not found");
            }
            Map<String, Object> patch = JsonSupport.fromJSON(
                    Files.readString(patchFile, StandardCharsets.UTF_8), Map.class);
            List<Map<String, Object>> changedFiles = parseChangedFiles(patch);
            String patchStatus = MapUtils.getString(patch, FIELD_PATCH_STATUS);
            log.info("SkillFactoryAiCodingService patch文件读取完成, workspaceId={}, patchId={}, patchStatus={}, "
                            + "changedFileCount={}",
                    workspaceId, patchId, patchStatus, changedFiles.size());
            if (STATUS_DISCARDED.equals(patchStatus)) {
                return SkillFactoryPatchApplyResult.fail(workspaceId, patchId, ERROR_PATCH_ALREADY_DISCARDED);
            }

            if (STATUS_APPLIED.equals(patchStatus)) {

                SkillFactoryPatchApplyResult result = buildTerminalPatchResult(
                        context, patch, changedFiles, patchId);

                return result;
            }
            if (!STATUS_PROPOSED.equals(patchStatus)) {
                return SkillFactoryPatchApplyResult.fail(workspaceId, patchId,
                        ERROR_PATCH_STATUS_UNSUPPORTED + StringUtils.defaultString(patchStatus));
            }
            List<Map<String, Object>> selectedChanges =
                    selectChangedFiles(safeParams.get(FIELD_SELECTED_FILE_PATHS), changedFiles);
            log.info("SkillFactoryAiCodingService patch文件选择完成, workspaceId={}, patchId={}, "
                            + "selectedFileCount={}",
                    workspaceId, patchId, selectedChanges.size());

            WorkspaceSnapshot currentSnapshot = workspaceSnapshotService.capture(workingDir);
            SkillFactoryPatchMergePlan mergePlan =
                    preparePatchMergePlan(patch, selectedChanges, workingDir, currentSnapshot);
            if (mergePlan.hasConflict()) {
                return buildPatchConflictResult(context, patch, patchId, currentSnapshot,
                        mergePlan.getConflictFiles());
            }
            WorkspaceSnapshot writeGuardSnapshot = workspaceSnapshotService.capture(workingDir);
            List<String> racedFiles = changedSelectedFiles(
                    currentSnapshot, writeGuardSnapshot, changedFilePaths(selectedChanges));
            if (!racedFiles.isEmpty()) {
                return buildPatchConflictResult(context, patch, patchId, writeGuardSnapshot, racedFiles);
            }

            List<String> appliedFiles = Lists.newArrayList();
            for (SkillFactoryPreparedPatchChange change : mergePlan.getChanges()) {
                log.info("SkillFactoryAiCodingService开始应用单文件变更, workspaceId={}, patchId={}, path={}, "
                                + "action={}",
                        workspaceId, patchId, change.getRelativePath(), change.getAction());
                applyPreparedChange(change);
                appliedFiles.add(change.getRelativePath());
                log.info("SkillFactoryAiCodingService单文件变更处理完成, workspaceId={}, patchId={}, path={}, "
                                + "action={}",
                        workspaceId, patchId, change.getRelativePath(), change.getAction());
            }
            for (SkillFactoryPreparedPatchChange change : mergePlan.getChanges()) {
                if (SkillFactoryPreparedPatchChange.Action.DELETE == change.getAction()) {
                    pruneEmptyParentDirectories(change.getTargetPath(), workingDir, workspaceId, patchId);
                }
            }
            WorkspaceSnapshot appliedSnapshot = workspaceSnapshotService.capture(workingDir);
            String digest = appliedSnapshot.getFileTreeDigest();
            patch.put(FIELD_APPLIED_FILES, appliedFiles);
            markPatchStatus(patchFile, patch, STATUS_APPLIED, digest);
            SkillFactoryPatchApplyResult result =
                    SkillFactoryPatchApplyResult.success(workspaceId, patchId, appliedFiles, digest);

            AgentObservationEventDO observationDO = appendPatchResultObservation(context, result,
                    OBS_SOURCE_CONFIRM_PATCH,
                    "AI Coding patch 已处理，实际应用文件数 " + appliedFiles.size()
                            + "，未选文件保持原状。");
            result.setObservationId(observationDO.getObservationId());

            return result;
        } catch (Exception e) {
            log.error("SkillFactoryAiCodingService确认patch异常, workspaceId={}, patchId={}",
                    workspaceId, patchId, e);
            return SkillFactoryPatchApplyResult.fail(workspaceId, patchId, StringUtils.defaultString(e.getMessage()));
        }
    }

    /**
     * 用户丢弃 patch。
     *
     * <p>该方法只把 patch 暂存文件标记为丢弃并返回当前 working 摘要，
     * 不修改 workspace 正式文件。
     */
    public SkillFactoryPatchApplyResult discardPatch(Map<String, String> params) {
        long startTime = System.currentTimeMillis();
        log.info("SkillFactoryAiCodingService收到CODING_PATCH_DISCARD请求, params={}", paramsSummary(params));
        Map<String, String> safeParams = Objects.isNull(params) ? Maps.newHashMap() : params;
        SkillFactoryAiCodingContext context = buildControlContext(safeParams);
        String workspaceId = context.workspaceId;
        String patchId = requireText(safeParams.get(FIELD_PATCH_ID), FIELD_PATCH_ID);
        Path workspaceRoot = context.workspaceRoot;
        try {
            requireRegisteredWorkspace(context);
            Path patchFile = resolvePatchFile(context, patchId);
            log.info("SkillFactoryAiCodingService准备丢弃patch, workspaceId={}, patchId={}, patchFile={}, "
                            + "workspaceRoot={}",
                    workspaceId, patchId, patchFile, workspaceRoot);
            if (!Files.exists(patchFile)) {
                log.info("SkillFactoryAiCodingService丢弃patch失败，patch文件不存在, workspaceId={}, "
                                + "patchId={}",
                        workspaceId, patchId);
                return SkillFactoryPatchApplyResult.fail(workspaceId, patchId, "patch not found");
            }
            Map<String, Object> patch = JsonSupport.fromJSON(
                    Files.readString(patchFile, StandardCharsets.UTF_8), Map.class);
            List<Map<String, Object>> changedFiles = parseChangedFiles(patch);
            String patchStatus = MapUtils.getString(patch, FIELD_PATCH_STATUS);
            log.info("SkillFactoryAiCodingService patch文件读取完成，准备标记丢弃, workspaceId={}, "
                            + "patchId={}, patchStatus={}",
                    workspaceId, patchId, patchStatus);
            if (STATUS_APPLIED.equals(patchStatus)) {
                return SkillFactoryPatchApplyResult.fail(workspaceId, patchId, ERROR_PATCH_ALREADY_APPLIED);
            }

            if (STATUS_DISCARDED.equals(patchStatus)) {

                SkillFactoryPatchApplyResult result = buildTerminalPatchResult(
                        context, patch, changedFiles, patchId);

                return result;
            }
            if (!STATUS_PROPOSED.equals(patchStatus)) {
                return SkillFactoryPatchApplyResult.fail(workspaceId, patchId,
                        ERROR_PATCH_STATUS_UNSUPPORTED + StringUtils.defaultString(patchStatus));
            }

            String digest = workspaceSnapshotService.capture(workingDir(workspaceId, workspaceRoot))
                    .getFileTreeDigest();
            markPatchStatus(patchFile, patch, STATUS_DISCARDED, digest);
            SkillFactoryPatchApplyResult result =
                    SkillFactoryPatchApplyResult.success(workspaceId, patchId, Lists.newArrayList(), digest);

            AgentObservationEventDO observationDO = appendPatchResultObservation(context, result,
                    OBS_SOURCE_DISCARD_PATCH, "AI Coding patch 已丢弃，workspace 文件未修改。");
            result.setObservationId(observationDO.getObservationId());

            return result;
        } catch (Exception e) {
            log.error("SkillFactoryAiCodingService丢弃patch异常, workspaceId={}, patchId={}",
                    workspaceId, patchId, e);
            return SkillFactoryPatchApplyResult.fail(workspaceId, patchId, StringUtils.defaultString(e.getMessage()));
        }
    }

    /**
     * 采集并构造本轮模型可见的 workspace 事实。
     *
     * <p>该方法只扫描一次 `preprod/current`，将实时快照与最近一次真正装配进模型上下文的快照比较。
     * 如文件发生变化，会追加模型可见 observation，并把同一份快照和摘要一起返回。任何采集、比对或
     * observation 写入失败都会中断本轮调用，禁止模型继续使用旧文件认知。
     */
    public WorkspaceModelContext prepareWorkspaceModelContext(Map<String, String> params) {
        SkillFactoryAiCodingContext context = buildContext(params);
        WorkspaceChangeGuardConfig config = workspaceChangeGuardConfig(context);
        try {
            requireRegisteredWorkspace(context);
            Path workingDir = workingDir(context);
            WorkspaceSnapshot currentSnapshot = workspaceSnapshotService.capture(workingDir);
            WorkspaceSnapshot previousSnapshot = latestWorkspaceSnapshot(context);
            WorkspaceSnapshotDiff diff = previousSnapshot == null
                                         ? null : workspaceSnapshotService.diff(previousSnapshot, currentSnapshot);
            StringBuilder builder = new StringBuilder();
            builder.append("- workspaceDigestCheck: enabled\n")
                    .append("  lastModelObservedFileTreeDigest: ")
                    .append(previousSnapshot == null ? "none" : previousSnapshot.getFileTreeDigest()).append('\n')
                    .append("  currentWorkspaceFileTreeDigest: ")
                    .append(currentSnapshot.getFileTreeDigest()).append('\n')
                    .append("  currentFileCount: ").append(currentSnapshot.getFileCount()).append('\n');
            if (previousSnapshot == null) {
                builder.append("  changedSinceLastModelRun: unknown\n")
                        .append("  instruction: 没有上一份模型已观测快照；如果本轮需要判断文件状态，先读取相关文件。");
                log.info("SkillFactoryAiCodingService构造workspace摘要上下文完成, context={}, previousDigest=none, "
                                + "currentDigest={}, changed=unknown",
                        contextSummary(context), currentSnapshot.getFileTreeDigest());
            } else {
                boolean changed = diff.hasChange();
                builder.append("  changedSinceLastModelRun: ").append(changed).append('\n');
                if (changed) {
                    List<String> changedPaths = workspaceSnapshotService.changedPaths(diff);
                    builder.append("  changedFileCount: ").append(diff.changedFileCount()).append('\n')
                            .append("  changedFiles: ")
                            .append(StringUtils.join(changedPaths.stream()
                                    .limit(config.safeMaxChangedFilesInSummary()).collect(Collectors.toList()), ", "))
                            .append('\n')
                            .append("  instruction: 文件区在模型上次观测后发生变化，继续回答或生成 patch 前必须重新读取受影响文件。")
                            .append('\n')
                            .append("  changeSummary: ")
                            .append(workspaceSnapshotService.buildModelVisibleSummary(workingDir, diff, config));
                    AgentObservationEventDO observationDO = appendWorkspaceChangedObservation(context, workingDir,
                            previousSnapshot, currentSnapshot, diff, config);
                    log.info("SkillFactoryAiCodingService已注入workspace变化observation, context={}, "
                                    + "observationId={}, previousDigest={}, currentDigest={}, changedFileCount={}",
                            contextSummary(context), observationDO.getObservationId(),
                            previousSnapshot.getFileTreeDigest(), currentSnapshot.getFileTreeDigest(),
                            diff.changedFileCount());
                } else {
                    builder.append("  instruction: 文件区摘要未变化；可以沿用上一轮已读取的文件认知，必要时再按需读取。");
                }
                log.info("SkillFactoryAiCodingService构造workspace摘要上下文完成, context={}, previousDigest={}, "
                                + "currentDigest={}, changed={}, changedFileCount={}",
                        contextSummary(context), previousSnapshot.getFileTreeDigest(),
                        currentSnapshot.getFileTreeDigest(), changed, diff.changedFileCount());
            }
            return new WorkspaceModelContext()
                    .setSnapshot(currentSnapshot)
                    .setModelContext(builder.toString());
        } catch (Exception e) {
            log.error("SkillFactoryAiCodingService构造workspace模型上下文失败, context={}",
                    contextSummary(context), e);
            throw new IllegalStateException(ERROR_WORKSPACE_MODEL_CONTEXT_FAILED, e);
        }
    }

    /**
     * 记录已经装配进本轮模型上下文的 workspace 快照。
     */
    public void recordWorkspaceSnapshotForModel(Map<String, String> params, WorkspaceSnapshot snapshot) {
        SkillFactoryAiCodingContext context = buildContext(params);
        recordWorkspaceSnapshot(context, snapshot, "本轮模型上下文已装配workspace实时快照");
    }

    /**
     * 查询最近可注入模型的 observation 摘要。
     *
     * <p>该方法只读取 Agent observation 表中的语义摘要，并由 Engine 作为独立上下文块注入本轮
     * prompt；不会把 UI 原始事件、完整工具返回或敏感字段塞进用户原始 message。
     */
    public List<String> recentModelVisibleObservationSummaries(Map<String, String> params) {
        SkillFactoryAiCodingContext context = buildContext(params);
        List<String> summaries = agentObservationService.listRecentVisibleSummaries(
                context.bizKey, context.sessionId, RECENT_OBSERVATION_LIMIT);
        log.info("SkillFactoryAiCodingService读取最近observation完成, context={}, observationCount={}",
                contextSummary(context), summaries.size());
        return summaries;
    }

    /**
     * 生成 M 端创作态受控 A2UI 业务卡片。
     *
     * <p>该方法不会执行模型输出的任意 UI，只根据后端已知的 Skill、workspace 和参考组件字段生成
     * 白名单内的需求确认卡片，用于前端 BusinessInteractionLayer 渲染。
     */
    public String buildAuthoringA2uiMessage(Map<String, String> params) {
        SkillFactoryAiCodingContext context = buildContext(params);
        String surfaceId = buildSurfaceId(context.messageId);
        List<String> componentRefs = parseStringList(params.get(FIELD_REFERENCE_COMPONENT_CODES));
        Map<String, Object> dataModel = Maps.newHashMap();
        dataModel.put(FIELD_SKILL_CODE, context.skillCode);
        dataModel.put(FIELD_WORKSPACE_ID, context.workspaceId);
        dataModel.put(FIELD_COMPONENT_REFS, componentRefs);
        dataModel.put(FIELD_MESSAGE, context.message);

        Map<String, Object> a2uiPayload = Maps.newHashMap();
        a2uiPayload.put("version", A2UI_VERSION);
        a2uiPayload.put("createSurface", createSurface(surfaceId, "确认 Skill 基础信息"));
        a2uiPayload.put("updateDataModel", updateDataModel(surfaceId, dataModel));
        a2uiPayload.put("actions", List.of(
                authoringAction(A2UI_COMPONENT_REQUIREMENT_CONFIRM, "确认需求", ACTION_CONFIRM_REQUIREMENT,
                        dataModel),
                authoringAction(A2UI_COMPONENT_COMPONENT_SELECT, "确认参考组件", ACTION_SELECT_COMPONENT_REFS,
                        Map.of(FIELD_COMPONENT_REFS, componentRefs))));
        log.info("SkillFactoryAiCodingService生成A2UI业务卡片完成, context={}, surfaceId={}, componentRefCount={}",
                contextSummary(context), surfaceId, componentRefs.size());
        AiCodingEventPayload payload = aiCodingEventPayloadFactory.a2uiMessage(context.workspaceId,
                context.sessionId, context.messageId, context.runId, context.conversationId, context.traceId,
                surfaceId, a2uiPayload);
        return aiCodingEventPayloadCodec.toJson(payload);
    }

    /**
     * 记录 M 端业务卡片 action 形成的模型可见 observation。
     *
     * <p>该方法只接受白名单 action，按 actionCode 校验最小 schema，并使用
     * `messageId/surfaceId/actionCode/idempotencyKey` 去重。成功后只把脱敏业务事实写成
     * observation，不把完整 A2UI 组件树或原始前端请求注入模型。
     */
    public String recordAuthoringActionObservation(Map<String, String> params) {
        SkillFactoryAiCodingContext context = buildContext(params);
        String actionCode = requireAuthoringActionCode(params.get(FIELD_ACTION_CODE));
        String surfaceId = requireText(params.get(FIELD_SURFACE_ID), FIELD_SURFACE_ID);
        String idempotencyKey = requireText(params.get(FIELD_IDEMPOTENCY_KEY), FIELD_IDEMPOTENCY_KEY);
        String sourceComponentId = StringUtils.defaultString(params.get(FIELD_SOURCE_COMPONENT_ID));
        Map<String, Object> actionParams = parseActionParams(params.get(FIELD_ACTION_PARAMS));
        validateAuthoringActionParams(actionCode, actionParams, context);
        Map<String, Object> stateDelta = Maps.newHashMap();
        stateDelta.put(FIELD_MESSAGE_ID, context.messageId);
        stateDelta.put(FIELD_RUN_ID, context.runId);
        stateDelta.put(FIELD_SURFACE_ID, surfaceId);
        stateDelta.put(FIELD_SOURCE_COMPONENT_ID, sourceComponentId);
        stateDelta.put(FIELD_ACTION_CODE, actionCode);
        stateDelta.put(FIELD_ACTION_PARAMS, actionParams);
        String summary = buildAuthoringObservationSummary(actionCode, actionParams, context);
        AgentObservationEventDO observationDO = agentObservationService.appendObservationOnce(
                context.bizKey, context.runId, context.sessionId, context.conversationId,
                context.sessionId, context.workspaceId, OBS_TYPE_UI_ACTION, OBS_SOURCE_A2UI_ACTION, summary,
                stateDelta, true, context.userName, context.traceId, idempotencyKey);
        log.info("SkillFactoryAiCodingService记录A2UI action observation完成, context={}, actionCode={}, "
                        + "surfaceId={}, observationId={}",
                contextSummary(context), actionCode, surfaceId, observationDO.getObservationId());
        AiCodingEventPayload payload = aiCodingEventPayloadFactory.authoringObservation(context.workspaceId,
                context.sessionId, context.messageId, context.runId, context.conversationId, context.traceId,
                surfaceId, actionCode, sourceComponentId, observationDO);
        return aiCodingEventPayloadCodec.toJson(payload);
    }

    private Map<String, Object> createSurface(String surfaceId, String title) {
        Map<String, Object> surfaceProperties = Maps.newHashMap();
        surfaceProperties.put("title", title);
        Map<String, Object> createSurface = Maps.newHashMap();
        createSurface.put(FIELD_SURFACE_ID, surfaceId);
        createSurface.put("surfaceProperties", surfaceProperties);
        return createSurface;
    }

    private Map<String, Object> updateDataModel(String surfaceId, Map<String, Object> dataModel) {
        Map<String, Object> updateDataModel = Maps.newHashMap();
        updateDataModel.put(FIELD_SURFACE_ID, surfaceId);
        updateDataModel.put(FIELD_PATH, "/");
        updateDataModel.put("value", dataModel);
        return updateDataModel;
    }

    private Map<String, Object> authoringAction(String sourceComponentId, String label, String actionCode,
            Map<String, Object> actionParams) {
        Map<String, Object> action = Maps.newHashMap();
        action.put(FIELD_SOURCE_COMPONENT_ID, sourceComponentId);
        action.put("label", label);
        action.put(FIELD_ACTION_CODE, actionCode);
        action.put(FIELD_ACTION_PARAMS, actionParams);
        return action;
    }

    private String buildSurfaceId(String messageId) {
        return A2UI_SURFACE_PREFIX + StringUtils.defaultIfBlank(messageId, String.valueOf(System.currentTimeMillis()))
                .replaceAll("[^A-Za-z0-9._-]", "_");
    }

    private String requireAuthoringActionCode(String actionCode) {
        String value = requireText(actionCode, FIELD_ACTION_CODE);
        if (!AUTHORING_ACTION_WHITELIST.contains(value)) {
            throw new IllegalArgumentException("unsupported actionCode: " + value);
        }
        return value;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseActionParams(String actionParamsJson) {
        if (StringUtils.isBlank(actionParamsJson)) {
            return Maps.newHashMap();
        }
        Object parsed = JsonSupport.fromJSON(actionParamsJson, Map.class);
        if (!(parsed instanceof Map<?, ?>)) {
            throw new IllegalArgumentException("actionParams must be object");
        }
        return (Map<String, Object>) parsed;
    }

    private void validateAuthoringActionParams(String actionCode, Map<String, Object> actionParams,
            SkillFactoryAiCodingContext context) {
        validateNoForbiddenActionParam(actionParams);
        if (ACTION_CONFIRM_REQUIREMENT.equals(actionCode)) {
            String skillCode = firstNonBlank(MapUtils.getString(actionParams, FIELD_SKILL_CODE), context.skillCode);
            requireText(skillCode, FIELD_SKILL_CODE);
            return;
        }
        if (ACTION_SELECT_COMPONENT_REFS.equals(actionCode)) {
            if (parseStringList(actionParams.get(FIELD_COMPONENT_REFS)).isEmpty()) {
                throw new IllegalArgumentException("componentRefs is required");
            }
            return;
        }
        if (ACTION_SUBMIT_MISSING_INFO.equals(actionCode)) {
            if (actionParams.isEmpty()) {
                throw new IllegalArgumentException("actionParams is required");
            }
            return;
        }
        if (ACTION_CONFIRM_ACCEPTANCE_CRITERIA.equals(actionCode)
                && parseStringList(actionParams.get(FIELD_ACCEPTANCE_CRITERIA)).isEmpty()) {
            throw new IllegalArgumentException("acceptanceCriteria is required");
        }
    }

    private void validateNoForbiddenActionParam(Object value) {
        if (value instanceof Map<?, ?> map) {
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                String key = String.valueOf(entry.getKey());
                if (FORBIDDEN_ACTION_FIELD_PATTERN.matcher(key).matches()) {
                    throw new IllegalArgumentException("forbidden actionParams field: " + key);
                }
                validateNoForbiddenActionParam(entry.getValue());
            }
            return;
        }
        if (value instanceof List<?> list) {
            for (Object item : list) {
                validateNoForbiddenActionParam(item);
            }
        }
    }

    private String buildAuthoringObservationSummary(String actionCode, Map<String, Object> actionParams,
            SkillFactoryAiCodingContext context) {
        if (ACTION_CONFIRM_REQUIREMENT.equals(actionCode)) {
            String skillName = StringUtils.defaultIfBlank(MapUtils.getString(actionParams, FIELD_SKILL_NAME),
                    context.skillCode);
            return "用户确认了 Skill 基础信息，Skill 为 " + skillName + "。";
        }
        if (ACTION_SELECT_COMPONENT_REFS.equals(actionCode)) {
            return "用户选择了参考组件：" + StringUtils.join(parseStringList(actionParams.get(FIELD_COMPONENT_REFS)),
                    ",") + "。";
        }
        if (ACTION_CONFIRM_ACCEPTANCE_CRITERIA.equals(actionCode)) {
            return "用户确认了验收项：" + StringUtils.join(parseStringList(actionParams.get(FIELD_ACCEPTANCE_CRITERIA)),
                    "；") + "。";
        }
        return "用户补充了 Skill 创建所需业务信息。";
    }

    private AgentObservationEventDO appendPatchResultObservation(SkillFactoryAiCodingContext context,
            SkillFactoryPatchApplyResult result, String source, String summary) {
        Map<String, Object> stateDelta = Maps.newHashMap();
        stateDelta.put(FIELD_PATCH_ID, result.getPatchId());

        stateDelta.put(FIELD_FILE_TREE_DIGEST, result.getFileTreeDigest());
        stateDelta.put(FIELD_CHANGED_FILES, result.getChangedFiles());
        String idempotencyKey = IDEMPOTENCY_PATCH_RESULT_PREFIX + source + ":" + result.getPatchId();
        return agentObservationService.appendObservationOnce(context.bizKey, context.runId,
                context.sessionId, context.conversationId, context.sessionId, context.workspaceId,
                OBS_TYPE_COMMAND_RESULT, source, summary, stateDelta, true, context.userName, context.traceId,
                idempotencyKey);
    }

    /**
     * 复用已经落定的 Patch 终态，不再次写文件或改写 Patch 状态。
     */
    private SkillFactoryPatchApplyResult buildTerminalPatchResult(SkillFactoryAiCodingContext context,
            Map<String, Object> patch, List<Map<String, Object>> changedFiles, String patchId) throws IOException {
        String patchStatus = MapUtils.getString(patch, FIELD_PATCH_STATUS);
        String digest = MapUtils.getString(patch, FIELD_FILE_TREE_DIGEST);
        if (StringUtils.isBlank(digest)) {
            digest = workspaceSnapshotService.capture(workingDir(context)).getFileTreeDigest();
        }
        List<String> resultFiles = STATUS_APPLIED.equals(patchStatus)
                ? appliedFilePaths(patch, changedFiles)
                : Lists.newArrayList();
        SkillFactoryPatchApplyResult result =
                SkillFactoryPatchApplyResult.success(context.workspaceId, patchId, resultFiles, digest);

        String observationSource = STATUS_APPLIED.equals(patchStatus)
                ? OBS_SOURCE_CONFIRM_PATCH
                : OBS_SOURCE_DISCARD_PATCH;
        String summary = STATUS_APPLIED.equals(patchStatus)
                ? "AI Coding patch 已应用，重复确认未再次修改文件。"
                : "AI Coding patch 已丢弃，重复丢弃未修改 workspace 文件。";
        AgentObservationEventDO observationDO =
                appendPatchResultObservation(context, result, observationSource, summary);
        result.setObservationId(observationDO.getObservationId());
        return result;
    }

    private SkillFactoryPatchApplyResult buildPatchConflictResult(SkillFactoryAiCodingContext context,
            Map<String, Object> patch, String patchId, WorkspaceSnapshot currentSnapshot,
            List<String> conflictFiles) {
        String baseDigest = StringUtils.defaultString(MapUtils.getString(patch, FIELD_BASE_FILE_TREE_DIGEST));
        SkillFactoryPatchApplyResult result = SkillFactoryPatchApplyResult.conflict(context.workspaceId, patchId,
                ERROR_PATCH_CONTENT_CONFLICT, baseDigest, currentSnapshot.getFileTreeDigest(),
                ERROR_CODE_PATCH_CONTENT_CONFLICT, conflictFiles);
        appendWorkspaceConflictObservation(context, patchId, baseDigest, currentSnapshot.getFileTreeDigest(),
                conflictFiles);
        log.info("SkillFactoryAiCodingService patch确认检测到文件冲突, context={}, patchId={}, baseDigest={}, "
                        + "currentDigest={}, conflictFiles={}",
                contextSummary(context), patchId, baseDigest, currentSnapshot.getFileTreeDigest(), conflictFiles);
        return result;
    }

    private AgentObservationEventDO appendWorkspaceConflictObservation(SkillFactoryAiCodingContext context,
            String patchId, String baseDigest, String currentDigest, List<String> conflictFiles) {
        Map<String, Object> stateDelta = Maps.newHashMap();
        stateDelta.put(FIELD_PATCH_ID, patchId);
        stateDelta.put(FIELD_PREVIOUS_FILE_TREE_DIGEST, baseDigest);
        stateDelta.put(FIELD_CURRENT_FILE_TREE_DIGEST, currentDigest);
        stateDelta.put(FIELD_CONFLICT_FILES, conflictFiles);
        stateDelta.put("conflictReason", ERROR_CODE_PATCH_CONTENT_CONFLICT);
        String summary = "确认 AI Coding patch 时检测到选中文件无法安全合并，本次未写入任何文件。"
                + "冲突文件：" + StringUtils.join(conflictFiles, ", ") + "。";
        return agentObservationService.appendObservation(context.bizKey, context.runId, context.sessionId,
                context.conversationId, context.sessionId, context.workspaceId, OBS_TYPE_WORKSPACE_CHANGED,
                OBS_SOURCE_WORKSPACE_CHANGE_GUARD, summary, stateDelta, true, context.userName, context.traceId);
    }

    private AgentObservationEventDO appendWorkspaceChangedObservation(SkillFactoryAiCodingContext context,
            Path workingDir, WorkspaceSnapshot previousSnapshot, WorkspaceSnapshot currentSnapshot,
            WorkspaceSnapshotDiff diff, WorkspaceChangeGuardConfig config) {
        Map<String, Object> stateDelta = Maps.newHashMap();
        stateDelta.put(FIELD_PREVIOUS_FILE_TREE_DIGEST, previousSnapshot.getFileTreeDigest());
        stateDelta.put(FIELD_CURRENT_FILE_TREE_DIGEST, currentSnapshot.getFileTreeDigest());
        stateDelta.put(FIELD_DIFF, diff);
        stateDelta.put(FIELD_WORKSPACE_SNAPSHOT, currentSnapshot);
        String summary = workspaceSnapshotService.buildModelVisibleSummary(workingDir, diff, config);
        return agentObservationService.appendObservation(context.bizKey, context.runId, context.sessionId,
                context.conversationId, context.sessionId, context.workspaceId, OBS_TYPE_WORKSPACE_CHANGED,
                OBS_SOURCE_WORKSPACE_CHANGE_GUARD, summary, stateDelta, true, context.userName, context.traceId);
    }

    private void recordWorkspaceSnapshot(SkillFactoryAiCodingContext context, WorkspaceSnapshot snapshot,
            String summary) {
        if (snapshot == null) {
            return;
        }
        Map<String, Object> stateDelta = Maps.newHashMap();
        stateDelta.put(FIELD_WORKSPACE_SNAPSHOT, snapshot);
        agentObservationService.appendObservation(context.bizKey, context.runId, context.sessionId,
                context.conversationId, context.sessionId, context.workspaceId, OBS_TYPE_WORKSPACE_SNAPSHOT,
                OBS_SOURCE_WORKSPACE_MODEL_CONTEXT, summary, stateDelta, false, context.userName, context.traceId);
        log.info("SkillFactoryAiCodingService已记录workspace快照, context={}, fileTreeDigest={}, fileCount={}",
                contextSummary(context), snapshot.getFileTreeDigest(), snapshot.getFileCount());
    }

    private WorkspaceSnapshot latestWorkspaceSnapshot(SkillFactoryAiCodingContext context) {
        AgentObservationEventDO eventDO = agentObservationService.findLatestByType(context.bizKey,
                context.sessionId, context.workspaceId, OBS_TYPE_WORKSPACE_SNAPSHOT,
                OBS_SOURCE_WORKSPACE_MODEL_CONTEXT);
        if (eventDO == null || StringUtils.isBlank(eventDO.getStateDeltaJson())) {
            return null;
        }
        try {
            Map<String, Object> stateDelta = JsonSupport.fromJSON(eventDO.getStateDeltaJson(), Map.class);
            Object snapshot = stateDelta == null ? null : stateDelta.get(FIELD_WORKSPACE_SNAPSHOT);
            if (snapshot == null) {
                return null;
            }
            return JsonSupport.fromJSON(JsonSupport.toJSON(snapshot), WorkspaceSnapshot.class);
        } catch (Exception e) {
            log.error("SkillFactoryAiCodingService解析模型已观测workspace快照失败, context={}, observationId={}",
                    contextSummary(context), eventDO.getObservationId(), e);
            throw new IllegalStateException(ERROR_WORKSPACE_MODEL_CONTEXT_FAILED, e);
        }
    }

    private WorkspaceChangeGuardConfig workspaceChangeGuardConfig(SkillFactoryAiCodingContext context) {
        return skillFactoryConfigReader.getWorkspaceChangeGuardConfig(context.bizKey);
    }

    private Map<String, Object> patchEventView(Map<String, Object> patch,
            List<Map<String, Object>> changedFiles) {
        Map<String, Object> eventPatch = Maps.newHashMap(patch);
        eventPatch.remove(FIELD_BASE_FILE_CONTENT_MAP);
        eventPatch.put(FIELD_CHANGED_FILES, summarizeChangedFiles(changedFiles));
        return eventPatch;
    }

    private void enrichAuthoringMeta(AiCodingEventPayload payload, SkillFactoryAiCodingContext context,
            String surfaceId) {
        if (payload == null || context == null) {
            return;
        }
        payload.setMessageId(context.messageId)
                .setRunId(context.runId)
                .setThreadId(context.sessionId)
                .setConversationId(context.conversationId)
                .setSurfaceId(surfaceId);
    }

    private SkillFactoryAiCodingContext buildContext(Map<String, String> params) {
        return buildContext(params, true);
    }

    /**
     * 构建 Patch 确认或丢弃的控制面上下文。
     *
     * <p>控制动作由非流式 handler 直接执行，不创建用户 turn，也不依赖 Chat message；workspace、session、
     * 审批和 observation 所需字段仍沿用统一上下文。
     */
    private SkillFactoryAiCodingContext buildControlContext(Map<String, String> params) {
        return buildContext(params, false);
    }

    private SkillFactoryAiCodingContext buildContext(Map<String, String> params, boolean messageRequired) {
        Map<String, String> safeParams = Objects.isNull(params) ? Maps.newHashMap() : params;
        String workspaceId = requireWorkspaceId(safeParams.get(FIELD_WORKSPACE_ID));
        String skillCode = requireText(safeParams.get(FIELD_SKILL_CODE), FIELD_SKILL_CODE);
        if (!StringUtils.equals(workspaceId, skillCode)) {
            log.warn("SkillFactory AI Coding工作区身份不一致，拒绝构造上下文, workspaceId={}, skillCode={}",
                    workspaceId, skillCode);
            throw new IllegalArgumentException(ERROR_WORKSPACE_IDENTITY_MISMATCH);
        }
        String bizKey = StringUtils.defaultIfBlank(safeParams.get(FIELD_BIZ_KEY), BIZ_KEY_HADES_SKILL_FACTORY);
        String sessionId = StringUtils.defaultIfBlank(safeParams.get(FIELD_SESSION_ID),
                "coding_session_" + System.currentTimeMillis());
        String message = messageRequired
                ? requireText(safeParams.get(FIELD_MESSAGE), FIELD_MESSAGE)
                : StringUtils.EMPTY;
        SkillFactoryAiCodingContext context = new SkillFactoryAiCodingContext();
        context.workspaceId = workspaceId;
        context.skillCode = skillCode;
        context.bizKey = bizKey;
        context.sessionId = sessionId;
        context.message = message;
        context.userName = StringUtils.defaultString(safeParams.get(FIELD_USER_NAME));

        context.workspaceRoot = resolveWorkspaceRoot(safeParams.get(FIELD_WORKSPACE_ROOT));
        context.traceId = StringUtils.defaultString(safeParams.get(FIELD_TRACE_ID));
        context.runId = firstNonBlank(safeParams.get(FIELD_RUN_ID), sessionId);
        context.conversationId = firstNonBlank(safeParams.get(FIELD_CONVERSATION_ID), sessionId);
        context.messageId = firstNonBlank(safeParams.get(FIELD_MESSAGE_ID), context.runId, sessionId);
        return context;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> normalizeChangedFiles(Map<String, Object> input, Path workingDir,
            SkillFactoryAiCodingContext context)
            throws IOException {
        Object changedFiles = input.get(FIELD_CHANGED_FILES);
        if (!(changedFiles instanceof List<?> changedFileList) || changedFileList.isEmpty()) {
            throw new IllegalArgumentException("changedFiles is required");
        }
        List<Map<String, Object>> result = Lists.newArrayList();
        Set<String> normalizedPaths = new HashSet<>();
        for (Object item : changedFileList) {
            if (!(item instanceof Map<?, ?>)) {
                throw new IllegalArgumentException("changedFiles item must be object");
            }
            Map<String, Object> rawChange = (Map<String, Object>) item;
            String relativePath = normalizeChangedFilePath(
                    requireText(MapUtils.getString(rawChange, FIELD_PATH), FIELD_PATH), workingDir, context);
            if (!normalizedPaths.add(relativePath)) {
                throw new IllegalArgumentException("changedFiles contains duplicate path: " + relativePath);
            }
            Path targetPath = resolveWorkingPath(workingDir, relativePath);
            String changeType = StringUtils.defaultIfBlank(MapUtils.getString(rawChange, FIELD_CHANGE_TYPE),
                    Files.exists(targetPath) ? CHANGE_TYPE_MODIFY : CHANGE_TYPE_ADD).toUpperCase();
            if (!Set.of(CHANGE_TYPE_ADD, CHANGE_TYPE_MODIFY, CHANGE_TYPE_DELETE).contains(changeType)) {
                throw new IllegalArgumentException("unsupported changeType: " + changeType);
            }
            String content = StringUtils.defaultString(MapUtils.getString(rawChange, FIELD_CONTENT));
            boolean targetExists = Files.exists(targetPath);
            String oldContent = readIfExists(targetPath);
            String diffPreview = buildDiffPreview(relativePath, targetExists, changeType, oldContent,
                    CHANGE_TYPE_DELETE.equalsIgnoreCase(changeType) ? StringUtils.EMPTY : content);
            Map<String, Object> normalized = Maps.newHashMap();
            normalized.put(FIELD_PATH, relativePath);
            normalized.put(FIELD_CHANGE_TYPE, changeType);
            normalized.put(FIELD_CONTENT, content);
            normalized.put(FIELD_DIFF_PREVIEW, diffPreview);
            result.add(normalized);
            log.info("SkillFactoryAiCodingService propose_patch文件变更校验通过, path={}, changeType={}, "
                            + "targetPath={}",
                    relativePath, changeType, targetPath);
        }
        return result;
    }

    private List<String> normalizeExplicitRiskItems(Object riskItems) {
        List<String> result = Lists.newArrayList();
        if (riskItems instanceof List<?> riskItemList) {
            for (Object riskItem : riskItemList) {
                String value = StringUtils.trimToEmpty(String.valueOf(riskItem));
                if (StringUtils.isNotBlank(value)) {
                    result.add(value);
                }
            }
        } else if (riskItems instanceof String riskItemText && StringUtils.isNotBlank(riskItemText)) {
            result.add(riskItemText);
        }
        return result;
    }

    private List<String> parseStringList(Object value) {
        List<String> result = Lists.newArrayList();
        if (value instanceof List<?> list) {
            for (Object item : list) {
                String text = StringUtils.trimToEmpty(String.valueOf(item));
                if (StringUtils.isNotBlank(text)) {
                    result.add(text);
                }
            }
            return result;
        }
        if (value instanceof String text) {
            String trimmed = StringUtils.trimToEmpty(text);
            if (StringUtils.startsWith(trimmed, "[")) {
                try {
                    Object parsed = JsonSupport.fromJSON(trimmed, List.class);
                    if (parsed instanceof List<?> list) {
                        return parseStringList(list);
                    }
                } catch (Exception e) {
                    log.warn("SkillFactoryAiCodingService解析字符串列表JSON失败, length={}",
                            StringUtils.length(trimmed), e);
                }
            }
            String[] items = StringUtils.split(trimmed, ",");
            if (items == null) {
                return result;
            }
            for (String item : items) {
                String itemText = StringUtils.trimToEmpty(item);
                if (StringUtils.isNotBlank(itemText)) {
                    result.add(itemText);
                }
            }
        }
        return result;
    }

    private boolean containsDeleteChange(List<Map<String, Object>> changedFiles) {
        return changedFiles.stream()
                .anyMatch(change -> CHANGE_TYPE_DELETE.equalsIgnoreCase(
                        MapUtils.getString(change, FIELD_CHANGE_TYPE)));
    }

    /**
     * 校验 AI Coding 只能进入 lifecycle 已注册且物理目录完整的 Skill 工作区。
     *
     * <p>DB 身份、请求身份、配置解析目录和磁盘目录必须同时一致。该门禁只读现有事实，不创建目录；
     * 从而避免 Capability 草稿 ID、错误 scopeId 或落到另一实例的请求生成空 workspace。
     */
    private void requireRegisteredWorkspace(SkillFactoryAiCodingContext context) {
        SkillDraft draft = workspaceRepository.findDraftByWorkspaceId(context.workspaceId);
        if (draft == null) {
            log.warn("SkillFactory AI Coding拒绝未注册工作区, context={}", contextSummary(context));
            throw new IllegalArgumentException(ERROR_WORKSPACE_NOT_REGISTERED);
        }
        Path registeredIdentityDir = workspaceRepository.resolveWorkspace(context.workspaceId)
                .toAbsolutePath().normalize();
        Path identityDir = identityWorkspaceDir(context.workspaceId, context.workspaceRoot);
        if (!StringUtils.equals(context.skillCode, draft.getSkillCode())
                || !registeredIdentityDir.equals(identityDir)) {
            log.warn("SkillFactory AI Coding注册身份与请求不一致, context={}, registeredSkillCode={}, "
                            + "registeredIdentityDir={}, requestIdentityDir={}",
                    contextSummary(context), draft.getSkillCode(), registeredIdentityDir, identityDir);
            throw new IllegalArgumentException(ERROR_WORKSPACE_IDENTITY_MISMATCH);
        }
        Path workingDir = workingDir(context);
        if (!Files.isDirectory(identityDir) || !Files.isDirectory(workingDir)) {
            log.warn("SkillFactory AI Coding注册工作区物理目录缺失, context={}, identityDir={}, workingDir={}",
                    contextSummary(context), identityDir, workingDir);
            throw new IllegalStateException(ERROR_WORKSPACE_DIRECTORY_MISSING);
        }
    }

    /**
     * 校验 lifecycle 当前变更是否仍允许 AI Coding 写入。
     *
     * <p>AI Coding 不实现新建变更或版本复制，只读取 lifecycle 写入的草稿状态文件。
     * 缺省无状态按历史工作区可编辑处理；一旦状态为 `SEALED`，普通 chat、propose_patch
     * 和 patch confirm 都必须被挡住，避免绕过已封板的 `preprod/current`。
     */
    private void requireDraftEditable(SkillFactoryAiCodingContext context, String action) {
        Properties draftState = loadDraftState(context);
        String draftStatus = StringUtils.defaultIfBlank(draftState.getProperty(DRAFT_STATE_KEY_STATUS),
                DRAFT_STATUS_EDITING);
        if (!StringUtils.equals(draftStatus, DRAFT_STATUS_SEALED)) {
            return;
        }
        log.warn("SkillFactoryAiCodingService当前变更已封板，拒绝AI Coding入口, context={}, action={}, "
                        + "draftStatus={}, baseVersion={}, sealedVersion={}",
                contextSummary(context), action, draftStatus,
                draftState.getProperty(DRAFT_STATE_KEY_BASE_VERSION),
                draftState.getProperty(DRAFT_STATE_KEY_SEALED_VERSION));
        throw new IllegalStateException(ERROR_DRAFT_SEALED);
    }

    private Properties loadDraftState(SkillFactoryAiCodingContext context) {
        Properties draftState = new Properties();
        Path stateFile = draftStateFile(context);
        if (!Files.exists(stateFile)) {
            return draftState;
        }
        try (InputStream inputStream = Files.newInputStream(stateFile)) {
            draftState.load(inputStream);
        } catch (IOException e) {
            log.warn("SkillFactoryAiCodingService读取变更草稿状态失败，按可编辑处理, context={}, stateFile={}",
                    contextSummary(context), stateFile, e);
        }
        return draftState;
    }

    private Path draftStateFile(SkillFactoryAiCodingContext context) {
        Path identityDir = identityWorkspaceDir(context.workspaceId, context.workspaceRoot);
        Path stateFile = identityDir.resolve(PREPROD_DIR).resolve(DRAFT_STATE_FILE).toAbsolutePath().normalize();
        if (!stateFile.startsWith(identityDir)) {
            throw new IllegalArgumentException("draft state outside workspace root");
        }
        return stateFile;
    }

    private List<Map<String, Object>> summarizeChangedFiles(List<Map<String, Object>> changedFiles) {
        return changedFiles.stream()
                .map(change -> {
                    Map<String, Object> summary = Maps.newHashMap();
                    summary.put(FIELD_PATH, MapUtils.getString(change, FIELD_PATH));
                    summary.put(FIELD_CHANGE_TYPE, MapUtils.getString(change, FIELD_CHANGE_TYPE));
                    summary.put(FIELD_DIFF_PREVIEW, MapUtils.getString(change, FIELD_DIFF_PREVIEW));
                    return summary;
                })
                .collect(Collectors.toList());
    }

    private List<String> changedFilePaths(List<Map<String, Object>> changedFiles) {
        if (changedFiles == null) {
            return Lists.newArrayList();
        }
        return changedFiles.stream()
                .map(change -> MapUtils.getString(change, FIELD_PATH))
                .filter(StringUtils::isNotBlank)
                .collect(Collectors.toList());
    }

    private List<String> appliedFilePaths(Map<String, Object> patch,
            List<Map<String, Object>> changedFiles) {
        if (!patch.containsKey(FIELD_APPLIED_FILES)) {
            return changedFilePaths(changedFiles);
        }
        return parseStringList(patch.get(FIELD_APPLIED_FILES));
    }

    /**
     * 从控制面参数中选择本次实际应用的文件。
     *
     * <p>未传 `selectedFilePaths` 时保持旧协议的全量应用；显式传入时必须是 Patch 内非空文件子集。
     * 未选文件不会写入，整个 Patch 在本次决策后进入终态。
     */
    private List<Map<String, Object>> selectChangedFiles(String selectedFilePaths,
            List<Map<String, Object>> changedFiles) {
        if (StringUtils.isBlank(selectedFilePaths)) {
            return changedFiles;
        }
        List<String> selectedPaths = parseStringList(selectedFilePaths);
        if (selectedPaths.isEmpty()) {
            throw new IllegalArgumentException("selectedFilePaths must not be empty");
        }
        Set<String> availablePaths = Set.copyOf(changedFilePaths(changedFiles));
        for (String selectedPath : selectedPaths) {
            if (!availablePaths.contains(selectedPath)) {
                throw new IllegalArgumentException("selectedFilePaths contains unknown path: " + selectedPath);
            }
        }
        Set<String> selectedPathSet = Set.copyOf(selectedPaths);
        return changedFiles.stream()
                .filter(change -> selectedPathSet.contains(MapUtils.getString(change, FIELD_PATH)))
                .collect(Collectors.toList());
    }

    /**
     * 为选中文件计算 Patch 三方合并计划；该阶段只读内存，不写 workspace。
     */
    private SkillFactoryPatchMergePlan preparePatchMergePlan(Map<String, Object> patch,
            List<Map<String, Object>> selectedChanges, Path workingDir, WorkspaceSnapshot currentSnapshot)
            throws IOException {
        List<String> selectedPaths = changedFilePaths(selectedChanges);
        Map<String, String> currentContentMap =
                workspaceSnapshotService.fileContentMapForPaths(workingDir, currentSnapshot, selectedPaths);
        Map<String, String> baseContentMap = parseNullableStringMap(patch.get(FIELD_BASE_FILE_CONTENT_MAP));
        boolean legacyPatch = !patch.containsKey(FIELD_BASE_FILE_CONTENT_MAP);
        boolean legacyBaseUnchanged = legacyPatch && StringUtils.equals(
                MapUtils.getString(patch, FIELD_BASE_FILE_TREE_DIGEST), currentSnapshot.getFileTreeDigest());
        return skillFactoryPatchMergeService.prepare(selectedChanges, baseContentMap, currentContentMap,
                legacyBaseUnchanged, path -> resolveWorkingPath(workingDir, path));
    }

    /**
     * 合并计划生成后再次检查选中文件，避免计算期间发生变化；无关文件变化不会阻塞应用。
     */
    private List<String> changedSelectedFiles(WorkspaceSnapshot previous, WorkspaceSnapshot current,
            List<String> selectedPaths) {
        List<String> changedFiles = Lists.newArrayList();
        Map<String, String> previousDigests = previous.safeFileDigestMap();
        Map<String, String> currentDigests = current.safeFileDigestMap();
        for (String path : selectedPaths) {
            if (!StringUtils.equals(previousDigests.get(path), currentDigests.get(path))) {
                changedFiles.add(path);
            }
        }
        return changedFiles;
    }

    private Map<String, String> parseNullableStringMap(Object value) {
        Map<String, String> result = Maps.newLinkedHashMap();
        if (!(value instanceof Map<?, ?> rawMap)) {
            return result;
        }
        for (Map.Entry<?, ?> entry : rawMap.entrySet()) {
            if (entry.getKey() != null) {
                result.put(String.valueOf(entry.getKey()),
                        entry.getValue() == null ? null : String.valueOf(entry.getValue()));
            }
        }
        return result;
    }

    private void writePatch(Path patchesDir, String patchId, Map<String, Object> patch) throws IOException {
        Files.createDirectories(patchesDir);
        Files.writeString(patchesDir.resolve(patchId + ".json"), JsonSupport.toJSON(patch),
                StandardCharsets.UTF_8);
        log.info("SkillFactoryAiCodingService patch草稿写入磁盘完成, patchId={}, patchFile={}",
                patchId, patchesDir.resolve(patchId + ".json"));
    }

    private void applyPreparedChange(SkillFactoryPreparedPatchChange change) throws IOException {
        if (SkillFactoryPreparedPatchChange.Action.NONE == change.getAction()) {
            return;
        }
        if (SkillFactoryPreparedPatchChange.Action.DELETE == change.getAction()) {
            Files.deleteIfExists(change.getTargetPath());
            return;
        }
        Files.createDirectories(change.getTargetPath().getParent());
        Files.writeString(change.getTargetPath(), StringUtils.defaultString(change.getContent()),
                StandardCharsets.UTF_8);
    }

    /**
     * 删除文件后向上清理空父目录，但绝不删除可编辑工作区根目录。
     *
     * <p>该清理在整批选中文件写入完成后执行，因此同批 ADD/MODIFY 写回的目录会因非空而保留。
     * 遇到首个非空目录立即停止，避免影响 Patch 未选中的工作区内容。
     */
    private void pruneEmptyParentDirectories(Path deletedFile, Path workingDir, String workspaceId,
            String patchId) throws IOException {
        Path normalizedWorkingDir = workingDir.toAbsolutePath().normalize();
        Path parent = deletedFile.toAbsolutePath().normalize().getParent();
        while (parent != null && parent.startsWith(normalizedWorkingDir)
                && !parent.equals(normalizedWorkingDir)) {
            if (!Files.isDirectory(parent)) {
                parent = parent.getParent();
                continue;
            }
            try (DirectoryStream<Path> children = Files.newDirectoryStream(parent)) {
                if (children.iterator().hasNext()) {
                    return;
                }
            }
            Files.deleteIfExists(parent);
            log.info("SkillFactoryAiCodingService清理Patch删除后的空目录, workspaceId={}, patchId={}, path={}",
                    workspaceId, patchId, normalizedWorkingDir.relativize(parent));
            parent = parent.getParent();
        }
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> parseChangedFiles(Map<String, Object> patch) {
        Object changedFiles = patch.get(FIELD_CHANGED_FILES);
        if (!(changedFiles instanceof List<?> changedFileList)) {
            throw new IllegalArgumentException("changedFiles is required");
        }
        return changedFileList.stream()
                .filter(Objects::nonNull)
                .map(item -> {
                    if (!(item instanceof Map<?, ?>)) {
                        throw new IllegalArgumentException("changedFiles item must be object");
                    }
                    return (Map<String, Object>) item;
                })
                .collect(Collectors.toList());
    }

    private Path resolveWorkingPath(Path workingDir, String relativePath) {
        Path relative = Path.of(relativePath);
        if (relative.isAbsolute()) {
            throw new IllegalArgumentException("Path outside workspace: " + relativePath);
        }
        Path normalizedWorkingDir = workingDir.toAbsolutePath().normalize();
        Path targetPath = normalizedWorkingDir.resolve(relative).normalize();
        if (!targetPath.startsWith(normalizedWorkingDir)) {
            throw new IllegalArgumentException("Path outside workspace: " + relativePath);
        }
        return targetPath;
    }

    /**
     * 归一化模型输出的变更路径。
     *
     * <p>AI Coding 工具的根目录已经是当前 Skill 工作区，模型偶尔会把 workspaceId/skillCode 当成
     * 文件路径前缀，导致新 patch 草稿变成 `test/skill.yaml` 这类嵌套路径。这里在 propose_patch
     * 入库前做确定性防线：只剥离与当前 workspaceId 或 skillCode 完全匹配的首段，不放宽越界校验，
     * 也不允许访问其他 workspace。
     */
    private String normalizeChangedFilePath(String rawPath, Path workingDir,
            SkillFactoryAiCodingContext context) {
        String path = StringUtils.replace(requireText(rawPath, FIELD_PATH), "\\", "/");
        Path candidate = Paths.get(path);
        if (candidate.isAbsolute()) {
            Path normalizedCandidate = candidate.toAbsolutePath().normalize();
            Path normalizedWorkingDir = workingDir.toAbsolutePath().normalize();
            if (normalizedCandidate.startsWith(normalizedWorkingDir)) {
                String relativePath = StringUtils.replace(
                        normalizedWorkingDir.relativize(normalizedCandidate).toString(), "\\", "/");
                log.info("SkillFactoryAiCodingService归一化绝对patch路径, workspaceId={}, rawPath={}, "
                                + "normalizedPath={}",
                        context.workspaceId, rawPath, relativePath);
                return relativePath;
            }
            return path;
        }
        while (StringUtils.startsWith(path, "./")) {
            path = StringUtils.removeStart(path, "./");
        }
        String normalized = stripWorkspacePrefix(path, context.workspaceId);
        normalized = stripWorkspacePrefix(normalized, context.skillCode);
        if (!StringUtils.equals(path, normalized)) {
            log.info("SkillFactoryAiCodingService剥离patch路径中的workspace前缀, workspaceId={}, "
                            + "skillCode={}, rawPath={}, normalizedPath={}",
                    context.workspaceId, context.skillCode, rawPath, normalized);
        }
        return normalized;
    }

    private String stripWorkspacePrefix(String path, String prefix) {
        if (StringUtils.isBlank(prefix)) {
            return path;
        }
        String cleanPrefix = StringUtils.stripEnd(StringUtils.replace(prefix.trim(), "\\", "/"), "/");
        if (StringUtils.equals(path, cleanPrefix)) {
            return path;
        }
        return StringUtils.startsWith(path, cleanPrefix + "/")
               ? StringUtils.removeStart(path, cleanPrefix + "/") : path;
    }

    private String digestWorkingTree(Path workingDir) throws IOException {
        return workspaceSnapshotService.capture(workingDir).getFileTreeDigest();
    }

    /**
     * 根据后端已经校验的旧内容和目标内容生成标准 unified Diff。
     *
     * <p>预览只由真实文件内容计算，不接受模型自报的 diff，避免展示与最终写入内容不一致。
     * JGit 负责行级比较、hunk 合并和行坐标生成；该方法不参与 Patch 应用和三方合并。
     */
    private String buildDiffPreview(String path, boolean targetExists, String changeType,
            String oldContent, String newContent) throws IOException {
        RawText oldText = new RawText(StringUtils.defaultString(oldContent).getBytes(StandardCharsets.UTF_8));
        RawText newText = new RawText(StringUtils.defaultString(newContent).getBytes(StandardCharsets.UTF_8));
        EditList edits = DiffAlgorithm.getAlgorithm(DiffAlgorithm.SupportedAlgorithm.HISTOGRAM)
                .diff(RawTextComparator.DEFAULT, oldText, newText);
        String oldPath = targetExists ? "a/" + path : "/dev/null";
        String newPath = CHANGE_TYPE_DELETE.equals(changeType) ? "/dev/null" : "b/" + path;
        try (ByteArrayOutputStream output = new ByteArrayOutputStream();
                DiffFormatter formatter = new DiffFormatter(output)) {
            formatter.setContext(DIFF_PREVIEW_CONTEXT_LINES);
            formatter.format(edits, oldText, newText);
            String hunks = output.toString(StandardCharsets.UTF_8);
            if (StringUtils.isEmpty(hunks)) {
                hunks = "@@ -0,0 +0,0 @@\n";
            }
            return "--- " + oldPath + "\n+++ " + newPath + "\n" + hunks;
        }
    }

    private String readIfExists(Path path) throws IOException {
        return Files.exists(path) ? Files.readString(path, StandardCharsets.UTF_8) : "";
    }

    private void markPatchStatus(Path patchFile, Map<String, Object> patch, String status, String fileTreeDigest)
            throws IOException {
        patch.put(FIELD_PATCH_STATUS, status);
        patch.put(FIELD_UPDATE_TIME, System.currentTimeMillis());
        if (StringUtils.isNotBlank(fileTreeDigest)) {
            patch.put(FIELD_FILE_TREE_DIGEST, fileTreeDigest);
        }
        Files.writeString(patchFile, JsonSupport.toJSON(patch), StandardCharsets.UTF_8);
        log.info("SkillFactoryAiCodingService patch状态已更新, patchId={}, status={}, fileTreeDigest={}, "
                        + "patchFile={}",
                MapUtils.getString(patch, FIELD_PATCH_ID), status, fileTreeDigest, patchFile);
    }

    private String paramsSummary(Map<String, String> params) {
        Map<String, String> safeParams = Objects.isNull(params) ? Maps.newHashMap() : params;
        Map<String, Object> summary = Maps.newHashMap();
        summary.put(FIELD_ACTION, safeParams.get(FIELD_ACTION));

        summary.put(FIELD_IDEMPOTENCY_KEY, safeParams.get(FIELD_IDEMPOTENCY_KEY));
        summary.put(FIELD_WORKSPACE_ID, safeParams.get(FIELD_WORKSPACE_ID));
        summary.put(FIELD_SKILL_CODE, safeParams.get(FIELD_SKILL_CODE));
        summary.put(FIELD_BIZ_KEY, safeParams.get(FIELD_BIZ_KEY));
        summary.put(FIELD_SESSION_ID, safeParams.get(FIELD_SESSION_ID));
        summary.put(FIELD_PATCH_ID, safeParams.get(FIELD_PATCH_ID));
        summary.put(FIELD_USER_NAME, safeParams.get(FIELD_USER_NAME));

        summary.put("selectedFilePathsLength",
                StringUtils.length(safeParams.get(FIELD_SELECTED_FILE_PATHS)));

        summary.put(FIELD_WORKSPACE_ROOT, safeParams.get(FIELD_WORKSPACE_ROOT));
        summary.put(FIELD_TRACE_ID, safeParams.get(FIELD_TRACE_ID));
        summary.put(FIELD_MESSAGE_ID, safeParams.get(FIELD_MESSAGE_ID));
        summary.put(FIELD_RUN_ID, safeParams.get(FIELD_RUN_ID));
        summary.put(FIELD_SURFACE_ID, safeParams.get(FIELD_SURFACE_ID));
        summary.put(FIELD_ACTION_CODE, safeParams.get(FIELD_ACTION_CODE));
        summary.put("actionParamsLength", StringUtils.length(safeParams.get(FIELD_ACTION_PARAMS)));
        summary.put(FIELD_MESSAGE_LENGTH, StringUtils.length(safeParams.get(FIELD_MESSAGE)));
        summary.put(FIELD_KEYS, safeParams.keySet().toString());
        return JsonSupport.toJSON(summary);
    }

    private String contextSummary(SkillFactoryAiCodingContext context) {
        if (context == null) {
            return "{}";
        }
        Map<String, Object> summary = Maps.newHashMap();
        summary.put(FIELD_WORKSPACE_ID, context.workspaceId);
        summary.put(FIELD_SKILL_CODE, context.skillCode);
        summary.put(FIELD_BIZ_KEY, context.bizKey);
        summary.put(FIELD_SESSION_ID, context.sessionId);
        summary.put(FIELD_USER_NAME, context.userName);

        summary.put(FIELD_WORKSPACE_ROOT, Objects.isNull(context.workspaceRoot)
                                          ? StringUtils.EMPTY : context.workspaceRoot.toString());
        summary.put(FIELD_TRACE_ID, context.traceId);
        summary.put(FIELD_RUN_ID, context.runId);
        summary.put(FIELD_CONVERSATION_ID, context.conversationId);
        summary.put(FIELD_MESSAGE_ID, context.messageId);
        summary.put(FIELD_MESSAGE_LENGTH, StringUtils.length(context.message));
        return JsonSupport.toJSON(summary);
    }

    private Path workingDir(SkillFactoryAiCodingContext context) {
        return editableWorkspaceDir(context.workspaceId, context.workspaceRoot);
    }

    private Path patchesDir(SkillFactoryAiCodingContext context) {
        return patchesDir(context.workspaceId, context.workspaceRoot);
    }

    private Path workingDir(String workspaceId, Path workspaceRoot) {
        return editableWorkspaceDir(workspaceId, workspaceRoot);
    }

    private Path patchesDir(String workspaceId, Path workspaceRoot) {
        Path identityDir = identityWorkspaceDir(workspaceId, workspaceRoot);
        Path path = identityDir.resolve(INTERNAL_STATE_DIR).resolve(PATCH_STORE_DIR).toAbsolutePath().normalize();
        if (!path.startsWith(identityDir)) {
            throw new IllegalArgumentException("workspaceId outside patch root");
        }
        return path;
    }

    private Path legacyPatchesDir(String workspaceId, Path workspaceRoot) {
        String safeWorkspaceId = requireWorkspaceId(workspaceId);
        Path path = workspaceRoot.resolve(LEGACY_PATCH_STORE_DIR)
                .resolve(safeWorkspaceId).toAbsolutePath().normalize();
        if (!path.startsWith(workspaceRoot)) {
            throw new IllegalArgumentException("workspaceId outside legacy patch root");
        }
        return path;
    }

    /**
     * 解析 Patch 文件，并把旧根级 `_patches` 中被实际处理的历史文件一次性迁入 Skill 隐藏控制目录。
     *
     * <p>迁移失败会中断确认或丢弃，不会退回双读或继续使用旧目录。迁移完成后仅在目录为空时删除
     * 对应旧目录，避免影响其他 workspace 的待处理 Patch。
     */
    private synchronized Path resolvePatchFile(SkillFactoryAiCodingContext context, String patchId)
            throws IOException {
        Path patchRoot = patchesDir(context);
        Path patchFile = resolvePatchFile(patchRoot, patchId);
        if (Files.exists(patchFile)) {
            return patchFile;
        }
        Path legacyPatchRoot = legacyPatchesDir(context.workspaceId, context.workspaceRoot);
        Path legacyPatchFile = resolvePatchFile(legacyPatchRoot, patchId);
        if (!Files.exists(legacyPatchFile)) {
            return patchFile;
        }
        Files.createDirectories(patchRoot);
        Files.move(legacyPatchFile, patchFile);
        deleteDirectoryIfEmpty(legacyPatchRoot);
        deleteDirectoryIfEmpty(legacyPatchRoot.getParent());
        log.info("SkillFactory AI Coding历史Patch文件迁移完成, context={}, patchId={}, legacyPath={}, "
                        + "currentPath={}",
                contextSummary(context), patchId, legacyPatchFile, patchFile);
        return patchFile;
    }

    private Path resolvePatchFile(Path patchRoot, String patchId) {
        Path normalizedRoot = patchRoot.toAbsolutePath().normalize();
        Path patchFile = normalizedRoot.resolve(requireText(patchId, FIELD_PATCH_ID) + ".json").normalize();
        if (!patchFile.startsWith(normalizedRoot)) {
            throw new IllegalArgumentException("patchId outside patch root");
        }
        return patchFile;
    }

    private void deleteDirectoryIfEmpty(Path directory) throws IOException {
        if (directory == null || !Files.isDirectory(directory)) {
            return;
        }
        try (DirectoryStream<Path> children = Files.newDirectoryStream(directory)) {
            if (!children.iterator().hasNext()) {
                Files.deleteIfExists(directory);
            }
        }
    }

    private Path identityWorkspaceDir(String workspaceId, Path workspaceRoot) {
        String safeWorkspaceId = requireWorkspaceId(workspaceId);
        Path path = workspaceRoot.resolve(safeWorkspaceId).toAbsolutePath().normalize();
        if (!path.startsWith(workspaceRoot)) {
            throw new IllegalArgumentException("workspaceId outside workspace root");
        }
        return path;
    }

    private Path editableWorkspaceDir(String workspaceId, Path workspaceRoot) {
        Path identityDir = identityWorkspaceDir(workspaceId, workspaceRoot);
        Path path = identityDir.resolve(PREPROD_DIR).resolve(CURRENT_DIR).toAbsolutePath().normalize();
        if (!path.startsWith(identityDir)) {
            throw new IllegalArgumentException("workspaceId outside editable workspace root");
        }
        return path;
    }

    private Path resolveWorkspaceRoot(String workspaceRoot) {
        if (StringUtils.isBlank(workspaceRoot)) {
            return defaultWorkspaceRoot();
        }
        return Paths.get(workspaceRoot).toAbsolutePath().normalize();
    }

    private Path defaultWorkspaceRoot() {
        if (skillFactoryConfigReader != null) {
            return skillFactoryConfigReader.getHadesSkillFactoryWorkspaceRoot();
        }
        if (fallbackWorkspaceRoot != null) {
            return fallbackWorkspaceRoot;
        }
        throw new IllegalStateException(ERROR_WORKSPACE_ROOT_UNAVAILABLE);
    }

    private String requireWorkspaceId(String workspaceId) {
        String value = requireText(workspaceId, "workspaceId");
        if (!WORKSPACE_ID_PATTERN.matcher(value).matches()) {
            throw new IllegalArgumentException("invalid workspaceId");
        }
        return value;
    }

    private String requireText(String value, String fieldName) {
        if (StringUtils.isBlank(value)) {
            throw new IllegalArgumentException(fieldName + " is required");
        }
        return value.trim();
    }

    private String firstNonBlank(String... values) {
        for (String value : values) {
            if (StringUtils.isNotBlank(value)) {
                return value;
            }
        }
        return StringUtils.EMPTY;
    }

    private String buildPatchId(String sessionId) {
        return "patch_" + sessionId.replaceAll("[^A-Za-z0-9._-]", "_") + "_" + System.currentTimeMillis();
    }

    private static class SkillFactoryAiCodingContext {
        private String workspaceId;
        private String skillCode;
        private String bizKey;
        private String sessionId;
        private String message;
        private String userName;

        private Path workspaceRoot;
        private String traceId;
        private String runId;
        private String conversationId;
        private String messageId;
    }

}
