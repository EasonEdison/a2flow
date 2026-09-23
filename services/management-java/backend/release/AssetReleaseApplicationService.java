package dev.a2flow.management.release;

import static dev.a2flow.management.release.ReleaseGatePresentationSupport.requiredGateFailureMessage;
import static dev.a2flow.management.release.ReleaseOnlineRecovery.sealVersion;
import static dev.a2flow.management.release.ReleaseOperationResultFactory.from;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.access.AssetAccessResult;
import dev.a2flow.management.access.AssetAction;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.release.ReleaseModels.AssetReleaseState;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.ReleaseModels.EnvironmentState;
import dev.a2flow.management.release.ReleaseModels.GateResult;
import dev.a2flow.management.release.ReleaseModels.GrayReleaseRule;
import dev.a2flow.management.release.ReleaseModels.PublishResult;

import dev.a2flow.management.release.ReleaseModels.ReleaseArtifact;
import dev.a2flow.management.release.ReleaseModels.ReleaseBuild;
import dev.a2flow.management.release.ReleaseModels.ReleaseChange;
import dev.a2flow.management.release.ReleaseModels.ReleaseDeployment;
import dev.a2flow.management.release.ReleaseModels.ReleaseOperationResult;
import dev.a2flow.management.release.ReleaseModels.ReleaseOverview;
import dev.a2flow.management.release.ReleaseModels.ReleasePointer;
import dev.a2flow.management.release.ReleaseModels.ReleasePublishContext;
import dev.a2flow.management.release.ReleaseModels.ReleaseReadinessCheck;
import dev.a2flow.management.release.ReleaseModels.ReleaseValidationEvidence;
import dev.a2flow.management.release.ReleaseModels.ReleaseValidationRequirement;
import dev.a2flow.management.release.ReleaseModels.ReleaseValidationWaiver;
import dev.a2flow.management.release.ReleaseModels.ReleaseVersion;

import dev.a2flow.management.release.diff.ReleaseDiffDocument;
import dev.a2flow.management.release.diff.ReleaseDiffQuery;
import dev.a2flow.management.release.diff.ReleaseDiffSummary;
import dev.a2flow.management.release.diff.ReleaseDiffViewMode;
import dev.a2flow.management.storage.db.repository.AssetReleaseStateRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 共享发布控制面应用服务。
 *
 * <p>该服务统一管理可编辑 Change、不可变预发 Build、不可变 Version、环境指针、幂等和摘要并发校验。
 * 它不读取领域正文，也不直接调用领域 Repository；所有领域行为均由 {@link ReleaseAssetAdapter}
 * 完成。外部发布未接通时，Adapter 返回 PLATFORM_PENDING/FAILED，本服务不会推进环境指针。
 */
@Service
@Slf4j
public class AssetReleaseApplicationService {
    private static final String ERROR_GRAY_GATE_FAILED = "gray online release requires all mandatory gates to pass";

    private static final String PARAM_ASSET_TYPE = "assetType";
    private static final String PARAM_ASSET_KEY = "assetKey";
    private static final String PARAM_REQUEST_ID = "requestId";
    private static final String PARAM_CHANGE_NAME = "changeName";
    private static final String PARAM_EXPECTED_DIGEST = "expectedDigest";
    private static final String PARAM_BASE_VERSION = "baseVersion";
    private static final String PARAM_VERSION = "version";
    private static final String PARAM_DEPLOYMENT_ID = "deploymentId";
    private static final String PARAM_ENTRY_PATH = "entryPath";
    private static final String PARAM_VIEW_MODE = "viewMode";
    private static final String PARAM_CONTEXT_LINES = "contextLines";
    private static final String PARAM_FORCE_PUBLISH = "forcePublish";
    private static final String PARAM_FORCE_REASON = "forceReason";

    private static final String PARAM_CANDIDATE_SOURCE_ID = "candidateSourceId";
    private static final String PARAM_CANDIDATE_DIGEST = "candidateDigest";
    private static final String LABEL_CURRENT_CONTENT = "当前内容";
    private static final String LABEL_NO_ONLINE_VERSION = "暂无线上版本";
    private static final String LABEL_INITIAL_VERSION = "初始版本";
    private static final String LABEL_VERSION_PREFIX = "版本 ";
    private static final String LABEL_CHANGE_SUFFIX = " 变更";
    private static final String STATUS_ACTIVE = "ACTIVE";
    private static final String STATUS_SEALED = "SEALED";
    private static final String STATUS_SUCCEEDED = "SUCCEEDED";
    private static final String STATUS_FAILED = "FAILED";
    private static final String STATUS_PUBLISHING = "PUBLISHING";
    private static final String STATUS_PARTIAL_FAILED = "PARTIAL_FAILED";
    private static final String STATUS_PLATFORM_PENDING = "PLATFORM_PENDING";
    private static final String STATUS_UNKNOWN = "UNKNOWN";
    private static final String SOURCE_BUILD = "BUILD";
    private static final String SOURCE_VERSION = "VERSION";
    private static final String ACTION_CREATE_CHANGE = "CREATE_CHANGE";
    private static final String ACTION_DIFF = "DIFF";
    private static final String ACTION_DEPLOY_PREPROD = "DEPLOY_PREPROD";
    private static final String ACTION_DEPLOY_ONLINE = "DEPLOY_ONLINE";
    private static final String ACTION_FORCE_DEPLOY_ONLINE = "FORCE_DEPLOY_ONLINE";
    private static final String ACTION_REDEPLOY_HISTORY = "REDEPLOY_HISTORY";

    private static final String ACTION_START_GRAY_PREPROD = "START_GRAY_PREPROD";
    private static final String ACTION_START_GRAY_ONLINE = "START_GRAY_ONLINE";

    private static final String ACTION_ADJUST_GRAY_PREPROD = "ADJUST_GRAY_PREPROD";
    private static final String ACTION_ADJUST_GRAY_ONLINE = "ADJUST_GRAY_ONLINE";
    private static final String ACTION_STOP_GRAY_PREPROD = "STOP_GRAY_PREPROD";
    private static final String ACTION_STOP_GRAY_ONLINE = "STOP_GRAY_ONLINE";
    private static final String ACTION_PROMOTE_GRAY_PREPROD = "PROMOTE_GRAY_PREPROD";
    private static final String ACTION_PROMOTE_GRAY_ONLINE = "PROMOTE_GRAY_ONLINE";
    private static final String GATE_PASSED = "PASSED";
    private static final String GATE_FAILED = "FAILED";
    private static final String GATE_EXPIRED = "EXPIRED";
    private static final String VALIDATION_STATUS_PASSED = "PASSED";
    private static final String VALIDATION_STATUS_FAILED = "FAILED";
    private static final String ERROR_REQUIRED_SUFFIX = " is required";
    private static final String ERROR_DIGEST_CHANGED = "asset content digest changed, please refresh";
    private static final String ERROR_VALIDATION_CODE_UNSUPPORTED = "release validation checkCode is unsupported";
    private static final String ERROR_VALIDATION_STATUS_INVALID =
            "release validation status must be PASSED or FAILED";
    private static final String ERROR_VALIDATION_RULE_VERSION_MISMATCH =
            "release validation ruleVersion does not match current requirement";
    private static final String MESSAGE_VALIDATION_RULE_VERSION_EXPIRED = "准出规则已更新，请重新核验";
    private static final String ERROR_ACTIVE_CHANGE_EXISTS = "active release change already exists";
    private static final String ERROR_ACTIVE_CHANGE_REQUIRED = "active release change is required";
    private static final String ERROR_VERIFIED_BUILD_REQUIRED = "verified preprod build is required";
    private static final String ERROR_DOMAIN_PUBLISH_FAILED = "领域发布执行失败";
    private static final String ERROR_DEPLOYMENT_IN_PROGRESS = "asset release deployment is in progress";
    private static final String ERROR_DEPLOYMENT_STATUS_UNSUPPORTED =
            "asset release deployment status is unsupported";
    private static final String ERROR_CODE_DEPLOYMENT_STATUS_UNSUPPORTED = "UNSUPPORTED_DEPLOYMENT_STATUS";
    private static final String ERROR_DIFF_VIEW_MODE_INVALID = "release diff viewMode is invalid";
    private static final String ERROR_FORCE_PUBLISH_INVALID = "forcePublish must be true or false";
    private static final String ERROR_FORCE_REASON_REQUIRED = "forceReason is required";

    private static final String ERROR_GRAY_RELEASE_UNSUPPORTED = "asset does not support gray release";
    private static final String ERROR_GRAY_STABLE_REQUIRED = "stable environment release is required before gray";
    private static final String ERROR_GRAY_ACTIVE = "active gray candidate must be stopped or promoted first";
    private static final String ERROR_GRAY_STATE_INVALID = "gray environment state is invalid";
    private static final String ERROR_GRAY_CANDIDATE_REQUIRED = "active gray candidate is required";
    private static final String ERROR_GRAY_CANDIDATE_CHANGED = "gray candidate changed, please refresh";

    private static final String STATUS_GRAYING = "GRAYING";
    private static final String STATUS_STABLE = "STABLE";
    private static final String MESSAGE_CHANGE_CREATED = "变更已创建";

    private static final String MESSAGE_PREPROD_SUCCEEDED = "预发发布成功";
    private static final String MESSAGE_ONLINE_SUCCEEDED = "线上发布成功";
    private static final String MESSAGE_HISTORY_REDEPLOY_SUCCEEDED = "历史版本重发成功";
    private static final String MESSAGE_GRAY_START_SUCCEEDED = "灰度启动成功";
    private static final String PUBLISH_MODE_GRAY_ADJUST = "GRAY_ADJUST";
    private static final String PUBLISH_MODE_GRAY_STOP = "GRAY_STOP";
    private static final String PUBLISH_MODE_GRAY_PROMOTE = "GRAY_PROMOTE";
    private static final String ERROR_CHANGE_NAME_TOO_LONG = "changeName length must not exceed 80";
    private static final String INITIAL_CHANGE_ID_PREFIX = "initial-change-";
    private static final String INITIAL_CHANGE_REQUEST_ID = "initial-current-draft";
    private static final int MAX_CHANGE_NAME_LENGTH = 80;
    private static final int MIN_GRAY_PERCENTAGE = 0;
    private static final int MAX_GRAY_PERCENTAGE = 100;
    @Resource private ReleaseAssetAdapterRegistry adapterRegistry;
    @Resource private AssetReleaseStateRepository stateRepository;
    @Resource private AssetAuthorizationService assetAuthorizationService;

    /** 查询一个资产的完整发布视图和后端允许动作。 */
    public ReleaseOverview overview(String userName, Map<String, String> params) {
        ReleaseContext context = context(params);
        assetAuthorizationService.requirePermission(
                userName, context.assetType, context.assetKey, AssetAction.VIEW);
        ReleaseOperationContext operationContext = new ReleaseOperationContext(userName);
        AssetSnapshot current = context.adapter.currentSnapshot(operationContext, context.assetKey, context.params);
        AssetReleaseState state = stateRepository.find(context.assetType, context.assetKey);
        AssetAccessResult access = assetAuthorizationService.getAccess(
                userName, context.assetType, context.assetKey);
        return restrictAllowedActions(
                buildOverview(context, operationContext, current, state,
                        access.getPermissions().isCanEdit()), access);
    }
    /**
     * 保存模型或自动检查器生成的摘要绑定准出证据。
     *
     * <p>目标资产由后端 ToolContext 提供，模型只能提交检查结论。这里在资产锁内重新读取真实摘要并执行
     * CAS 校验，防止核验期间文件变化后仍把旧结论写成有效状态。调用来源 Skill 身份不参与校验，Tool
     * 是否暴露由 Agent/Skill 的工具配置控制。
     */
    public ReleaseValidationEvidence recordValidationEvidence(String userName, ReleaseAssetType assetType,
            String assetKey, String expectedDigest, ReleaseValidationEvidence input) {
        assetAuthorizationService.requirePermission(userName, assetType, assetKey, AssetAction.EDIT);
        return recordValidationEvidenceInternal(userName, assetType, assetKey, expectedDigest, input);
    }
    /**
     * 保存来自可信 B 端 Chat ToolContext 的摘要绑定准出证据。
     *
     * <p>B 端 Chat 使用数字用户 ID 作为运行态审计标识，无法与 M 端员工英文名负责人关系直接匹配。
     * 调用方必须从可信 ToolContext 派生资产身份，禁止接受模型传入的 assetType 或 assetKey。本入口只跳过
     * M 端资产负责人校验，摘要 CAS、规则版本和状态校验仍与普通入口完全一致，也不触发发布动作。
     */
    public ReleaseValidationEvidence recordTrustedToolValidationEvidence(
            String operator, ReleaseAssetType assetType, String assetKey, String expectedDigest,
            ReleaseValidationEvidence input) {
        log.info("共享发布接收可信B端Chat Tool准出证据, assetType:{}, assetKey:{}, "
                        + "checkCode:{}, operator:{}",
                assetType, assetKey, input.getCheckCode(), operator);
        return recordValidationEvidenceInternal(operator, assetType, assetKey, expectedDigest, input);
    }
    /**
     * 执行准出证据的规则校验、摘要 CAS 和持久化。
     */
    private ReleaseValidationEvidence recordValidationEvidenceInternal(
            String operator, ReleaseAssetType assetType, String assetKey, String expectedDigest,
            ReleaseValidationEvidence input) {
        ReleaseAssetAdapter adapter = adapterRegistry.get(assetType);
        ReleaseValidationRequirement requirement = requireValidationRequirement(adapter, input.getCheckCode());
        String status = StringUtils.upperCase(StringUtils.trim(input.getStatus()));
        if (!StringUtils.equalsAny(status, VALIDATION_STATUS_PASSED, VALIDATION_STATUS_FAILED)) {
            throw new IllegalArgumentException(ERROR_VALIDATION_STATUS_INVALID);
        }
        String ruleVersion = StringUtils.trim(input.getRuleVersion());
        if (StringUtils.isNotBlank(requirement.getExpectedRuleVersion())
                && !StringUtils.equals(StringUtils.trim(requirement.getExpectedRuleVersion()), ruleVersion)) {
            log.warn("共享发布拒绝保存规则版本不匹配的准出证据, assetType:{}, assetKey:{}, checkCode:{}, "
                            + "expectedRuleVersion:{}, actualRuleVersion:{}, operator:{}",
                    assetType, assetKey, requirement.getCode(), requirement.getExpectedRuleVersion(),
                    ruleVersion, operator);
            throw new IllegalArgumentException(ERROR_VALIDATION_RULE_VERSION_MISMATCH);
        }
        return stateRepository.executeLocked(assetType, assetKey, () -> {
            Map<String, String> params = new HashMap<>();
            params.put(PARAM_ASSET_TYPE, assetType.name());
            params.put(PARAM_ASSET_KEY, assetKey);
            AssetSnapshot current = adapter.currentSnapshot(
                    new ReleaseOperationContext(operator), assetKey, params);
            verifyDigest(current, expectedDigest);
            AssetReleaseState state = stateRepository.find(assetType, assetKey);
            ReleaseValidationEvidence evidence = new ReleaseValidationEvidence()
                    .setCheckCode(requirement.getCode())
                    .setStatus(status)
                    .setBoundDigest(current.getDigest())
                    .setRuleVersion(ruleVersion)
                    .setCheckRunId(StringUtils.trim(input.getCheckRunId()))
                    .setSummary(StringUtils.trim(input.getSummary()))
                    .setFindings(copyFindings(input.getFindings()))
                    .setChecks(copyChecks(input.getChecks()))
                    .setWaivers(copyWaivers(input.getWaivers()))
                    .setOperator(StringUtils.defaultString(operator))
                    .setCheckedAt(System.currentTimeMillis());
            validations(state).put(requirement.getCode(), evidence);
            stateRepository.save(state, state.getRevision());
            log.info("共享发布准出证据已保存, assetType:{}, assetKey:{}, checkCode:{}, status:{}, "
                            + "boundDigest:{}, checkRunId:{}, operator:{}",
                    assetType, assetKey, requirement.getCode(), status, current.getDigest(),
                    evidence.getCheckRunId(), operator);
            return evidence;
        });
    }
    /** 创建下一数字版本的可编辑变更，可选从历史版本恢复领域内容。 */
    public ReleaseOperationResult createChange(String userName, Map<String, String> params) {
        ReleaseContext context = context(params);
        assetAuthorizationService.requirePermission(
                userName, context.assetType, context.assetKey, AssetAction.EDIT);
        String requestId = required(params, PARAM_REQUEST_ID);
        String changeName = StringUtils.trim(required(params, PARAM_CHANGE_NAME));
        if (changeName.length() > MAX_CHANGE_NAME_LENGTH) {
            throw new IllegalArgumentException(ERROR_CHANGE_NAME_TOO_LONG);
        }
        return stateRepository.executeLocked(context.assetType, context.assetKey, () -> {
            AssetReleaseState state = stateRepository.find(context.assetType, context.assetKey);
            if (state.getActiveChange() != null
                    && StringUtils.equals(state.getActiveChange().getRequestId(), requestId)) {
                return from(state.getActiveChange(), MESSAGE_CHANGE_CREATED);
            }
            if (state.getActiveChange() != null
                    && StringUtils.equals(state.getActiveChange().getStatus(), STATUS_ACTIVE)) {
                throw new IllegalStateException(ERROR_ACTIVE_CHANGE_EXISTS);
            }
            Integer baseVersion = optionalInteger(params.get(PARAM_BASE_VERSION));
            if (baseVersion != null) {
                ReleaseVersion version = requireVersion(state, baseVersion);
                log.info("共享发布创建变更前恢复历史版本, assetType:{}, assetKey:{}, baseVersion:{}, operator:{}",
                        context.assetType, context.assetKey, baseVersion, userName);
                context.adapter.restore(new ReleaseOperationContext(userName),
                        context.assetKey, version.getSnapshot(), context.params);
            }
            AssetSnapshot current = context.adapter.currentSnapshot(
                    new ReleaseOperationContext(userName), context.assetKey, context.params);
            long now = System.currentTimeMillis();
            ReleaseChange change = new ReleaseChange()
                    .setChangeId(id("change"))
                    .setRequestId(requestId)
                    .setChangeName(changeName)
                    .setTargetVersion(nextVersion(state))
                    .setBaseVersion(baseVersion)
                    .setStatus(STATUS_ACTIVE)
                    .setSourceDigest(current.getDigest())
                    .setOperator(userName)
                    .setCreateTime(now)
                    .setUpdateTime(now);
            state.setActiveChange(change);
            stateRepository.save(state, state.getRevision());
            log.info("共享发布变更创建完成, assetType:{}, assetKey:{}, changeName:{}, targetVersion:{}, "
                            + "baseVersion:{}, operator:{}",
                    context.assetType, context.assetKey, changeName, change.getTargetVersion(), baseVersion, userName);
            return from(change, MESSAGE_CHANGE_CREATED);
        });
    }
    /** 比较当前领域内容与指定历史版本；具体方向由领域 Adapter 定义，未指定版本时使用当前线上版本。 */
    public ReleaseDiffDocument diff(String userName, Map<String, String> params) {
        ReleaseContext context = context(params);
        assetAuthorizationService.requirePermission(
                userName, context.assetType, context.assetKey, AssetAction.VIEW);
        AssetReleaseState state = stateRepository.find(context.assetType, context.assetKey);
        Integer versionNumber = optionalInteger(params.get(PARAM_VERSION));
        ReleaseVersion target = versionNumber == null ? onlineVersion(state)
                : requireVersion(state, versionNumber);
        AssetSnapshot current = context.adapter.currentSnapshot(new ReleaseOperationContext(userName),
                context.assetKey, context.params);
        if (target == null) {
            return new ReleaseDiffDocument()
                    .setAssetType(context.assetType.name())
                    .setAssetKey(context.assetKey)
                    .setCurrentDigest(current.getDigest())
                    .setHasTarget(false)
                    .setFrom(LABEL_CURRENT_CONTENT)
                    .setTo(LABEL_NO_ONLINE_VERSION)
                    .setViewMode(ReleaseDiffViewMode.UNIFIED)
                    .setSummary(new ReleaseDiffSummary()
                            .setChangedFiles(0)
                            .setAdditions(0)
                            .setDeletions(0));
        }
        ReleaseDiffQuery query = diffQuery(params);
        ReleaseDiffDocument document = context.adapter.diff(current, target.getSnapshot(), query);
        return document
                .setAssetType(context.assetType.name())
                .setAssetKey(context.assetKey)
                .setCurrentDigest(current.getDigest())
                .setTargetVersion(target.getVersion())
                .setHasTarget(true);
    }

    /** 冻结当前领域快照为不可变 Build，并执行 PRT 发布。 */
    public ReleaseOperationResult deployPreprod(String userName, Map<String, String> params) {
        return deployBuild(userName, params, ReleaseEnvironment.PRT);
    }
    /** 从已验证且摘要未过期的 Build 封板正式版本并发布 ONLINE。 */
    public ReleaseOperationResult deployOnline(String userName, Map<String, String> params) {
        ReleaseContext context = context(params);
        boolean forcePublish = forcePublish(params);
        assetAuthorizationService.requirePermission(
                userName, context.assetType, context.assetKey,
                forcePublish ? AssetAction.FORCE_PUBLISH : AssetAction.PUBLISH);
        String requestId = required(params, PARAM_REQUEST_ID);

        if (forcePublish
                && StringUtils.isBlank(params.get(PARAM_FORCE_REASON))) {
            throw new IllegalArgumentException(ERROR_FORCE_REASON_REQUIRED);
        }
        String publishMode = forcePublish ? "FORCE" : "NORMAL";
        return stateRepository.executeLocked(context.assetType, context.assetKey, () -> {
            AssetReleaseState state = stateRepository.find(context.assetType, context.assetKey);
            ReleaseDeployment idempotent = resolveIdempotentDeployment(
                    state, ReleaseEnvironment.ONLINE, requestId);
            if (idempotent != null) {

                if (!StringUtils.equals(idempotent.getStatus(), STATUS_PUBLISHING)
                        || !context.adapter.supportsPublishingRecovery()) {
                    return from(idempotent, MESSAGE_ONLINE_SUCCEEDED);
                }
            }
            requireNoActiveCandidate(state, ReleaseEnvironment.ONLINE);
            ReleaseBuild recovered = idempotent == null ? null : ReleaseOnlineRecovery.requireBuild(
                    state, idempotent, required(params, PARAM_EXPECTED_DIGEST), forcePublish);
            AssetSnapshot current = recovered == null ? context.adapter.currentPublishSnapshot(
                    new ReleaseOperationContext(userName), context.assetKey, context.params)
                    : new AssetSnapshot().setDigest(inputDigest(recovered));
            ReleaseChange change = recovered == null ? requireActiveChange(context, current, state, userName)
                    : state.getActiveChange();
            verifyDigest(current, required(params, PARAM_EXPECTED_DIGEST));
            ReleaseBuild build = recovered == null
                    ? latestSuccessfulBuild(state, change.getChangeId(), current.getDigest()) : recovered;
            if (build == null) {
                throw new IllegalStateException(ERROR_VERIFIED_BUILD_REQUIRED);
            }
            AssetSnapshot onlineSnapshot = context.adapter.prepareOnlineSnapshot(context.assetKey, build.getSnapshot());
            List<GateResult> gates = mergeGates(context.adapter.evaluateGates(
                    new ReleaseOperationContext(userName), context.assetKey, ReleaseEnvironment.ONLINE,
                    onlineSnapshot, build.getArtifact(), context.params),
                    evaluateValidationGates(context.adapter, ReleaseEnvironment.ONLINE, onlineSnapshot,
                    inputDigest(build), validations(state), ValidationEvidencePolicy.CURRENT_RULE));

            ReleaseDeployment deployment = recovered != null ? idempotent.setGates(gates)
                    : deployment(requestId, ReleaseEnvironment.ONLINE,
                    new DeploymentSource(SOURCE_BUILD, build.getBuildId(), change.getTargetVersion(),
                            build.getSourceDigest()), gates, userName)
                    .setForced(forcePublish)
                    .setForceReason(forcePublish
                                    ? StringUtils.trimToNull(params.get(PARAM_FORCE_REASON)) : null)
                    .setPublishMode(publishMode);
            boolean gateFailed = hasRequiredGateFailure(gates);
            if (gateFailed && !forcePublish) {
                deployment.setStatus(STATUS_FAILED).setMessage("线上发布门禁未通过");
                if (recovered == null) {
                    state.getDeployments().add(0, deployment);
                }
                stateRepository.save(state, state.getRevision());
            } else {
                if (gateFailed) {
                    log.warn("共享发布管理员忽视准出结果强制发布, assetType:{}, assetKey:{}, "
                                    + "targetVersion:{}, requestId:{}, operator:{}",
                            context.assetType, context.assetKey, change.getTargetVersion(), requestId, userName);
                }
                ReleaseDeployment previousDeployment = latestRetryableDeployment(state, ReleaseEnvironment.ONLINE,
                        build.getSourceDigest(), null);
                deployment.setStatus(STATUS_PUBLISHING).setArtifact(build.getArtifact());
                if (recovered == null) {
                    state.getDeployments().add(0, deployment);
                }
                state = stateRepository.save(state, state.getRevision());
                ReleasePublishContext publishContext = publishContext(context,
                        new DeploymentSource(SOURCE_BUILD, build.getBuildId(), change.getTargetVersion(),
                                build.getSourceDigest()),
                        ReleaseEnvironment.ONLINE, requestId, userName, onlineSnapshot, build.getArtifact())
                        .setPreviousDeployment(previousDeployment);
                PublishResult publishResult = deploy(context, new ReleaseOperationContext(userName), publishContext);
                deployment = requireDeployment(state, deployment.getDeploymentId());
                applyPublishResult(deployment, publishResult);
                if (StringUtils.equals(deployment.getStatus(), STATUS_SUCCEEDED)) {
                    ReleaseVersion version = sealVersion(change, build, publishResult.getArtifact(),
                            matchingValidations(validations(state), inputDigest(build)), userName)
                            .setSnapshot(onlineSnapshot).setSourceDigest(onlineSnapshot.getDigest());
                    state.getVersions().add(0, version);
                    state.getActiveChange().setStatus(STATUS_SEALED).setUpdateTime(System.currentTimeMillis());
                    updateEnvironment(state, ReleaseEnvironment.ONLINE, SOURCE_VERSION, version.getVersionId(),
                            version.getVersion(), version.getSourceDigest(), deployment.getDeploymentId());
                }
                state = stateRepository.save(state, state.getRevision());

            }
            log.info("共享发布线上部署完成, assetType:{}, assetKey:{}, targetVersion:{}, status:{}, "
                            + "forced:{}, operator:{}", context.assetType, context.assetKey, change.getTargetVersion(), deployment.getStatus(), forcePublish, userName);
            return from(deployment, MESSAGE_ONLINE_SUCCEEDED);
        });
    }
    /** 重新发布历史正式版本，不创建新版本。 */
    public ReleaseOperationResult redeployHistory(String userName, Map<String, String> params) {
        ReleaseContext context = context(params);
        assetAuthorizationService.requirePermission(
                userName, context.assetType, context.assetKey, AssetAction.PUBLISH);
        String requestId = required(params, PARAM_REQUEST_ID);

        int versionNumber = integer(required(params, PARAM_VERSION), PARAM_VERSION);
        return stateRepository.executeLocked(context.assetType, context.assetKey, () -> {
            AssetReleaseState state = stateRepository.find(context.assetType, context.assetKey);
            ReleaseDeployment idempotent = resolveIdempotentDeployment(
                    state, ReleaseEnvironment.ONLINE, requestId);
            if (idempotent != null) {

                return from(idempotent, MESSAGE_HISTORY_REDEPLOY_SUCCEEDED);
            }
            requireNoActiveCandidate(state, ReleaseEnvironment.ONLINE);
            ReleaseVersion version = requireVersion(state, versionNumber);
            if (!StringUtils.equals(
                    version.getSourceDigest(), required(params, PARAM_EXPECTED_DIGEST))) {
                throw new IllegalStateException(ERROR_DIGEST_CHANGED);
            }
            List<GateResult> gates = mergeGates(context.adapter.evaluateGates(
                    new ReleaseOperationContext(userName), context.assetKey, ReleaseEnvironment.ONLINE,
                    version.getSnapshot(), version.getArtifact(), context.params),
                    evaluateValidationGates(context.adapter, ReleaseEnvironment.ONLINE, version.getSnapshot(),
                    inputDigest(version), validations(version), ValidationEvidencePolicy.FROZEN_RULE));

            ReleaseDeployment deployment = deployment(requestId, ReleaseEnvironment.ONLINE,
                    new DeploymentSource(SOURCE_VERSION, version.getVersionId(), version.getVersion(),
                            version.getSourceDigest()), gates, userName)
                    .setPublishMode("HISTORICAL");
            if (hasRequiredGateFailure(gates)) {
                deployment.setStatus(STATUS_FAILED).setMessage("历史版本重发门禁未通过");
                state.getDeployments().add(0, deployment);
                stateRepository.save(state, state.getRevision());
            } else {
                ReleaseDeployment previousDeployment = latestRetryableDeployment(state, ReleaseEnvironment.ONLINE,
                        version.getSourceDigest(), version.getArtifact());
                deployment.setStatus(STATUS_PUBLISHING).setArtifact(version.getArtifact());
                state.getDeployments().add(0, deployment);
                state = stateRepository.save(state, state.getRevision());
                ReleasePublishContext publishContext = publishContext(context,
                        new DeploymentSource(SOURCE_VERSION, version.getVersionId(), version.getVersion(),
                                version.getSourceDigest()),
                        ReleaseEnvironment.ONLINE, requestId, userName, version.getSnapshot(), version.getArtifact())
                        .setPreviousDeployment(previousDeployment);
                PublishResult publishResult = deploy(context, new ReleaseOperationContext(userName), publishContext);
                deployment = requireDeployment(state, deployment.getDeploymentId());
                applyPublishResult(deployment, publishResult);
                if (StringUtils.equals(deployment.getStatus(), STATUS_SUCCEEDED)) {
                    updateEnvironment(state, ReleaseEnvironment.ONLINE, SOURCE_VERSION, version.getVersionId(),
                            version.getVersion(), version.getSourceDigest(), deployment.getDeploymentId());
                }
                state = stateRepository.save(state, state.getRevision());

            }
            log.info("共享发布历史版本重发完成, assetType:{}, assetKey:{}, version:{}, status:{}, "
                            + "operator:{}", context.assetType, context.assetKey, versionNumber, deployment.getStatus(), userName);
            return from(deployment, MESSAGE_HISTORY_REDEPLOY_SUCCEEDED);
        });
    }
    /**
     * 为 PRT 或 ONLINE 启动一轮新的不可变候选灰度。
     *
     * <p>PRT candidate 是 Build，ONLINE candidate 是由当前成功 Build 封板得到的 Version。该方法
     * 只写 candidate，不移动 stable。
     */
    public ReleaseOperationResult startGray(String userName, Map<String, String> params) {
        ReleaseContext context = context(params);
        requireGraySupported(context);
        assetAuthorizationService.requirePermission(
                userName, context.assetType, context.assetKey, AssetAction.PUBLISH);
        ReleaseEnvironment environment = GrayReleaseRequestParser.environment(params);
        String requestId = required(params, PARAM_REQUEST_ID);
        GrayReleaseRule grayRule = GrayReleaseRequestParser.rule(params);

        return stateRepository.executeLocked(context.assetType, context.assetKey, () -> {
            AssetReleaseState state = stateRepository.find(context.assetType, context.assetKey);
            ReleasePublishingRecovery.supersedePreprod(state, environment, requestId, context.assetKey, userName);
            ReleaseDeployment idempotent = resolveIdempotentDeployment(state, environment, requestId);
            if (idempotent != null) {
                if (ReleasePublishingRecovery.canRecoverGray(environment, idempotent, context.adapter)) {
                    idempotent = ReleasePublishingRecovery.recoverGray(state, idempotent, grayRule,
                            ReleasePublishingRecovery.context(context.assetKey, context.params, environment,
                                    requestId, userName),
                            publishContext -> deploy(context, new ReleaseOperationContext(userName), publishContext),
                            this::applyPublishResult);
                    stateRepository.save(state, state.getRevision());
                }

                return from(idempotent, MESSAGE_GRAY_START_SUCCEEDED);
            }
            EnvironmentState environmentState = requireStableEnvironment(state, environment);
            requireGrayStartable(environmentState);
            return environment == ReleaseEnvironment.PRT
                    ? startPreprodGray(context, state, grayRule, requestId, userName)
                    : startOnlineGray(context, state, grayRule, requestId, userName);
        });
    }
    /** 调整当前候选的比例和白名单，不调用领域发布器。 */
    public ReleaseOperationResult adjustGray(String userName, Map<String, String> params) {
        return mutateGray(userName, params, GrayMutation.ADJUST);
    }
    /** 终止当前候选灰度并保留原 stable，不调用领域发布器。 */
    public ReleaseOperationResult stopGray(String userName, Map<String, String> params) {
        return mutateGray(userName, params, GrayMutation.STOP);
    }
    /** 显式把当前 candidate 提升为 stable，不调用领域发布器。 */
    public ReleaseOperationResult promoteGray(String userName, Map<String, String> params) {
        return mutateGray(userName, params, GrayMutation.PROMOTE);
    }

    private ReleaseOperationResult startPreprodGray(ReleaseContext context, AssetReleaseState state,
            GrayReleaseRule grayRule, String requestId, String userName) {
        ReleaseOperationContext operationContext = new ReleaseOperationContext(userName);
        AssetSnapshot current = context.adapter.currentPublishSnapshot(
                operationContext, context.assetKey, context.params);
        ReleaseChange change = requireActiveChange(context, current, state, userName);
        verifyDigest(current, required(context.params, PARAM_EXPECTED_DIGEST));
        AssetSnapshot frozen = context.adapter.freezeBuildSnapshot(
                operationContext, context.assetKey, ReleaseEnvironment.PRT,
                current, context.params);
        List<GateResult> gates = context.adapter.evaluateGates(
                operationContext, context.assetKey, ReleaseEnvironment.PRT,
                frozen, null, context.params);
        ReleaseBuild build = new ReleaseBuild()
                .setBuildId(id("build"))
                .setChangeId(change.getChangeId())
                .setTargetVersion(change.getTargetVersion())
                .setBuildNumber(nextBuildNumber(state, change.getChangeId()))
                .setInputDigest(current.getDigest())
                .setSourceDigest(frozen.getDigest())
                .setSnapshot(frozen)
                .setGates(gates)
                .setOperator(userName)
                .setCreateTime(System.currentTimeMillis());
        ReleaseDeployment deployment = deployment(requestId, ReleaseEnvironment.PRT,
                new DeploymentSource(SOURCE_BUILD, build.getBuildId(), build.getTargetVersion(),
                        build.getSourceDigest()), gates, userName)
                .setPublishMode("GRAY");
        if (hasRequiredGateFailure(gates)) {
            build.setStatus(STATUS_FAILED);
            deployment.setStatus(STATUS_FAILED).setMessage("预发灰度门禁未通过");
            state.getBuilds().add(0, build);
            state.getDeployments().add(0, deployment);
            stateRepository.save(state, state.getRevision());
        } else {
            deployment.setStatus(STATUS_PUBLISHING);
            build.setStatus(STATUS_PUBLISHING);
            state.getBuilds().add(0, build);
            state.getDeployments().add(0, deployment);
            state = stateRepository.save(state, state.getRevision());
            ReleasePublishContext publishContext = publishContext(context,
                    new DeploymentSource(SOURCE_BUILD, build.getBuildId(), build.getTargetVersion(),
                            build.getSourceDigest()), ReleaseEnvironment.PRT, requestId, userName,
                    frozen, null);
            PublishResult publishResult = deploy(context, new ReleaseOperationContext(userName), publishContext);
            deployment = requireDeployment(state, deployment.getDeploymentId());
            build = requireBuild(state, build.getBuildId());
            applyPublishResult(deployment, publishResult);
            build.setStatus(deployment.getStatus()).setArtifact(publishResult.getArtifact());
            if (StringUtils.equals(deployment.getStatus(), STATUS_SUCCEEDED)) {
                setCandidate(requireStableEnvironment(state, ReleaseEnvironment.PRT),
                        SOURCE_BUILD, build.getBuildId(), build.getTargetVersion(), build.getSourceDigest(),
                        deployment.getDeploymentId(), grayRule);
            }
            stateRepository.save(state, state.getRevision());
        }
        log.info("共享发布预发灰度启动完成, assetType:{}, assetKey:{}, buildId:{}, percentage:{}, "
                        + "status:{}, operator:{}",
                context.assetType, context.assetKey, build.getBuildId(), grayRule.getPercentage(),
                deployment.getStatus(), userName);
        return from(deployment, MESSAGE_GRAY_START_SUCCEEDED);
    }

    private ReleaseOperationResult startOnlineGray(ReleaseContext context, AssetReleaseState state, GrayReleaseRule grayRule, String requestId, String userName) {
        ReleaseOperationContext operationContext = new ReleaseOperationContext(userName);
        AssetSnapshot current = context.adapter.currentPublishSnapshot(
                operationContext, context.assetKey, context.params);
        ReleaseChange change = requireActiveChange(context, current, state, userName);
        verifyDigest(current, required(context.params, PARAM_EXPECTED_DIGEST));
        ReleaseBuild build = latestSuccessfulBuild(state, change.getChangeId(), current.getDigest());
        if (build == null) {
            throw new IllegalStateException(ERROR_VERIFIED_BUILD_REQUIRED);
        }
        List<GateResult> gates = mergeGates(context.adapter.evaluateGates(
                operationContext, context.assetKey, ReleaseEnvironment.ONLINE,
                build.getSnapshot(), build.getArtifact(), context.params),
                evaluateValidationGates(context.adapter, ReleaseEnvironment.ONLINE, build.getSnapshot(),
                inputDigest(build), validations(state), ValidationEvidencePolicy.CURRENT_RULE));
        if (hasRequiredGateFailure(gates)) {
            throw new IllegalStateException(ERROR_GRAY_GATE_FAILED);
        }
        DeploymentSource buildSource = new DeploymentSource(SOURCE_BUILD, build.getBuildId(),
                change.getTargetVersion(), build.getSourceDigest());

        ReleaseDeployment deployment = deployment(
                requestId, ReleaseEnvironment.ONLINE, buildSource, gates, userName)
                .setPublishMode("GRAY")
                .setStatus(STATUS_PUBLISHING)
                .setArtifact(build.getArtifact());
        state.getDeployments().add(0, deployment);
        state = stateRepository.save(state, state.getRevision());
        ReleasePublishContext publishContext = publishContext(context, buildSource,
                ReleaseEnvironment.ONLINE, requestId, userName, build.getSnapshot(), build.getArtifact());
        PublishResult publishResult = deploy(context, new ReleaseOperationContext(userName), publishContext);
        deployment = requireDeployment(state, deployment.getDeploymentId());
        applyPublishResult(deployment, publishResult);
        if (StringUtils.equals(deployment.getStatus(), STATUS_SUCCEEDED)) {
            ReleaseVersion version = sealVersion(change, build, publishResult.getArtifact(),
                    matchingValidations(validations(state), inputDigest(build)), userName);
            state.getVersions().add(0, version);
            state.getActiveChange().setStatus(STATUS_SEALED).setUpdateTime(System.currentTimeMillis());
            setCandidate(requireStableEnvironment(state, ReleaseEnvironment.ONLINE),
                    SOURCE_VERSION, version.getVersionId(), version.getVersion(), version.getSourceDigest(),
                    deployment.getDeploymentId(), grayRule);
        }
        stateRepository.save(state, state.getRevision());

        log.info("共享发布线上灰度启动完成, assetType:{}, assetKey:{}, targetVersion:{}, percentage:{}, "
                        + "status:{}, operator:{}", context.assetType, context.assetKey, change.getTargetVersion(), grayRule.getPercentage(), deployment.getStatus(), userName);
        return from(deployment, MESSAGE_GRAY_START_SUCCEEDED);
    }
    private ReleaseOperationResult mutateGray(String userName, Map<String, String> params,
            GrayMutation mutation) {
        ReleaseContext context = context(params);
        requireGraySupported(context);
        assetAuthorizationService.requirePermission(
                userName, context.assetType, context.assetKey, AssetAction.PUBLISH);
        ReleaseEnvironment environment = GrayReleaseRequestParser.environment(params);
        String requestId = required(params, PARAM_REQUEST_ID);
        return stateRepository.executeLocked(context.assetType, context.assetKey, () -> {
            AssetReleaseState state = stateRepository.find(context.assetType, context.assetKey);
            ReleaseDeployment idempotent = resolveIdempotentDeployment(state, environment, requestId);
            if (idempotent != null) {
                return from(idempotent, mutation.message);
            }
            EnvironmentState environmentState = requireStableEnvironment(state, environment);
            ReleasePointer candidate = requireCandidate(
                    state, environmentState, environment, params);
            DeploymentSource source = new DeploymentSource(candidate.getSourceType(), candidate.getSourceId(),
                    candidate.getVersion(), candidate.getDigest());
            if (mutation == GrayMutation.ADJUST) {
                environmentState.setGrayRule(GrayReleaseRequestParser.rule(params)).setGrayStatus(STATUS_GRAYING);
            } else if (mutation == GrayMutation.PROMOTE) {
                promoteCandidate(environmentState, candidate);
            } else {
                clearCandidate(environmentState);
            }
            ReleaseDeployment audit = deployment(requestId, environment, source, List.of(), userName)
                    .setStatus(STATUS_SUCCEEDED)
                    .setPublishMode(mutation.publishMode)
                    .setMessage(mutation.message);
            state.getDeployments().add(0, audit);
            stateRepository.save(state, state.getRevision());
            log.info("共享灰度状态变更完成, assetType:{}, assetKey:{}, environment:{}, mutation:{}, "
                            + "candidateSourceId:{}, operator:{}",
                    context.assetType, context.assetKey, environment, mutation,
                    candidate.getSourceId(), userName);
            return from(audit, mutation.message);
        });
    }
    /** 查询单条部署流水详情。 */
    public ReleaseDeployment deploymentDetail(String userName, Map<String, String> params) {
        ReleaseContext context = context(params);
        assetAuthorizationService.requirePermission(
                userName, context.assetType, context.assetKey, AssetAction.VIEW);
        String deploymentId = required(params, PARAM_DEPLOYMENT_ID);
        return stateRepository.find(context.assetType, context.assetKey).getDeployments().stream()
                .filter(item -> StringUtils.equals(item.getDeploymentId(), deploymentId))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("release deployment not found"));
    }
    private ReleaseOperationResult deployBuild(String userName, Map<String, String> params,
            ReleaseEnvironment environment) {
        ReleaseContext context = context(params);
        assetAuthorizationService.requirePermission(
                userName, context.assetType, context.assetKey, AssetAction.PUBLISH);
        String requestId = required(params, PARAM_REQUEST_ID);
        return stateRepository.executeLocked(context.assetType, context.assetKey, () -> {
            AssetReleaseState state = stateRepository.find(context.assetType, context.assetKey);
            ReleaseOperationContext operationContext = new ReleaseOperationContext(userName);
            AssetSnapshot current = context.adapter.currentPublishSnapshot(
                    operationContext, context.assetKey, context.params);
            verifyDigest(current, required(params, PARAM_EXPECTED_DIGEST));
            ReleasePublishingRecovery.supersedePreprod(state, environment, requestId, context.assetKey, userName);
            ReleaseDeployment idempotent = resolveIdempotentDeployment(state, environment, requestId);
            if (idempotent != null) {
                if (StringUtils.equals(idempotent.getStatus(), STATUS_PUBLISHING)
                        && context.adapter.supportsPublishingRecovery()) {
                    ReleaseDeployment recovered = ReleasePublishingRecovery.recover(
                            state, idempotent, ReleasePublishingRecovery.context(
                                    context.assetKey, context.params, environment, requestId, userName),
                            publishContext -> deploy(context, operationContext, publishContext),
                            this::applyPublishResult);
                    stateRepository.save(state, state.getRevision());
                    return from(recovered, MESSAGE_PREPROD_SUCCEEDED);
                }
                return from(idempotent, MESSAGE_PREPROD_SUCCEEDED);
            }
            requireNoActiveCandidate(state, environment);
            ReleaseChange change = requireActiveChange(context, current, state, userName);
            AssetSnapshot frozen = context.adapter.freezeBuildSnapshot(
                    operationContext, context.assetKey, environment, current, context.params);
            ReleaseModels.ReleaseRelationSnapshot relationSnapshot =
                    context.adapter.freezeBuildRelationSnapshot(
                            context.assetKey, frozen, context.params);
            List<GateResult> gates = mergeGates(context.adapter.evaluateGates(
                    operationContext, context.assetKey, environment, frozen, null, context.params),
                    evaluateValidationGates(context.adapter, environment, frozen, current.getDigest(),
                            validations(state), ValidationEvidencePolicy.CURRENT_RULE));
            ReleaseBuild build = new ReleaseBuild()
                    .setBuildId(id("build"))
                    .setChangeId(change.getChangeId())
                    .setTargetVersion(change.getTargetVersion())
                    .setBuildNumber(nextBuildNumber(state, change.getChangeId()))
                    .setInputDigest(current.getDigest())
                    .setSourceDigest(frozen.getDigest())
                    .setSnapshot(frozen)
                    .setRelationSnapshot(relationSnapshot)
                    .setGates(gates)
                    .setOperator(userName)
                    .setCreateTime(System.currentTimeMillis());
            ReleaseDeployment deployment = deployment(requestId, environment,
                    new DeploymentSource(SOURCE_BUILD, build.getBuildId(), change.getTargetVersion(),
                            frozen.getDigest()), gates, userName);
            if (hasRequiredGateFailure(gates)) {
                build.setStatus(STATUS_FAILED);
                deployment.setStatus(STATUS_FAILED).setMessage("预发发布门禁未通过");
                state.getBuilds().add(0, build);
                state.getDeployments().add(0, deployment);
                change.setSourceDigest(current.getDigest()).setUpdateTime(System.currentTimeMillis());
                stateRepository.save(state, state.getRevision());
            } else {
                ReleaseDeployment previousDeployment = latestRetryableDeployment(state, environment,
                        frozen.getDigest(), null);
                build.setStatus(STATUS_PUBLISHING);
                deployment.setStatus(STATUS_PUBLISHING);
                state.getBuilds().add(0, build);
                state.getDeployments().add(0, deployment);
                change.setSourceDigest(current.getDigest()).setUpdateTime(System.currentTimeMillis());
                state = stateRepository.save(state, state.getRevision());
                ReleasePublishContext publishContext = publishContext(context,
                        new DeploymentSource(SOURCE_BUILD, build.getBuildId(), change.getTargetVersion(),
                                frozen.getDigest()),
                        environment, requestId, userName, frozen, null)
                        .setPreviousDeployment(previousDeployment);
                PublishResult publishResult = deploy(context, new ReleaseOperationContext(userName), publishContext);
                deployment = requireDeployment(state, deployment.getDeploymentId());
                build = requireBuild(state, build.getBuildId());
                applyPublishResult(deployment, publishResult);
                build.setStatus(deployment.getStatus()).setArtifact(publishResult.getArtifact());
                if (StringUtils.equals(deployment.getStatus(), STATUS_SUCCEEDED)) {
                    updateEnvironment(state, environment, SOURCE_BUILD, build.getBuildId(),
                            build.getTargetVersion(), build.getSourceDigest(), deployment.getDeploymentId());
                }
                stateRepository.save(state, state.getRevision());
            }
            log.info("共享发布预发构建完成, assetType:{}, assetKey:{}, targetVersion:{}, buildNumber:{}, "
                            + "status:{}, operator:{}",
                    context.assetType, context.assetKey, change.getTargetVersion(), build.getBuildNumber(),
                    deployment.getStatus(), userName);
            return from(deployment, MESSAGE_PREPROD_SUCCEEDED);
        });
    }

    private ReleaseOverview buildOverview(ReleaseContext context,
            ReleaseOperationContext operationContext, AssetSnapshot current,
            AssetReleaseState state, boolean previewGatesAllowed) {
        List<GateResult> preprodGates = previewGatesAllowed
                ? context.adapter.evaluatePreviewGates(
                        operationContext, context.assetKey, ReleaseEnvironment.PRT,
                        current, null, context.params)
                : List.of();
        List<GateResult> validationGates = evaluateValidationGates(context.adapter, ReleaseEnvironment.PRT,
                current, current.getDigest(), validations(state), ValidationEvidencePolicy.CURRENT_RULE);
        List<GateResult> gates = mergeGates(preprodGates, validationGates);
        Map<String, List<GateResult>> environmentGates = new LinkedHashMap<>();
        environmentGates.put(ReleaseEnvironment.PRT.name(), gates);

        List<String> allowedActions = new ArrayList<>();
        List<String> blockedReasons = new ArrayList<>();
        boolean graySupported = context.adapter.grayReleasePolicy()
                == GrayReleasePolicy.PERCENTAGE_AND_WHITELIST;
        EnvironmentState preprodState = environmentState(state, ReleaseEnvironment.PRT);
        EnvironmentState onlineState = environmentState(state, ReleaseEnvironment.ONLINE);
        boolean preprodGrayActive = graySupported && hasCandidate(preprodState);
        boolean onlineGrayActive = graySupported && hasCandidate(onlineState);
        boolean preprodGrayValid = preprodGrayActive && hasValidActiveGrayState(
                state, ReleaseEnvironment.PRT, preprodState);
        boolean onlineGrayValid = onlineGrayActive && hasValidActiveGrayState(
                state, ReleaseEnvironment.ONLINE, onlineState);
        ReleaseChange active = resolveActiveChange(context, current, state, StringUtils.EMPTY);
        boolean activeChange = active != null && StringUtils.equals(active.getStatus(), STATUS_ACTIVE);
        if (!activeChange) {
            allowedActions.add(ACTION_CREATE_CHANGE);
        } else {
            allowedActions.add(ACTION_DIFF);
            if (preprodGrayActive) {
                if (preprodGrayValid) {
                    addGrayMutationActions(allowedActions, ReleaseEnvironment.PRT);
                    blockedReasons.add("PRT 灰度进行中，请先停止或转全量");
                } else {
                    blockedReasons.add("PRT 灰度状态损坏，请联系平台排查");
                }
            } else if (!hasRequiredGateFailure(gates)) {
                allowedActions.add(ACTION_DEPLOY_PREPROD);
                if (graySupported && hasValidStableEnvironment(
                        state, ReleaseEnvironment.PRT)) {
                    allowedActions.add(ACTION_START_GRAY_PREPROD);
                }
            } else {
                blockedReasons.add(requiredGateFailureMessage("预发", gates));
            }
            ReleaseBuild verified = latestSuccessfulBuild(state, active.getChangeId(), current.getDigest());
            if (verified != null) {
                List<GateResult> onlineGates = previewGatesAllowed
                        ? mergeGates(context.adapter.evaluatePreviewGates(
                                operationContext, context.assetKey, ReleaseEnvironment.ONLINE,
                                verified.getSnapshot(), verified.getArtifact(), context.params),
                                evaluateValidationGates(context.adapter, ReleaseEnvironment.ONLINE,
                                verified.getSnapshot(), inputDigest(verified), validations(state),
                                ValidationEvidencePolicy.CURRENT_RULE))
                        : List.of();
                environmentGates.put(ReleaseEnvironment.ONLINE.name(), onlineGates);
                if (onlineGrayActive) {
                    if (onlineGrayValid) {
                        addGrayMutationActions(allowedActions, ReleaseEnvironment.ONLINE);
                        blockedReasons.add("ONLINE 灰度进行中，请先停止或转全量");
                    } else {
                        blockedReasons.add("ONLINE 灰度状态损坏，请联系平台排查");
                    }
                } else if (!hasRequiredGateFailure(onlineGates)) {
                    allowedActions.add(ACTION_DEPLOY_ONLINE);
                    if (graySupported && hasValidStableEnvironment(
                            state, ReleaseEnvironment.ONLINE)) {
                        allowedActions.add(ACTION_START_GRAY_ONLINE);
                    }
                } else {
                    allowedActions.add(ACTION_FORCE_DEPLOY_ONLINE);
                    blockedReasons.add(requiredGateFailureMessage("线上", onlineGates));
                }
            } else {
                blockedReasons.add("需要与当前摘要一致的成功预发 Build");
            }
        }
        if (preprodGrayValid && !allowedActions.contains(ACTION_ADJUST_GRAY_PREPROD)) {
            addGrayMutationActions(allowedActions, ReleaseEnvironment.PRT);
        }
        if (onlineGrayValid && !allowedActions.contains(ACTION_ADJUST_GRAY_ONLINE)) {
            addGrayMutationActions(allowedActions, ReleaseEnvironment.ONLINE);
        }
        if (!state.getVersions().isEmpty() && !onlineGrayActive) {
            allowedActions.add(ACTION_REDEPLOY_HISTORY);
        }
        return new ReleaseOverview()
                .setGrayReleaseSupported(graySupported)
                .setGrayReleasePolicy(context.adapter.grayReleasePolicy().name())
                .setNextVersion(nextVersion(state))
                .setCurrentSnapshot(current)
                .setActiveChange(readableChange(active))
                .setBuilds(new ArrayList<>(state.getBuilds()))
                .setVersions(new ArrayList<>(state.getVersions()))
                .setDeployments(new ArrayList<>(state.getDeployments()))
                .setEnvironments(new LinkedHashMap<>(state.getEnvironments()))
                .setGates(gates)
                .setEnvironmentGates(environmentGates)
                .setAllowedActions(allowedActions)
                .setBlockedReasons(blockedReasons);
    }
    /**
     * 把领域状态机动作与当前操作者权限取交集。
     *
     * <p>VIEWER 仍能读取版本、Diff 和部署记录，但发布 Tab 不得向其暴露任何修改动作。
     */
    private ReleaseOverview restrictAllowedActions(
            ReleaseOverview overview, AssetAccessResult access) {
        if (!access.getPermissions().isCanEdit() || !access.getPermissions().isCanPublish()) {
            overview.setAllowedActions(overview.getAllowedActions().stream()
                    .filter(action -> StringUtils.equals(action, ACTION_DIFF))
                    .toList());
            if (overview.getBlockedReasons() == null) {
                overview.setBlockedReasons(new ArrayList<>());
            }
            overview.getBlockedReasons().add(StringUtils.defaultIfBlank(access.getReason(), "当前用户仅可查看"));
            return overview;
        }
        if (!access.getPermissions().isCanForcePublish()) {
            overview.setAllowedActions(overview.getAllowedActions().stream()
                    .filter(action -> !StringUtils.equalsAny(
                            action, ACTION_FORCE_DEPLOY_ONLINE))
                    .toList());
        }
        return overview;
    }

    /**
     * 解析管理员强制发布标志；空值表示普通发布，其他非布尔值直接拒绝。
     */
    private boolean forcePublish(Map<String, String> params) {
        String value = StringUtils.trimToEmpty(params.get(PARAM_FORCE_PUBLISH));
        if (StringUtils.isBlank(value)) {
            return false;
        }
        if (!StringUtils.equalsAnyIgnoreCase(value, Boolean.TRUE.toString(), Boolean.FALSE.toString())) {
            throw new IllegalArgumentException(ERROR_FORCE_PUBLISH_INVALID);
        }
        return Boolean.parseBoolean(value);
    }

    private ReleaseContext context(Map<String, String> params) {
        ReleaseAssetType assetType = ReleaseAssetType.parse(required(params, PARAM_ASSET_TYPE));
        String assetKey = required(params, PARAM_ASSET_KEY);
        return new ReleaseContext(assetType, assetKey, adapterRegistry.get(assetType), new HashMap<>(params));
    }

    private void verifyDigest(AssetSnapshot snapshot, String expectedDigest) {
        if (!StringUtils.equals(snapshot.getDigest(), expectedDigest)) {
            throw new IllegalStateException(ERROR_DIGEST_CHANGED);
        }
    }
    /**
     * 获取可发布变更，并按领域声明补齐新资产的首个可编辑变更。
     *
     * <p>首次发布时在同一个资产锁内把领域已有的编辑态固化为 ACTIVE change，避免首个版本必须先选择
     * 不存在的正式版本。领域是否具备初始编辑态由 Adapter 明确声明，共享层不猜测领域状态字段。
     */
    private ReleaseChange requireActiveChange(ReleaseContext context, AssetSnapshot current,
            AssetReleaseState state, String operator) {
        ReleaseChange change = resolveActiveChange(context, current, state, operator);
        if (change == null || !StringUtils.equals(change.getStatus(), STATUS_ACTIVE)) {
            throw new IllegalStateException(ERROR_ACTIVE_CHANGE_REQUIRED);
        }
        if (state.getActiveChange() == null
                || !StringUtils.equals(state.getActiveChange().getStatus(), STATUS_ACTIVE)) {
            state.setActiveChange(change);
            log.info("共享发布补齐资产初始编辑变更, assetType:{}, assetKey:{}, targetVersion:{}, operator:{}",
                    context.assetType, context.assetKey, change.getTargetVersion(), operator);
        }
        return change;
    }
    /**
     * 返回显式 ACTIVE change，或按领域声明为没有历史正式版本的新资产构造初始变更。
     */
    private ReleaseChange resolveActiveChange(ReleaseContext context, AssetSnapshot current,
            AssetReleaseState state, String operator) {
        ReleaseChange active = state.getActiveChange();
        if (active != null && StringUtils.equals(active.getStatus(), STATUS_ACTIVE)) {
            return active;
        }
        if (!state.getVersions().isEmpty() || !context.adapter.isInitialEditableChange(current)) {
            return active;
        }
        int targetVersion = nextVersion(state);
        long now = System.currentTimeMillis();
        return new ReleaseChange()
                .setChangeId(INITIAL_CHANGE_ID_PREFIX + context.assetKey + "-" + targetVersion)
                .setRequestId(INITIAL_CHANGE_REQUEST_ID)
                .setChangeName(LABEL_INITIAL_VERSION)
                .setTargetVersion(targetVersion)
                .setStatus(STATUS_ACTIVE)
                .setSourceDigest(current.getDigest())
                .setOperator(operator)
                .setCreateTime(now)
                .setUpdateTime(now);
    }

    private ReleaseVersion requireVersion(AssetReleaseState state, int version) {
        return state.getVersions().stream()
                .filter(item -> Objects.equals(item.getVersion(), version))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("release version not found: " + version));
    }

    private ReleaseVersion onlineVersion(AssetReleaseState state) {
        EnvironmentState online = state.getEnvironments().get(ReleaseEnvironment.ONLINE.name());
        return online == null || online.getVersion() == null ? null : requireVersion(state, online.getVersion());
    }

    private ReleaseBuild latestSuccessfulBuild(AssetReleaseState state, String changeId, String digest) {
        return state.getBuilds().stream()
                .filter(item -> StringUtils.equals(item.getChangeId(), changeId))
                .filter(item -> StringUtils.equals(inputDigest(item), digest))
                .filter(item -> StringUtils.equals(item.getStatus(), STATUS_SUCCEEDED))
                .max(Comparator.comparing(ReleaseBuild::getBuildNumber))
                .orElse(null);
    }

    private boolean hasRequiredGateFailure(List<GateResult> gates) {
        return gates.stream().anyMatch(item -> Boolean.TRUE.equals(item.getRequired())
                && !StringUtils.equals(item.getStatus(), GATE_PASSED));
    }
    /** 把领域门禁与共享摘要证据门禁合并成单一判断结果。 */
    private List<GateResult> mergeGates(List<GateResult> first, List<GateResult> second) {
        Map<String, GateResult> result = new LinkedHashMap<>();
        if (first != null) {
            first.forEach(gate -> mergeGate(result, gate));
        }
        if (second != null) {
            second.forEach(gate -> mergeGate(result, gate));
        }
        return new ArrayList<>(result.values());
    }
    /** 同一门禁编码只展示一行，失败或过期结果不得被成功结果覆盖。 */
    private void mergeGate(Map<String, GateResult> result, GateResult candidate) {
        if (candidate == null) {
            return;
        }
        String code = StringUtils.defaultIfBlank(candidate.getCode(), id("gate"));
        GateResult current = result.get(code);
        if (current == null || StringUtils.equals(current.getStatus(), GATE_PASSED)
                && !StringUtils.equals(candidate.getStatus(), GATE_PASSED)) {
            result.put(code, candidate);
        }
    }
    /**
     * 根据领域声明，把已保存证据转换为共享发布门禁。
     *
     * <p>当前内容可执行 Adapter 声明的可选规则版本校验；历史正式版本只信任封板时冻结的证据，
     * 不用当前规则追溯淘汰已发布版本。
     */
    private List<GateResult> evaluateValidationGates(ReleaseAssetAdapter adapter, ReleaseEnvironment environment,
            AssetSnapshot snapshot, String sourceDigest, Map<String, ReleaseValidationEvidence> evidenceMap,
            ValidationEvidencePolicy evidencePolicy) {
        List<GateResult> gates = new ArrayList<>();
        for (ReleaseValidationRequirement requirement : adapter.validationRequirements(environment, snapshot)) {
            ReleaseValidationEvidence evidence = evidenceMap.get(requirement.getCode());
            String status;
            String message;
            if (evidence == null) {
                status = GATE_FAILED;
                message = "尚未生成准出证据";
            } else if (!StringUtils.equals(evidence.getBoundDigest(), sourceDigest)) {
                status = GATE_EXPIRED;
                message = "准出证据绑定的文件摘要与当前内容不一致，请重新核验";
            } else if (evidencePolicy == ValidationEvidencePolicy.CURRENT_RULE
                    && StringUtils.isNotBlank(requirement.getExpectedRuleVersion())
                    && !StringUtils.equals(StringUtils.trim(requirement.getExpectedRuleVersion()),
                            StringUtils.trim(evidence.getRuleVersion()))) {
                status = GATE_EXPIRED;
                message = MESSAGE_VALIDATION_RULE_VERSION_EXPIRED;
            } else if (!StringUtils.equals(evidence.getStatus(), VALIDATION_STATUS_PASSED)) {
                status = GATE_FAILED;
                message = StringUtils.defaultIfBlank(evidence.getSummary(), "准出检查未通过");
            } else {
                status = GATE_PASSED;
                message = StringUtils.defaultIfBlank(evidence.getSummary(), "准出检查已通过");
            }
            gates.add(new GateResult()
                    .setCode(requirement.getCode())
                    .setLabel(requirement.getLabel())
                    .setStatus(status)
                    .setRequired(true)
                    .setMessage(message));
        }
        return gates;
    }
    /** 当前草稿证据与正式版本冻结证据采用不同的规则版本策略。 */
    private enum ValidationEvidencePolicy {
        CURRENT_RULE,
        FROZEN_RULE
    }

    private ReleaseValidationRequirement requireValidationRequirement(ReleaseAssetAdapter adapter,
            String checkCode) {
        return Arrays.stream(ReleaseEnvironment.values())
                .flatMap(environment -> adapter.validationRequirements(environment).stream())
                .filter(item -> StringUtils.equals(item.getCode(), StringUtils.trim(checkCode)))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(ERROR_VALIDATION_CODE_UNSUPPORTED));
    }

    private Map<String, ReleaseValidationEvidence> validations(AssetReleaseState state) {
        if (state.getValidations() == null) {
            state.setValidations(new LinkedHashMap<>());
        }
        return state.getValidations();
    }

    private Map<String, ReleaseValidationEvidence> validations(ReleaseVersion version) {
        return version.getValidations() == null ? new LinkedHashMap<>() : version.getValidations();
    }
    /** 只把与封板摘要一致的准出证据冻结到正式版本。 */
    private Map<String, ReleaseValidationEvidence> matchingValidations(
            Map<String, ReleaseValidationEvidence> source, String digest) {
        Map<String, ReleaseValidationEvidence> result = new LinkedHashMap<>();
        source.forEach((code, evidence) -> {
            if (evidence != null && StringUtils.equals(evidence.getBoundDigest(), digest)) {
                result.put(code, copyEvidence(evidence));
            }
        });
        return result;
    }

    private ReleaseValidationEvidence copyEvidence(ReleaseValidationEvidence source) {
        return new ReleaseValidationEvidence()
                .setCheckCode(source.getCheckCode())
                .setStatus(source.getStatus())
                .setBoundDigest(source.getBoundDigest())
                .setRuleVersion(source.getRuleVersion())
                .setCheckRunId(source.getCheckRunId())
                .setSummary(source.getSummary())
                .setFindings(copyFindings(source.getFindings()))
                .setChecks(copyChecks(source.getChecks()))
                .setWaivers(copyWaivers(source.getWaivers()))
                .setOperator(source.getOperator())
                .setCheckedAt(source.getCheckedAt());
    }

    private List<Map<String, Object>> copyFindings(List<Map<String, Object>> findings) {
        List<Map<String, Object>> result = new ArrayList<>();
        if (findings != null) {
            findings.forEach(item -> result.add(item == null ? new LinkedHashMap<>()
                    : new LinkedHashMap<>(item)));
        }
        return result;
    }

    private List<ReleaseReadinessCheck> copyChecks(List<ReleaseReadinessCheck> checks) {
        List<ReleaseReadinessCheck> result = new ArrayList<>();
        if (checks != null) {
            checks.forEach(check -> result.add(check == null ? new ReleaseReadinessCheck()
                    : new ReleaseReadinessCheck()
                            .setCode(check.getCode())
                            .setStatus(check.getStatus())
                            .setRequired(check.getRequired())
                            .setSource(check.getSource())
                            .setSummary(check.getSummary())
                            .setFindings(copyFindings(check.getFindings()))));
        }
        return result;
    }

    private List<ReleaseValidationWaiver> copyWaivers(List<ReleaseValidationWaiver> waivers) {
        List<ReleaseValidationWaiver> result = new ArrayList<>();
        if (waivers != null) {
            waivers.forEach(waiver -> result.add(waiver == null ? new ReleaseValidationWaiver()
                    : new ReleaseValidationWaiver()
                            .setCheckCode(waiver.getCheckCode())
                            .setReason(waiver.getReason())
                            .setMessageId(waiver.getMessageId())
                            .setRunId(waiver.getRunId())
                            .setOperator(waiver.getOperator())
                            .setWaivedAt(waiver.getWaivedAt())));
        }
        return result;
    }
    /**
     * 按环境处理当前发布与最近一次完成发布的幂等语义。
     *
     * <p>同一环境存在 PUBLISHING 时，相同 requestId 返回当前流水，不同 requestId 拒绝并发。
     * 没有进行中流水时，只检查该环境最近一条部署：相同 requestId 且成功或平台待续时复用；
     * 失败和部分失败允许用相同 requestId 创建新的 deploymentId 重试。更早的历史流水只用于审计，
     * 不再永久阻断历史版本重发。
     */
    private ReleaseDeployment resolveIdempotentDeployment(AssetReleaseState state,
            ReleaseEnvironment environment, String requestId) {
        ReleaseDeployment latest = latestDeployment(state, environment, null);
        if (latest == null) {
            return null;
        }
        if (StringUtils.equals(latest.getStatus(), STATUS_PUBLISHING)) {
            if (StringUtils.equals(latest.getRequestId(), requestId)) {
                log.info("共享发布复用进行中流水, environment:{}, requestId:{}, deploymentId:{}",
                        environment, requestId, latest.getDeploymentId());
                return latest;
            }
            throw new IllegalStateException(ERROR_DEPLOYMENT_IN_PROGRESS);
        }
        if (!StringUtils.equalsAny(latest.getStatus(), STATUS_SUCCEEDED, STATUS_PLATFORM_PENDING,
                STATUS_FAILED, STATUS_PARTIAL_FAILED)) {
            throw new IllegalStateException(ERROR_DEPLOYMENT_STATUS_UNSUPPORTED
                    + ": environment=" + environment + ", status="
                    + StringUtils.defaultIfBlank(latest.getStatus(), STATUS_UNKNOWN));
        }
        if (!StringUtils.equals(latest.getRequestId(), requestId)) {
            return null;
        }
        if (StringUtils.equalsAny(latest.getStatus(), STATUS_SUCCEEDED, STATUS_PLATFORM_PENDING)) {
            log.info("共享发布复用最近完成流水, environment:{}, requestId:{}, deploymentId:{}, status:{}",
                    environment, requestId, latest.getDeploymentId(), latest.getStatus());
            return latest;
        }
        log.info("共享发布最近失败流水允许原requestId重试, environment:{}, requestId:{}, "
                        + "deploymentId:{}, status:{}",
                environment, requestId, latest.getDeploymentId(), latest.getStatus());
        return null;
    }
    /** 返回指定环境和可选状态的最近一条部署。 */
    private ReleaseDeployment latestDeployment(AssetReleaseState state, ReleaseEnvironment environment,
            String status) {
        return state.getDeployments().stream()
                .filter(item -> StringUtils.equals(item.getEnvironment(), environment.name()))
                .filter(item -> StringUtils.isBlank(status) || StringUtils.equals(item.getStatus(), status))
                .max(Comparator.comparing(this::deploymentTimestamp))
                .orElse(null);
    }

    private long deploymentTimestamp(ReleaseDeployment deployment) {
        return Objects.requireNonNullElse(deployment.getUpdateTime(),
                Objects.requireNonNullElse(deployment.getCreateTime(), 0L));
    }
    /** 复制变更并为旧状态补充只读展示名，不回写历史 state_json。 */
    private ReleaseChange readableChange(ReleaseChange change) {
        if (change == null) {
            return null;
        }
        String version = change.getTargetVersion() == null
                ? StringUtils.EMPTY : String.valueOf(change.getTargetVersion());
        return new ReleaseChange()
                .setChangeId(change.getChangeId())
                .setRequestId(change.getRequestId())
                .setChangeName(StringUtils.defaultIfBlank(
                        change.getChangeName(), LABEL_VERSION_PREFIX + version + LABEL_CHANGE_SUFFIX))
                .setTargetVersion(change.getTargetVersion())
                .setBaseVersion(change.getBaseVersion())
                .setStatus(change.getStatus())
                .setSourceDigest(change.getSourceDigest())
                .setOperator(change.getOperator())
                .setCreateTime(change.getCreateTime())
                .setUpdateTime(change.getUpdateTime());
    }

    private ReleaseDeployment deployment(String requestId, ReleaseEnvironment environment, DeploymentSource source,
            List<GateResult> gates, String operator) {
        long now = System.currentTimeMillis();
        return new ReleaseDeployment()
                .setDeploymentId(id("deployment"))
                .setRequestId(requestId)
                .setEnvironment(environment.name())
                .setSourceType(source.type)
                .setSourceId(source.id)
                .setSourceVersion(source.version)
                .setSourceDigest(source.digest)
                .setGates(gates)
                .setOperator(operator)
                .setCreateTime(now)
                .setUpdateTime(now);
    }

    private void applyPublishResult(ReleaseDeployment deployment, PublishResult publishResult) {
        String status = StringUtils.defaultIfBlank(StringUtils.trim(publishResult.getStatus()), STATUS_UNKNOWN);
        boolean supported = StringUtils.equalsAny(status, STATUS_SUCCEEDED, STATUS_FAILED,
                STATUS_PLATFORM_PENDING, STATUS_PARTIAL_FAILED);
        String errorCode = publishResult.getErrorCode();
        String message = publishResult.getMessage();
        if (!supported) {
            errorCode = ERROR_CODE_DEPLOYMENT_STATUS_UNSUPPORTED;
            message = ERROR_DEPLOYMENT_STATUS_UNSUPPORTED + ": " + status;
            log.error("共享发布领域Adapter返回未知状态, deploymentId:{}, environment:{}, status:{}",
                    deployment.getDeploymentId(), deployment.getEnvironment(), status);
        }
        deployment.setStatus(status)
                .setCurrentStage(publishResult.getCurrentStage())
                .setRetryable(supported && Boolean.TRUE.equals(publishResult.getRetryable()))
                .setErrorCode(errorCode)
                .setMessage(message)
                .setArtifact(publishResult.getArtifact())
                .setDomainResult(publishResult.getData())
                .setUpdateTime(System.currentTimeMillis());
    }
    /**
     * 使用共享控制面冻结的来源信息构造领域发布上下文，避免 Adapter 从当前页面参数猜测历史版本。
     */
    private ReleasePublishContext publishContext(ReleaseContext context, DeploymentSource source,
            ReleaseEnvironment environment, String requestId, String userName, AssetSnapshot snapshot,
            ReleaseArtifact artifact) {
        return new ReleasePublishContext()
                .setUserName(userName)
                .setAssetKey(context.assetKey)
                .setEnvironment(environment)
                .setSourceType(source.type)
                .setSourceId(source.id)
                .setSourceVersion(source.version)
                .setRequestId(requestId)
                .setSnapshot(snapshot)
                .setArtifact(artifact)
                .setParams(new HashMap<>(context.params));
    }

    private PublishResult deploy(ReleaseContext context,
            ReleaseOperationContext operationContext, ReleasePublishContext publishContext) {
        log.info("共享发布调用领域Adapter, assetType:{}, assetKey:{}, environment:{}, sourceType:{}, "
                        + "sourceVersion:{}, requestId:{}",
                context.assetType, context.assetKey, publishContext.getEnvironment(),
                publishContext.getSourceType(), publishContext.getSourceVersion(), publishContext.getRequestId());
        try {
            return context.adapter.deploy(operationContext, publishContext);
        } catch (RuntimeException e) {
            log.warn("共享发布调用领域Adapter失败, assetType:{}, assetKey:{}, environment:{}, sourceType:{}, "
                            + "sourceVersion:{}, requestId:{}",
                    context.assetType, context.assetKey, publishContext.getEnvironment(),
                    publishContext.getSourceType(), publishContext.getSourceVersion(),
                    publishContext.getRequestId(), e);
            return new PublishResult()
                    .setStatus(STATUS_FAILED)
                    .setCurrentStage("ADAPTER_FAILED")
                    .setRetryable(false)
                    .setErrorCode("ADAPTER_EXCEPTION")
                    .setMessage(ERROR_DOMAIN_PUBLISH_FAILED)
                    .setData(new LinkedHashMap<>());
        }
    }

    private String inputDigest(ReleaseBuild build) {
        return StringUtils.defaultIfBlank(build.getInputDigest(), build.getSourceDigest());
    }

    private String inputDigest(ReleaseVersion version) {
        return StringUtils.defaultIfBlank(version.getInputDigest(), version.getSourceDigest());
    }

    private ReleaseDeployment requireDeployment(AssetReleaseState state, String deploymentId) {
        return state.getDeployments().stream()
                .filter(item -> StringUtils.equals(item.getDeploymentId(), deploymentId))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("release deployment not found: " + deploymentId));
    }

    private ReleaseBuild requireBuild(AssetReleaseState state, String buildId) {
        return state.getBuilds().stream()
                .filter(item -> StringUtils.equals(item.getBuildId(), buildId))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("release build not found: " + buildId));
    }
    /**
     * 查找同环境、同产物最近一条可重试部署，供领域 Adapter 判断是否只重试末端运行平台注册。
     */
    private ReleaseDeployment latestRetryableDeployment(AssetReleaseState state, ReleaseEnvironment environment,
            String sourceDigest, ReleaseArtifact artifact) {
        ReleaseDeployment latest = latestDeployment(state, environment, null);
        if (latest == null
                || !StringUtils.equalsAny(latest.getStatus(), STATUS_FAILED, STATUS_PARTIAL_FAILED)
                || !Boolean.TRUE.equals(latest.getRetryable())
                || !StringUtils.equals(latest.getSourceDigest(), sourceDigest)
                || (artifact != null && !sameArtifact(latest.getArtifact(), artifact))) {
            return null;
        }
        return latest;
    }

    private boolean sameArtifact(ReleaseArtifact left, ReleaseArtifact right) {
        if (left == null || right == null) {
            return left == right;
        }
        return StringUtils.equals(left.getPackageDigest(), right.getPackageDigest())
                && StringUtils.equals(left.getObjectKey(), right.getObjectKey());
    }

    private void updateEnvironment(AssetReleaseState state, ReleaseEnvironment environment, String sourceType,
            String sourceId, Integer version, String digest, String deploymentId) {
        environments(state).put(environment.name(), new EnvironmentState()
                .setEnvironment(environment.name())
                .setSourceType(sourceType)
                .setSourceId(sourceId)
                .setVersion(version)
                .setDigest(digest)
                .setDeploymentId(deploymentId)
                .setUpdateTime(System.currentTimeMillis()));
    }

    private void requireGraySupported(ReleaseContext context) {
        if (context.adapter.grayReleasePolicy() != GrayReleasePolicy.PERCENTAGE_AND_WHITELIST) {
            throw new IllegalStateException(ERROR_GRAY_RELEASE_UNSUPPORTED);
        }
    }

    private Map<String, EnvironmentState> environments(AssetReleaseState state) {
        if (state.getEnvironments() == null) {
            state.setEnvironments(new LinkedHashMap<>());
        }
        return state.getEnvironments();
    }

    private EnvironmentState environmentState(AssetReleaseState state, ReleaseEnvironment environment) {
        return environments(state).get(environment.name());
    }

    private EnvironmentState requireStableEnvironment(AssetReleaseState state, ReleaseEnvironment environment) {
        EnvironmentState environmentState = environmentState(state, environment);
        String expectedSourceType = environment == ReleaseEnvironment.PRT ? SOURCE_BUILD : SOURCE_VERSION;
        if (environmentState == null
                || !StringUtils.equals(environmentState.getEnvironment(), environment.name())
                || !StringUtils.equals(environmentState.getSourceType(), expectedSourceType)
                || StringUtils.isAnyBlank(environmentState.getSourceId(), environmentState.getDigest())
                || environmentState.getVersion() == null) {
            throw new IllegalStateException(ERROR_GRAY_STABLE_REQUIRED);
        }
        if (environment == ReleaseEnvironment.PRT) {
            ReleaseBuild build = requireBuild(state, environmentState.getSourceId());
            if (!StringUtils.equals(build.getStatus(), STATUS_SUCCEEDED)
                    || !Objects.equals(build.getTargetVersion(), environmentState.getVersion())
                    || !StringUtils.equals(build.getSourceDigest(), environmentState.getDigest())) {
                throw new IllegalStateException(ERROR_GRAY_STABLE_REQUIRED);
            }
        } else {
            ReleaseVersion version = state.getVersions().stream()
                    .filter(item -> StringUtils.equals(item.getVersionId(), environmentState.getSourceId()))
                    .findFirst()
                    .orElseThrow(() -> new IllegalStateException(ERROR_GRAY_STABLE_REQUIRED));
            if (!Objects.equals(version.getVersion(), environmentState.getVersion())
                    || !StringUtils.equals(version.getSourceDigest(), environmentState.getDigest())) {
                throw new IllegalStateException(ERROR_GRAY_STABLE_REQUIRED);
            }
        }
        return environmentState;
    }

    private void requireNoActiveCandidate(AssetReleaseState state, ReleaseEnvironment environment) {
        if (hasCandidate(environmentState(state, environment))) {
            throw new IllegalStateException(ERROR_GRAY_ACTIVE);
        }
    }

    private void requireGrayStartable(EnvironmentState environmentState) {
        if (environmentState.getCandidate() != null) {
            throw new IllegalStateException(ERROR_GRAY_ACTIVE);
        }
        if (environmentState.getGrayRule() != null
                || (StringUtils.isNotBlank(environmentState.getGrayStatus())
                && !StringUtils.equals(environmentState.getGrayStatus(), STATUS_STABLE))) {
            throw new IllegalStateException(ERROR_GRAY_STATE_INVALID);
        }
    }

    private boolean hasValidStableEnvironment(
            AssetReleaseState state, ReleaseEnvironment environment) {
        try {
            requireStableEnvironment(state, environment);
            return true;
        } catch (IllegalStateException exception) {
            return false;
        }
    }

    private boolean hasValidActiveGrayState(AssetReleaseState state,
            ReleaseEnvironment environment, EnvironmentState environmentState) {
        try {
            requireStableEnvironment(state, environment);
            ReleasePointer candidate = environmentState.getCandidate();
            String expectedSourceType = environment == ReleaseEnvironment.PRT
                    ? SOURCE_BUILD : SOURCE_VERSION;
            if (candidate == null
                    || !StringUtils.equals(environmentState.getGrayStatus(), STATUS_GRAYING)
                    || !validStoredGrayRule(environmentState.getGrayRule())
                    || !StringUtils.equals(candidate.getSourceType(), expectedSourceType)
                    || StringUtils.isAnyBlank(candidate.getSourceId(), candidate.getDigest())
                    || candidate.getVersion() == null) {
                return false;
            }
            requireImmutableCandidate(state, environment, candidate);
            return true;
        } catch (IllegalStateException exception) {
            return false;
        }
    }

    private boolean hasCandidate(EnvironmentState environmentState) {
        return environmentState != null && environmentState.getCandidate() != null;
    }

    private ReleasePointer requireCandidate(AssetReleaseState state,
            EnvironmentState environmentState, ReleaseEnvironment environment,
            Map<String, String> params) {
        ReleasePointer candidate = environmentState.getCandidate();
        GrayReleaseRule currentRule = environmentState.getGrayRule();
        String expectedSourceType = environment == ReleaseEnvironment.PRT
                ? SOURCE_BUILD : SOURCE_VERSION;
        if (candidate == null
                || !StringUtils.equals(environmentState.getGrayStatus(), STATUS_GRAYING)
                || !validStoredGrayRule(currentRule)
                || !StringUtils.equals(candidate.getSourceType(), expectedSourceType)
                || StringUtils.isAnyBlank(candidate.getSourceType(), candidate.getSourceId(), candidate.getDigest())
                || candidate.getVersion() == null) {
            throw new IllegalStateException(ERROR_GRAY_CANDIDATE_REQUIRED);
        }
        requireImmutableCandidate(state, environment, candidate);
        String expectedSourceId = required(params, PARAM_CANDIDATE_SOURCE_ID);
        String expectedDigest = required(params, PARAM_CANDIDATE_DIGEST);
        if (!StringUtils.equals(candidate.getSourceId(), expectedSourceId)
                || !StringUtils.equals(candidate.getDigest(), expectedDigest)) {
            throw new IllegalStateException(ERROR_GRAY_CANDIDATE_CHANGED);
        }
        return candidate;
    }

    private boolean validStoredGrayRule(GrayReleaseRule rule) {
        if (rule == null || rule.getPercentage() == null
                || rule.getPercentage() < MIN_GRAY_PERCENTAGE
                || rule.getPercentage() > MAX_GRAY_PERCENTAGE
                || rule.getUserIdWhitelist() == null) {
            return false;
        }
        return rule.getUserIdWhitelist().stream()
                .allMatch(Objects::nonNull)
                && rule.getUserIdWhitelist().stream().distinct().count()
                == rule.getUserIdWhitelist().size();
    }

    private void requireImmutableCandidate(AssetReleaseState state,
            ReleaseEnvironment environment, ReleasePointer candidate) {
        if (environment == ReleaseEnvironment.PRT) {
            ReleaseBuild build = state.getBuilds().stream()
                    .filter(item -> StringUtils.equals(
                            item.getBuildId(), candidate.getSourceId()))
                    .findFirst()
                    .orElseThrow(() -> new IllegalStateException(ERROR_GRAY_STATE_INVALID));
            if (!StringUtils.equals(build.getStatus(), STATUS_SUCCEEDED)
                    || !Objects.equals(build.getTargetVersion(), candidate.getVersion())
                    || !StringUtils.equals(build.getSourceDigest(), candidate.getDigest())) {
                throw new IllegalStateException(ERROR_GRAY_STATE_INVALID);
            }
            return;
        }
        ReleaseVersion version = state.getVersions().stream()
                .filter(item -> StringUtils.equals(
                        item.getVersionId(), candidate.getSourceId()))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException(ERROR_GRAY_STATE_INVALID));
        if (!Objects.equals(version.getVersion(), candidate.getVersion())
                || !StringUtils.equals(version.getSourceDigest(), candidate.getDigest())) {
            throw new IllegalStateException(ERROR_GRAY_STATE_INVALID);
        }
    }

    private void setCandidate(EnvironmentState environmentState, String sourceType, String sourceId,
            Integer version, String digest, String deploymentId, GrayReleaseRule rule) {
        environmentState
                .setCandidate(new ReleasePointer()
                        .setSourceType(sourceType)
                        .setSourceId(sourceId)
                        .setVersion(version)
                        .setDigest(digest)
                        .setDeploymentId(deploymentId)
                        .setUpdateTime(System.currentTimeMillis()))
                .setGrayRule(rule)
                .setGrayStatus(STATUS_GRAYING);
    }

    private void promoteCandidate(EnvironmentState environmentState, ReleasePointer candidate) {
        environmentState
                .setSourceType(candidate.getSourceType())
                .setSourceId(candidate.getSourceId())
                .setVersion(candidate.getVersion())
                .setDigest(candidate.getDigest())
                .setDeploymentId(candidate.getDeploymentId())
                .setUpdateTime(System.currentTimeMillis());
        clearCandidate(environmentState);
    }

    private void clearCandidate(EnvironmentState environmentState) {
        environmentState
                .setCandidate(null)
                .setGrayRule(null)
                .setGrayStatus(STATUS_STABLE);
    }

    private void addGrayMutationActions(List<String> allowedActions, ReleaseEnvironment environment) {
        if (environment == ReleaseEnvironment.PRT) {
            allowedActions.add(ACTION_ADJUST_GRAY_PREPROD);
            allowedActions.add(ACTION_STOP_GRAY_PREPROD);
            allowedActions.add(ACTION_PROMOTE_GRAY_PREPROD);
        } else {
            allowedActions.add(ACTION_ADJUST_GRAY_ONLINE);
            allowedActions.add(ACTION_STOP_GRAY_ONLINE);
            allowedActions.add(ACTION_PROMOTE_GRAY_ONLINE);
        }
    }

    private int nextVersion(AssetReleaseState state) {
        return state.getVersions().stream()
                .map(ReleaseVersion::getVersion)
                .filter(Objects::nonNull)
                .max(Integer::compareTo)
                .orElse(0) + 1;
    }

    private int nextBuildNumber(AssetReleaseState state, String changeId) {
        return state.getBuilds().stream()
                .filter(item -> StringUtils.equals(item.getChangeId(), changeId))
                .map(ReleaseBuild::getBuildNumber)
                .filter(Objects::nonNull)
                .max(Integer::compareTo)
                .orElse(0) + 1;
    }
    /** 从统一 RELEASE_DIFF 参数构造强类型查询，非法展示模式必须显式失败。 */
    private ReleaseDiffQuery diffQuery(Map<String, String> params) {
        String viewModeValue = params.get(PARAM_VIEW_MODE);
        ReleaseDiffViewMode viewMode = ReleaseDiffViewMode.UNIFIED;
        if (StringUtils.isNotBlank(viewModeValue)) {
            try {
                viewMode = ReleaseDiffViewMode.valueOf(StringUtils.upperCase(viewModeValue));
            } catch (IllegalArgumentException e) {
                throw new IllegalArgumentException(ERROR_DIFF_VIEW_MODE_INVALID + ": " + viewModeValue, e);
            }
        }
        return new ReleaseDiffQuery()
                .setEntryPath(StringUtils.trimToNull(params.get(PARAM_ENTRY_PATH)))
                .setViewMode(viewMode)
                .setContextLines(optionalInteger(params.get(PARAM_CONTEXT_LINES)));
    }

    private String required(Map<String, String> params, String key) {
        String value = params == null ? null : params.get(key);
        if (StringUtils.isBlank(value)) {
            throw new IllegalArgumentException(key + ERROR_REQUIRED_SUFFIX);
        }
        return value;
    }

    private Integer optionalInteger(String value) {
        return StringUtils.isBlank(value) ? null : integer(value, "integer");
    }

    private int integer(String value, String field) {
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(field + " must be integer", e);
        }
    }

    private String id(String prefix) {
        return prefix + "_" + UUID.randomUUID().toString().replace("-", "");
    }

    private record ReleaseContext(ReleaseAssetType assetType, String assetKey,
            ReleaseAssetAdapter adapter, Map<String, String> params) { }
    /** 部署来源的内部值对象，避免部署构造方法暴露过多同类型参数。 */
    private static final class DeploymentSource {
        private final String type;
        private final String id;
        private final Integer version;
        private final String digest;

        private DeploymentSource(String type, String id, Integer version, String digest) {
            this.type = type;
            this.id = id;
            this.version = version;
            this.digest = digest;
        }
    }

    /** 不调用领域发布器的灰度状态变更类型。 */
    private enum GrayMutation {
        ADJUST(PUBLISH_MODE_GRAY_ADJUST, "灰度规则调整完成"),
        STOP(PUBLISH_MODE_GRAY_STOP, "灰度已停止，稳定版本保持不变"),
        PROMOTE(PUBLISH_MODE_GRAY_PROMOTE, "灰度候选已转为稳定版本");

        private final String publishMode;
        private final String message;

        GrayMutation(String publishMode, String message) {
            this.publishMode = publishMode;
            this.message = message;
        }
    }
}
