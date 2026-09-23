package dev.a2flow.management.access;

import java.nio.file.Path;
import java.util.Map;

import jakarta.annotation.Resource;

import org.springframework.stereotype.Service;

import org.springframework.transaction.annotation.Transactional;
import dev.a2flow.management.lifecycle.CapabilityActionClassificationRelationService;
import dev.a2flow.management.lifecycle.CapabilityActionClassificationRelationService.ClassificationSelection;
import dev.a2flow.management.lifecycle.SkillFactorySpecialistRelationService;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.lifecycle.domain.SkillDraft;
import dev.a2flow.management.model.CapabilityActionDraft;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.storage.db.entity.WorkflowDefinitionDO;
import dev.a2flow.management.storage.db.mapper.SkillFactoryMapperConstants;
import dev.a2flow.management.storage.db.repository.CapabilityActionDraftRepository;
import dev.a2flow.management.storage.db.repository.SkillFactoryComponentAssetRepository;
import dev.a2flow.management.storage.db.repository.SkillFactoryWorkspaceRepository;
import dev.a2flow.management.storage.db.repository.WorkflowDefinitionRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 资产创建的短数据库事务编排服务。
 *
 * <p>上游 Skill、组件、业务能力和 Workflow 创建 Service 在完成参数校验后调用本类；下游只访问
 * sellerDataManager 中的领域 Repository 和非版本化负责人关系。本类保证领域记录与初始
 * ACTIVE OWNER 同事务成功或回滚，不执行文件扫描、文件写入、模型推理、LangBridge 或发布调用。
 */
@Service
@Slf4j
public class AssetCreationTransactionService {

    private static final String PARAM_SPECIALIST_IDS = "specialistIds";
    private static final String PARAM_OWNERS_JSON = "ownersJson";

    @Resource
    private SkillFactoryWorkspaceRepository skillFactoryWorkspaceRepository;

    @Resource
    private SkillFactorySpecialistRelationService specialistRelationService;

    @Resource
    private SkillFactoryComponentAssetRepository componentAssetRepository;

    @Resource
    private CapabilityActionDraftRepository capabilityActionDraftRepository;

    @Resource
    private CapabilityActionClassificationRelationService capabilityClassificationRelationService;

    @Resource
    private AssetAuthorizationService assetAuthorizationService;

    @Resource
    private WorkflowDefinitionRepository workflowDefinitionRepository;

    /**
     * 原子写入 Skill 草稿元数据、当前版本所属专员关系和稳定资产负责人。
     */
    @Transactional(rollbackFor = Exception.class)
    public SkillDraft createSkill(String operator, String workspaceId, Path workspace,
            String fileTreeDigest, int fileCount, Map<String, String> params) {
        SkillDraft draft = skillFactoryWorkspaceRepository.upsertDraftMetadata(
                workspaceId, workspace, fileTreeDigest, fileCount, params, operator);
        specialistRelationService.replaceSpecialists(
                draft, params.get(PARAM_SPECIALIST_IDS), operator);
        assetAuthorizationService.initializeOwners(
                operator, ReleaseAssetType.SKILL, draft.getSkillCode(), params.get(PARAM_OWNERS_JSON));
        log.info("SkillFactory创建Skill数据库短事务完成, skillCode:{}, draftId:{}, operator:{}",
                draft.getSkillCode(), draft.getId(), operator);
        return draft;
    }

    /**
     * 原子写入组件 Registry 记录和稳定资产负责人。
     */
    @Transactional(rollbackFor = Exception.class)
    public ComponentAsset createComponent(String operator, ComponentAsset asset, String ownersJson) {
        ComponentAsset created = componentAssetRepository.save(asset);
        assetAuthorizationService.initializeOwners(
                operator, ReleaseAssetType.COMPONENT, String.valueOf(created.getId()), ownersJson);
        log.info("SkillFactory创建组件数据库短事务完成, assetId:{}, componentName:{}, operator:{}",
                created.getId(), created.getComponentName(), operator);
        return created;
    }

    /**
     * 原子写入业务能力草稿和稳定资产负责人。
     */
    @Transactional(rollbackFor = Exception.class)
    public CapabilityActionDraft createCapability(
            String operator, CapabilityActionDraft draft, ClassificationSelection selection,
            String ownersJson) {
        CapabilityActionDraft created = capabilityActionDraftRepository.insert(draft);
        capabilityClassificationRelationService.replaceForRevision(
                created.getDraftId(), created.getRevision(), selection, operator);
        assetAuthorizationService.initializeOwners(
                operator, ReleaseAssetType.CAPABILITY_ACTION, created.getDraftId(), ownersJson);
        log.info("SkillFactory创建业务能力数据库短事务完成, draftId:{}, operator:{}",
                created.getDraftId(), operator);
        return capabilityClassificationRelationService.project(created);
    }

    /**
     * 原子写入仅含中文名称的初始业务能力草稿和稳定资产负责人。
     *
     * <p>该入口只负责建立 Authoring Chat 可复用的 draftId，不写分类关系；后续基础信息保存必须
     * 通过完整分类选择覆盖新 revision。本方法不创建占位分类，也不放宽校验或发布门禁。
     */
    @Transactional(rollbackFor = Exception.class)
    public CapabilityActionDraft createCapabilityRegistration(
            String operator, CapabilityActionDraft draft, String ownersJson) {
        CapabilityActionDraft created = capabilityActionDraftRepository.insert(draft);
        assetAuthorizationService.initializeOwners(
                operator, ReleaseAssetType.CAPABILITY_ACTION, created.getDraftId(), ownersJson);
        log.info("SkillFactory创建业务能力名称草稿数据库短事务完成, draftId:{}, operator:{}",
                created.getDraftId(), operator);
        return capabilityClassificationRelationService.project(created);
    }

    /**
     * 原子写入 Workflow 定义和稳定资产负责人。
     *
     * <p>调用方（WorkflowDefinitionService）负责在调用前完整构造 WorkflowDefinitionDO（含
     * workflowCode / specialistCode / 初始 draftPayloadJson / 时间戳等），本方法仅完成
     * DB 写入和 OWNER 初始化，不再重新构造任何业务字段。
     *
     * @param operator     操作者 userName，同时成为初始 OWNER
     * @param workflowDO   已完整构造的 Workflow 定义 DO
     * @param ownersJson   初始负责人 JSON（null 时默认 operator 为唯一 OWNER）
     * @return 回填 id 后的 WorkflowDefinitionDO
     */
    @Transactional(rollbackFor = Exception.class)
    public WorkflowDefinitionDO createWorkflow(
            String operator, WorkflowDefinitionDO workflowDO, String ownersJson) {
        WorkflowDefinitionDO created = workflowDefinitionRepository.insert(workflowDO);
        assetAuthorizationService.initializeOwners(
                operator, ReleaseAssetType.ORCHESTRATION_CONFIG, created.getWorkflowCode(), ownersJson);
        log.info("SkillFactory创建Workflow数据库短事务完成, workflowCode:{}, operator:{}",
                created.getWorkflowCode(), operator);
        return created;
    }
}
