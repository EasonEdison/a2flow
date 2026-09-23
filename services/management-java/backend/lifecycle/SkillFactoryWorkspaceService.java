package dev.a2flow.management.lifecycle;

import static dev.a2flow.management.release.SkillReleaseMetadataSupport.publishDescription;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Properties;
import java.util.UUID;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.fileguard.WorkspaceSnapshot;
import dev.a2flow.management.fileguard.WorkspaceSnapshotService;
import dev.a2flow.management.lifecycle.SkillPreprodBuildRestoreService.BuildRestoreResult;
import dev.a2flow.management.lifecycle.artifact.SkillPackageArtifactService;
import dev.a2flow.management.lifecycle.assembler.SkillLifecycleViewAssembler;
import dev.a2flow.management.lifecycle.domain.SkillDraft;
import dev.a2flow.management.lifecycle.domain.SkillWorkspaceFile;
import dev.a2flow.management.lifecycle.publish.SkillDatabasePublishResult;
import dev.a2flow.management.lifecycle.publish.SkillDatabasePublishService;
import dev.a2flow.management.model.SkillFactoryEntityRelationConstants;
import dev.a2flow.management.release.AssetReleaseEditGuard;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.ReleaseModels.AssetReleaseState;
import dev.a2flow.management.release.ReleaseModels.EnvironmentState;
import dev.a2flow.management.release.ReleaseModels.ReleaseArtifact;
import dev.a2flow.management.release.ReleaseModels.ReleaseDeployment;
import dev.a2flow.management.release.ReleaseModels.ReleaseVersion;
import dev.a2flow.management.storage.db.entity.EntityRelationDO;
import dev.a2flow.management.storage.db.repository.AssetReleaseStateRepository;
import dev.a2flow.management.storage.db.repository.EntityRelationRepository;
import dev.a2flow.management.storage.db.repository.SkillFactoryWorkspaceFileRepository;
import dev.a2flow.management.storage.db.repository.SkillFactoryWorkspaceRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 本地工作区生命周期 Service。
 *
 * <p>该类承接 sellerdata-operation-service 内 Skill 生命周期非 chat 方法，包括 workspace 初始化、目录树读取、
 * 文件读写、ZIP 构建，以及数据库产物保存和运行时配置发布。M 端权限校验、AI Coding
 * engine 和共享 release 状态机不在本类职责内。
 */
@Service
@Slf4j
public class SkillFactoryWorkspaceService {

    @Resource
    private dev.a2flow.management.storage.db.repository.SkillWorkspaceRequestSession workspaceSession;

    private static final String DEFAULT_SKILL_CODE = "live-plan-create-skill";
    private static final String DEFAULT_VERSION = "1";
    private static final String BUILD_DIR = "_build";
    private static final String PUBLISH_BUILD_DIR = "publish";
    private static final String DIR_PREPROD = "preprod";
    private static final String DIR_CURRENT = "current";
    private static final String DIR_ONLINE = "online";
    private static final String DIR_RELEASES = "releases";
    private static final String DIR_PACKAGES = "packages";
    private static final String PACKAGE_DIR_PREPROD = "preprod";
    private static final String PACKAGE_DIR_ONLINE = "online";
    private static final String ZIP_FILE_PREPROD_SNAPSHOT = "snapshot.zip";
    private static final String UUID_SEPARATOR = "-";
    private static final String EMPTY = "";
    private static final String ROOT_KEY = "root";
    private static final String LINE_SEPARATOR = "\n";
    private static final String VIEW_MODE_PREPROD_CURRENT = "PREPROD_CURRENT";
    private static final String VIEW_MODE_ONLINE_RELEASE = "ONLINE_RELEASE";
    private static final String PUBLISH_SOURCE_CURRENT = "CURRENT";
    private static final String PUBLISH_SOURCE_HISTORICAL = "HISTORICAL";
    private static final String SOURCE_LABEL_CURRENT = "当前内容";
    private static final String SOURCE_LABEL_HISTORICAL = "历史版本";
    private static final String DRAFT_STATUS_EDITING = "EDITING";
    private static final String DRAFT_STATUS_SEALED = "SEALED";
    private static final String PACKAGE_TYPE_PREPROD_SNAPSHOT = "PREPROD_SNAPSHOT";
    private static final String PACKAGE_TYPE_ONLINE_RELEASE = "ONLINE_RELEASE";
    private static final String DIFF_TYPE_ADDED = "ADDED";
    private static final String DIFF_TYPE_MODIFIED = "MODIFIED";
    private static final String DIFF_TYPE_DELETED = "DELETED";
    private static final String PARAM_WORKSPACE_ID = "workspaceId";
    private static final String PARAM_SKILL_CODE = "skillCode";
    private static final String PARAM_SKILL_NAME_CN = "skillNameCn";
    private static final String PARAM_SKILL_DESCRIPTION = "skillDescription";
    private static final String PARAM_BUSINESS_DOMAIN = "businessDomain";
    private static final String PARAM_CAPABILITY_DOMAIN = "capabilityDomain";
    private static final String PARAM_SPECIALIST_ID = "specialistId";
    private static final String PARAM_SPECIALIST_IDS = "specialistIds";
    private static final String PARAM_KEYWORD = "keyword";
    private static final String PARAM_VERSION = "version";
    private static final String PARAM_USER_NAME = "userName";
    private static final String PARAM_FILE_PATH = "filePath";
    private static final String PARAM_CONTENT = "content";
    private static final String PARAM_PACKAGE_TYPE = "packageType";
    private static final String PARAM_PACKAGE_URL = "packageUrl";
    private static final String PARAM_ZIP_FILE_NAME = "zipFileName";
    private static final String PARAM_ZIP_BASE64 = "zipBase64";
    private static final String PARAM_CREATE_SOURCE = "createSource";
    private static final String PARAM_SOURCE_ZIP_URL = "sourceZipUrl";
    private static final String PARAM_VIEW_MODE = "viewMode";
    private static final String PARAM_SOURCE_VERSION = "sourceVersion";
    private static final String PARAM_SOURCE_TYPE = "sourceType";
    private static final String PARAM_SOURCE_ID = "sourceId";
    private static final String PARAM_COMPARE_VERSION = "compareVersion";
    private static final String PARAM_PUBLISH_SOURCE_TYPE = "publishSourceType";
    private static final String PARAM_BASE_VERSION = "baseVersion";
    private static final String PARAM_REQUEST_ID = "requestId";
    private static final String PARAM_OWNERS_JSON = "ownersJson";
    private static final String DEFAULT_OPERATOR = "system";
    private static final String DRAFT_STATE_KEY_STATUS = "draftStatus";
    private static final String DRAFT_STATE_KEY_BASE_VERSION = "baseVersion";
    private static final String DRAFT_STATE_KEY_SEALED_VERSION = "sealedVersion";
    private static final String ACTION_SAVE_FILE = "保存文件";
    private static final String ACTION_DELETE_PATH = "删除工作区文件或目录";
    private static final String ACTION_RESET_WORKSPACE = "从指定来源重置当前变更";
    private static final String ACTION_SAVE_WORKSPACE = "保存工作区";
    private static final String ACTION_ZIP_IMPORT = "ZIP导入";
    private static final String ACTION_RESTORE_PACKAGE = "恢复包版本";
    private static final String ACTION_PUBLISH_PREPROD = "发布到预发";
    private static final String ACTION_PUBLISH_ONLINE_CURRENT = "发布当前内容到线上";
    private static final String FILE_SKILL_MD = "SKILL.md";
    private static final String DIR_SCRIPTS = "scripts/";
    private static final String DIR_REFERENCES = "references/";
    private static final String DIR_EXAMPLES = "examples/";
    private static final String EXTENSION_JSON = ".json";
    private static final String EXTENSION_MARKDOWN = ".md";
    private static final String EXTENSION_PYTHON = ".py";
    private static final String EXTENSION_TEXT = ".txt";
    private static final String EXTENSION_YAML = ".yaml";
    private static final String EXTENSION_YML = ".yml";
    private static final String EXTENSION_ZIP = ".zip";
    private static final String TAG_CARD_CONTAINER_START = "<card-container>";
    private static final String TAG_CARD_CONTAINER_END = "</card-container>";
    private static final String TAG_A2UI_CONTAINER_START = "<a2ui-container>";
    private static final String TAG_A2UI_CONTAINER_END = "</a2ui-container>";
    private static final String TAG_AGENT_UI_DSL_START = "<agent-ui-dsl>";
    private static final String TAG_AGENT_UI_DSL_END = "</agent-ui-dsl>";
    private static final String TAG_LOCAL_METHOD_START = "<local-method>";
    private static final String TAG_LOCAL_METHOD_END = "</local-method>";
    private static final String PROTOCOL_CARD_CONTAINER = "CARD_CONTAINER";
    private static final String PROTOCOL_A2UI = "A2UI";
    private static final String PROTOCOL_AGENT_UI_DSL = "agentUiDsl";
    private static final String PROTOCOL_LOCAL_METHOD = "localMethod";
    private static final String STATUS_NOT_FOUND = "NOT_FOUND";
    private static final String STATUS_EXTRACTED = "EXTRACTED";
    private static final String STATUS_NOT_REGISTERED = "NOT_REGISTERED";
    private static final String STATUS_IMPORTED = "IMPORTED";
    private static final String RESTORE_STATUS_RESTORED = "RESTORED";
    private static final String RESTORE_STATUS_PACKAGE_DOWNLOAD_NOT_CONNECTED = "PACKAGE_DOWNLOAD_NOT_CONNECTED";
    private static final String RESTORE_MESSAGE_PACKAGE_DOWNLOAD_NOT_CONNECTED =
            "PACKAGE_VERSION_RESTORE requires object storage download integration";
    private static final String RESTORE_MESSAGE_LOCAL_PACKAGE_RESTORED = "local package restored";
    private static final String RESTORE_MESSAGE_REMOTE_PACKAGE_RESTORED = "remote package restored";
    private static final String CREATE_SOURCE_ZIP_IMPORT = "ZIP_IMPORT";
    private static final String UPLOAD_PACKAGE_URL_PREFIX = "upload://";
    private static final String ZIP_BASE64_DATA_URL_MARKER = "base64,";
    private static final String LOCAL_FILE_URL_PREFIX = "file:";
    private static final String HTTP_URL_PREFIX = "http:";
    private static final String HTTPS_URL_PREFIX = "https:";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_TREE_DATA = "treeData";
    private static final String FIELD_CONTENT = "content";
    private static final String FIELD_DIFF = "diff";
    private static final String FIELD_WORKSPACE_DIGEST = "workspaceDigest";
    private static final String FIELD_FILE_TREE_DIGEST = "fileTreeDigest";
    private static final String FIELD_FILES = "files";
    private static final String FIELD_SAMPLES = "samples";
    private static final String FIELD_STATUS = "status";
    private static final String FIELD_PACKAGE_URL = "packageUrl";
    private static final String FIELD_RESTORE_STATUS = "restoreStatus";
    private static final String FIELD_RESTORED_FILE_COUNT = "restoredFileCount";
    private static final String FIELD_MESSAGE = "message";
    private static final String FIELD_NODE_KEY = "key";
    private static final String FIELD_NODE_TITLE = "title";
    private static final String FIELD_NODE_DIRECTORY = "directory";
    private static final String FIELD_NODE_CHILDREN = "children";
    private static final String FIELD_SAMPLE_SOURCE = "source";
    private static final String FIELD_RENDER_PROTOCOL = "renderProtocol";
    private static final String FIELD_PAYLOAD = "payload";
    private static final String FIELD_CONTENT_DIGEST = "contentDigest";
    private static final String FIELD_BEFORE_LINE_COUNT = "beforeLineCount";
    private static final String FIELD_AFTER_LINE_COUNT = "afterLineCount";
    private static final String FIELD_CHANGED = "changed";
    private static final String FIELD_WORKSPACE_ROOT = "workspaceRoot";
    private static final String FIELD_WORKSPACE_PATH = "workspacePath";
    private static final String FIELD_FILE_COUNT = "fileCount";
    private static final String FIELD_FILE_PATH = "filePath";
    private static final String FIELD_FILE_NAME = "fileName";
    private static final String FIELD_FILE_TYPE = "fileType";
    private static final String FIELD_FILE_SIZE = "fileSize";
    private static final String FIELD_MODIFY_TIME = "modifyTime";
    private static final String FIELD_ZIP_FILE_NAME = "zipFileName";
    private static final String FIELD_PACKAGE_DIGEST = "packageDigest";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_SKILL_NAME_CN = "skillNameCn";
    private static final String FIELD_SKILL_NAME_EN = "skillNameEn";
    private static final String FIELD_SKILL_DESCRIPTION = "skillDescription";
    private static final String FIELD_BUSINESS_DOMAIN = "businessDomain";
    private static final String FIELD_CAPABILITY_DOMAIN = "capabilityDomain";
    private static final String FIELD_CREATE_SOURCE = "createSource";
    private static final String FIELD_SOURCE_ZIP_URL = "sourceZipUrl";
    private static final String FIELD_IMPORT_STATUS = "importStatus";
    private static final String FIELD_IMPORTED_FILE_COUNT = "importedFileCount";
    private static final String FIELD_VERSION = "version";
    private static final String FIELD_VERSION_LABEL = "versionLabel";
    private static final String FIELD_VERSION_STATUS = "versionStatus";
    private static final String FIELD_PREPROD_VERSION_ID = "preprodVersionId";
    private static final String FIELD_ONLINE_VERSION_ID = "onlineVersionId";
    private static final String FIELD_REGISTER_STATUS = "registerStatus";
    private static final String FIELD_LANG_BRIDGE_SKILL_ID = "langBridgeSkillId";
    private static final String FIELD_PUBLISH_TARGET = "publishTarget";
    private static final String FIELD_PREPROD_PACKAGE_ID = "preprodPackageId";
    private static final String FIELD_ONLINE_PACKAGE_ID = "onlinePackageId";
    private static final String FIELD_PREPROD_VERSION = "preprodVersion";
    private static final String FIELD_ONLINE_VERSION = "onlineVersion";
    private static final String FIELD_OWNER = "owner";
    private static final String FIELD_CREATOR = "creator";
    private static final String FIELD_MODIFIER = "modifier";
    private static final String FIELD_EXT_JSON = "extJson";
    private static final String FIELD_REFERENCE_RENDER_ASSETS = "referenceRenderAssets";
    private static final String FIELD_REFERENCE_COMPONENT_CODES = "referenceComponentCodes";
    private static final String FIELD_REFERENCE_CAPABILITIES = "referenceCapabilities";
    private static final String FIELD_REFERENCE_CAPABILITY_DRAFT_IDS = "referenceCapabilityDraftIds";
    private static final String FIELD_CAPABILITY_BINDINGS = "capabilityBindings";
    private static final String FIELD_COMPONENT_BINDINGS = "componentBindings";
    private static final String FIELD_COMPONENT_CODE = "componentCode";
    private static final String FIELD_CODE = "code";
    private static final String COMMA = ",";
    private static final String FIELD_CAPABILITY_DRAFT_ID = "draftId";
    private static final String FIELD_CREATE_TIME = "createTime";
    private static final String FIELD_UPDATE_TIME = "updateTime";
    private static final String FIELD_BINDING_RECORDS = "bindingRecords";
    private static final String FIELD_PUBLISH_RECORDS = "publishRecords";
    private static final String FIELD_OPERATOR = "operator";
    private static final String FIELD_PUBLISH_STAGE = "publishStage";
    private static final String FIELD_PUBLISH_STATUS = "publishStatus";
    private static final String FIELD_PUBLISH_RESULT = "publishResult";
    private static final String FIELD_ARTIFACT = "artifact";
    private static final String FIELD_LANG_BRIDGE_VERSION_LABEL = "langBridgeVersionLabel";
    private static final String FIELD_VIEW_MODE = "viewMode";
    private static final String FIELD_READONLY = "readonly";
    private static final String FIELD_EDITABLE = "editable";
    private static final String FIELD_DRAFT_STATUS = "draftStatus";
    private static final String FIELD_BASE_VERSION = "baseVersion";
    private static final String FIELD_SEALED_VERSION = "sealedVersion";
    private static final String FIELD_RELEASE_VERSIONS = "releaseVersions";
    private static final String FIELD_PREPROD_BUILD_RESET_SOURCES = "preprodBuildResetSources";
    private static final String FIELD_LATEST_RELEASE_VERSION = "latestReleaseVersion";
    private static final String FIELD_NEXT_RELEASE_VERSION = "nextReleaseVersion";
    private static final String FIELD_VERSION_NUMBER = "version";
    private static final String FIELD_SOURCE_VERSION = "sourceVersion";
    private static final String FIELD_COMPARE_VERSION = "compareVersion";
    private static final String FIELD_PUBLISH_SOURCE_TYPE = "publishSourceType";
    private static final String FIELD_SOURCE_LABEL = "sourceLabel";
    private static final String FIELD_DIFF_FILES = "diffFiles";
    private static final String FIELD_DIFF_SUMMARY = "diffSummary";
    private static final String FIELD_CHANGE_TYPE = "changeType";
    private static final String FIELD_BEFORE_DIGEST = "beforeDigest";
    private static final String FIELD_AFTER_DIGEST = "afterDigest";
    private static final String FIELD_ADDED_COUNT = "addedCount";
    private static final String FIELD_MODIFIED_COUNT = "modifiedCount";
    private static final String FIELD_DELETED_COUNT = "deletedCount";
    private static final String FIELD_RESET_SOURCE_VERSION = "resetSourceVersion";
    private static final String FIELD_RESET_SOURCE_TYPE = "resetSourceType";
    private static final String FIELD_RESET_SOURCE_ID = "resetSourceId";
    private static final String FIELD_RESET_TARGET_VERSION = "resetTargetVersion";
    private static final String FIELD_RESTORED_RELATION_COUNT = "restoredRelationCount";
    private static final String FIELD_PACKAGE_SOURCE_PATH = "packageSourcePath";
    private static final String FIELD_DELETED_PATH = "deletedPath";
    private static final String FIELD_DELETED_DIRECTORY = "deletedDirectory";
    private static final String PUBLISH_STAGE_ONLINE_CURRENT = "ONLINE_PUBLISH_CURRENT";
    private static final String PUBLISH_STAGE_ONLINE_HISTORICAL = "ONLINE_PUBLISH_HISTORICAL";
    private static final String PUBLISH_STAGE_PREPROD = "PREPROD_PUBLISH";
    private static final String PUBLISH_STAGE_ONLINE = "ONLINE_PUBLISH";
    private static final String ERROR_SKILL_DRAFT_NOT_FOUND = "skill draft not found";
    private static final String ERROR_ONLINE_VERSION_RECORD_NOT_FOUND =
            "online skill version record not found";
    private static final String ERROR_SKILL_CODE_DB_ALREADY_EXISTS =
            "Skill 注册失败：数据库中已存在相同 skillCode";
    private static final String ERROR_SKILL_WORKSPACE_DIRECTORY_ALREADY_EXISTS =
            "Skill 注册失败：对应工作区目录已存在";
    private static final String ERROR_SKILL_CODE_AND_WORKSPACE_ALREADY_EXISTS =
            "Skill 注册失败：数据库中已存在相同 skillCode，且对应工作区目录已存在";
    private static final String ERROR_FILE_PATH_INVALID = "filePath is invalid";
    private static final String ERROR_FILE_OUTSIDE_WORKSPACE = "filePath outside workspace";
    private static final String ERROR_FILE_TYPE_NOT_EDITABLE = "file type is not editable in SkillFactory";
    private static final String ERROR_WORKSPACE_NOT_FOUND = "workspace does not exist";
    private static final String ERROR_WORKSPACE_SNAPSHOT_FAILED = "workspace snapshot failed";
    private static final String ERROR_WORKSPACE_PATH_NOT_FOUND = "工作区文件或目录不存在";
    private static final String ERROR_WORKSPACE_ROOT_DELETE_NOT_ALLOWED = "不允许删除工作区根目录";
    private static final String ERROR_RELEASE_VERSION_NOT_FOUND = "release version does not exist";
    private static final String ERROR_RELEASE_VERSION_RECORD_NOT_FOUND = "正式版本记录不存在";
    private static final String ERROR_CURRENT_SKILL_VERSION_INVALID = "当前 Skill 版本无效";
    private static final String ERROR_RELEASE_VERSION_INVALID = "release version is invalid";
    private static final String ERROR_CURRENT_RELEASE_VERSION_INVALID =
            "CURRENT publish must use the next release version";
    private static final String ERROR_PUBLISH_SOURCE_TYPE_INVALID = "publishSourceType is invalid";
    private static final String ERROR_RESET_SOURCE_TYPE_INVALID = "重置来源类型非法";
    private static final String ERROR_ZIP_BASE64_INVALID = "zipBase64 is invalid";
    private static final String ERROR_DRAFT_SEALED = "current draft is sealed, create a new change first";
    private static final String ERROR_ENTITY_RELATION_SNAPSHOT_INVALID = "entity relation snapshot is invalid";
    private static final String ERROR_REQUIRED_SUFFIX = " is required";
    private static final String IMPORT_MESSAGE_ZIP_IMPORTED = "zip imported into workspace";
    private static final String CHANGE_CREATE_MESSAGE = "change draft created from release";
    private static final String DELETE_PATH_MESSAGE = "工作区文件或目录已删除";
    private static final String RESET_WORKSPACE_MESSAGE = "当前变更已从指定来源重置";
    private static final String RESET_SOURCE_TYPE_BUILD = "BUILD";
    private static final String RESET_SOURCE_TYPE_VERSION = "VERSION";
    private static final String ACTION_UPDATE_SKILL_BASIC_INFO = "更新Skill基础信息";

    @Resource
    private SkillFactoryWorkspaceRepository workspaceRepository;

    @Resource
    private AssetAuthorizationService assetAuthorizationService;

    @Resource
    private SkillFactoryWorkspaceRegistrationService workspaceRegistrationService;

    @Resource
    private SkillFactoryWorkspaceFileRepository fileRepository;

    @Resource
    private WorkspaceSnapshotService workspaceSnapshotService;

    @Resource
    private SkillPackageArtifactService packageArtifactService;

    @Resource
    private SkillLifecycleViewAssembler viewAssembler;

    @Resource
    private EntityRelationRepository entityRelationRepository;

    @Resource
    private SkillDatabasePublishService externalPublishService;

    @Resource
    private AssetReleaseStateRepository releaseStateRepository;

    @Resource
    private SkillPreprodBuildRestoreService preprodBuildRestoreService;

    @Resource
    private SkillFactorySpecialistRelationService specialistRelationService;

    @Resource
    private AssetReleaseEditGuard assetReleaseEditGuard;

    /**
     * 查询 Skill 草稿列表，供 M 端 workbench 首屏选择 Skill。
     */
    public List<Map<String, Object>> listSkills(Map<String, String> params) {
        String keyword = string(params == null ? null : params.get(PARAM_KEYWORD));
        String businessDomain = string(params == null ? null : params.get(PARAM_BUSINESS_DOMAIN));
        String capabilityDomain = string(params == null ? null : params.get(PARAM_CAPABILITY_DOMAIN));
        log.info("SkillFactory查询Skill列表, keyword:{}, businessDomain:{}, capabilityDomain:{}",
                keyword, businessDomain, capabilityDomain);
        List<Map<String, Object>> results = workspaceRepository
                .listDrafts(StringUtils.EMPTY, businessDomain, capabilityDomain)
                .stream()
                .filter(draft -> specialistRelationService.matchesKeyword(draft, keyword))
                .map(this::draftSummaryToMap)
                .collect(Collectors.toList());
        log.info("SkillFactory查询Skill列表完成, keyword:{}, businessDomain:{}, capabilityDomain:{}, count:{}",
                keyword, businessDomain, capabilityDomain, results.size());
        return results;
    }

    /**
     * 查询 Skill 草稿详情，返回页面基础信息和当前 workspace 元数据。
     */
    public Map<String, Object> skillDetail(String skillCode, Map<String, String> params) {
        log.info("SkillFactory查询Skill详情, skillCode:{}", skillCode);
        SkillDraft draft = workspaceRepository.findDraftBySkillCode(skillCode);
        if (draft == null) {
            log.warn("SkillFactory查询Skill详情失败，草稿不存在, skillCode:{}", skillCode);
            throw new IllegalArgumentException(ERROR_SKILL_DRAFT_NOT_FOUND);
        }
        Map<String, Object> result = draftToMap(draft);
        WorkspaceSnapshot currentSnapshot = currentWorkspaceSnapshot(draft.getWorkspaceId());
        result.put(FIELD_FILE_TREE_DIGEST, currentSnapshot.getFileTreeDigest());
        result.put(FIELD_FILE_COUNT, currentSnapshot.getFileCount());
        result.put(FIELD_BINDING_RECORDS, Collections.emptyList());
        result.put(FIELD_PUBLISH_RECORDS,
                viewAssembler.releaseRecords(releaseState(draft.getWorkspaceId())));
        log.info("SkillFactory查询Skill详情完成, skillCode:{}, workspaceId:{}, publishRecordCount:{}",
                skillCode, result.get(FIELD_WORKSPACE_ID),
                ((List<?>) result.get(FIELD_PUBLISH_RECORDS)).size());
        return result;
    }

    /**
     * 实时读取当前可编辑工作区的 canonical 快照。
     *
     * <p>该方法供 Skill 详情和共享发布控制面读取从 PostgreSQL 文档恢复的请求内投影。
     * 文件修改通过同一请求的数据库 revision CAS 保存；列表摘要仍只是投影。
     */
    public WorkspaceSnapshot currentWorkspaceSnapshot(String workspaceId) {
        Path workspace = requireWorkspace(workspaceId);
        try {
            WorkspaceSnapshot snapshot = workspaceSnapshotService.capture(workspace);
            log.info("SkillFactory读取当前真实工作区快照完成, workspaceId:{}, fileTreeDigest:{}, fileCount:{}",
                    workspaceId, snapshot.getFileTreeDigest(), snapshot.getFileCount());
            return snapshot;
        } catch (IOException e) {
            log.warn("SkillFactory读取当前真实工作区快照失败, workspaceId:{}, workspacePath:{}",
                    workspaceId, workspace, e);
            throw new IllegalStateException(ERROR_WORKSPACE_SNAPSHOT_FAILED, e);
        }
    }

    /**
     * 更新 Skill 基础信息。
     *
     * <p>注册后 Skill code、workspace 目录、版本身份和负责人不可变；当前可编辑变更允许修改中文名、
     * 描述、业务场域、能力域和当前版本所属专员。所属专员覆盖当前版本 `entity_relation`，并与
     * Skill 主记录更新处于同一数据源事务。该方法不会创建、移动或重命名 workspace。
     */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public Map<String, Object> updateSkillName(String skillCode, Map<String, String> params, String operator) {
        String skillNameCn = required(params, PARAM_SKILL_NAME_CN);
        String skillDescription = params != null && params.containsKey(PARAM_SKILL_DESCRIPTION)
                ? StringUtils.defaultString(string(params.get(PARAM_SKILL_DESCRIPTION))) : null;
        String businessDomain = params != null && params.containsKey(PARAM_BUSINESS_DOMAIN)
                ? StringUtils.defaultString(string(params.get(PARAM_BUSINESS_DOMAIN))) : null;
        String capabilityDomain = params != null && params.containsKey(PARAM_CAPABILITY_DOMAIN)
                ? StringUtils.defaultString(string(params.get(PARAM_CAPABILITY_DOMAIN))) : null;
        SkillDescriptionValidator.validate(skillCode, skillDescription, operator);
        boolean updateSpecialists = params != null
                && (params.containsKey(PARAM_SPECIALIST_IDS) || params.containsKey(PARAM_SPECIALIST_ID));
        String specialistIds = updateSpecialists
                ? firstNonBlank(string(params.get(PARAM_SPECIALIST_IDS)), string(params.get(PARAM_SPECIALIST_ID)))
                : null;
        log.info("SkillFactory开始更新Skill基础信息, skillCode:{}, skillNameCn:{}, businessDomain:{}, "
                        + "capabilityDomain:{}, descriptionLength:{}, updateSpecialists:{}, operator:{}",
                skillCode, skillNameCn, businessDomain, capabilityDomain,
                StringUtils.length(skillDescription), updateSpecialists, operator);
        SkillDraft draft = workspaceRepository.findDraftBySkillCode(skillCode);
        if (draft == null) {
            log.warn("SkillFactory更新Skill基础信息失败，草稿不存在, skillCode:{}, operator:{}",
                    skillCode, operator);
            throw new IllegalArgumentException(ERROR_SKILL_DRAFT_NOT_FOUND);
        }
        assetReleaseEditGuard.requireEditableChange(
                ReleaseAssetType.SKILL, skillCode, ACTION_UPDATE_SKILL_BASIC_INFO, operator);
        requireEditableWorkspace(draft.getWorkspaceId());
        if (workspaceRepository.draftExistsBySkillNameCn(skillNameCn, skillCode)) {
            log.warn("SkillFactory更新Skill中文名失败，中文名重复, skillCode:{}, skillNameCn:{}",
                    skillCode, skillNameCn);
            throw SkillFactoryValidationException.duplicateSkillNameCn(skillNameCn);
        }
        if (updateSpecialists) {
            specialistRelationService.validateSpecialists(specialistIds);
        }
        SkillDraft updatedDraft = workspaceRepository.updateSkillBasicInfo(
                skillCode, skillNameCn, skillDescription, businessDomain, capabilityDomain,
                StringUtils.defaultIfBlank(operator, operator(params)));
        if (updatedDraft == null) {
            throw new IllegalArgumentException(ERROR_SKILL_DRAFT_NOT_FOUND);
        }
        if (updateSpecialists) {
            specialistRelationService.replaceSpecialists(
                    updatedDraft, specialistIds, StringUtils.defaultIfBlank(operator, operator(params)));
        }
        log.info("SkillFactory更新Skill基础信息完成, skillCode:{}, workspaceId:{}, businessDomain:{}, "
                        + "capabilityDomain:{}, descriptionLength:{}, updateSpecialists:{}",
                skillCode, updatedDraft.getWorkspaceId(), updatedDraft.getBusinessDomain(),
                updatedDraft.getCapabilityDomain(), StringUtils.length(updatedDraft.getSkillDescription()),
                updateSpecialists);
        return draftToMap(updatedDraft);
    }

    /**
     * 将用户上传的 Skill 工程 ZIP 解压到当前受控 workspace，并返回导入后的目录摘要。
     *
     * <p>该方法只处理 agent-service 本地文件落盘和摘要刷新；正式的上传鉴权、草稿状态机和来源审计由 adviser
     * 或后续 DB Repository 负责。当前 DB 未建表时，导入来源摘要仍保留在 Repository 层临时 mock 返回值里。
     */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public Map<String, Object> confirmZipImport(String skillCode, String zipFileName,
            Map<String, String> params) throws IOException {
        String workspaceId = deriveWorkspaceId(skillCode);
        String zipBase64 = required(params, PARAM_ZIP_BASE64);
        log.info("SkillFactory开始导入ZIP工作区, workspaceId:{}, skillCode:{}, zipFileName:{}, base64Length:{}",
                workspaceId, skillCode, zipFileName, zipBase64.length());
        byte[] zipBytes = decodeZipBase64(zipBase64);
        requireDraftEditable(workspaceId, ACTION_ZIP_IMPORT);
        Path workspace = requireEditableWorkspace(workspaceId);
        int importedFileCount = packageArtifactService.importUploadedZip(
                workspaceRepository.workspaceRoot(), workspace, skillCode, zipFileName, zipBytes);
        Map<String, String> importParams = new HashMap<>();
        if (params != null) {
            importParams.putAll(params);
        }
        importParams.remove(PARAM_ZIP_BASE64);
        importParams.put(PARAM_WORKSPACE_ID, workspaceId);
        importParams.put(PARAM_SKILL_CODE, skillCode);
        importParams.put(PARAM_CREATE_SOURCE, CREATE_SOURCE_ZIP_IMPORT);
        importParams.put(PARAM_SOURCE_ZIP_URL, UPLOAD_PACKAGE_URL_PREFIX + zipFileName);
        SkillDraft workspaceDO = persistWorkspaceState(workspaceId, importParams);
        Map<String, Object> result = workspaceToMap(workspaceDO);
        result.put(FIELD_ZIP_FILE_NAME, zipFileName);
        result.put(FIELD_SOURCE_ZIP_URL, importParams.get(PARAM_SOURCE_ZIP_URL));
        result.put(FIELD_IMPORT_STATUS, STATUS_IMPORTED);
        result.put(FIELD_IMPORTED_FILE_COUNT, importedFileCount);
        result.put(FIELD_MESSAGE, IMPORT_MESSAGE_ZIP_IMPORTED);
        log.info("SkillFactory ZIP导入完成, workspaceId:{}, skillCode:{}, zipFileName:{}, "
                        + "importedFileCount:{}, fileTreeDigest:{}",
                workspaceId, skillCode, zipFileName, importedFileCount, workspaceDO.getFileTreeDigest());
        return result;
    }

    /**
     * 注册 SkillFactory 工作区身份，只创建受控目录，不生成模板文件。
     */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public Map<String, Object> createWorkspace(String userName, Map<String, String> params) throws IOException {
        String skillCode = required(params, PARAM_SKILL_CODE);
        String skillNameCn = StringUtils.defaultIfBlank(string(params == null ? null : params.get(PARAM_SKILL_NAME_CN)),
                skillCode);
        String skillDescription = StringUtils.defaultString(
                string(params == null ? null : params.get(PARAM_SKILL_DESCRIPTION)));
        String businessDomain = StringUtils.defaultString(
                string(params == null ? null : params.get(PARAM_BUSINESS_DOMAIN)));
        String capabilityDomain = StringUtils.defaultString(
                string(params == null ? null : params.get(PARAM_CAPABILITY_DOMAIN)));
        String specialistIds = firstNonBlank(
                string(params == null ? null : params.get(PARAM_SPECIALIST_IDS)),
                string(params == null ? null : params.get(PARAM_SPECIALIST_ID)));
        String workspaceId = deriveWorkspaceId(skillCode);
        SkillDescriptionValidator.validate(skillCode, skillDescription, userName);
        String version = StringUtils.defaultIfBlank(string(params == null ? null : params.get(PARAM_VERSION)),
                DEFAULT_VERSION);
        log.info("SkillFactory开始创建工作区, workspaceId:{}, skillCode:{}, version:{}, businessDomain:{}, "
                        + "capabilityDomain:{}, descriptionLength:{}",
                workspaceId, skillCode, version, businessDomain, capabilityDomain,
                StringUtils.length(skillDescription));
        Path workspace = workspaceRepository.resolveWorkspace(workspaceId);
        boolean dbSkillCodeExists = workspaceRepository.draftExistsBySkillCode(skillCode);
        boolean workspaceDirectoryExists = workspaceSession.exists(workspaceId);
        if (dbSkillCodeExists || workspaceDirectoryExists) {
            log.warn("SkillFactory创建工作区失败，注册身份冲突, skillCode:{}, workspaceId:{}, "
                            + "dbSkillCodeExists:{}, workspaceDirectoryExists:{}",
                    skillCode, workspaceId, dbSkillCodeExists, workspaceDirectoryExists);
            if (dbSkillCodeExists && workspaceDirectoryExists) {
                throw new IllegalArgumentException(ERROR_SKILL_CODE_AND_WORKSPACE_ALREADY_EXISTS);
            }
            if (dbSkillCodeExists) {
                throw new IllegalArgumentException(ERROR_SKILL_CODE_DB_ALREADY_EXISTS);
            }
            throw new IllegalArgumentException(ERROR_SKILL_WORKSPACE_DIRECTORY_ALREADY_EXISTS);
        }
        if (workspaceRepository.draftExistsBySkillNameCn(skillNameCn, null)) {
            log.warn("SkillFactory创建工作区失败，Skill中文名已存在, skillCode:{}, skillNameCn:{}",
                    skillCode, skillNameCn);
            throw SkillFactoryValidationException.duplicateSkillNameCn(skillNameCn);
        }
        specialistRelationService.validateSpecialists(specialistIds);
        assetAuthorizationService.validateCreationOwners(
                userName, ReleaseAssetType.SKILL, skillCode,
                params == null ? null : params.get(PARAM_OWNERS_JSON));
        Map<String, String> createParams = new HashMap<>();
        if (params != null) {
            createParams.putAll(params);
        }
        createParams.put(PARAM_WORKSPACE_ID, workspaceId);
        createParams.put(PARAM_SKILL_CODE, skillCode);
        createParams.put(PARAM_SKILL_NAME_CN, skillNameCn);
        createParams.put(PARAM_SKILL_DESCRIPTION, skillDescription);
        createParams.put(PARAM_BUSINESS_DOMAIN, businessDomain);
        createParams.put(PARAM_CAPABILITY_DOMAIN, capabilityDomain);
        createParams.put(PARAM_SPECIALIST_IDS, specialistIds);
        createParams.put(PARAM_USER_NAME, userName);
        workspaceSession.create(workspaceId, 0);
        AssetReleaseState initialReleaseState = releaseState(workspaceId);
        if (initialReleaseState.getRevision() == null || initialReleaseState.getRevision() != 0) {
            throw new IllegalStateException("Release state already exists for new workspace");
        }
        releaseStateRepository.save(initialReleaseState, 0);
        SkillDraft workspaceDO = workspaceRegistrationService.register(
                userName, workspaceId, skillCode, workspace, createParams, () -> {
                    Files.createDirectories(editableWorkspace(workspaceId));
                });
        Map<String, Object> result = draftToMap(workspaceDO);
        log.info("SkillFactory工作区创建完成, workspaceId:{}, skillCode:{}, fileCount:{}",
                workspaceId, skillCode, workspaceDO.getFileCount());
        return result;
    }

    /**
     * 从一个已封板正式包版本创建新的可编辑变更。
     *
     * <p>该方法是修改封板版本的唯一入口：它不会改变 workspace 身份，只会清空并重建
     * `preprod/current`，把所选 `online/releases/{baseVersion}` 复制进去，然后重新打开编辑态。
     */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public Map<String, Object> createChange(String workspaceId, Map<String, String> params)
            throws IOException {
        requireIdentityWorkspace(workspaceId);
        SkillDraft currentDraft = workspaceRepository.findDraftByWorkspaceId(workspaceId);
        if (currentDraft == null || currentDraft.getId() == null) {
            log.warn("SkillFactory新建变更失败，Skill草稿不存在, workspaceId:{}", workspaceId);
            throw new IllegalArgumentException(ERROR_SKILL_DRAFT_NOT_FOUND);
        }
        int baseVersion = parsePositiveVersion(firstNonBlank(
                params == null ? EMPTY : params.get(PARAM_BASE_VERSION),
                params == null ? EMPTY : params.get(PARAM_VERSION),
                params == null ? EMPTY : params.get(PARAM_SOURCE_VERSION)));
        int targetVersion = nextReleaseVersion(workspaceId);
        log.info("SkillFactory开始新建变更, workspaceId:{}, baseVersion:{}, targetVersion:{}",
                workspaceId, baseVersion, targetVersion);
        int restoredRelationCount = preprodBuildRestoreService.restoreVersion(
                currentDraft, releaseState(workspaceId), baseVersion, targetVersion,
                releaseWorkspace(workspaceId, baseVersion), requireEditableWorkspace(workspaceId), operator(params));
        Map<String, String> changeParams = new HashMap<>();
        if (params != null) {
            changeParams.putAll(params);
        }
        changeParams.put(PARAM_WORKSPACE_ID, workspaceId);
        changeParams.put(PARAM_BASE_VERSION, String.valueOf(baseVersion));
        changeParams.put(PARAM_VERSION, String.valueOf(targetVersion));
        SkillDraft workspaceDO = persistWorkspaceState(workspaceId, changeParams);
        Map<String, Object> result = workspaceToMap(workspaceDO);
        result.put(FIELD_VIEW_MODE, VIEW_MODE_PREPROD_CURRENT);
        result.put(FIELD_READONLY, false);
        result.put(FIELD_BASE_VERSION, baseVersion);
        result.put(FIELD_VERSION, targetVersion);
        result.put(FIELD_RELEASE_VERSIONS, releaseVersions(workspaceId));
        result.put(FIELD_LATEST_RELEASE_VERSION, latestReleaseVersion(workspaceId));
        result.put(FIELD_NEXT_RELEASE_VERSION, nextReleaseVersion(workspaceId));
        result.put(FIELD_MESSAGE, CHANGE_CREATE_MESSAGE);
        log.info("SkillFactory新建变更完成, workspaceId:{}, baseVersion:{}, targetVersion:{}, "
                        + "fileCount:{}, relationCount:{}, fileTreeDigest:{}",
                workspaceId, baseVersion, targetVersion, workspaceDO.getFileCount(),
                restoredRelationCount, workspaceDO.getFileTreeDigest());
        return result;
    }

    /**
     * 读取工作区目录树。
     */
    public Map<String, Object> tree(String workspaceId, Map<String, String> params) throws IOException {
        WorkspaceView workspaceView = resolveWorkspaceView(workspaceId, params);
        log.info("SkillFactory读取工作区目录树, workspaceId:{}, viewMode:{}, version:{}",
                workspaceId, workspaceView.viewMode, workspaceView.version);
        Map<String, Object> result = workspaceViewSummary(workspaceId, workspaceView, params);
        result.put(FIELD_TREE_DATA, treeNode(workspaceView.path, workspaceView.path, workspaceId));
        return result;
    }

    /**
     * 读取工作区内单个文本文件内容。
     */
    public Map<String, Object> fileContent(String workspaceId, String filePath, Map<String, String> params)
            throws IOException {
        WorkspaceView workspaceView = resolveWorkspaceView(workspaceId, params);
        log.info("SkillFactory读取文件内容, workspaceId:{}, viewMode:{}, version:{}, filePath:{}",
                workspaceId, workspaceView.viewMode, workspaceView.version, filePath);
        Path file = resolveFile(workspaceView.path, filePath);
        Map<String, Object> result = viewAssembler.fileToMap(fileRepository.file(workspaceView.path, file));
        result.put(FIELD_CONTENT, fileRepository.readText(file));
        result.put(FIELD_VIEW_MODE, workspaceView.viewMode);
        result.put(FIELD_READONLY, workspaceView.readonly);
        putWorkspaceViewState(result, workspaceId, workspaceView);
        return result;
    }

    /**
     * 保存工作区内单个可编辑文本文件，并返回行数变化摘要和最新 workspace digest。
     */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public Map<String, Object> saveFile(String workspaceId, String filePath, String content,
            Map<String, String> params) throws IOException {
        log.info("SkillFactory保存文件内容, workspaceId:{}, filePath:{}, contentLength:{}",
                workspaceId, filePath, StringUtils.defaultString(content).length());
        requireDraftEditable(workspaceId, ACTION_SAVE_FILE);
        Path workspace = requireWorkspace(workspaceId);
        Path file = resolveFile(workspace, filePath);
        ensureEditablePath(filePath);
        String before = fileRepository.exists(file) ? fileRepository.readText(file) : EMPTY;
        fileRepository.writeText(file, StringUtils.defaultString(content));
        SkillDraft workspaceDO = persistWorkspaceState(workspaceId, params);
        Map<String, Object> result = viewAssembler.fileToMap(fileRepository.file(workspace, file));
        result.put(FIELD_DIFF, buildLineDiff(before, StringUtils.defaultString(content)));
        result.put(FIELD_WORKSPACE_DIGEST, workspaceDO.getFileTreeDigest());
        log.info("SkillFactory文件保存完成, workspaceId:{}, filePath:{}, digest:{}",
                workspaceId, filePath, result.get(FIELD_WORKSPACE_DIGEST));
        return result;
    }

    /**
     * 删除当前可编辑工作区内的单个文件或目录。
     *
     * <p>目录删除采用递归方式，但只能作用于 `preprod/current` 的子路径；工作区根目录、正式版本目录、
     * 越界路径和已封板草稿均不会被删除。删除完成后同步刷新文件元数据和工作区摘要。
     */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public Map<String, Object> deletePath(String workspaceId, String filePath, Map<String, String> params)
            throws IOException {
        requireDraftEditable(workspaceId, ACTION_DELETE_PATH);
        if (StringUtils.equals(ROOT_KEY, filePath)) {
            log.warn("SkillFactory拒绝删除工作区根目录, workspaceId:{}, filePath:{}", workspaceId, filePath);
            throw new IllegalArgumentException(ERROR_WORKSPACE_ROOT_DELETE_NOT_ALLOWED);
        }
        Path workspace = requireEditableWorkspace(workspaceId);
        Path target = resolveFile(workspace, filePath);
        if (workspace.equals(target)) {
            log.warn("SkillFactory拒绝通过等价路径删除工作区根目录, workspaceId:{}, filePath:{}",
                    workspaceId, filePath);
            throw new IllegalArgumentException(ERROR_WORKSPACE_ROOT_DELETE_NOT_ALLOWED);
        }
        if (!fileRepository.exists(target)) {
            log.warn("SkillFactory删除工作区路径失败，目标不存在, workspaceId:{}, filePath:{}",
                    workspaceId, filePath);
            throw new IllegalArgumentException(ERROR_WORKSPACE_PATH_NOT_FOUND);
        }
        boolean directory = fileRepository.isDirectory(target);
        long deletedCount = countPathEntries(target);
        log.info("SkillFactory开始删除工作区路径, workspaceId:{}, filePath:{}, directory:{}, entryCount:{}",
                workspaceId, filePath, directory, deletedCount);
        deleteRecursively(target);
        SkillDraft workspaceDO = persistWorkspaceState(workspaceId, params);
        Map<String, Object> result = tree(workspaceId, Collections.emptyMap());
        result.put(FIELD_DELETED_PATH, filePath);
        result.put(FIELD_DELETED_DIRECTORY, directory);
        result.put(FIELD_DELETED_COUNT, deletedCount);
        result.put(FIELD_MESSAGE, DELETE_PATH_MESSAGE);
        log.info("SkillFactory工作区路径删除完成, workspaceId:{}, filePath:{}, directory:{}, "
                        + "deletedCount:{}, fileTreeDigest:{}",
                workspaceId, filePath, directory, deletedCount, workspaceDO.getFileTreeDigest());
        return result;
    }

    /**
     * 丢弃当前可编辑内容，并从成功 PRT Build 或线上正式版本恢复完整文件和实体关系基线。
     *
     * <p>VERSION 保持原正式目录恢复语义；BUILD 必须拥有成功 PRT Deployment、不可变 BS3 ZIP
     * 和完整关系快照。两类来源都不创建 Skill 数字版本，不改变 workspaceId、正式历史和环境指针；
     * BUILD 恢复还保留当前 ACTIVE change 的原 baseVersion。
     */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public Map<String, Object> resetWorkspaceFromVersion(String workspaceId, Map<String, String> params)
            throws IOException {
        requireDraftEditable(workspaceId, ACTION_RESET_WORKSPACE);
        SkillDraft currentDraft = workspaceRepository.findDraftByWorkspaceId(workspaceId);
        if (currentDraft == null || currentDraft.getId() == null) {
            log.warn("SkillFactory重置当前变更失败，Skill草稿不存在, workspaceId:{}", workspaceId);
            throw new IllegalArgumentException(ERROR_SKILL_DRAFT_NOT_FOUND);
        }
        int targetVersion = currentDraft.getVersion() == null ? 0 : currentDraft.getVersion();
        if (targetVersion <= 0) {
            log.warn("SkillFactory重置当前变更失败，当前Skill版本无效, workspaceId:{}, version:{}",
                    workspaceId, currentDraft.getVersion());
            throw new IllegalArgumentException(ERROR_CURRENT_SKILL_VERSION_INVALID);
        }
        String sourceType = StringUtils.upperCase(StringUtils.defaultIfBlank(
                params == null ? EMPTY : params.get(PARAM_SOURCE_TYPE), RESET_SOURCE_TYPE_VERSION));
        String sourceId;
        int sourceVersion = 0;
        int restoredRelationCount;
        int resetBaseVersion;
        if (StringUtils.equals(sourceType, RESET_SOURCE_TYPE_BUILD)) {
            sourceId = required(params, PARAM_SOURCE_ID);
            resetBaseVersion = parseOptionalVersion(
                    loadDraftState(workspaceId).getProperty(DRAFT_STATE_KEY_BASE_VERSION));
            BuildRestoreResult restored = preprodBuildRestoreService.restoreBuild(
                    workspaceId, currentDraft, releaseState(workspaceId), sourceId,
                    workspaceRepository.workspaceRoot(), requireEditableWorkspace(workspaceId), operator(params));
            restoredRelationCount = restored.getRestoredRelationCount();
        } else if (StringUtils.equals(sourceType, RESET_SOURCE_TYPE_VERSION)) {
            sourceVersion = parsePositiveVersion(firstNonBlank(
                    params == null ? EMPTY : params.get(PARAM_SOURCE_ID),
                    params == null ? EMPTY : params.get(PARAM_SOURCE_VERSION),
                    params == null ? EMPTY : params.get(PARAM_BASE_VERSION),
                    params == null ? EMPTY : params.get(PARAM_VERSION)));
            sourceId = String.valueOf(sourceVersion);
            resetBaseVersion = sourceVersion;
            restoredRelationCount = preprodBuildRestoreService.restoreVersion(
                    currentDraft, releaseState(workspaceId), sourceVersion, targetVersion,
                    releaseWorkspace(workspaceId, sourceVersion), requireEditableWorkspace(workspaceId),
                    operator(params));
        } else {
            log.warn("SkillFactory重置当前变更失败，来源类型非法, workspaceId:{}, sourceType:{}",
                    workspaceId, sourceType);
            throw new IllegalArgumentException(ERROR_RESET_SOURCE_TYPE_INVALID);
        }
        updateResetBaseVersion(workspaceId, resetBaseVersion);
        Map<String, String> resetParams = new HashMap<>();
        if (params != null) {
            resetParams.putAll(params);
        }
        resetParams.put(PARAM_WORKSPACE_ID, workspaceId);
        resetParams.put(PARAM_BASE_VERSION, String.valueOf(resetBaseVersion));
        resetParams.put(PARAM_VERSION, String.valueOf(targetVersion));
        SkillDraft workspaceDO = persistWorkspaceState(workspaceId, resetParams);
        Map<String, Object> result = tree(workspaceId, Collections.emptyMap());
        result.put(FIELD_RESET_SOURCE_TYPE, sourceType);
        result.put(FIELD_RESET_SOURCE_ID, sourceId);
        if (sourceVersion > 0) {
            result.put(FIELD_RESET_SOURCE_VERSION, sourceVersion);
        }
        result.put(FIELD_RESET_TARGET_VERSION, targetVersion);
        result.put(FIELD_RESTORED_RELATION_COUNT, restoredRelationCount);
        result.put(FIELD_RESTORED_FILE_COUNT, defaultInteger(workspaceDO.getFileCount()));
        result.put(FIELD_MESSAGE, RESET_WORKSPACE_MESSAGE);
        log.warn("SkillFactory从指定来源重置当前变更完成, workspaceId:{}, sourceType:{}, sourceId:{}, "
                        + "targetVersion:{}, fileCount:{}, relationCount:{}, fileTreeDigest:{}",
                workspaceId, sourceType, sourceId, targetVersion, workspaceDO.getFileCount(),
                restoredRelationCount, workspaceDO.getFileTreeDigest());
        return result;
    }

    /**
     * 返回当前 workspace 的文件摘要列表，作为轻量 diff/保存摘要。
     */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public Map<String, Object> workspaceDiff(String workspaceId, Map<String, String> params) throws IOException {
        log.info("SkillFactory计算工作区diff摘要, workspaceId:{}", workspaceId);
        SkillDraft workspaceDO = readWorkspaceState(workspaceId);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_WORKSPACE_ID, workspaceId);
        result.put(FIELD_FILE_TREE_DIGEST, workspaceDO.getFileTreeDigest());
        result.put(FIELD_FILES, workspaceDO.getFiles().stream()
                .map(viewAssembler::fileToMap)
                .collect(Collectors.toList()));
        putDraftStateFields(result, workspaceDO.getWorkspaceId());
        return result;
    }

    /**
     * 保存当前工作区摘要。
     */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public Map<String, Object> saveWorkspace(String workspaceId, Map<String, String> params) throws IOException {
        log.info("SkillFactory保存工作区摘要, workspaceId:{}", workspaceId);
        requireDraftEditable(workspaceId, ACTION_SAVE_WORKSPACE);
        return workspaceToMap(persistWorkspaceState(workspaceId, params));
    }

    /**
     * 从当前 workspace 文本文件中提取可供前端渲染校验的卡片/A2UI 样例。
     */
    public Map<String, Object> extractRenderSample(String workspaceId, Map<String, String> params)
            throws IOException {
        log.info("SkillFactory提取工作区渲染样例, workspaceId:{}", workspaceId);
        Path workspace = requireWorkspace(workspaceId);
        List<Map<String, Object>> samples = new ArrayList<>();
        for (Path path : fileRepository.listFiles(workspace)) {
            if (fileRepository.size(path) > SkillFactoryWorkspaceFileRepository.MAX_TEXT_FILE_BYTES) {
                continue;
            }
            String content = fileRepository.readText(path);
            for (String sample : extractBetween(content, TAG_CARD_CONTAINER_START, TAG_CARD_CONTAINER_END)) {
                samples.add(sample(path, workspace, PROTOCOL_CARD_CONTAINER, sample));
            }
            for (String sample : extractBetween(content, TAG_A2UI_CONTAINER_START, TAG_A2UI_CONTAINER_END)) {
                samples.add(sample(path, workspace, PROTOCOL_A2UI, sample));
            }
            for (String sample : extractBetween(content, TAG_AGENT_UI_DSL_START, TAG_AGENT_UI_DSL_END)) {
                samples.add(sample(path, workspace, PROTOCOL_AGENT_UI_DSL, sample));
            }
            for (String sample : extractBetween(content, TAG_LOCAL_METHOD_START, TAG_LOCAL_METHOD_END)) {
                samples.add(sample(path, workspace, PROTOCOL_LOCAL_METHOD, sample));
            }
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_WORKSPACE_ID, workspaceId);
        result.put(FIELD_SAMPLES, samples);
        result.put(FIELD_STATUS, samples.isEmpty() ? STATUS_NOT_FOUND : STATUS_EXTRACTED);
        log.info("SkillFactory渲染样例提取完成, workspaceId:{}, sampleCount:{}, status:{}",
                workspaceId, samples.size(), result.get(FIELD_STATUS));
        return result;
    }

    /**
     * 查询当前 Skill 已经沉淀的正式包版本，供页面只读浏览和线上发布来源选择。
     */
    public Map<String, Object> releaseOptions(String workspaceId, Map<String, String> params) {
        requireIdentityWorkspace(workspaceId);
        Map<String, Object> result = releaseVersionSummary(workspaceId);
        log.info("SkillFactory查询正式包版本完成, workspaceId:{}, releaseVersions:{}",
                workspaceId, result.get(FIELD_RELEASE_VERSIONS));
        return result;
    }

    /**
     * 预览线上发布来源和对比版本之间的文件 diff。
     */
    public Map<String, Object> onlinePublishDiff(String workspaceId, Map<String, String> params)
            throws IOException {
        PublishSource publishSource = resolvePublishSource(workspaceId, params, false);
        Map<String, Object> result = releaseVersionSummary(workspaceId);
        result.put(FIELD_WORKSPACE_ID, workspaceId);
        result.put(FIELD_PUBLISH_SOURCE_TYPE, publishSource.sourceType);
        result.put(FIELD_SOURCE_LABEL, publishSource.sourceLabel);
        result.put(FIELD_SOURCE_VERSION, publishSource.sourceVersion);
        result.put(FIELD_COMPARE_VERSION, publishSource.compareVersion);
        result.putAll(diffResult(publishSource.comparePath, publishSource.sourcePath));
        log.info("SkillFactory线上发布diff预览完成, workspaceId:{}, sourceType:{}, sourceVersion:{}, "
                        + "compareVersion:{}",
                workspaceId, publishSource.sourceType, publishSource.sourceVersion,
                publishSource.compareVersion);
        return result;
    }

    /**
     * 从当前 workspace 构建本地 ZIP 包。
     */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public Map<String, Object> buildPackage(String workspaceId, String packageType, Map<String, String> params)
            throws IOException {
        log.info("SkillFactory开始构建包, workspaceId:{}, packageType:{}", workspaceId, packageType);
        Path workspace = requireWorkspace(workspaceId);
        SkillDraft workspaceDO = persistWorkspaceState(workspaceId, params);
        String buildId = UUID.randomUUID().toString().replace(UUID_SEPARATOR, EMPTY);
        Path buildDir = workspaceRepository.workspaceRoot()
                .resolve(BUILD_DIR)
                .resolve(workspaceId)
                .resolve(buildId)
                .normalize();
        List<Path> packageFiles = fileRepository.listFiles(workspace).stream()
                .filter(path -> isPackageFile(normalize(workspace.relativize(path))))
                .collect(Collectors.toList());
        ReleaseArtifact artifact = packageArtifactService.buildPackage(
                workspaceDO, buildDir, workspace, packageFiles);
        Map<String, Object> result = workspaceToMap(workspaceDO);
        result.putAll(viewAssembler.toMap(
                artifact, defaultVersion(workspaceDO.getVersion()), packageType, null));
        result.put(FIELD_ARTIFACT, artifact);
        log.info("SkillFactory构建包完成, workspaceId:{}, packageType:{}, packageDigest:{}",
                workspaceId, packageType, artifact.getPackageDigest());
        return result;
    }

    /**
     * 保存不可变数据库产物，并发布 Skill 正式环境运行时配置。
     *
     * <p>CURRENT 先从数据库工作区投影复制到临时目录并构建 ZIP；只有数据库产物与
     * 运行时配置发布都成功后，才写入 `online/releases/{version}` 投影并封板。HISTORICAL 使用既有正式
     * 目录和不可变 ZIP，不创建版本、不修改 current。返回 `publishStatus=SUCCEEDED` 供共享发布控制面推进，
     * 同时用 `externalPublishStage=PUBLISHED` 暴露真实完成阶段。
     */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public Map<String, Object> publishOnlinePackage(String workspaceId, Map<String, String> params)
            throws IOException {
        throw new IllegalArgumentException("USE_RELEASE_CONTROL_PLANE_WITH_IMMUTABLE_SNAPSHOT");
    }

    /**
     * 使用共享发布控制面冻结的来源产物发布线上。
     *
     * <p>CURRENT 会按当前工作区原始内容重新构建最终 ZIP；HISTORICAL 必须复用共享正式 Version 中的
     * 不可变产物。该方法不创建共享版本、不更新线上指针，只在完整成功后封板当前目录。
     */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public Map<String, Object> publishOnlinePackage(String workspaceId, Map<String, String> params,
            ReleaseArtifact sourceArtifact, ReleaseDeployment previousDeployment, String requestId,
            dev.a2flow.management.lifecycle.publish.SkillPublicationInput publicationInput)
            throws IOException {
        SkillDraft draft = workspaceRepository.findDraftByWorkspaceId(workspaceId);
        PublishSource publishSource = resolvePublishSource(workspaceId, params, true);
        if (draft == null) {
            throw new IllegalArgumentException(ERROR_SKILL_DRAFT_NOT_FOUND);
        }
        boolean currentPublish = StringUtils.equals(publishSource.sourceType, PUBLISH_SOURCE_CURRENT);
        if (currentPublish && parsePositiveVersion(publishSource.sourceVersion) != nextReleaseVersion(workspaceId)) {
            log.warn("SkillFactory拒绝使用非下一版本发布CURRENT, workspaceId:{}, requestVersion:{}, nextVersion:{}",
                    workspaceId, publishSource.sourceVersion, nextReleaseVersion(workspaceId));
            throw new IllegalArgumentException(ERROR_CURRENT_RELEASE_VERSION_INVALID);
        }
        Path finalReleaseSource = publishSource.sourcePath;
        Path packageSource = currentPublish
                ? workspaceRepository.workspaceRoot().resolve(BUILD_DIR).resolve(PUBLISH_BUILD_DIR)
                        .resolve(workspaceId).resolve(publishSource.sourceVersion).normalize()
                : finalReleaseSource;
        if (currentPublish) {
            requireDraftEditable(workspaceId, ACTION_PUBLISH_ONLINE_CURRENT);
            replaceDirectory(packageSource, requireWorkspace(workspaceId));
            log.info("SkillFactory当前内容已原样复制到线上发布临时目录, workspaceId:{}, releaseVersion:{}, "
                            + "path:{}",
                    workspaceId, publishSource.sourceVersion, packageSource);
        }
        String zipFileName = publishSource.sourceVersion + EXTENSION_ZIP;
        Path buildDir = workspaceRepository.resolveWorkspace(workspaceId)
                .resolve(DIR_PACKAGES)
                .resolve(PACKAGE_DIR_ONLINE)
                .normalize();
        Map<String, String> buildParams = new HashMap<>();
        if (params != null) {
            buildParams.putAll(params);
        }
        buildParams.put(PARAM_SOURCE_VERSION, publishSource.sourceVersion);
        try {
            int sourceVersion = parsePositiveVersion(publishSource.sourceVersion);
            ReleaseArtifact artifact;
            Map<String, Object> packageResult;
            if (StringUtils.equals(publishSource.sourceType, PUBLISH_SOURCE_HISTORICAL)) {
                artifact = sourceArtifact == null ? requireReleaseVersion(workspaceId, sourceVersion).getArtifact()
                        : sourceArtifact;
                if (artifact == null) {
                    throw new IllegalStateException(ERROR_ONLINE_VERSION_RECORD_NOT_FOUND);
                }
                packageResult = viewAssembler.toMap(
                        artifact, sourceVersion, PACKAGE_TYPE_ONLINE_RELEASE, previousDeployment);
                packageResult.put(FIELD_FILE_COUNT, fileRepository.listFiles(packageSource).size());
                packageResult.put(FIELD_PACKAGE_SOURCE_PATH,
                        normalize(workspaceRepository.workspaceRoot().relativize(packageSource)));
            } else {
                packageResult = buildPackageFromSource(workspaceId, packageSource,
                        PACKAGE_TYPE_ONLINE_RELEASE, buildDir, zipFileName, buildParams);
                artifact = (ReleaseArtifact) packageResult.get(FIELD_ARTIFACT);
            }
            SkillDatabasePublishResult externalResult = externalPublishService.publish(
                    draft, publishDescription(draft.getSkillDescription(), params), artifact, sourceVersion,
                    SkillDatabasePublishService.ENV_PROD, operator(params),
                    requestId, previousDeployment, publicationInput);
            packageResult.put(FIELD_ARTIFACT, externalResult.getArtifact());
            if (externalResult.isSuccess()) {
                if (currentPublish) {
                    replaceDirectory(finalReleaseSource, packageSource);
                    log.info("SkillFactory线上发布完整成功并封板, workspaceId:{}, releaseVersion:{}, "
                                    + "releasePath:{}",
                            workspaceId, sourceVersion, finalReleaseSource);
                }
            }
            Map<String, Object> result = publishResult(workspaceId, draft, publishSource, packageResult,
                    packageSource, externalResult, params);
            log.info("SkillFactory线上发布结束, workspaceId:{}, sourceType:{}, sourceVersion:{}, "
                            + "publishStatus:{}, externalStage:{}",
                    workspaceId, publishSource.sourceType, publishSource.sourceVersion,
                    result.get(FIELD_PUBLISH_STATUS), externalResult.getPublishStage());
            return result;
        } finally {
            if (currentPublish && Files.exists(packageSource)) {
                try {
                    deleteRecursively(packageSource);
                } catch (IOException cleanupException) {
                    log.warn("SkillFactory线上发布临时目录清理失败, workspaceId:{}, path:{}, error:{}",
                            workspaceId, packageSource, cleanupException.getMessage(), cleanupException);
                }
            }
        }
    }

    /** 构建数据库预发快照，并发布对应预发环境运行时配置。 */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public Map<String, Object> publishPreprodPackage(String workspaceId, Map<String, String> params)
            throws IOException {
        throw new IllegalArgumentException("USE_RELEASE_CONTROL_PLANE_WITH_IMMUTABLE_SNAPSHOT");
    }

    /** 构建预发 ZIP，并把真实发布结果交给共享 Build/Deployment 保存。 */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public Map<String, Object> publishPreprodPackage(String workspaceId, Map<String, String> params,
            ReleaseDeployment previousDeployment,
            dev.a2flow.management.lifecycle.publish.SkillPublicationInput publicationInput) throws IOException {
        SkillDraft draft = workspaceRepository.findDraftByWorkspaceId(workspaceId);
        requireDraftEditable(workspaceId, ACTION_PUBLISH_PREPROD);
        if (draft == null) {
            throw new IllegalArgumentException(ERROR_SKILL_DRAFT_NOT_FOUND);
        }
        Path source = requireWorkspace(workspaceId);
        Path buildDir = workspaceRepository.resolveWorkspace(workspaceId)
                .resolve(DIR_PACKAGES).resolve(PACKAGE_DIR_PREPROD).normalize();
        Map<String, String> buildParams = new HashMap<>();
        if (params != null) {
            buildParams.putAll(params);
        }
        buildParams.put(PARAM_SOURCE_VERSION, String.valueOf(defaultVersion(draft.getVersion())));
        Map<String, Object> packageResult = buildPackageFromSource(workspaceId, source,
                PACKAGE_TYPE_PREPROD_SNAPSHOT, buildDir, ZIP_FILE_PREPROD_SNAPSHOT, buildParams);
        ReleaseArtifact artifact = (ReleaseArtifact) packageResult.get(FIELD_ARTIFACT);
        SkillDatabasePublishResult externalResult = externalPublishService.publish(
                draft, publishDescription(draft.getSkillDescription(), params), artifact, defaultVersion(draft.getVersion()),
                SkillDatabasePublishService.ENV_PRT, operator(params), publicationInput.requestId(),
                previousDeployment, publicationInput);
        packageResult.put(FIELD_ARTIFACT, externalResult.getArtifact());
        PublishSource sourceInfo = new PublishSource(PUBLISH_SOURCE_CURRENT, SOURCE_LABEL_CURRENT,
                String.valueOf(defaultVersion(draft.getVersion())), String.valueOf(latestReleaseVersion(workspaceId)),
                source, latestReleaseVersion(workspaceId) > 0
                        ? releaseWorkspace(workspaceId, latestReleaseVersion(workspaceId)) : null);
        Map<String, Object> result = publishResult(workspaceId, draft, sourceInfo, packageResult,
                source, externalResult, params);
        result.put(FIELD_PUBLISH_STAGE, PUBLISH_STAGE_PREPROD);
        return result;
    }

    private Map<String, Object> publishResult(String workspaceId, SkillDraft draft,
            PublishSource publishSource, Map<String, Object> packageResult, Path packageSource,
            SkillDatabasePublishResult externalResult, Map<String, String> params) throws IOException {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_SKILL_CODE, firstNonBlank(
                params == null ? EMPTY : params.get(PARAM_SKILL_CODE), draft.getSkillCode(), workspaceId));
        result.put(FIELD_WORKSPACE_ID, workspaceId);
        result.put(FIELD_PUBLISH_STAGE, PUBLISH_SOURCE_HISTORICAL.equals(publishSource.sourceType)
                ? PUBLISH_STAGE_ONLINE_HISTORICAL : PUBLISH_STAGE_ONLINE_CURRENT);
        result.put(FIELD_PUBLISH_SOURCE_TYPE, publishSource.sourceType);
        result.put(FIELD_SOURCE_LABEL, publishSource.sourceLabel);
        result.put(FIELD_SOURCE_VERSION, publishSource.sourceVersion);
        result.put(FIELD_COMPARE_VERSION, publishSource.compareVersion);
        result.put(FIELD_PUBLISH_RESULT, packageResult);
        result.put(FIELD_VERSION, packageResult.get(FIELD_VERSION));
        result.put(FIELD_PACKAGE_DIGEST, packageResult.get(FIELD_PACKAGE_DIGEST));
        result.putAll(externalResult.toMap());
        result.putAll(diffResult(publishSource.comparePath, packageSource));
        result.put(FIELD_OPERATOR, operator(params));
        result.put(FIELD_CREATE_TIME, System.currentTimeMillis());
        return result;
    }

    /**
     * 恢复包版本。
     *
     * <p>`file://` 用于恢复 `PACKAGE_BUILD` 产生的本地包，HTTP/HTTPS 用于恢复对象存储暴露的 ZIP URL。
     * 未确认的对象存储私有协议继续返回明确未接入状态，避免把平台发布链路伪装成已完成。
     */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public Map<String, Object> restorePackage(String workspaceId, String packageUrl, Map<String, String> params)
            throws IOException {
        log.info("SkillFactory包版本恢复被调用, workspaceId:{}, packageUrl:{}",
                workspaceId, packageUrl);
        if (!isSupportedRestorePackageUrl(packageUrl)) {
            log.info("SkillFactory包版本恢复跳过，packageUrl协议未接入, workspaceId:{}, packageUrl:{}",
                    workspaceId, packageUrl);
            Map<String, Object> result = workspaceSummary(workspaceId, params);
            result.put(FIELD_PACKAGE_URL, StringUtils.defaultString(packageUrl));
            result.put(FIELD_RESTORE_STATUS, RESTORE_STATUS_PACKAGE_DOWNLOAD_NOT_CONNECTED);
            result.put(FIELD_MESSAGE, RESTORE_MESSAGE_PACKAGE_DOWNLOAD_NOT_CONNECTED);
            return result;
        }
        requireDraftEditable(workspaceId, ACTION_RESTORE_PACKAGE);
        Path workspace = requireWorkspace(workspaceId);
        int restoredFileCount = packageArtifactService.restorePackage(
                workspaceRepository.workspaceRoot(), workspace, packageUrl, workspaceId,
                workspaceId);
        SkillDraft workspaceDO = persistWorkspaceState(workspaceId, params);
        Map<String, Object> result = workspaceToMap(workspaceDO);
        result.put(FIELD_PACKAGE_URL, StringUtils.defaultString(packageUrl));
        result.put(FIELD_RESTORE_STATUS, RESTORE_STATUS_RESTORED);
        result.put(FIELD_RESTORED_FILE_COUNT, restoredFileCount);
        result.put(FIELD_MESSAGE, restoreMessage(packageUrl));
        log.info("SkillFactory包版本恢复完成, workspaceId:{}, restoredFileCount:{}, digest:{}",
                workspaceId, restoredFileCount, workspaceDO.getFileTreeDigest());
        return result;
    }

    private Map<String, Object> workspaceSummary(String workspaceId, Map<String, String> params) throws IOException {
        return workspaceToMap(readWorkspaceState(workspaceId));
    }

    private SkillDraft readWorkspaceState(String workspaceId) throws IOException {
        Path workspace = requireWorkspace(workspaceId);
        SkillDraft current = workspaceRepository.findDraftByWorkspaceId(workspaceId);
        if (current == null) {
            throw new IllegalStateException("PostgreSQL workspace metadata is missing");
        }
        List<SkillWorkspaceFile> files = fileRepository.files(workspace);
        return current.setFileTreeDigest(fileRepository.digestWorkspace(workspace))
                .setFileCount(files.size()).setFiles(files);
    }

    private Map<String, Object> workspaceViewSummary(String workspaceId, WorkspaceView workspaceView,
            Map<String, String> params) throws IOException {
        if (!workspaceView.readonly) {
            Map<String, Object> result = workspaceSummary(workspaceId, params);
            result.put(FIELD_VIEW_MODE, workspaceView.viewMode);
            result.put(FIELD_READONLY, false);
            putWorkspaceViewState(result, workspaceId, workspaceView);
            result.put(FIELD_RELEASE_VERSIONS, releaseVersions(workspaceId));
            result.put(FIELD_LATEST_RELEASE_VERSION, latestReleaseVersion(workspaceId));
            result.put(FIELD_NEXT_RELEASE_VERSION, nextReleaseVersion(workspaceId));
            return result;
        }
        List<SkillWorkspaceFile> files = fileRepository.files(workspaceView.path);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_WORKSPACE_ID, workspaceId);
        result.put(FIELD_WORKSPACE_ROOT, normalize(workspaceRepository.workspaceRoot()));
        result.put(FIELD_WORKSPACE_PATH, normalize(workspaceRepository.workspaceRoot().relativize(workspaceView.path)));
        result.put(FIELD_FILE_TREE_DIGEST, fileRepository.digestWorkspace(workspaceView.path));
        result.put(FIELD_FILE_COUNT, files.size());
        result.put(FIELD_FILES, files.stream().map(viewAssembler::fileToMap).collect(Collectors.toList()));
        result.put(FIELD_VIEW_MODE, workspaceView.viewMode);
        result.put(FIELD_READONLY, true);
        putWorkspaceViewState(result, workspaceId, workspaceView);
        result.put(FIELD_VERSION_NUMBER, workspaceView.version);
        result.put(FIELD_RELEASE_VERSIONS, releaseVersions(workspaceId));
        result.put(FIELD_LATEST_RELEASE_VERSION, latestReleaseVersion(workspaceId));
        result.put(FIELD_NEXT_RELEASE_VERSION, nextReleaseVersion(workspaceId));
        return result;
    }

    private SkillDraft persistWorkspaceState(String workspaceId, Map<String, String> params)
            throws IOException {
        Path workspace = requireWorkspace(workspaceId);
        List<SkillWorkspaceFile> files = fileRepository.files(workspace);
        String fileTreeDigest = fileRepository.digestWorkspace(workspace);
        workspaceSession.save(workspaceId);
        SkillDraft workspaceDO = workspaceRepository.upsertDraftMetadata(workspaceId,
                workspaceRepository.resolveWorkspace(workspaceId),
                fileTreeDigest, files.size(), params, operator(params));
        workspaceDO.setFileTreeDigest(fileTreeDigest)
                .setFiles(files);
        return workspaceDO;
    }

    private void requireDraftEditable(String workspaceId, String action) {
        if (isDraftEditable(workspaceId)) {
            return;
        }
        log.warn("SkillFactory当前变更已封板，拒绝写操作, workspaceId:{}, action:{}",
                workspaceId, action);
        throw new IllegalStateException(ERROR_DRAFT_SEALED);
    }

    private boolean isDraftEditable(String workspaceId) {
        return !StringUtils.equals(draftStatus(workspaceId), DRAFT_STATUS_SEALED);
    }

    private void putWorkspaceViewState(Map<String, Object> result, String workspaceId,
            WorkspaceView workspaceView) {
        putDraftStateFields(result, workspaceId);
        if (workspaceView.readonly) {
            result.put(FIELD_EDITABLE, false);
        }
    }

    private void putDraftStateFields(Map<String, Object> result, String workspaceId) {
        Properties draftState = loadDraftState(workspaceId);
        String status = draftStatus(draftState);
        result.put(FIELD_EDITABLE, !StringUtils.equals(status, DRAFT_STATUS_SEALED));
        result.put(FIELD_DRAFT_STATUS, status);
        result.put(FIELD_BASE_VERSION, parseOptionalVersion(draftState.getProperty(DRAFT_STATE_KEY_BASE_VERSION)));
        result.put(FIELD_SEALED_VERSION,
                parseOptionalVersion(draftState.getProperty(DRAFT_STATE_KEY_SEALED_VERSION)));
    }

    private String draftStatus(String workspaceId) {
        return draftStatus(loadDraftState(workspaceId));
    }

    private String draftStatus(Properties draftState) {
        String status = draftState.getProperty(DRAFT_STATE_KEY_STATUS);
        if (!DRAFT_STATUS_EDITING.equals(status) && !DRAFT_STATUS_SEALED.equals(status)) {
            throw new IllegalStateException("Invalid workspace edit-protection state");
        }
        return status;
    }

    /** Project existing release lifecycle fields; local directory loss cannot change edit permissions. */
    private Properties loadDraftState(String workspaceId) {
        AssetReleaseState state = releaseState(workspaceId);
        if (state.getRevision() == null || state.getRevision() <= 0 || state.getVersions() == null) {
            throw new IllegalStateException("Persisted workspace release state is missing");
        }
        Properties draftState = new Properties();
        dev.a2flow.management.release.ReleaseModels.ReleaseChange change = state.getActiveChange();
        String status;
        if (change == null) {
            // This is an explicitly persisted initial aggregate, not a missing-row fallback.
            status = state.getVersions().isEmpty() ? DRAFT_STATUS_EDITING : DRAFT_STATUS_SEALED;
        } else if ("ACTIVE".equals(change.getStatus())) {
            status = DRAFT_STATUS_EDITING;
        } else if (DRAFT_STATUS_SEALED.equals(change.getStatus())) {
            status = DRAFT_STATUS_SEALED;
        } else {
            throw new IllegalStateException("Invalid persisted release change status");
        }
        draftState.setProperty(DRAFT_STATE_KEY_STATUS, status);
        if (change != null && change.getBaseVersion() != null && change.getBaseVersion() > 0) {
            draftState.setProperty(DRAFT_STATE_KEY_BASE_VERSION, String.valueOf(change.getBaseVersion()));
        }
        if (DRAFT_STATUS_SEALED.equals(status)) {
            int sealedVersion = state.getVersions().stream().map(ReleaseVersion::getVersion)
                    .filter(Objects::nonNull).max(Integer::compareTo).orElse(0);
            if (sealedVersion > 0) {
                draftState.setProperty(DRAFT_STATE_KEY_SEALED_VERSION, String.valueOf(sealedVersion));
            }
        }
        return draftState;
    }

    private void updateResetBaseVersion(String workspaceId, int baseVersion) {
        AssetReleaseState state = releaseState(workspaceId);
        if (state.getRevision() == null || state.getRevision() <= 0) {
            throw new IllegalStateException("Persisted workspace release state is missing");
        }
        if (state.getActiveChange() == null) {
            if (baseVersion > 0) {
                throw new IllegalStateException("An active release change is required to reset a version base");
            }
            return;
        }
        if (!"ACTIVE".equals(state.getActiveChange().getStatus())) {
            throw new IllegalStateException("An active release change is required to reset a version base");
        }
        state.getActiveChange().setBaseVersion(baseVersion > 0 ? baseVersion : null);
        releaseStateRepository.save(state, state.getRevision());
    }

    private Path requireWorkspace(String workspaceId) {
        return requireEditableWorkspace(workspaceId);
    }

    private Path requireIdentityWorkspace(String workspaceId) {
        Path workspace = workspaceRepository.resolveWorkspace(workspaceId);
        try {
            if (!workspaceSession.exists(workspaceId)) {
                throw new IllegalArgumentException(ERROR_WORKSPACE_NOT_FOUND);
            }
            Files.createDirectories(workspace);
        } catch (IOException failure) {
            throw new IllegalStateException("Cannot load PostgreSQL workspace identity", failure);
        }
        return workspace;
    }

    /**
     * 返回当前可编辑工作区根目录。
     *
     * <p>每个请求从 PostgreSQL 恢复隔离的临时投影，同请求中的编辑通过 revision CAS 保存。
     * 旧本地目录不会隐式导入数据库；遗留内容迁移必须通过显式导入流程完成。
     */
    private Path requireEditableWorkspace(String workspaceId) {
        try {
            // The same request keeps its edited projection; each new request restores PostgreSQL bytes.
            workspaceRepository.resolveWorkspace(workspaceId);
            return workspaceSession.load(workspaceId, workspaceRepository.workspaceRoot().resolve("_projections"));
        } catch (IOException e) {
            throw new IllegalStateException("Cannot materialize PostgreSQL workspace", e);
        }
    }

    private Path editableWorkspace(String workspaceId) {
        return workspaceRepository.resolveWorkspace(workspaceId)
                .resolve(DIR_PREPROD)
                .resolve(DIR_CURRENT)
                .normalize();
    }

    private Path releaseWorkspace(String workspaceId, int version) {
        return workspaceRepository.resolveWorkspace(workspaceId)
                .resolve(DIR_ONLINE)
                .resolve(DIR_RELEASES)
                .resolve(String.valueOf(version))
                .normalize();
    }

    private WorkspaceView resolveWorkspaceView(String workspaceId, Map<String, String> params) {
        String viewMode = StringUtils.defaultIfBlank(params == null ? EMPTY : params.get(PARAM_VIEW_MODE),
                VIEW_MODE_PREPROD_CURRENT);
        if (StringUtils.equals(viewMode, VIEW_MODE_ONLINE_RELEASE)) {
            int version = parsePositiveVersion(firstNonBlank(
                    params == null ? EMPTY : params.get(PARAM_VERSION),
                    params == null ? EMPTY : params.get(PARAM_SOURCE_VERSION)));
            Path releaseWorkspace = releaseWorkspace(workspaceId, version);
            if (!Files.exists(releaseWorkspace)) {
                log.warn("SkillFactory正式包只读目录不存在, workspaceId:{}, version:{}, path:{}",
                        workspaceId, version, releaseWorkspace);
                throw new IllegalArgumentException(ERROR_RELEASE_VERSION_NOT_FOUND);
            }
            return new WorkspaceView(releaseWorkspace, VIEW_MODE_ONLINE_RELEASE, String.valueOf(version), true);
        }
        return new WorkspaceView(requireEditableWorkspace(workspaceId), VIEW_MODE_PREPROD_CURRENT, EMPTY, false);
    }

    private void copyLegacyRootFiles(Path identityWorkspace, Path editableWorkspace) throws IOException {
        if (!Files.exists(identityWorkspace)) {
            return;
        }
        int copiedCount = 0;
        for (Path child : fileRepository.listChildren(identityWorkspace)) {
            String name = child.getFileName() == null ? EMPTY : child.getFileName().toString();
            if (isWorkspaceSystemDir(name)) {
                continue;
            }
            Path target = editableWorkspace.resolve(name).normalize();
            if (Files.exists(target)) {
                continue;
            }
            copyPath(child, target);
            copiedCount++;
        }
        if (copiedCount > 0) {
            log.info("SkillFactory历史根目录文件已迁移到preprod/current, identityWorkspace:{}, "
                            + "editableWorkspace:{}, copiedCount:{}",
                    identityWorkspace, editableWorkspace, copiedCount);
        }
    }

    private boolean isWorkspaceSystemDir(String name) {
        return StringUtils.equals(name, DIR_PREPROD)
                || StringUtils.equals(name, DIR_ONLINE)
                || StringUtils.equals(name, DIR_PACKAGES)
                || StringUtils.equals(name, BUILD_DIR);
    }

    private Map<String, Object> releaseVersionSummary(String workspaceId) {
        AssetReleaseState state = releaseState(workspaceId);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_WORKSPACE_ID, workspaceId);
        result.put(FIELD_PREPROD_BUILD_RESET_SOURCES, preprodBuildRestoreService.selectableBuildSources(state));
        result.put(FIELD_RELEASE_VERSIONS, releaseVersions(state));
        result.put(FIELD_LATEST_RELEASE_VERSION, latestReleaseVersion(state));
        result.put(FIELD_NEXT_RELEASE_VERSION, nextReleaseVersion(state));
        return result;
    }
    private List<Integer> releaseVersions(String workspaceId) {
        return releaseVersions(releaseState(workspaceId));
    }
    private List<Integer> releaseVersions(AssetReleaseState state) {
        return state.getVersions().stream()
                .map(ReleaseVersion::getVersion)
                .filter(Objects::nonNull)
                .sorted()
                .collect(Collectors.toList());
    }

    private int latestReleaseVersion(String workspaceId) {
        return latestReleaseVersion(releaseState(workspaceId));
    }

    private int latestReleaseVersion(AssetReleaseState state) {
        List<Integer> versions = releaseVersions(state);
        return versions.isEmpty() ? 0 : versions.get(versions.size() - 1);
    }

    private int nextReleaseVersion(String workspaceId) {
        return nextReleaseVersion(releaseState(workspaceId));
    }

    private int nextReleaseVersion(AssetReleaseState state) {
        return Math.max(1, latestReleaseVersion(state) + 1);
    }

    /** 返回当前 ONLINE 环境实际生效版本，而不是简单取数字最大的历史版本。 */
    private int onlineReleaseVersion(String workspaceId) {
        EnvironmentState online = releaseState(workspaceId).getEnvironments().get(ReleaseEnvironment.ONLINE.name());
        return online == null || online.getVersion() == null ? 0 : online.getVersion();
    }

    private PublishSource resolvePublishSource(String workspaceId, Map<String, String> params, boolean forPublish) {
        String sourceType = StringUtils.defaultIfBlank(params == null ? EMPTY : params.get(PARAM_PUBLISH_SOURCE_TYPE),
                PUBLISH_SOURCE_CURRENT);
        int compareVersion = parseOptionalVersion(params == null ? EMPTY : params.get(PARAM_COMPARE_VERSION));
        if (compareVersion <= 0) {
            compareVersion = onlineReleaseVersion(workspaceId);
        }
        Path comparePath = compareVersion > 0 && Files.exists(releaseWorkspace(workspaceId, compareVersion))
                ? releaseWorkspace(workspaceId, compareVersion) : null;
        if (StringUtils.equals(sourceType, PUBLISH_SOURCE_CURRENT)) {
            int sourceVersion = parseOptionalVersion(firstNonBlank(
                    params == null ? EMPTY : params.get(PARAM_SOURCE_VERSION),
                    params == null ? EMPTY : params.get(PARAM_VERSION)));
            if (sourceVersion <= 0) {
                sourceVersion = nextReleaseVersion(workspaceId);
            }
            Path sourcePath = forPublish ? releaseWorkspace(workspaceId, sourceVersion)
                    : requireEditableWorkspace(workspaceId);
            return new PublishSource(PUBLISH_SOURCE_CURRENT, SOURCE_LABEL_CURRENT,
                    String.valueOf(sourceVersion), String.valueOf(compareVersion), sourcePath, comparePath);
        }
        if (StringUtils.equals(sourceType, PUBLISH_SOURCE_HISTORICAL)) {
            int sourceVersion = parsePositiveVersion(firstNonBlank(
                    params == null ? EMPTY : params.get(PARAM_SOURCE_VERSION),
                    params == null ? EMPTY : params.get(PARAM_VERSION)));
            Path sourcePath = releaseWorkspace(workspaceId, sourceVersion);
            if (!Files.exists(sourcePath)) {
                log.warn("SkillFactory历史正式包不存在, workspaceId:{}, sourceVersion:{}, path:{}",
                        workspaceId, sourceVersion, sourcePath);
                throw new IllegalArgumentException(ERROR_RELEASE_VERSION_NOT_FOUND);
            }
            return new PublishSource(PUBLISH_SOURCE_HISTORICAL, SOURCE_LABEL_HISTORICAL,
                    String.valueOf(sourceVersion), String.valueOf(compareVersion), sourcePath, comparePath);
        }
        log.warn("SkillFactory线上发布来源类型非法, workspaceId:{}, sourceType:{}", workspaceId, sourceType);
        throw new IllegalArgumentException(ERROR_PUBLISH_SOURCE_TYPE_INVALID);
    }

    private Map<String, Object> buildPackageFromSource(String workspaceId, Path sourceWorkspace, String packageType,
            Path buildDir, String zipFileName, Map<String, String> params) throws IOException {
        List<SkillWorkspaceFile> files = fileRepository.files(sourceWorkspace);
        String fileTreeDigest = fileRepository.digestWorkspace(sourceWorkspace);
        SkillDraft draft = workspaceRepository.findDraftByWorkspaceId(workspaceId);
        SkillDraft workspaceDO = new SkillDraft()
                .setId(draft == null ? null : draft.getId())
                .setWorkspaceId(workspaceId)
                .setSkillCode(draft == null ? workspaceId : draft.getSkillCode())
                .setVersion(parseOptionalVersion(firstNonBlank(
                        params == null ? EMPTY : params.get(PARAM_SOURCE_VERSION),
                        params == null ? EMPTY : params.get(PARAM_VERSION))))
                .setFileTreeDigest(fileTreeDigest)
                .setFiles(files);
        if (workspaceDO.getVersion() == null || workspaceDO.getVersion() <= 0) {
            workspaceDO.setVersion(defaultVersion(draft == null ? null : draft.getVersion()));
        }
        List<Path> packageFiles = fileRepository.listFiles(sourceWorkspace).stream()
                .filter(path -> isPackageFile(normalize(sourceWorkspace.relativize(path))))
                .collect(Collectors.toList());
        ReleaseArtifact artifact = packageArtifactService.buildPackage(
                workspaceDO, buildDir, sourceWorkspace, zipFileName, packageFiles);
        Map<String, Object> result = viewAssembler.toMap(
                artifact, defaultVersion(workspaceDO.getVersion()), packageType, null);
        result.put(FIELD_ARTIFACT, artifact);
        result.put(FIELD_FILE_TREE_DIGEST, fileTreeDigest);
        result.put(FIELD_FILE_COUNT, files.size());
        result.put(FIELD_PACKAGE_SOURCE_PATH, normalize(workspaceRepository.workspaceRoot().relativize(sourceWorkspace)));
        return result;
    }

    private Map<String, Object> diffResult(Path beforeRoot, Path afterRoot) throws IOException {
        Map<String, SkillWorkspaceFile> beforeFiles = fileMetaMap(beforeRoot);
        Map<String, SkillWorkspaceFile> afterFiles = fileMetaMap(afterRoot);
        List<Map<String, Object>> diffFiles = new ArrayList<>();
        int added = 0;
        int modified = 0;
        int deleted = 0;
        for (Map.Entry<String, SkillWorkspaceFile> entry : afterFiles.entrySet()) {
            SkillWorkspaceFile before = beforeFiles.get(entry.getKey());
            SkillWorkspaceFile after = entry.getValue();
            if (before == null) {
                added++;
                diffFiles.add(diffFile(entry.getKey(), DIFF_TYPE_ADDED, EMPTY, after.getContentDigest()));
            } else if (!StringUtils.equals(before.getContentDigest(), after.getContentDigest())) {
                modified++;
                diffFiles.add(diffFile(entry.getKey(), DIFF_TYPE_MODIFIED,
                        before.getContentDigest(), after.getContentDigest()));
            }
        }
        for (Map.Entry<String, SkillWorkspaceFile> entry : beforeFiles.entrySet()) {
            if (!afterFiles.containsKey(entry.getKey())) {
                deleted++;
                diffFiles.add(diffFile(entry.getKey(), DIFF_TYPE_DELETED,
                        entry.getValue().getContentDigest(), EMPTY));
            }
        }
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put(FIELD_ADDED_COUNT, added);
        summary.put(FIELD_MODIFIED_COUNT, modified);
        summary.put(FIELD_DELETED_COUNT, deleted);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_DIFF_FILES, diffFiles);
        result.put(FIELD_DIFF_SUMMARY, summary);
        return result;
    }

    private Map<String, SkillWorkspaceFile> fileMetaMap(Path root) throws IOException {
        if (root == null || !Files.exists(root)) {
            return Collections.emptyMap();
        }
        return fileRepository.files(root).stream()
                .collect(Collectors.toMap(SkillWorkspaceFile::getFilePath, item -> item,
                        (left, right) -> left, LinkedHashMap::new));
    }

    private Map<String, Object> diffFile(String filePath, String changeType, String beforeDigest,
            String afterDigest) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put(FIELD_FILE_PATH, filePath);
        item.put(FIELD_CHANGE_TYPE, changeType);
        item.put(FIELD_BEFORE_DIGEST, beforeDigest);
        item.put(FIELD_AFTER_DIGEST, afterDigest);
        return item;
    }

    private void replaceDirectory(Path target, Path source) throws IOException {
        if (Files.exists(target)) {
            deleteRecursively(target);
        }
        Files.createDirectories(target);
        for (Path child : fileRepository.listChildren(source)) {
            copyPath(child, target.resolve(child.getFileName().toString()).normalize());
        }
    }

    private void copyPath(Path source, Path target) throws IOException {
        if (Files.isDirectory(source)) {
            Files.createDirectories(target);
            for (Path child : fileRepository.listChildren(source)) {
                copyPath(child, target.resolve(child.getFileName().toString()).normalize());
            }
            return;
        }
        Files.createDirectories(target.getParent());
        Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
    }

    private void deleteRecursively(Path path) throws IOException {
        try (java.util.stream.Stream<Path> stream = Files.walk(path)) {
            for (Path item : stream.sorted(Comparator.reverseOrder()).collect(Collectors.toList())) {
                Files.deleteIfExists(item);
            }
        }
    }

    private long countWorkspaceEntries(Path workspace) throws IOException {
        try (java.util.stream.Stream<Path> stream = Files.walk(workspace)) {
            return Math.max(0L, stream.count() - 1L);
        }
    }

    private long countPathEntries(Path path) throws IOException {
        try (java.util.stream.Stream<Path> stream = Files.walk(path)) {
            return stream.count();
        }
    }

    /**
     * 按 SkillFactory 新口径派生 workspaceId：平台创建入口只认 skillCode，workspaceId 永远等于 skillCode。
     */
    private String deriveWorkspaceId(String skillCode) {
        return required(Collections.singletonMap(PARAM_SKILL_CODE, skillCode), PARAM_SKILL_CODE);
    }

    private Path resolveFile(Path workspace, String filePath) {
        if (StringUtils.isBlank(filePath) || Paths.get(filePath).isAbsolute() || filePath.contains("..")) {
            log.warn("SkillFactory文件路径非法, workspacePath:{}, filePath:{}", workspace, filePath);
            throw new IllegalArgumentException(ERROR_FILE_PATH_INVALID);
        }
        Path file = workspace.resolve(filePath).normalize();
        if (!file.startsWith(workspace)) {
            log.warn("SkillFactory文件路径越界, workspacePath:{}, filePath:{}", workspace, filePath);
            throw new IllegalArgumentException(ERROR_FILE_OUTSIDE_WORKSPACE);
        }
        return file;
    }

    private Map<String, Object> treeNode(Path workspace, Path path, String title) throws IOException {
        Map<String, Object> node = new LinkedHashMap<>();
        String key = workspace.equals(path) ? ROOT_KEY : normalize(workspace.relativize(path));
        node.put(FIELD_NODE_KEY, key);
        node.put(FIELD_NODE_TITLE, title);
        node.put(FIELD_NODE_DIRECTORY, fileRepository.isDirectory(path));
        if (fileRepository.isDirectory(path)) {
            List<Map<String, Object>> children = new ArrayList<>();
            for (Path child : fileRepository.listChildren(path)) {
                children.add(treeNode(workspace, child, child.getFileName().toString()));
            }
            node.put(FIELD_NODE_CHILDREN, children);
        } else {
            node.putAll(viewAssembler.fileToMap(fileRepository.file(workspace, path)));
        }
        return node;
    }

    private void ensureEditablePath(String filePath) {
        if (!isPackageFile(filePath)) {
            log.warn("SkillFactory文件类型不可编辑, filePath:{}", filePath);
            throw new IllegalArgumentException(ERROR_FILE_TYPE_NOT_EDITABLE);
        }
    }

    private boolean isPackageFile(String filePath) {
        return StringUtils.equals(filePath, FILE_SKILL_MD)
                || StringUtils.startsWith(filePath, DIR_SCRIPTS)
                || StringUtils.startsWith(filePath, DIR_REFERENCES)
                || StringUtils.startsWith(filePath, DIR_EXAMPLES)
                || StringUtils.endsWith(filePath, EXTENSION_JSON)
                || StringUtils.endsWith(filePath, EXTENSION_MARKDOWN)
                || StringUtils.endsWith(filePath, EXTENSION_PYTHON)
                || StringUtils.endsWith(filePath, EXTENSION_TEXT)
                || StringUtils.endsWith(filePath, EXTENSION_YAML)
                || StringUtils.endsWith(filePath, EXTENSION_YML);
    }

    private List<String> extractBetween(String content, String start, String end) {
        if (StringUtils.isBlank(content)) {
            return Collections.emptyList();
        }
        List<String> results = new ArrayList<>();
        int offset = 0;
        while (offset < content.length()) {
            int startIndex = content.indexOf(start, offset);
            if (startIndex < 0) {
                break;
            }
            int dataStart = startIndex + start.length();
            int endIndex = content.indexOf(end, dataStart);
            if (endIndex < 0) {
                break;
            }
            results.add(content.substring(dataStart, endIndex).trim());
            offset = endIndex + end.length();
        }
        return results;
    }

    private Map<String, Object> sample(Path file, Path workspace, String protocol, String payload) throws IOException {
        Map<String, Object> sample = new HashMap<>();
        sample.put(FIELD_SAMPLE_SOURCE, normalize(workspace.relativize(file)));
        sample.put(FIELD_RENDER_PROTOCOL, protocol);
        sample.put(FIELD_PAYLOAD, payload);
        sample.put(FIELD_CONTENT_DIGEST, fileRepository.sha256(fileRepository.readText(file)
                .getBytes(StandardCharsets.UTF_8)));
        return sample;
    }

    private String buildLineDiff(String before, String after) {
        Map<String, Object> diff = new LinkedHashMap<>();
        diff.put(FIELD_BEFORE_LINE_COUNT,
                StringUtils.splitByWholeSeparatorPreserveAllTokens(before, LINE_SEPARATOR).length);
        diff.put(FIELD_AFTER_LINE_COUNT,
                StringUtils.splitByWholeSeparatorPreserveAllTokens(after, LINE_SEPARATOR).length);
        diff.put(FIELD_CHANGED, !Objects.equals(before, after));
        return diff.toString();
    }

    private boolean isSupportedRestorePackageUrl(String packageUrl) {
        return StringUtils.startsWithIgnoreCase(packageUrl, LOCAL_FILE_URL_PREFIX)
                || StringUtils.startsWithIgnoreCase(packageUrl, HTTP_URL_PREFIX)
                || StringUtils.startsWithIgnoreCase(packageUrl, HTTPS_URL_PREFIX);
    }

    private byte[] decodeZipBase64(String zipBase64) {
        String normalized = StringUtils.defaultString(zipBase64).trim();
        int markerIndex = StringUtils.indexOfIgnoreCase(normalized, ZIP_BASE64_DATA_URL_MARKER);
        if (markerIndex >= 0) {
            normalized = normalized.substring(markerIndex + ZIP_BASE64_DATA_URL_MARKER.length());
        }
        normalized = StringUtils.deleteWhitespace(normalized);
        try {
            return Base64.getDecoder().decode(normalized);
        } catch (IllegalArgumentException e) {
            log.warn("SkillFactory ZIP导入失败，zipBase64不是合法Base64, base64Length:{}",
                    StringUtils.defaultString(zipBase64).length(), e);
            throw new IllegalArgumentException(ERROR_ZIP_BASE64_INVALID, e);
        }
    }

    private String restoreMessage(String packageUrl) {
        if (StringUtils.startsWithIgnoreCase(packageUrl, LOCAL_FILE_URL_PREFIX)) {
            return RESTORE_MESSAGE_LOCAL_PACKAGE_RESTORED;
        }
        return RESTORE_MESSAGE_REMOTE_PACKAGE_RESTORED;
    }

    private Map<String, Object> workspaceToMap(SkillDraft workspaceDO) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_WORKSPACE_ID, workspaceDO.getWorkspaceId());
        result.put(FIELD_WORKSPACE_ROOT, workspaceDO.getWorkspaceRoot());
        result.put(FIELD_WORKSPACE_PATH, workspaceDO.getWorkspacePath());
        result.put(FIELD_FILE_TREE_DIGEST, workspaceDO.getFileTreeDigest());
        result.put(FIELD_FILE_COUNT, workspaceDO.getFileCount());
        result.put(FIELD_LANG_BRIDGE_SKILL_ID, workspaceDO.getLangBridgeSkillId());
        result.put(FIELD_FILES, workspaceDO.getFiles().stream()
                .map(viewAssembler::fileToMap)
                .collect(Collectors.toList()));
        return result;
    }

    private Map<String, Object> draftSummaryToMap(SkillDraft draft) {
        return draftToMap(draft, false);
    }

    private Map<String, Object> draftToMap(SkillDraft draft) {
        return draftToMap(draft, true);
    }

    /** 把 Skill 草稿转换为页面数据，并按需读取当前 Skill 版本的实体关系。 */
    private Map<String, Object> draftToMap(SkillDraft draft, boolean includeRelations) {
        Map<String, Object> result = new LinkedHashMap<>();
        Integer version = defaultVersion(draft.getVersion());
        AssetReleaseState releaseState = releaseState(draft.getWorkspaceId());
        EnvironmentState preprod = releaseState.getEnvironments().get(ReleaseEnvironment.PRT.name());
        EnvironmentState online = releaseState.getEnvironments().get(ReleaseEnvironment.ONLINE.name());
        String owner = StringUtils.defaultString(draft.getOwner());
        result.put(FIELD_SKILL_CODE, StringUtils.defaultString(draft.getSkillCode()));
        result.put(FIELD_SKILL_NAME_CN, StringUtils.defaultString(draft.getSkillNameCn()));
        result.put(FIELD_SKILL_NAME_EN, StringUtils.defaultString(draft.getSkillNameEn()));
        result.put(FIELD_SKILL_DESCRIPTION, StringUtils.defaultString(draft.getSkillDescription()));
        result.put(FIELD_BUSINESS_DOMAIN, StringUtils.defaultString(draft.getBusinessDomain()));
        result.put(FIELD_CAPABILITY_DOMAIN, StringUtils.defaultString(draft.getCapabilityDomain()));
        specialistRelationService.putPageProjection(result, draft);
        result.put(FIELD_CREATE_SOURCE, StringUtils.defaultString(draft.getCreateSource()));
        result.put(FIELD_WORKSPACE_ID, StringUtils.defaultString(draft.getWorkspaceId()));
        result.put(FIELD_WORKSPACE_PATH, StringUtils.defaultString(draft.getWorkspacePath()));
        result.put(FIELD_FILE_TREE_DIGEST, StringUtils.defaultString(draft.getFileTreeDigest()));
        result.put(FIELD_SOURCE_ZIP_URL, StringUtils.defaultString(draft.getSourceZipUrl()));
        result.put(FIELD_VERSION, version);
        result.put(FIELD_VERSION_LABEL, versionLabel(version));
        result.put(FIELD_VERSION_STATUS, releaseState.getActiveChange() == null
                ? StringUtils.defaultString(draft.getStatus())
                : StringUtils.defaultString(releaseState.getActiveChange().getStatus()));
        result.put(FIELD_REGISTER_STATUS, registerStatus(draft));
        result.put(FIELD_LANG_BRIDGE_SKILL_ID, draft.getLangBridgeSkillId());
        result.put(FIELD_PUBLISH_TARGET, EMPTY);
        result.put(FIELD_PREPROD_VERSION_ID, preprod == null ? EMPTY : preprod.getSourceId());
        result.put(FIELD_ONLINE_VERSION_ID, online == null ? EMPTY : online.getSourceId());
        result.put(FIELD_PREPROD_PACKAGE_ID, preprod == null ? EMPTY : preprod.getSourceId());
        result.put(FIELD_ONLINE_PACKAGE_ID, online == null ? EMPTY : online.getSourceId());
        result.put(FIELD_PREPROD_VERSION, preprod == null ? 0 : defaultInteger(preprod.getVersion()));
        result.put(FIELD_ONLINE_VERSION, online == null ? 0 : defaultInteger(online.getVersion()));
        result.put(FIELD_PREPROD_BUILD_RESET_SOURCES,
                preprodBuildRestoreService.selectableBuildSources(releaseState));
        result.put(FIELD_RELEASE_VERSIONS, releaseVersions(releaseState));
        result.put(FIELD_LATEST_RELEASE_VERSION, latestReleaseVersion(releaseState));
        result.put(FIELD_NEXT_RELEASE_VERSION, nextReleaseVersion(releaseState));
        putDraftStateFields(result, draft.getWorkspaceId());
        result.put(FIELD_STATUS, StringUtils.defaultString(draft.getStatus()));
        result.put(FIELD_OWNER, owner);
        result.put(FIELD_CREATOR, StringUtils.defaultIfBlank(draft.getCreator(), owner));
        result.put(FIELD_MODIFIER, StringUtils.defaultIfBlank(draft.getModifier(), owner));
        result.put(FIELD_EXT_JSON, StringUtils.defaultString(draft.getExtJson()));
        List<Map<String, Object>> capabilityBindings = includeRelations
                ? relationSnapshots(draft,
                        SkillFactoryEntityRelationConstants.RELATION_TYPE_SKILL_USES_CAPABILITY)
                : Collections.emptyList();
        List<Map<String, Object>> componentBindings = includeRelations
                ? relationSnapshots(draft,
                        SkillFactoryEntityRelationConstants.RELATION_TYPE_SKILL_USES_COMPONENT)
                : Collections.emptyList();
        result.put(FIELD_CAPABILITY_BINDINGS, capabilityBindings);
        result.put(FIELD_COMPONENT_BINDINGS, componentBindings);
        result.put(FIELD_REFERENCE_RENDER_ASSETS, componentBindings);
        result.put(FIELD_REFERENCE_COMPONENT_CODES, componentBindings.stream()
                .map(item -> firstNonBlank(string(item.get(FIELD_COMPONENT_CODE)), string(item.get(FIELD_CODE))))
                .filter(StringUtils::isNotBlank)
                .collect(Collectors.joining(COMMA)));
        result.put(FIELD_REFERENCE_CAPABILITIES, capabilityBindings);
        result.put(FIELD_REFERENCE_CAPABILITY_DRAFT_IDS, capabilityBindings.stream()
                .map(item -> string(item.get(FIELD_CAPABILITY_DRAFT_ID)))
                .filter(StringUtils::isNotBlank)
                .collect(Collectors.toList()));
        result.put(FIELD_CREATE_TIME, defaultLong(draft.getCreateTime()));
        result.put(FIELD_UPDATE_TIME, defaultLong(draft.getUpdateTime()));
        return result;
    }

    /** 读取指定 Skill 数字版本和关系类型下的受控快照。 */
    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> relationSnapshots(SkillDraft draft, String relationType) {
        if (draft.getId() == null) {
            log.warn("SkillFactory查询实体关系失败，Skill草稿缺少主键, skillCode:{}, workspaceId:{}",
                    draft.getSkillCode(), draft.getWorkspaceId());
            throw new IllegalStateException(ERROR_ENTITY_RELATION_SNAPSHOT_INVALID);
        }
        int version = defaultVersion(draft.getVersion());
        List<EntityRelationDO> relations = entityRelationRepository.listBySourceVersion(
                SkillFactoryEntityRelationConstants.NAMESPACE_SKILL_FACTORY,
                SkillFactoryEntityRelationConstants.ENTITY_TYPE_SKILL,
                String.valueOf(draft.getId()), version);
        if (relations.isEmpty()) {
            return Collections.emptyList();
        }
        List<Map<String, Object>> snapshots = new ArrayList<>();
        for (EntityRelationDO relation : relations) {
            if (!StringUtils.equals(relationType, relation.getRelationType())) {
                continue;
            }
            try {
                Object snapshot = JsonSupport.fromJSON(relation.getSnapshotJson(), Object.class);
                if (!(snapshot instanceof Map)) {
                    throw new IllegalStateException(ERROR_ENTITY_RELATION_SNAPSHOT_INVALID);
                }
                snapshots.add(new LinkedHashMap<>((Map<String, Object>) snapshot));
            } catch (Exception e) {
                log.warn("SkillFactory实体关系快照解析失败, skillCode:{}, skillVersion:{}, "
                                + "relationId:{}, relationType:{}, error:{}",
                        draft.getSkillCode(), version, relation.getId(), relation.getRelationType(),
                        e.getMessage());
                throw new IllegalStateException(ERROR_ENTITY_RELATION_SNAPSHOT_INVALID, e);
            }
        }
        return snapshots;
    }

    private AssetReleaseState releaseState(String workspaceId) {
        return releaseStateRepository.find(ReleaseAssetType.SKILL, workspaceId);
    }

    private ReleaseVersion requireReleaseVersion(String workspaceId, int version) {
        return releaseState(workspaceId).getVersions().stream()
                .filter(item -> Objects.equals(item.getVersion(), version))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(ERROR_RELEASE_VERSION_RECORD_NOT_FOUND));
    }

    private String required(Map<String, ?> params, String key) {
        String value = string(params.get(key));
        if (StringUtils.isBlank(value)) {
            throw new IllegalArgumentException(key + ERROR_REQUIRED_SUFFIX);
        }
        return value;
    }

    private String string(Object value) {
        return value == null ? EMPTY : String.valueOf(value);
    }

    private int parsePositiveVersion(String value) {
        int version = parseOptionalVersion(value);
        if (version <= 0) {
            log.warn("SkillFactory版本号非法, version:{}", value);
            throw new IllegalArgumentException(ERROR_RELEASE_VERSION_INVALID);
        }
        return version;
    }

    private int parseOptionalVersion(String value) {
        String normalized = StringUtils.trimToEmpty(value);
        if (StringUtils.isBlank(normalized)) {
            return 0;
        }
        try {
            int version = Integer.parseInt(normalized);
            return version > 0 ? version : 0;
        } catch (NumberFormatException e) {
            log.warn("SkillFactory版本号解析失败, version:{}", value);
            throw new IllegalArgumentException(ERROR_RELEASE_VERSION_INVALID, e);
        }
    }

    private boolean isPositiveIntegerText(String value) {
        try {
            return Integer.parseInt(StringUtils.trimToEmpty(value)) > 0;
        } catch (NumberFormatException e) {
            return false;
        }
    }

    private String operator(Map<String, String> params) {
        return params == null ? DEFAULT_OPERATOR
                : StringUtils.defaultIfBlank(params.get(PARAM_USER_NAME), DEFAULT_OPERATOR);
    }

    private String normalize(Path path) {
        return path.normalize().toString().replace('\\', '/');
    }

    private String versionLabel(Integer version) {
        return String.valueOf(defaultVersion(version));
    }

    private String versionPointer(Integer version) {
        Integer value = defaultInteger(version);
        if (value <= 0) {
            return EMPTY;
        }
        return String.valueOf(value);
    }

    private String registerStatus(SkillDraft draft) {
        return firstNonBlank(draft.getStatus(), STATUS_NOT_REGISTERED);
    }

    private String firstNonBlank(String... values) {
        for (String value : values) {
            if (StringUtils.isNotBlank(value)) {
                return value;
            }
        }
        return EMPTY;
    }

    private Integer defaultInteger(Integer value) {
        return value == null ? 0 : value;
    }

    private Integer defaultVersion(Integer value) {
        return value == null || value <= 0 ? 1 : value;
    }

    private Long defaultLong(Long value) {
        return value == null ? 0L : value;
    }

    private static class WorkspaceView {
        private final Path path;
        private final String viewMode;
        private final String version;
        private final boolean readonly;

        WorkspaceView(Path path, String viewMode, String version, boolean readonly) {
            this.path = path;
            this.viewMode = viewMode;
            this.version = version;
            this.readonly = readonly;
        }
    }

    private static class PublishSource {
        private final String sourceType;
        private final String sourceLabel;
        private final String sourceVersion;
        private final String compareVersion;
        private final Path sourcePath;
        private final Path comparePath;

        PublishSource(String sourceType, String sourceLabel, String sourceVersion, String compareVersion,
                Path sourcePath, Path comparePath) {
            this.sourceType = sourceType;
            this.sourceLabel = sourceLabel;
            this.sourceVersion = sourceVersion;
            this.compareVersion = compareVersion;
            this.sourcePath = sourcePath;
            this.comparePath = comparePath;
        }
    }
}
