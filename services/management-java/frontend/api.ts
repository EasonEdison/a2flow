import { jsonParse, jsonStringify } from './shared/safeJson';
import { assertManualManagementMethod } from './shared/managementAuthoringPolicy';
import type { ComponentAssetQuery, ComponentPreviewResult, ComponentRenderPreviewParams, ComponentRenderPreviewResult, AssetReleaseEnvironmentFacts, AssetAccessResult, AssetReleaseOperationResult, AssetReleaseOverview, ReleaseDiffDocument, ReleaseDiffQuery, ReleaseAssetType, ReleaseEnvironment, SkillFactoryComponentAsset, } from './types';
import type { A2uiCatalogAuthoringJson, A2uiCatalogComponentContract, A2uiCatalogComponentQuery, A2uiCatalogComponentRecord, A2uiManagedCatalogImportResult, A2uiCatalogQuery, A2uiCatalogRecord, } from './a2uiCatalogContracts';
import { parseA2uiCatalogAuthoringJson } from './a2uiCatalogContracts';
import type { A2uiApplicationBlueprintCode, A2uiApplicationBlueprintWireSource, A2uiApplicationDraft, A2uiApplicationQuery, A2uiApplicationRecord, } from './a2uiApplicationContracts';
import { projectA2uiApplicationBlueprintOptions, projectA2uiApplicationActionScanResult, projectA2uiApplicationBlueprintWireSource, normalizeA2uiApplicationDraft, toA2uiApplicationAuthoringPayload, } from './a2uiApplicationContracts';
import type { CapabilityClient } from './capabilityClientVariantLayout';
import { buildSpecialistPrtBindingRequest } from './specialistPrtDebug';
const BASE_URL = '/api/management/v2/handler';
const BIZ_RENDER_URL = '/api/management/v2/bizrender';
const CHAT_URL = '/api/management/v2/chat';
const SKILL_BINDING_ADD_URL = '/api/management/v2/bindings/add';
const SKILL_BINDING_REMOVE_URL = '/api/management/v2/bindings/remove';
const SKILL_BINDING_SOURCE = 'SKILL_FACTORY';
const SUCCESS_RESULT = 1;
export const SKILL_FACTORY_CHAT_BIZ_KEYS = {
    SKILL_CODING: 'HADES_SKILL_FACTORY',
    COMPONENT_CENTER_AUTHORING: 'HADES_COMPONENT_CENTER_AUTHORING',
    CAPABILITY_CENTER_AUTHORING: 'HADES_CAPABILITY_CENTER_AUTHORING',
    A2UI_COMPONENT_AUTHORING: 'HADES_A2UI_COMPONENT_AUTHORING',
} as const;
export const SkillBindingAction = {
    ADD: 'ADD',
    REMOVE: 'REMOVE',
} as const;
export type SkillBindingActionCode = (typeof SkillBindingAction)[keyof typeof SkillBindingAction];
export const SkillFactoryMethod = {
    SKILL_FACTORY_CONFIG: 'SKILL_FACTORY_CONFIG',
    SKILL_LIST: 'SKILL_LIST',
    SKILL_DETAIL: 'SKILL_DETAIL',
    SKILL_UPDATE: 'SKILL_UPDATE',
    SKILL_COMPONENT_CANDIDATE_LIST: 'SKILL_COMPONENT_CANDIDATE_LIST',
    SKILL_CAPABILITY_CANDIDATE_LIST: 'SKILL_CAPABILITY_CANDIDATE_LIST',
    WORKSPACE_CREATE: 'WORKSPACE_CREATE',
    ZIP_CONFIRM_IMPORT: 'ZIP_CONFIRM_IMPORT',
    WORKSPACE_TREE: 'WORKSPACE_TREE',
    WORKSPACE_FILE_CONTENT: 'WORKSPACE_FILE_CONTENT',
    WORKSPACE_ZIP_EXPORT: 'WORKSPACE_ZIP_EXPORT',
    WORKSPACE_FILE_SAVE: 'WORKSPACE_FILE_SAVE',
    WORKSPACE_PATH_DELETE: 'WORKSPACE_PATH_DELETE',
    WORKSPACE_RESET_FROM_VERSION: 'WORKSPACE_RESET_FROM_VERSION',
    WORKSPACE_SAVE: 'WORKSPACE_SAVE',
    WORKSPACE_RENDER_SAMPLE_EXTRACT: 'WORKSPACE_RENDER_SAMPLE_EXTRACT',
    SKILL_BINDINGS_REPLACE: 'SKILL_BINDINGS_REPLACE',
    CAPABILITY_SKILL_CREATOR_CONTEXT: 'CAPABILITY_SKILL_CREATOR_CONTEXT',
    RUNTIME_VALIDATE: 'RUNTIME_VALIDATE',
    PACKAGE_PUBLISH_PREPROD: 'PACKAGE_PUBLISH_PREPROD',
    PACKAGE_RELEASE_OPTIONS: 'PACKAGE_RELEASE_OPTIONS',
    PACKAGE_ONLINE_PUBLISH_DIFF: 'PACKAGE_ONLINE_PUBLISH_DIFF',
    PACKAGE_PUBLISH_ONLINE: 'PACKAGE_PUBLISH_ONLINE',
    CODING_CHAT: 'CODING_CHAT',
    CODING_PATCH_CONFIRM: 'CODING_PATCH_CONFIRM',
    CODING_PATCH_DISCARD: 'CODING_PATCH_DISCARD',
    AUTHORING_UI_ACTION: 'AUTHORING_UI_ACTION',
    CODING_VALIDATE: 'CODING_VALIDATE',
    CODING_VALIDATION_REPAIR: 'CODING_VALIDATION_REPAIR',
    COMPONENT_LIST: 'COMPONENT_LIST',
    COMPONENT_ENABLED_LIST: 'COMPONENT_ENABLED_LIST',
    COMPONENT_PUBLISHED_LIST: 'COMPONENT_PUBLISHED_LIST',
    COMPONENT_DETAIL: 'COMPONENT_DETAIL',
    COMPONENT_REGISTER: 'COMPONENT_REGISTER',
    COMPONENT_BASIC_INFO_UPDATE: 'COMPONENT_BASIC_INFO_UPDATE',
    COMPONENT_UPDATE: 'COMPONENT_UPDATE',
    COMPONENT_OFFLINE: 'COMPONENT_OFFLINE',
    COMPONENT_PREVIEW: 'COMPONENT_PREVIEW',
    COMPONENT_RUNTIME_DETAIL: 'COMPONENT_RUNTIME_DETAIL',
    COMPONENT_RUNTIME_BATCH_GET: 'COMPONENT_RUNTIME_BATCH_GET',
    COMPONENT_RENDER_PREVIEW: 'COMPONENT_RENDER_PREVIEW',
    A2UI_CATALOG_COMPONENT_LIST: 'A2UI_CATALOG_COMPONENT_LIST',
    A2UI_CATALOG_COMPONENT_DETAIL: 'A2UI_CATALOG_COMPONENT_DETAIL',
    A2UI_CATALOG_COMPONENT_CREATE: 'A2UI_CATALOG_COMPONENT_CREATE',
    A2UI_CATALOG_COMPONENT_UPDATE: 'A2UI_CATALOG_COMPONENT_UPDATE',
    A2UI_CATALOG_LIST: 'A2UI_CATALOG_LIST',
    A2UI_CATALOG_DETAIL: 'A2UI_CATALOG_DETAIL',
    A2UI_CATALOG_CREATE: 'A2UI_CATALOG_CREATE',
    A2UI_CATALOG_UPDATE: 'A2UI_CATALOG_UPDATE',
    A2UI_CATALOG_MANAGED_IMPORT: 'A2UI_CATALOG_MANAGED_IMPORT',
    A2UI_APPLICATION_LIST: 'A2UI_APPLICATION_LIST',
    A2UI_APPLICATION_DETAIL: 'A2UI_APPLICATION_DETAIL',
    A2UI_APPLICATION_CREATE: 'A2UI_APPLICATION_CREATE',
    A2UI_APPLICATION_UPDATE: 'A2UI_APPLICATION_UPDATE',
    A2UI_APPLICATION_BLUEPRINT_LIST: 'A2UI_APPLICATION_BLUEPRINT_LIST',
    A2UI_APPLICATION_BLUEPRINT_IMPORT: 'A2UI_APPLICATION_BLUEPRINT_IMPORT',
    A2UI_APPLICATION_ACTION_SCAN: 'A2UI_APPLICATION_ACTION_SCAN',
    CAPABILITY_LIST: 'CAPABILITY_LIST',
    CAPABILITY_PUBLISHED_LIST: 'CAPABILITY_PUBLISHED_LIST',
    CAPABILITY_DRAFT_CREATE: 'CAPABILITY_DRAFT_CREATE',
    CAPABILITY_DRAFT_DETAIL: 'CAPABILITY_DRAFT_DETAIL',
    CAPABILITY_DRAFT_SAVE: 'CAPABILITY_DRAFT_SAVE',
    CAPABILITY_VALIDATE: 'CAPABILITY_VALIDATE',
    CAPABILITY_DRY_RUN: 'CAPABILITY_DRY_RUN',
    CAPABILITY_PUBLISH: 'CAPABILITY_PUBLISH',
    RELEASE_OVERVIEW: 'RELEASE_OVERVIEW',
    RELEASE_CHANGE_CREATE: 'RELEASE_CHANGE_CREATE',
    RELEASE_DIFF: 'RELEASE_DIFF',
    RELEASE_PREPROD_DEPLOY: 'RELEASE_PREPROD_DEPLOY',
    RELEASE_ONLINE_DEPLOY: 'RELEASE_ONLINE_DEPLOY',
    RELEASE_HISTORY_REDEPLOY: 'RELEASE_HISTORY_REDEPLOY',
    RELEASE_DEPLOYMENT_DETAIL: 'RELEASE_DEPLOYMENT_DETAIL',
    RELEASE_GRAY_START: 'RELEASE_GRAY_START',
    RELEASE_GRAY_ADJUST: 'RELEASE_GRAY_ADJUST',
    RELEASE_GRAY_STOP: 'RELEASE_GRAY_STOP',
    RELEASE_GRAY_PROMOTE: 'RELEASE_GRAY_PROMOTE',
    ASSET_ACCESS_GET: 'ASSET_ACCESS_GET',
    ASSET_OWNER_REPLACE: 'ASSET_OWNER_REPLACE',
    WORKFLOW_CREATE: 'WORKFLOW_CREATE',
    WORKFLOW_DETAIL: 'WORKFLOW_DETAIL',
    WORKFLOW_LIST: 'WORKFLOW_LIST',
    WORKFLOW_BASIC_INFO_UPDATE: 'WORKFLOW_BASIC_INFO_UPDATE',
    WORKFLOW_DRAFT_DETAIL: 'WORKFLOW_DRAFT_DETAIL',
    WORKFLOW_DRAFT_UPDATE: 'WORKFLOW_DRAFT_UPDATE',
    WORKFLOW_SKILL_CANDIDATES: 'WORKFLOW_SKILL_CANDIDATES',
    WORKFLOW_COMPILED_PLAN_PREVIEW: 'WORKFLOW_COMPILED_PLAN_PREVIEW',
    AUTHORING_SESSION_HISTORY: 'AUTHORING_SESSION_HISTORY',
    AUTHORING_SESSION_CREATE: 'AUTHORING_SESSION_CREATE',
    CODING_RUN_STATUS: 'CODING_RUN_STATUS',
    CODING_RUN_CANCEL: 'CODING_RUN_CANCEL',
} as const;
export type SkillFactoryMethodCode = (typeof SkillFactoryMethod)[keyof typeof SkillFactoryMethod];
export interface SkillFactoryCommonResponse {
    result: number;
    errorMsg?: string;
    error_msg?: string;
    data?: unknown;
    traceId?: string;
    trace_id?: string;
    isList?: boolean;
    is_list?: boolean;
}
export type WorkspaceViewMode = 'PREPROD_CURRENT' | 'ONLINE_RELEASE';
export type PublishSourceType = 'CURRENT' | 'HISTORICAL';
export type DraftStatus = 'EDITING' | 'SEALED';
export type WorkspaceResetSourceType = 'BUILD' | 'VERSION';
export interface PreprodBuildResetSource {
    sourceType: 'BUILD';
    sourceId: string;
    buildNumber: number;
    targetVersion: number;
    createTime?: number;
    completionTime?: number;
    operator?: string;
    packageDigest: string;
    label?: string;
}
export interface WorkspaceResetSource {
    sourceType: WorkspaceResetSourceType;
    sourceId: string;
}
export interface SkillDraft {
    skillCode: string;
    skillNameCn: string;
    skillNameEn: string;
    skillDescription?: string;
    businessDomain?: string;
    capabilityDomain?: string;
    specialistId: string;
    specialistName: string;
    workspaceId: string;
    workspacePath: string;
    fileTreeDigest: string;
    version: number;
    versionLabel: string;
    versionStatus: string;
    preprodVersionId: string;
    onlineVersionId: string;
    registerStatus: string;
    langBridgeSkillId: string | number | null;
    publishTarget: string;
    owner: string;
    creator: string;
    modifier: string;
    createTime: number;
    updateTime: number;
    bindingRecords?: SkillBindingRecord[];
    publishRecords?: SkillPublishRecord[];
    preprodBuildResetSources?: PreprodBuildResetSource[];
    releaseVersions?: number[];
    latestReleaseVersion?: number;
    nextReleaseVersion?: number;
    editable?: boolean;
    draftStatus?: DraftStatus;
    baseVersion?: number;
    sealedVersion?: number;
    referenceRenderAssets?: SkillFactoryReferenceAsset[];
    referenceComponentCodes?: string;
    referenceCapabilities?: SkillFactoryReferenceCapability[];
    referenceCapabilityDraftIds?: string[];
    capabilityBindings?: SkillFactoryCapabilityBinding[];
    componentBindings?: SkillFactoryComponentBinding[];
}
export interface SkillFactorySpecialistOption {
    id: string;
    name: string;
    value?: string;
    label?: string;
    digitalEmployeeId?: string;
    specialistId?: string;
    specialistName?: string;
    roleCode?: string;
    ownerId?: string;
    debugPageUrl?: string;
    tracePageUrl?: string;
}
export interface SkillFactoryDomainOption {
    value?: string;
    label?: string;
    code?: string;
    name?: string;
    id?: string;
}
export interface SkillFactoryQuickPrompt {
    key: string;
    label: string;
    prompt: string;
}
export interface SkillFactoryBizConfig {
    agentId?: string;
    ownerId?: string;
    scopeType?: string;
    capabilityDomains?: SkillFactoryDomainOption[];
}
export type CapabilityFieldSource = 'MODEL_INPUT' | 'CONSTANT' | 'SYSTEM_VARIABLE';
export type CapabilitySystemVariable = 'userId' | 'client';
export interface CapabilityActionAllowedValue {
    value?: string | number;
    label?: string;
    description?: string;
}
export type CapabilityActionValueSchemaType = 'string' | 'number' | 'integer' | 'boolean' | 'object' | 'array';
export interface CapabilityActionValueSchema {
    type?: CapabilityActionValueSchemaType;
    description?: string;
    items?: CapabilityActionValueSchema;
    properties?: Record<string, CapabilityActionValueSchema>;
    required?: string[];
}
export interface CapabilityActionInputField {
    toolField?: string;
    type?: Exclude<CapabilityActionValueSchemaType, 'object'>;
    businessMeaning?: string;
    unit?: string;
    source?: CapabilityFieldSource;
    constantValue?: string | number | boolean | unknown[];
    systemVariable?: CapabilitySystemVariable;
    valueMapping?: Record<string, string>;
    required?: boolean;
    examples?: string;
    allowedValues?: CapabilityActionAllowedValue[];
    items?: CapabilityActionValueSchema;
}
export interface CapabilityActionKeyOutputField {
    path?: string;
    description?: string;
    observedType?: string;
}
export type CapabilityPresentationUsage = 'SUCCESS_RESULT' | 'APPROVAL_INTERACTION' | 'ERROR_RESULT';
export interface CapabilityPresentationComponent {
    assetId?: number;
    componentName: string;
    componentNameCn?: string;
    assetType?: string;
    renderProtocol?: string;
    dslType?: string;
    agentUiDsl?: string;
    componentVersion?: string;
    protocolVersion?: string;
    usage: CapabilityPresentationUsage;
    paramsMapping?: Record<string, string>;
}
export interface CapabilityActionDraftData {
    payloadType?: string;
    mode?: 'CREATE' | 'UPDATE';
    supportedClients?: CapabilityClient[];
    clientVariants?: Partial<Record<CapabilityClient, CapabilityClientTechnicalVariant>>;
    basicInfo: {
        actionCode?: string;
        nameCn?: string;
        description?: string;
        technicalOwner?: string;
        status?: string;
    };
    apiSource: {
        sourceType?: string;
        importedAt?: string;
        sanitized?: boolean;
    };
    modelContract: {
        description?: string;
        inputFields?: CapabilityActionInputField[];
        inputExampleJson?: string;
    };
    executionBinding: {
        bindingType?: string;
        target?: {
            targetKey?: string;
            serviceName?: string;
            methodName?: string;
            descriptorSetBase64?: string;
            contextField?: string;
        };
        requestMappingsJson?: string;
        contextMappingsJson?: string;
        timeoutMs?: string | number;
        maxResponseBytes?: string | number;
        responsePolicy?: 'ORIGINAL';
        idempotency?: string;
    };
    resultContract: {
        keyOutputFields?: CapabilityActionKeyOutputField[];
        responseDemoJson?: string;
        technicalOutputSchema?: string;
        errorMappings?: string;
        presentationComponents?: CapabilityPresentationComponent[];
    };
    governance: {
        sideEffectLevel?: string;

        publishBlockers?: string;
    };
}
export type CapabilityClientTechnicalVariant = Pick<CapabilityActionDraftData, 'apiSource' | 'modelContract' | 'executionBinding' | 'resultContract'>;
export interface CapabilityActionDraft {
    draftId: string;
    revision: number;
    status: string;
    draft: CapabilityActionDraftData;
    validationErrors?: string[];
    validationWarnings?: string[];
    validationStatus?: string;
    published?: boolean;
    publishedVersion?: number;
    businessDomain?: string;
    businessDomainName?: string;
    capabilityDomain?: string;
    capabilityDomainName?: string;
    specialistId?: string;
    specialistName?: string;
    editing?: boolean;
    online?: boolean;
    releaseEnvironmentFacts?: AssetReleaseEnvironmentFacts;
    creator?: string;
    modifier?: string;
    createTime?: number;
    updateTime?: number;
}
export interface SkillFactoryReferenceCapability {
    draftId: string;
    revision?: number;
    published?: boolean;
    publishedVersion?: number;
    releaseEnvironmentFacts?: AssetReleaseEnvironmentFacts;
    status?: string;
    validationStatus?: string;
    actionCode?: string;
    nameCn?: string;
    description?: string;
    businessDomain?: string;
    sourceType?: string;
    sideEffectLevel?: string;

    modelContract?: CapabilityActionDraftData['modelContract'];
    executionBinding?: CapabilityActionDraftData['executionBinding'];
    resultContract?: CapabilityActionDraftData['resultContract'];
    governance?: CapabilityActionDraftData['governance'];
}
export type SkillFactoryCapabilityBindMode = 'EXECUTION_ONLY' | 'EXECUTION_AND_RENDER';
export interface SkillFactoryCapabilityBinding extends SkillFactoryReferenceCapability {
    capabilityCode: string;
    bindMode: SkillFactoryCapabilityBindMode;
}
export interface CapabilitySkillCreatorContext {
    schemaVersion: string;
    capabilities: Array<{
        bindingIdentity: {
            draftId: string;
            revision: number;
        };
        actionCode?: string;
        nameCn?: string;
        businessDomain?: string;
        description?: string;
        bindMode?: SkillFactoryCapabilityBindMode;
        modelContract?: {
            description?: string;
            inputFields?: CapabilityActionInputField[];
            inputExample?: unknown;
        };
        resultContract?: {
            keyOutputFields?: CapabilityActionKeyOutputField[];
            responseExample?: unknown;
        };
        governance?: {
            sideEffectLevel?: string;

        };
        presentation?: {
            enabled?: boolean;
            runtimeManaged?: boolean;
            instruction?: string;
        };
    }>;
}
export interface CapabilityActionValidationResult {
    draftId: string;
    revision: number;
    valid: boolean;
    status: string;
    errors: string[];
    warnings: string[];
    publishBlockers: string[];
    validatedAt: number;
}
export type CapabilityActionDryRunEnvironment = 'PRT' | 'ONLINE';
export interface CapabilityActionToolResult {
    success: boolean;
    actionCode?: string;
    capabilityVersion?: number;
    clientType: CapabilityClient;
    requestedEnvironment?: string;
    resolvedEnvironment?: string;
    httpStatus?: number;
    contentType?: string;
    traceId?: string;
    data?: unknown;
    errorCode?: string;
    message?: string;
}
export interface CapabilityActionDryRunResult {
    protocol?: string;
    targetKey?: string;
    serviceName?: string;
    methodName?: string;
    environment: CapabilityActionDryRunEnvironment;
    clientType: CapabilityClient;
    configuredHost?: string;
    processLane?: string;
    httpMethod?: string;
    path?: string;
    effectiveArguments?: Record<string, unknown>;
    effectiveRequestBody?: Record<string, unknown>;
    toolResult: CapabilityActionToolResult;
}
export type AuthoringGuideActionType = 'SEND' | 'FILL_INPUT';
export interface AuthoringGuidePrompt {
    key?: string;
    text: string;
    sendMsg: string;
    actionType?: AuthoringGuideActionType;
}
export interface AuthoringGuideConfig {
    enabled?: boolean;
    welcomeMessage?: string;
    quickPrompts?: AuthoringGuidePrompt[];
    composerPrompts?: AuthoringGuidePrompt[];
}
export interface SkillFactoryReferenceComponent {
    code: string;
    name: string;
    componentName: string;
    renderProtocol?: string;
    scene?: string;
    prompt: string;
}
export interface SkillFactoryReferenceAsset {
    assetId?: number;
    code: string;
    name: string;
    assetType: string;
    renderProtocol: string;
    componentName?: string;
    dslCode?: string;
    agentUiDsl?: string;
    dslType?: string;
    localMethod?: string;
    scene?: string;
    owner?: string;
    lifecycleStatus?: string;
    enabled?: boolean;
    published?: boolean;
    publishedVersion?: number;
    releaseEnvironmentFacts?: AssetReleaseEnvironmentFacts;
    protocolVersion?: string;
    interactionMode?: 'DISPLAY_ONLY' | 'INTERACTIVE';
    rendererVersion?: string;
    componentVersion?: string;
    officialDemoJson?: string;
    integrationPrompt?: string;
    schemaJson?: string;
    paramsSchemaJson?: string;
    dataSourceConfigJson?: string;
    renderTemplateJson?: string;
    resultAdaptersJson?: string;
    entityContextPolicyJson?: string;
    source?: string;
}
export interface SkillFactoryComponentBinding extends SkillFactoryReferenceAsset {
    assetId: number;
    componentCode: string;
    componentVersion?: string;
    componentNameCn?: string;
}
export interface SkillFactoryPageConfig {
    agentId?: string;
    ownerId?: string;
    scopeType?: string;
    bizConfigs?: Record<string, SkillFactoryBizConfig>;
    specialists?: SkillFactorySpecialistOption[];
    businessDomains?: SkillFactoryDomainOption[];
    capabilityDomains?: SkillFactoryDomainOption[];
    quickPrompts?: SkillFactoryQuickPrompt[];
    referenceComponents?: SkillFactoryReferenceComponent[];
    referenceRenderAssets?: SkillFactoryReferenceAsset[];
    links?: {
        bEndDebugPageUrl?: string;
        tracePageUrl?: string;
        componentCenterUrl?: string;
    };
}
export interface SkillInfoPayload {
    skillCode: string;
    skillNameCn: string;
    skillNameEn: string;
    skillDescription?: string;
    businessDomain?: string;
    capabilityDomain?: string;
    specialistId: string;
    specialistName: string;
    specialistIds?: string;
    specialistNames?: string;
    owner?: string;
    ownersJson?: string;
    version?: string;
}
export interface SkillInfoUpdatePayload {
    skillCode: string;
    skillNameCn: string;
    skillDescription?: string;
    businessDomain?: string;
    capabilityDomain?: string;
    specialistId?: string;
    specialistIds?: string;
}
export interface SkillTreeNode {
    key: string;
    title: string;
    directory?: boolean;
    children?: SkillTreeNode[];
    filePath?: string;
    fileType?: string;
    fileSize?: number;
    contentDigest?: string;
    modifyTime?: number;
}
export interface WorkspaceTreeResult {
    workspaceId: string;
    workspacePath: string;
    fileTreeDigest: string;
    fileCount: number;
    treeData: SkillTreeNode;
    files?: WorkspaceFileMeta[];
    viewMode?: WorkspaceViewMode;
    readonly?: boolean;
    version?: string | number;
    preprodBuildResetSources?: PreprodBuildResetSource[];
    releaseVersions?: number[];
    latestReleaseVersion?: number;
    nextReleaseVersion?: number;
    editable?: boolean;
    draftStatus?: DraftStatus;
    baseVersion?: number;
    sealedVersion?: number;
    deletedPath?: string;
    deletedDirectory?: boolean;
    deletedCount?: number;
    resetSourceVersion?: number;
    resetSourceType?: WorkspaceResetSourceType;
    resetSourceId?: string;
    resetTargetVersion?: number;
    restoredFileCount?: number;
    restoredRelationCount?: number;
    message?: string;
}
export interface ZipImportResult extends WorkspaceTreeResult {
    zipFileName: string;
    sourceZipUrl?: string;
    importStatus: string;
    importedFileCount: number;
    message?: string;
}
export interface WorkspaceZipExportResult {
    workspaceId: string;
    skillCode: string;
    zipFileName: string;
    zipBase64: string;
    fileCount: number;
    fileTreeDigest: string;
    viewMode?: WorkspaceViewMode;
    readonly?: boolean;
    version?: string | number;
}
export interface WorkspaceFileMeta {
    filePath: string;
    fileName: string;
    fileType: string;
    fileSize: number;
    contentDigest: string;
    modifyTime: number;
}
export interface WorkspaceFileContent extends WorkspaceFileMeta {
    content: string;
    viewMode?: WorkspaceViewMode;
    readonly?: boolean;
    editable?: boolean;
}
export interface WorkspaceViewParams {
    viewMode?: WorkspaceViewMode;
    version?: string | number;
}
export interface ReleaseVersionOptions {
    workspaceId: string;
    preprodBuildResetSources?: PreprodBuildResetSource[];
    releaseVersions: number[];
    latestReleaseVersion: number;
    nextReleaseVersion: number;
    editable?: boolean;
    draftStatus?: DraftStatus;
    baseVersion?: number;
    sealedVersion?: number;
}
export interface ReleaseDiffSummary {
    addedCount?: number;
    modifiedCount?: number;
    deletedCount?: number;
}
export interface ReleaseDiffFile {
    filePath: string;
    changeType: string;
    beforeDigest?: string;
    afterDigest?: string;
}
export interface OnlinePublishParams {
    publishSourceType: PublishSourceType;
    sourceVersion?: string | number;
    compareVersion?: string | number;
}
export interface OnlinePublishDiffResult extends ReleaseVersionOptions {
    publishSourceType: PublishSourceType;
    sourceLabel: string;
    sourceVersion: string;
    compareVersion: string;
    diffFiles: ReleaseDiffFile[];
    diffSummary: ReleaseDiffSummary;
}
export interface RenderSampleResult {
    workspaceId: string;
    status: string;
    samples: Array<{
        source: string;
        renderProtocol: string;
        payload: unknown;
        contentDigest: string;
    }>;
}
export interface RuntimeValidationCheck {
    key: string;
    label: string;
    status: string;
    message?: string;
}
export interface RuntimeValidationResult {
    workspaceId: string;
    skillCode?: string;
    status: string;
    sampleSource: string;
    samples: Array<{
        source: string;
        renderProtocol: string;
        payload: unknown;
        contentDigest?: string;
    }>;
    parsedPayload?: unknown;
    protocolType: string;
    route: string;
    registryStatus: string;
    schemaStatus: string;
    runtimeStatus: string;
    frontendStatus: string;
    actionStatus: string;
    entityContextStatus: string;
    errors: string[];
    warnings: string[];
    checklist: RuntimeValidationCheck[];
    preview?: {
        pc?: unknown;
        app?: unknown;
    };
    repairPrompt?: string;
    referenceRenderAssets?: SkillFactoryReferenceAsset[];
}
export interface SkillBindingRecord {
    skillCode: string;
    workspaceId: string;
    userId: string;
    digitalEmployeeId?: string;
    specialistId: string;
    specialistName: string;
    operation: string;
    bindStatus: string;
    adviserResult: string;
    operator: string;
    createTime: number;
}
export interface SkillPublishRecord {
    skillCode: string;
    workspaceId: string;
    publishStage: string;
    publishStatus: string;
    publishResult: unknown;
    operator: string;
    createTime: number;
    publishSourceType?: PublishSourceType;
    sourceLabel?: string;
    sourceVersion?: string;
    compareVersion?: string;
    diffFiles?: ReleaseDiffFile[];
    diffSummary?: ReleaseDiffSummary;
    externalPublishStage?: string;
    message?: string;
    langBridgeSkillId?: string | number;
    langBridgeVersionLabel?: string;
    agentEnv?: 'PRT' | 'PROD';
    runtimeAgentBizKey?: string;
    objectKey?: string;
    packageUrl?: string;
    packageDigest?: string;
}
export interface SkillFactoryCodingEvent {
    recordId?: string;
    eventType: string;
    eventCode?: string;
    schemaVersion?: string;
    category?: string;
    source?: string;
    eventId?: string;
    blockId?: string;
    sessionId: string;
    workspaceId: string;
    messageId?: string;
    runId?: string;
    threadId?: string;
    conversationId?: string;
    surfaceId?: string;
    patchId?: string;

    observationId?: string;
    title?: string;
    content?: Record<string, unknown>;

    observation?: Record<string, unknown>;
    success?: boolean;
    errorMsg?: string;
    timestamp?: number;
    traceId?: string;
    trace_id?: string;
    modelContentBlock?: Record<string, unknown>;
    modelContentBlockJson?: string;
    payloadType?: string;
    payloadJson?: string;
    payload?: Record<string, unknown>;
    toolCallId?: string;
    toolName?: string;
    toolArgs?: unknown;
    toolSuccess?: boolean;
    tokenCount?: number;
    enterTokenCount?: number;
    outputTokenCount?: number;
    answerAgentId?: number;
    invokeId?: string;
    hasKnowledge?: boolean;
}
export interface AuthoringSessionSummary {
    sessionId: string;
    bizKey: string;
    scopeType: string;
    scopeId: string;
    workspaceId?: string;
    title?: string;
    creator?: string;
    lastOperator?: string;
    active?: boolean;
    createTime?: number;
    updateTime?: number;
    lastMessageTime?: number;
    messageCount?: number;
}
export interface AuthoringChatTurn {
    id: string;
    role: 'user' | 'assistant';
    text: string;
    timestamp: number;
    sessionId: string;
    messageId?: string;
    operator?: string;
}
export interface AuthoringSessionHistory {
    bizKey: string;
    scopeType: string;
    scopeId: string;
    workspaceId?: string;
    activeSessionId?: string;
    selectedSessionId?: string;
    sessions?: AuthoringSessionSummary[];
    turns?: AuthoringChatTurn[];
    events?: SkillFactoryCodingEvent[];
    authoringGuideConfig?: AuthoringGuideConfig;
}
export interface AuthoringSessionCreateResult {
    sessionId: string;
}
export type SkillFactoryRunState = '' | 'RUNNING' | 'CANCELLING' | 'CANCELLED' | 'COMPLETED' | 'FAILED';
export interface SkillFactoryRunStatus {
    sessionId: string;
    invokeId: string;
    status: SkillFactoryRunState;
    updateTime: number;
}
export interface SkillFactoryRunIdentity {
    sessionId: string;
    invokeId: string;
}
const TERMINAL_RUN_EVENT_TYPES = new Set([
    'COMPLETED',
    'RUN_COMPLETED',
    'FAILED',
    'RUN_FAILED',
    'RUN_CANCELLED',
]);
export function isTerminalCodingRunEvent(eventType: string): boolean {
    return TERMINAL_RUN_EVENT_TYPES.has(eventType);
}
/** 从历史事件中找到最近一条缺少终态的运行，用于页面刷新后恢复服务端运行状态。 */
export function latestUnfinishedCodingRun(events: SkillFactoryCodingEvent[], fallbackSessionId = ''): SkillFactoryRunIdentity | null {
    const states = new Map<string, {
        identity: SkillFactoryRunIdentity;
        terminal: boolean;
        time: number;
    }>();
    (events || []).forEach((event) => {
        const invokeId = event.invokeId || event.messageId || event.runId || '';
        const sessionId = event.sessionId || fallbackSessionId;
        if (!invokeId || !sessionId)
            return;
        const previous = states.get(invokeId);
        states.set(invokeId, {
            identity: { sessionId, invokeId },
            terminal: Boolean(previous?.terminal || isTerminalCodingRunEvent(event.eventType)),
            time: Math.max(previous?.time || 0, event.timestamp || 0),
        });
    });
    return (Array.from(states.values())
        ?.filter((item) => !item.terminal)
        ?.sort?.((left, right) => right.time - left.time)?.[0]?.identity || null);
}
export function isActiveCodingRun(status?: SkillFactoryRunStatus | null): boolean {
    return status?.status === 'RUNNING' || status?.status === 'CANCELLING';
}
const delay = (milliseconds: number): Promise<void> => new Promise((resolve) => window.setTimeout(resolve, milliseconds));
export interface AuthoringSessionScopeParams {
    bizKey: string;
    scopeType: string;
    scopeId: string;
    workspaceId?: string;
    skillCode?: string;
    componentCode?: string;
    componentName?: string;
    assetId?: string;
    draftId?: string;
    authoringDomain?: string;
    sessionId?: string;
}
export interface SkillFactoryPatchApplyResult {
    success: boolean;
    errorMsg?: string;
    workspaceId: string;
    patchId: string;

    decisionId?: string;
    observationId?: string;
    fileTreeDigest?: string;
    baseFileTreeDigest?: string;
    errorCode?: string;
    changedFiles?: string[];
    conflictFiles?: string[];
}
interface StreamOptions {
    signal?: AbortSignal;
}
interface AdviserBaseResponse {
    code?: number;
    codeName?: string;
    code_name?: string;
    errorMsg?: string;
    error_msg?: string;
    message?: string;
}
interface AdviserSkillBindingResponse {
    baseResponse?: AdviserBaseResponse;
    base_response?: AdviserBaseResponse;
    success?: boolean;
    requestId?: string;
    request_id?: string;
}
export interface SkillBindingParams {
    skillCode: string;
    workspaceId: string;
    userId: string;
    digitalEmployeeId: string;
    specialistName?: string;
}
export interface SpecialistPrtBindingState {
    employeeId: string;
    employeeCode: string;
    employeeName: string;
    skillCode: string;
    versionAction: 'REUSE' | 'CREATE' | 'BLOCKED';
    versionId: string;
    versionLabel: string;
    versionStatus: string;
    containsSkill: boolean;
    prtEffective: boolean;
    blockedReason: string;
    bindingAction?: 'ADDED' | 'ALREADY_PRESENT';
    publishStatus?: 'PRT_EFFECTIVE' | 'PARTIAL';
    failureStage?: string;
    message?: string;
}
interface EventFallback {
    sessionId?: string;
    workspaceId?: string;
    traceId?: string;
    trace_id?: string;
    messageId?: string;
    runId?: string;
    threadId?: string;
    conversationId?: string;
    invokeId?: string;
    invoke_id?: string;
}
const RAW_AGENT_EVENT_TYPES = new Set([
    'STARTED',
    'RUN_STARTED',
    'ANSWER_TEXT_DELTA',
    'THINK_TEXT_DELTA',
    'MODEL_CONTENT_DELTA',
    'MODEL_CONTENT_DONE',
    'TOOL_CALL',
    'TOOL_RESULT',
    'TOOL_CALL_STARTED',
    'TOOL_CALL_FINISHED',
    'ARTIFACT_CREATED',
    'BUSINESS_INTERACTION_CREATED',
    'OBSERVATION_CREATED',
    'STDOUT',
    'STDERR',
    'USAGE',
    'COMPLETED',
    'RUN_COMPLETED',
    'ERROR',
    'FAILED',
    'RUN_FAILED',
    'RUN_CANCELLED',
]);
function normalizeCommon(raw: unknown): SkillFactoryCommonResponse | null {
    if (!raw || typeof raw !== 'object')
        return null;
    const value = raw as Record<string, unknown>;
    if (value.result === undefined)
        return null;
    return value as unknown as SkillFactoryCommonResponse;
}
function parseSseResponse(text: string): SkillFactoryCommonResponse {
    const lines = text.split(/\r?\n/);
    for (const line of lines) {
        if (!line.startsWith('data:'))
            continue;
        const payload = line?.replace(/^data:\s?/, '')?.trim?.();
        if (!payload || payload === '[DONE]')
            continue;
        const parsed = jsonParse(payload, null);
        const common = normalizeCommon(parsed);
        if (common)
            return common;
    }
    const direct = normalizeCommon(jsonParse(text, null));
    if (direct)
        return direct;
    throw new Error('SkillFactory 返回格式异常');
}
function parseData<T>(response: SkillFactoryCommonResponse): T {
    const result = Number(response.result);
    if (result !== SUCCESS_RESULT) {
        throw new Error(response.errorMsg || response.error_msg || 'SkillFactory 请求失败');
    }
    const data = response.data;
    const isList = Boolean(response.isList ?? response.is_list);
    if (typeof data === 'string') {
        const text = data.trim();
        if (!text)
            return (isList ? [] : {}) as T;
        return jsonParse(text, isList ? [] : {}) as T;
    }
    if (data === undefined || data === null) {
        return (isList ? [] : {}) as T;
    }
    return data as T;
}
function stringifyRequestBody(method: string, params: object): string {
    return jsonStringify({ method, params }) || '{}';
}
function stringifyDirectBody(params: object): string {
    return jsonStringify(params) || '{}';
}
export async function callSkillFactory<T>(method: SkillFactoryMethodCode, params: object = {}): Promise<T> {
    assertManualManagementMethod(method);
    const response = await fetch(BASE_URL, {
        method: 'POST',
        credentials: 'include',
        headers: {
            Accept: 'text/event-stream',
            'Content-Type': 'application/json',
        },
        body: stringifyRequestBody(method, params),
    });
    if (!response.ok) {
        throw new Error(`SkillFactory 请求失败: ${response.status}`);
    }
    const text = await response.text();
    return parseData<T>(parseSseResponse(text));
}
export async function callSkillFactoryBizRender<T>(method: SkillFactoryMethodCode, params: object = {}): Promise<T> {
    assertManualManagementMethod(method);
    const response = await fetch(BIZ_RENDER_URL, {
        method: 'POST',
        credentials: 'include',
        headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
        },
        body: stringifyRequestBody(method, params),
    });
    if (!response.ok) {
        throw new Error(`SkillFactory 渲染请求失败: ${response.status}`);
    }
    const parsed = jsonParse(await response.text(), null);
    const common = normalizeCommon(parsed);
    if (common) {
        return parseData<T>(common);
    }
    return parsed as T;
}
function parseSsePayload(payload: string): unknown | null {
    const trimmed = payload.trim();
    if (!trimmed || trimmed === '[DONE]')
        return null;
    return jsonParse(trimmed, null);
}
function recordOf(value: unknown): Record<string, unknown> | null {
    if (!value || typeof value !== 'object' || Array.isArray(value))
        return null;
    return value as Record<string, unknown>;
}
function stringOf(value: unknown): string {
    if (value === undefined || value === null)
        return '';
    return String(value);
}
function numberOf(value: unknown): number | undefined {
    if (typeof value === 'number')
        return value;
    if (typeof value === 'string' && value.trim()) {
        const num = Number(value);
        return Number.isFinite(num) ? num : undefined;
    }
    return undefined;
}
function baseResponseOf(response: AdviserSkillBindingResponse): AdviserBaseResponse {
    const baseResponse = response.baseResponse || response.base_response || {};
    return {
        code: numberOf(baseResponse.code),
        codeName: stringOf(baseResponse.codeName || baseResponse.code_name),
        errorMsg: stringOf(baseResponse.errorMsg || baseResponse.error_msg),
        message: stringOf(baseResponse.message),
    };
}
function skillBindingEndpoint(action: SkillBindingActionCode): string {
    return action === SkillBindingAction.ADD ? SKILL_BINDING_ADD_URL : SKILL_BINDING_REMOVE_URL;
}
function skillBindingResultText(response: AdviserSkillBindingResponse, baseResponse: AdviserBaseResponse): string {
    const requestId = stringOf(response.requestId || response.request_id);
    return [
        baseResponse.errorMsg,
        baseResponse.message,
        baseResponse.codeName,
        requestId ? `requestId=${requestId}` : '',
    ]
        ?.filter(Boolean)
        ?.join?.('，');
}
async function callSkillBinding(action: SkillBindingActionCode, params: SkillBindingParams): Promise<SkillBindingRecord> {
    const response = await fetch(skillBindingEndpoint(action), {
        method: 'POST',
        credentials: 'include',
        headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
        },
        body: stringifyDirectBody({
            userId: params.userId,
            digitalEmployeeId: Number(params.digitalEmployeeId),
            skills: [
                {
                    skillCode: params.skillCode,
                    source: SKILL_BINDING_SOURCE,
                },
            ],
        }),
    });
    if (!response.ok) {
        throw new Error(`Skill 绑定请求失败: ${response.status}`);
    }
    const parsed = jsonParse(await response.text(), {}) as AdviserSkillBindingResponse;
    const baseResponse = baseResponseOf(parsed);
    const success = parsed.success === true &&
        (baseResponse.code === SUCCESS_RESULT || baseResponse.code === undefined);
    const resultText = skillBindingResultText(parsed, baseResponse);
    if (!success) {
        throw new Error(resultText || 'Skill 绑定请求失败');
    }
    return {
        skillCode: params.skillCode,
        workspaceId: params.workspaceId,
        userId: params.userId,
        digitalEmployeeId: params.digitalEmployeeId,
        specialistId: params.digitalEmployeeId,
        specialistName: params.specialistName || '',
        operation: action,
        bindStatus: 'SUCCESS',
        adviserResult: resultText || '操作成功',
        operator: '',
        createTime: Date.now(),
    };
}
function booleanOf(value: unknown): boolean {
    return value === true || value === 1 || value === '1' || value === 'true';
}
function normalizeSpecialistPrtBindingState(value: Record<string, unknown>): SpecialistPrtBindingState {
    const blockedReason = stringOf(value.blockedReason || value.blocked_reason);
    const rawAction = stringOf(value.versionAction || value.version_action);
    const versionAction = blockedReason
        ? 'BLOCKED'
        : rawAction === 'REUSE' || rawAction === 'REUSED'
            ? 'REUSE'
            : rawAction === 'CREATE' || rawAction === 'CREATED'
                ? 'CREATE'
                : 'BLOCKED';
    const bindingAction = stringOf(value.bindingAction || value.binding_action);
    const publishStatus = stringOf(value.publishStatus || value.publish_status);
    return {
        employeeId: stringOf(value.employeeId || value.employee_id),
        employeeCode: stringOf(value.employeeCode || value.employee_code),
        employeeName: stringOf(value.employeeName || value.employee_name),
        skillCode: stringOf(value.skillCode || value.skill_code),
        versionAction,
        versionId: stringOf(value.versionId || value.version_id),
        versionLabel: stringOf(value.versionLabel || value.version_label),
        versionStatus: stringOf(value.versionStatus || value.version_status),
        containsSkill: booleanOf(value.containsSkill ?? value.contains_skill),
        prtEffective: booleanOf(value.prtEffective ?? value.prt_effective),
        blockedReason,
        bindingAction: bindingAction === 'ADDED' || bindingAction === 'ALREADY_PRESENT' ? bindingAction : undefined,
        publishStatus: publishStatus === 'PRT_EFFECTIVE' || publishStatus === 'PARTIAL' ? publishStatus : undefined,
        failureStage: stringOf(value.failureStage || value.failure_stage),
        message: stringOf(value.message),
    };
}
async function callSpecialistPrtBinding(url: string, body: Record<string, unknown>): Promise<SpecialistPrtBindingState> {
    const response = await fetch(url, {
        method: 'POST',
        credentials: 'include',
        headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
        },
        body: stringifyDirectBody(body),
    });
    if (!response.ok) {
        throw new Error(`专员 PRT 绑定请求失败: ${response.status}`);
    }
    const binding = parseData<Record<string, unknown>>(parseSseResponse(await response.text()));
    return normalizeSpecialistPrtBindingState(binding);
}
function parseRecord(value: unknown): Record<string, unknown> | null {
    if (typeof value === 'string') {
        return recordOf(jsonParse(value, null));
    }
    return recordOf(value);
}
function contentFromNestedEvent(record: Record<string, unknown>): Record<string, unknown> {
    const nestedContent = recordOf(record.content);
    if (nestedContent)
        return nestedContent;
    return Object.entries(record).reduce<Record<string, unknown>>((acc, [key, value]) => {
        if (key !== 'eventType' &&
            key !== 'eventCode' &&
            key !== 'schemaVersion' &&
            key !== 'category' &&
            key !== 'sessionId' &&
            key !== 'workspaceId' &&
            key !== 'messageId' &&
            key !== 'runId' &&
            key !== 'threadId' &&
            key !== 'conversationId' &&
            key !== 'surfaceId' &&
            key !== 'patchId' &&
            key !== 'approvalId' &&
            key !== 'observationId' &&
            key !== 'title' &&
            key !== 'timestamp' &&
            key !== 'traceId' &&
            key !== 'trace_id' &&
            key !== 'approval' &&
            key !== 'observation' &&
            key !== 'modelContentBlock' &&
            key !== 'modelContentBlockJson' &&
            key !== 'payload' &&
            key !== 'payloadType' &&
            key !== 'payloadJson') {
            acc[key] = value;
        }
        return acc;
    }, {});
}
function isRawAgentEvent(record: Record<string, unknown>): boolean {
    const eventType = stringOf(record.eventType || record.type);
    if (!RAW_AGENT_EVENT_TYPES.has(eventType))
        return false;
    return (typeof record.content === 'string' ||
        'toolCallId' in record ||
        'toolName' in record ||
        'toolArgs' in record ||
        'toolSuccess' in record ||
        'answerAgentId' in record ||
        'tokenCount' in record);
}
function normalizeNestedCodingEvent(record: Record<string, unknown>, fallback: EventFallback): SkillFactoryCodingEvent | null {
    const eventType = stringOf(record.eventType || record.eventCode);
    if (!eventType)
        return null;
    const traceId = stringOf(record.traceId || record.trace_id || fallback.traceId);
    const messageId = stringOf(record.messageId ||
        record.invokeId ||
        record.invoke_id ||
        fallback.messageId ||
        fallback.invokeId ||
        fallback.invoke_id ||
        fallback.runId);
    const runId = stringOf(record.runId || record.invokeId || record.invoke_id || fallback.runId || messageId);
    const conversationId = stringOf(record.conversationId || fallback.conversationId || fallback.sessionId);
    return {
        recordId: stringOf(record.recordId) || undefined,
        eventType,
        eventCode: stringOf(record.eventCode || eventType) || undefined,
        schemaVersion: stringOf(record.schemaVersion) || undefined,
        category: stringOf(record.category) || undefined,
        sessionId: stringOf(record.sessionId || fallback.sessionId),
        workspaceId: stringOf(record.workspaceId || fallback.workspaceId),
        messageId: messageId || undefined,
        runId: runId || undefined,
        threadId: stringOf(record.threadId || fallback.threadId || fallback.sessionId) || undefined,
        conversationId: conversationId || undefined,
        surfaceId: stringOf(record.surfaceId) || undefined,
        patchId: stringOf(record.patchId) || undefined,

        observationId: stringOf(record.observationId) || undefined,
        title: stringOf(record.title) || undefined,
        content: contentFromNestedEvent(record),

        observation: recordOf(record.observation) || undefined,
        success: typeof record.success === 'boolean' ? record.success : undefined,
        errorMsg: stringOf(record.errorMsg || record.error_msg) || undefined,
        timestamp: numberOf(record.timestamp) || Date.now(),
        traceId: traceId || undefined,
        trace_id: traceId || undefined,
        toolCallId: stringOf(record.toolCallId) || undefined,
        toolName: stringOf(record.toolName) || undefined,
        toolArgs: parseRecord(record.toolArgs) || record.toolArgs,
        toolSuccess: typeof record.toolSuccess === 'boolean'
            ? record.toolSuccess
            : typeof record.success === 'boolean'
                ? record.success
                : undefined,
        tokenCount: numberOf(record.tokenCount) || undefined,
        enterTokenCount: numberOf(record.enterTokenCount) || undefined,
        outputTokenCount: numberOf(record.outputTokenCount) || undefined,
        answerAgentId: numberOf(record.answerAgentId) || undefined,
        invokeId: stringOf(record.invokeId || record.invoke_id) || undefined,
        hasKnowledge: typeof record.hasKnowledge === 'boolean' ? record.hasKnowledge : undefined,
    };
}
function payloadRecordOf(record: Record<string, unknown>): Record<string, unknown> | null {
    return recordOf(record.payload) || parseRecord(record.payloadJson);
}
function isStructuredStreamEnvelope(record: Record<string, unknown>): boolean {
    return (stringOf(record.schemaVersion) === 'skill-factory.agent-stream-event/v1' ||
        Boolean(record.modelContentBlock) ||
        Boolean(record.modelContentBlockJson) ||
        Boolean(record.payloadType) ||
        Boolean(record.payloadJson));
}
function normalizeStructuredStreamEvent(record: Record<string, unknown>, fallback: EventFallback): SkillFactoryCodingEvent | null {
    if (!isStructuredStreamEnvelope(record))
        return null;
    const eventType = stringOf(record.eventType || record.type);
    if (!eventType)
        return null;
    const payload = payloadRecordOf(record) || undefined;
    const modelContentBlock = recordOf(record.modelContentBlock) || parseRecord(record.modelContentBlockJson) || undefined;
    const traceId = stringOf(record.traceId || record.trace_id || fallback.traceId);
    const messageId = stringOf(record.messageId ||
        fallback.messageId ||
        fallback.invokeId ||
        fallback.invoke_id ||
        fallback.runId);
    const runId = stringOf(record.runId || fallback.runId || messageId);
    const payloadContent = payload ? contentFromNestedEvent(payload) : {};
    const toolCallId = stringOf(record.toolCallId ||
        payload?.toolCallId ||
        payloadContent.toolCallId ||
        modelContentBlock?.toolCallId);
    const toolName = stringOf(record.toolName ||
        payload?.toolName ||
        payloadContent.toolName ||
        payloadContent.toolCallName ||
        modelContentBlock?.toolName);
    const toolArgs = modelContentBlock?.toolArgs ||
        payload?.toolArgs ||
        payloadContent.toolArgs ||
        parseRecord(record.toolArgs) ||
        record.toolArgs;
    const toolSuccess = typeof record.toolSuccess === 'boolean'
        ? record.toolSuccess
        : typeof payload?.toolSuccess === 'boolean'
            ? payload.toolSuccess
            : typeof payload?.success === 'boolean'
                ? payload.success
                : typeof record.success === 'boolean'
                    ? record.success
                    : undefined;
    let content: Record<string, unknown> = payloadContent;
    const blockType = stringOf(modelContentBlock?.type);
    if (modelContentBlock) {
        if (blockType === 'TEXT' || blockType === 'THINKING') {
            content = {
                ...payloadContent,
                text: stringOf(modelContentBlock.text || modelContentBlock.content || record.content),
                modelContentBlock,
            };
        }
        else if (blockType === 'TOOL_USE') {
            content = {
                ...payloadContent,
                toolCallId,
                toolName,
                toolArgs,
                modelContentBlock,
            };
        }
    }
    else if (!Object.keys(content).length) {
        content = parseRecord(record.content) || {
            text: stringOf(record.content),
        };
    }
    return {
        recordId: stringOf(record.recordId) || undefined,
        eventType,
        eventCode: stringOf(payload?.eventCode || record.eventCode || eventType) || undefined,
        schemaVersion: stringOf(record.schemaVersion || payload?.schemaVersion) || undefined,
        category: stringOf(payload?.category || record.category) || undefined,
        source: stringOf(record.source) || undefined,
        eventId: stringOf(record.eventId) || undefined,
        blockId: stringOf(record.blockId || modelContentBlock?.blockId) || undefined,
        sessionId: stringOf(payload?.sessionId || record.threadId || fallback.sessionId),
        workspaceId: stringOf(payload?.workspaceId || fallback.workspaceId),
        messageId: messageId || undefined,
        runId: runId || undefined,
        threadId: stringOf(record.threadId || payload?.threadId || fallback.threadId || fallback.sessionId) ||
            undefined,
        conversationId: stringOf(record.conversationId ||
            payload?.conversationId ||
            fallback.conversationId ||
            fallback.sessionId) || undefined,
        surfaceId: stringOf(payload?.surfaceId || record.surfaceId) || undefined,
        patchId: stringOf(payload?.patchId || record.patchId) || undefined,

        observationId: stringOf(payload?.observationId || record.observationId) || undefined,
        title: stringOf(payload?.title || record.title) || undefined,
        content,

        observation: recordOf(payload?.observation) || recordOf(record.observation) || undefined,
        success: typeof payload?.success === 'boolean'
            ? payload.success
            : typeof record.success === 'boolean'
                ? record.success
                : undefined,
        errorMsg: stringOf(payload?.errorMsg || record.errorMsg || record.error_msg) || undefined,
        timestamp: numberOf(record.timestamp || payload?.timestamp) || Date.now(),
        traceId: traceId || undefined,
        trace_id: traceId || undefined,
        modelContentBlock,
        modelContentBlockJson: stringOf(record.modelContentBlockJson) || undefined,
        payloadType: stringOf(record.payloadType) || undefined,
        payloadJson: stringOf(record.payloadJson) || undefined,
        payload,
        toolCallId: toolCallId || undefined,
        toolName: toolName || undefined,
        toolArgs,
        toolSuccess,
        tokenCount: numberOf(record.tokenCount || payload?.tokenCount) || undefined,
        enterTokenCount: numberOf(record.enterTokenCount || payload?.enterTokenCount) || undefined,
        outputTokenCount: numberOf(record.outputTokenCount || payload?.outputTokenCount) || undefined,
        answerAgentId: numberOf(record.answerAgentId || payload?.answerAgentId) || undefined,
        invokeId: stringOf(record.invokeId || record.invoke_id || payload?.invokeId) || undefined,
        hasKnowledge: typeof record.hasKnowledge === 'boolean'
            ? record.hasKnowledge
            : typeof payload?.hasKnowledge === 'boolean'
                ? payload.hasKnowledge
                : undefined,
    };
}
function normalizeInvokeEvent(record: Record<string, unknown>, fallback: EventFallback): SkillFactoryCodingEvent | null {
    const directStructuredEvent = normalizeStructuredStreamEvent(record, fallback);
    if (directStructuredEvent) {
        return directStructuredEvent;
    }
    const eventType = stringOf(record.eventType || record.type);
    if (!eventType)
        return null;
    const nextFallback = {
        sessionId: stringOf(record.sessionId || fallback.sessionId),
        workspaceId: stringOf(record.workspaceId || fallback.workspaceId),
        traceId: stringOf(record.traceId || record.trace_id || fallback.traceId),
        messageId: stringOf(record.messageId || record.invokeId || record.invoke_id || fallback.messageId),
        runId: stringOf(record.runId || record.invokeId || record.invoke_id || fallback.runId),
        threadId: stringOf(record.threadId || fallback.threadId),
        conversationId: stringOf(record.conversationId || fallback.conversationId),
    };
    const contentRecord = parseRecord(record.content);
    const structuredEvent = contentRecord
        ? normalizeStructuredStreamEvent(contentRecord, nextFallback)
        : null;
    if (structuredEvent) {
        return structuredEvent;
    }
    const nestedEvent = contentRecord
        ? normalizeNestedCodingEvent(contentRecord, nextFallback)
        : null;
    if (nestedEvent && (eventType === 'TOOL_RESULT' || eventType === 'ERROR')) {
        return nestedEvent;
    }
    const traceId = stringOf(record.traceId || record.trace_id || fallback.traceId);
    const messageId = stringOf(nextFallback.messageId || nextFallback.runId || nextFallback.sessionId);
    const runId = stringOf(nextFallback.runId || messageId);
    const timestamp = numberOf(record.timestamp) || Date.now();
    if (eventType === 'ANSWER_TEXT_DELTA' || eventType === 'THINK_TEXT_DELTA') {
        return {
            eventType,
            sessionId: nextFallback.sessionId,
            workspaceId: nextFallback.workspaceId,
            messageId: messageId || undefined,
            runId: runId || undefined,
            threadId: nextFallback.threadId || nextFallback.sessionId || undefined,
            conversationId: nextFallback.conversationId || nextFallback.sessionId || undefined,
            content: { text: stringOf(record.content) },
            timestamp,
            traceId: traceId || undefined,
            trace_id: traceId || undefined,
        };
    }
    if (eventType === 'ERROR' || eventType === 'FAILED' || eventType === 'RUN_FAILED') {
        return {
            eventType,
            eventCode: eventType,
            sessionId: nextFallback.sessionId,
            workspaceId: nextFallback.workspaceId,
            messageId: messageId || undefined,
            runId: runId || undefined,
            threadId: nextFallback.threadId || nextFallback.sessionId || undefined,
            conversationId: nextFallback.conversationId || nextFallback.sessionId || undefined,
            content: { errorMsg: stringOf(record.content || record.errorMsg || record.error_msg) },
            errorMsg: stringOf(record.content || record.errorMsg || record.error_msg),
            timestamp,
            traceId: traceId || undefined,
            trace_id: traceId || undefined,
        };
    }
    if (eventType === 'TOOL_CALL') {
        return {
            eventType,
            sessionId: nextFallback.sessionId,
            workspaceId: nextFallback.workspaceId,
            messageId: messageId || undefined,
            runId: runId || undefined,
            threadId: nextFallback.threadId || nextFallback.sessionId || undefined,
            conversationId: nextFallback.conversationId || nextFallback.sessionId || undefined,
            content: {
                toolCallId: stringOf(record.toolCallId),
                toolName: stringOf(record.toolName),
                toolArgs: parseRecord(record.toolArgs) || stringOf(record.toolArgs),
            },
            toolCallId: stringOf(record.toolCallId) || undefined,
            toolName: stringOf(record.toolName) || undefined,
            toolArgs: parseRecord(record.toolArgs) || stringOf(record.toolArgs),
            timestamp,
            traceId: traceId || undefined,
            trace_id: traceId || undefined,
        };
    }
    if (eventType === 'TOOL_RESULT') {
        return {
            eventType,
            sessionId: nextFallback.sessionId,
            workspaceId: nextFallback.workspaceId,
            messageId: messageId || undefined,
            runId: runId || undefined,
            threadId: nextFallback.threadId || nextFallback.sessionId || undefined,
            conversationId: nextFallback.conversationId || nextFallback.sessionId || undefined,
            content: {
                toolCallId: stringOf(record.toolCallId),
                toolName: stringOf(record.toolName),
                toolSuccess: Boolean(record.toolSuccess || record.success),
                result: contentRecord || stringOf(record.content),
            },
            toolCallId: stringOf(record.toolCallId) || undefined,
            toolName: stringOf(record.toolName) || undefined,
            toolSuccess: Boolean(record.toolSuccess || record.success),
            timestamp,
            traceId: traceId || undefined,
            trace_id: traceId || undefined,
        };
    }
    return {
        eventType,
        sessionId: nextFallback.sessionId,
        workspaceId: nextFallback.workspaceId,
        messageId: messageId || undefined,
        runId: runId || undefined,
        threadId: nextFallback.threadId || nextFallback.sessionId || undefined,
        conversationId: nextFallback.conversationId || nextFallback.sessionId || undefined,
        surfaceId: stringOf(record.surfaceId) || undefined,
        patchId: stringOf(record.patchId) || undefined,

        observationId: stringOf(record.observationId) || undefined,
        title: stringOf(record.title) || undefined,
        content: contentRecord || (typeof record.content === 'string' ? { text: record.content } : {}),

        observation: recordOf(record.observation) || undefined,
        success: typeof record.success === 'boolean' ? record.success : undefined,
        errorMsg: stringOf(record.errorMsg || record.error_msg) || undefined,
        timestamp,
        traceId: traceId || undefined,
        trace_id: traceId || undefined,
    };
}
function normalizeCodingEvent(record: Record<string, unknown>, fallback: EventFallback): SkillFactoryCodingEvent | null {
    const structuredEvent = normalizeStructuredStreamEvent(record, fallback);
    if (structuredEvent) {
        return structuredEvent;
    }
    if (isRawAgentEvent(record)) {
        return normalizeInvokeEvent(record, fallback) || normalizeNestedCodingEvent(record, fallback);
    }
    return normalizeNestedCodingEvent(record, fallback) || normalizeInvokeEvent(record, fallback);
}
function normalizeReplayEvent(event: unknown, fallback: EventFallback): SkillFactoryCodingEvent | null {
    const record = recordOf(event);
    if (!record)
        return null;
    return normalizeCodingEvent(record, fallback);
}
function normalizeAuthoringSessionHistory(history: AuthoringSessionHistory): AuthoringSessionHistory {
    const fallback: EventFallback = {
        sessionId: stringOf(history.selectedSessionId || history.activeSessionId),
        workspaceId: stringOf(history.workspaceId || history.scopeId),
        conversationId: stringOf(history.selectedSessionId || history.activeSessionId),
        threadId: stringOf(history.selectedSessionId || history.activeSessionId),
    };
    return {
        ...history,
        sessions: [...(history.sessions || [])].sort((left, right) => Number(right.lastMessageTime || right.updateTime || 0) -
            Number(left.lastMessageTime || left.updateTime || 0)),
        turns: history.turns || [],
        events: (history.events || [])
            .map((event) => normalizeReplayEvent(event, fallback))
            .filter(Boolean) as SkillFactoryCodingEvent[],
    };
}
function normalizeAuthoringSessionCreateResult(result: AuthoringSessionCreateResult): AuthoringSessionCreateResult {
    return {
        sessionId: stringOf(result?.sessionId),
    };
}
function emitCommonDataEvents(common: SkillFactoryCommonResponse, fallback: EventFallback, onEvent: (event: SkillFactoryCodingEvent) => void) {
    const parsedData = parseData<unknown>(common);
    if (!parsedData)
        return;
    const items = Array.isArray(parsedData) ? parsedData : [parsedData];
    items.forEach((item) => {
        const record = recordOf(item);
        if (!record)
            return;
        const event = normalizeCodingEvent(record, fallback);
        if (event)
            onEvent(event);
    });
}
function handleSsePayload(payload: string, fallback: EventFallback, onEvent: (event: SkillFactoryCodingEvent) => void) {
    const parsed = parseSsePayload(payload);
    if (!parsed)
        return;
    const common = normalizeCommon(parsed);
    if (common) {
        if (Number(common.result) !== SUCCESS_RESULT) {
            throw new Error(common.errorMsg || common.error_msg || 'SkillFactory 请求失败');
        }
        emitCommonDataEvents(common, fallback, onEvent);
        return;
    }
    const record = recordOf(parsed);
    if (!record)
        return;
    const event = normalizeCodingEvent(record, fallback);
    if (event)
        onEvent(event);
}
function consumeSseText(text: string, fallback: EventFallback, onEvent: (event: SkillFactoryCodingEvent) => void) {
    text?.split(/\r?\n\r?\n/)?.forEach?.((block) => {
        const payload = block
            ?.split(/\r?\n/)
            ?.filter?.((line) => line.startsWith('data:'))
            ?.map?.((line) => line.replace(/^data:\s?/, ''))
            ?.join?.('\n');
        handleSsePayload(payload, fallback, onEvent);
    });
}
export async function streamSkillFactoryEvents(params: object, onEvent: (event: SkillFactoryCodingEvent) => void, options: StreamOptions = {}): Promise<void> {
    assertManualManagementMethod('CODING_CHAT');
    const fallback = params as EventFallback;
    const response = await fetch(CHAT_URL, {
        method: 'POST',
        credentials: 'include',
        headers: {
            Accept: 'text/event-stream',
            'Content-Type': 'application/json',
        },
        body: stringifyDirectBody(params),
        signal: options.signal,
    });
    if (!response.ok) {
        throw new Error(`SkillFactory 请求失败: ${response.status}`);
    }
    if (!response.body) {
        consumeSseText(await response.text(), fallback, onEvent);
        return;
    }
    const reader = response.body?.getReader?.();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let reading = true;
    while (reading) {
        const { done, value } = await reader.read();
        if (done) {
            reading = false;
            continue;
        }
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() || '';
        blocks.forEach((block) => consumeSseText(`${block}\n\n`, fallback, onEvent));
    }
    buffer += decoder.decode();
    if (buffer.trim())
        consumeSseText(buffer, fallback, onEvent);
}
export interface SkillListQuery {
    keyword?: string;
    businessDomain?: string;
    capabilityDomain?: string;
    specialistId?: string;
    status?: string;
    page: number;
    pageSize: number;
}
export interface SkillListPage {
    list: SkillDraft[];
    total: number;
    page: number;
    pageSize: number;
    editingCount: number;
    onlineCount: number;
}
export const skillFactoryApi = {
    config: () => callSkillFactory<SkillFactoryPageConfig>(SkillFactoryMethod.SKILL_FACTORY_CONFIG, {}),
    list: (query: SkillListQuery) => callSkillFactory<SkillListPage>(SkillFactoryMethod.SKILL_LIST, query),
    detail: (skillCode: string) => callSkillFactory<SkillDraft>(SkillFactoryMethod.SKILL_DETAIL, { skillCode }),
    saveSkillInfo: (payload: SkillInfoPayload) => callSkillFactory<SkillDraft>(SkillFactoryMethod.WORKSPACE_CREATE, payload),
    updateSkillInfo: (payload: SkillInfoUpdatePayload) => callSkillFactory<SkillDraft>(SkillFactoryMethod.SKILL_UPDATE, payload),
    importZip: (skillCode: string, zipFileName: string, zipBase64: string) => callSkillFactory<ZipImportResult>(SkillFactoryMethod.ZIP_CONFIRM_IMPORT, {
        skillCode,
        zipFileName,
        zipBase64,
    }),
    workspaceTree: (workspaceId: string, viewParams: WorkspaceViewParams = {}) => callSkillFactory<WorkspaceTreeResult>(SkillFactoryMethod.WORKSPACE_TREE, {
        workspaceId,
        ...viewParams,
    }),
    fileContent: (workspaceId: string, filePath: string, viewParams: WorkspaceViewParams = {}) => callSkillFactory<WorkspaceFileContent>(SkillFactoryMethod.WORKSPACE_FILE_CONTENT, {
        workspaceId,
        filePath,
        ...viewParams,
    }),
    exportWorkspaceZip: (workspaceId: string, viewParams: WorkspaceViewParams = {}) => callSkillFactory<WorkspaceZipExportResult>(SkillFactoryMethod.WORKSPACE_ZIP_EXPORT, {
        workspaceId,
        ...viewParams,
    }),
    saveFile: (workspaceId: string, skillCode: string, filePath: string, content: string) => callSkillFactory<WorkspaceFileContent>(SkillFactoryMethod.WORKSPACE_FILE_SAVE, {
        workspaceId,
        skillCode,
        filePath,
        content,
    }),
    deleteWorkspacePath: (workspaceId: string, filePath: string) => callSkillFactory<WorkspaceTreeResult>(SkillFactoryMethod.WORKSPACE_PATH_DELETE, {
        workspaceId,
        filePath,
    }),
    resetWorkspaceFromSource: (workspaceId: string, source: WorkspaceResetSource) => callSkillFactory<WorkspaceTreeResult>(SkillFactoryMethod.WORKSPACE_RESET_FROM_VERSION, {
        workspaceId,
        sourceType: source.sourceType,
        sourceId: source.sourceId,
    }),
    saveWorkspace: (workspaceId: string, skillCode: string) => callSkillFactory<WorkspaceTreeResult>(SkillFactoryMethod.WORKSPACE_SAVE, {
        workspaceId,
        skillCode,
    }),
    extractRenderSample: (workspaceId: string) => callSkillFactory<RenderSampleResult>(SkillFactoryMethod.WORKSPACE_RENDER_SAMPLE_EXTRACT, {
        workspaceId,
    }),
    replaceBindings: (workspaceId: string, skillCode: string, version: number, capabilityBindings: SkillFactoryCapabilityBinding[], componentBindings: SkillFactoryComponentBinding[]) => callSkillFactory<{
        workspaceId: string;
        skillCode: string;
        version: number;
        capabilityBindings: SkillFactoryCapabilityBinding[];
        componentBindings: SkillFactoryComponentBinding[];
        referenceCapabilities: SkillFactoryCapabilityBinding[];
        referenceCapabilityDraftIds: string[];
        referenceRenderAssets: SkillFactoryReferenceAsset[];
        referenceComponentCodes: string;
        updateTime?: number;
    }>(SkillFactoryMethod.SKILL_BINDINGS_REPLACE, {
        workspaceId,
        skillCode,
        version,
        capabilityBindings: jsonStringify(capabilityBindings) || '[]',
        componentBindings: jsonStringify(componentBindings) || '[]',
    }),
    capabilitySkillCreatorContext: (workspaceId: string, draftId: string, revision: number) => callSkillFactory<CapabilitySkillCreatorContext>(SkillFactoryMethod.CAPABILITY_SKILL_CREATOR_CONTEXT, {
        workspaceId,
        draftId,
        revision,
    }),
    runtimeValidate: (workspaceId: string, skillCode: string, params: {
        sampleSource: string;
        filePath?: string;
        samplePayload?: string;
        referenceRenderAssets?: SkillFactoryReferenceAsset[];
    }) => callSkillFactory<RuntimeValidationResult>(SkillFactoryMethod.RUNTIME_VALIDATE, {
        workspaceId,
        skillCode,
        sampleSource: params.sampleSource,
        filePath: params.filePath || '',
        samplePayload: params.samplePayload || '',
        referenceRenderAssets: jsonStringify(params.referenceRenderAssets || []) || '[]',
    }),
    bindSkill: (action: SkillBindingActionCode, params: SkillBindingParams) => callSkillBinding(action, params),
    querySpecialistPrtBinding: (employeeId: string, skillCode: string, operator: string) => {
        const request = buildSpecialistPrtBindingRequest('QUERY', employeeId, skillCode, operator);
        return callSpecialistPrtBinding(request.path, request.body);
    },
    ensureSpecialistPrtBinding: (employeeId: string, skillCode: string, operator: string) => {
        const request = buildSpecialistPrtBindingRequest('PUBLISH', employeeId, skillCode, operator);
        return callSpecialistPrtBinding(request.path, request.body);
    },
    releaseOptions: (workspaceId: string) => callSkillFactory<ReleaseVersionOptions>(SkillFactoryMethod.PACKAGE_RELEASE_OPTIONS, {
        workspaceId,
    }),
    onlinePublishDiff: (workspaceId: string, params: OnlinePublishParams) => callSkillFactory<OnlinePublishDiffResult>(SkillFactoryMethod.PACKAGE_ONLINE_PUBLISH_DIFF, {
        workspaceId,
        ...params,
    }),
    releaseAction: (method: SkillFactoryMethodCode, params: Record<string, unknown>) => callSkillFactory<SkillPublishRecord | WorkspaceTreeResult>(method, params),
    streamCodingChat: (params: Record<string, unknown>, onEvent: (event: SkillFactoryCodingEvent) => void, options?: StreamOptions) => streamSkillFactoryEvents(params, onEvent, options),
    codingPatchAction: (action: typeof SkillFactoryMethod.CODING_PATCH_CONFIRM | typeof SkillFactoryMethod.CODING_PATCH_DISCARD, params: Record<string, string>) => callSkillFactory<SkillFactoryPatchApplyResult>(action, params),
    streamAuthoringAction: (params: Record<string, unknown>, onEvent: (event: SkillFactoryCodingEvent) => void, options?: StreamOptions) => streamSkillFactoryEvents({
        ...params,
        action: SkillFactoryMethod.AUTHORING_UI_ACTION,
        message: '处理业务卡片操作',
    }, onEvent, options),
    authoringSessionHistory: (params: AuthoringSessionScopeParams) => callSkillFactory<AuthoringSessionHistory>(SkillFactoryMethod.AUTHORING_SESSION_HISTORY, params).then(normalizeAuthoringSessionHistory),
    authoringSessionCreate: (params: AuthoringSessionScopeParams) => callSkillFactory<AuthoringSessionCreateResult>(SkillFactoryMethod.AUTHORING_SESSION_CREATE, params).then(normalizeAuthoringSessionCreateResult),
    codingRunStatus: (sessionId: string, invokeId: string) => callSkillFactory<SkillFactoryRunStatus>(SkillFactoryMethod.CODING_RUN_STATUS, {
        sessionId,
        invokeId,
    }),
    codingRunCancel: (sessionId: string, invokeId: string) => callSkillFactory<SkillFactoryRunStatus>(SkillFactoryMethod.CODING_RUN_CANCEL, {
        sessionId,
        invokeId,
    }),
    waitCodingRunTerminal: async (sessionId: string, invokeId: string, timeoutMs = 10000, intervalMs = 300): Promise<SkillFactoryRunStatus> => {
        const deadline = Date.now() + timeoutMs;
        let status = await skillFactoryApi.codingRunStatus(sessionId, invokeId);
        while (isActiveCodingRun(status) && Date.now() < deadline) {
            await delay(intervalMs);
            status = await skillFactoryApi.codingRunStatus(sessionId, invokeId);
        }
        return status;
    },
};
const compact = (payload: object): Record<string, unknown> => Object.entries(payload).reduce<Record<string, unknown>>((acc, [key, value]) => {
    if (value !== undefined && value !== null && value !== '' && value !== 'ALL') {
        acc[key] = value;
    }
    return acc;
}, {});
const releaseRequestId = (action: string): string => `${action}-${Date.now()}-${Math.random()?.toString(16)?.slice?.(2)}`;
const releaseDeploymentRequestId = (assetKey: string, version: number, digest: string, environment: ReleaseEnvironment): string => `${assetKey}:${version}:${digest}:${environment}`;
const grayReleaseRequestId = (assetType: ReleaseAssetType, assetKey: string, environment: ReleaseEnvironment, sourceIdentity: string, digest: string, action: string, ruleIdentity?: string): string => [assetType, assetKey, environment, sourceIdentity, digest, action, ruleIdentity]
    ?.filter(Boolean)
    ?.join?.(':');
export const assetReleaseApi = {
    overview: (assetType: ReleaseAssetType, assetKey: string) => callSkillFactory<AssetReleaseOverview>(SkillFactoryMethod.RELEASE_OVERVIEW, {
        assetType,
        assetKey,
    }),
    createChange: (assetType: ReleaseAssetType, assetKey: string, baseVersion: number | undefined, changeName: string) => callSkillFactory<AssetReleaseOperationResult>(SkillFactoryMethod.RELEASE_CHANGE_CREATE, compact({
        assetType,
        assetKey,
        baseVersion,
        changeName,
        requestId: releaseRequestId('change'),
    })),
    diff: (assetType: ReleaseAssetType, assetKey: string, version?: number, query: ReleaseDiffQuery = {}) => callSkillFactory<ReleaseDiffDocument>(SkillFactoryMethod.RELEASE_DIFF, compact({
        assetType,
        assetKey,
        version,
        entryPath: query.entryPath,
        viewMode: query.viewMode,
        contextLines: query.contextLines,
    })),
    deployPreprod: (assetType: ReleaseAssetType, assetKey: string, version: number, expectedDigest: string) => callSkillFactory<AssetReleaseOperationResult>(SkillFactoryMethod.RELEASE_PREPROD_DEPLOY, {
        assetType,
        assetKey,
        expectedDigest,
        requestId: releaseDeploymentRequestId(assetKey, version, expectedDigest, 'PRT'),
    }),
    deployOnline: (assetType: ReleaseAssetType, assetKey: string, version: number, expectedDigest: string, sourceDigest?: string) => callSkillFactory<AssetReleaseOperationResult>(SkillFactoryMethod.RELEASE_ONLINE_DEPLOY, compact({
        assetType,
        assetKey,
        expectedDigest,
        requestId: releaseDeploymentRequestId(assetKey, version, sourceDigest || expectedDigest, 'ONLINE'),
    })),
    startGray: (assetType: ReleaseAssetType, assetKey: string, environment: ReleaseEnvironment, version: number, expectedDigest: string, percentage: number, userIdWhitelist: string) => callSkillFactory<AssetReleaseOperationResult>(SkillFactoryMethod.RELEASE_GRAY_START, compact({
        assetType,
        assetKey,
        environment,
        expectedDigest,
        percentage,
        userIdWhitelist,
        requestId: grayReleaseRequestId(assetType, assetKey, environment, String(version), expectedDigest, 'GRAY_START', `${percentage}-${userIdWhitelist}`),
    })),
    mutateGray: (method: 'RELEASE_GRAY_ADJUST' | 'RELEASE_GRAY_STOP' | 'RELEASE_GRAY_PROMOTE', assetType: ReleaseAssetType, assetKey: string, environment: ReleaseEnvironment, candidateSourceId: string, candidateDigest: string, percentage?: number, userIdWhitelist?: string) => callSkillFactory<AssetReleaseOperationResult>(SkillFactoryMethod[method], compact({
        assetType,
        assetKey,
        environment,
        candidateSourceId,
        candidateDigest,
        percentage,
        userIdWhitelist,
        requestId: grayReleaseRequestId(assetType, assetKey, environment, candidateSourceId, candidateDigest, method.replace('RELEASE_', ''), method === 'RELEASE_GRAY_ADJUST' ? `${percentage}-${userIdWhitelist}` : undefined),
    })),
    forceDeployOnline: (assetType: ReleaseAssetType, assetKey: string, version: number, expectedDigest: string, sourceDigest?: string, forceReason?: string) => callSkillFactory<AssetReleaseOperationResult>(SkillFactoryMethod.RELEASE_ONLINE_DEPLOY, compact({
        assetType,
        assetKey,
        expectedDigest,
        forceReason,
        forcePublish: 'true',
        requestId: `${releaseDeploymentRequestId(assetKey, version, sourceDigest || expectedDigest, 'ONLINE')}:FORCE`,
    })),
    redeployHistory: (assetType: ReleaseAssetType, assetKey: string, version: number, sourceDigest: string) => callSkillFactory<AssetReleaseOperationResult>(SkillFactoryMethod.RELEASE_HISTORY_REDEPLOY, compact({
        assetType,
        assetKey,
        version,
        expectedDigest: sourceDigest,
        requestId: releaseDeploymentRequestId(assetKey, version, sourceDigest, 'ONLINE'),
    })),
};
export const assetAccessApi = {
    get: (assetType: ReleaseAssetType, assetKey: string) => callSkillFactory<AssetAccessResult>(SkillFactoryMethod.ASSET_ACCESS_GET, {
        assetType,
        assetKey,
    }),
    replaceOwners: (assetType: ReleaseAssetType, assetKey: string, owners: string[]) => callSkillFactory<AssetAccessResult>(SkillFactoryMethod.ASSET_OWNER_REPLACE, {
        assetType,
        assetKey,
        ownersJson: jsonStringify(owners) || '[]',
    }),
};
function ownerIds(owner?: string): string[] {
    return Array.from(new Set(String(owner || '')
        ?.split(',')
        ?.map?.((item) => item.trim())
        ?.filter?.(Boolean)));
}
function componentWriteParams(asset: SkillFactoryComponentAsset): Record<string, string> {
    // API Center binds params to Map<String, String>; detail responses may contain null fields.
    return Object.entries(asset).reduce<Record<string, string>>((params, [key, value]) => {
        if (value === undefined || value === null)
            return params;
        if (Array.isArray(value) || typeof value === 'object') {
            params[key] = jsonStringify(value) || (Array.isArray(value) ? '[]' : '{}');
            return params;
        }
        params[key] = String(value);
        return params;
    }, {});
}
function componentBasicInfoWriteParams(asset: SkillFactoryComponentAsset): Record<string, string> {
    return {
        id: String(asset.id || ''),
        componentNameCn: String(asset.componentNameCn || ''),
        interactionMode: String(asset.interactionMode || ''),
        bundleUrl: String(asset.bundleUrl || ''),
        appBundleUrl: String(asset.appBundleUrl || ''),
        scene: String(asset.scene || ''),
    };
}
export const componentCenterApi = {
    list: (query: ComponentAssetQuery) => callSkillFactory<SkillFactoryComponentAsset[]>(SkillFactoryMethod.COMPONENT_LIST, compact(query)),
    enabledList: (query: ComponentAssetQuery = {}) => callSkillFactory<SkillFactoryComponentAsset[]>(SkillFactoryMethod.COMPONENT_ENABLED_LIST, compact(query)),
    publishedList: (query: ComponentAssetQuery = {}) => callSkillFactory<SkillFactoryComponentAsset[]>(SkillFactoryMethod.COMPONENT_PUBLISHED_LIST, compact(query)),
    detail: (id: number) => callSkillFactory<SkillFactoryComponentAsset>(SkillFactoryMethod.COMPONENT_DETAIL, { id }),
    register: (asset: SkillFactoryComponentAsset) => {
        const owners = ownerIds(asset.owner);
        return callSkillFactory<SkillFactoryComponentAsset>(SkillFactoryMethod.COMPONENT_REGISTER, {
            ...componentWriteParams(asset),
            ...(owners.length ? { ownersJson: jsonStringify(owners) || '[]' } : {}),
        });
    },
    update: (asset: SkillFactoryComponentAsset) => callSkillFactory<SkillFactoryComponentAsset>(SkillFactoryMethod.COMPONENT_UPDATE, componentWriteParams(asset)),
    updateBasicInfo: (asset: SkillFactoryComponentAsset) => callSkillFactory<SkillFactoryComponentAsset>(SkillFactoryMethod.COMPONENT_BASIC_INFO_UPDATE, componentBasicInfoWriteParams(asset)),
    offline: (id: number) => callSkillFactory<SkillFactoryComponentAsset>(SkillFactoryMethod.COMPONENT_OFFLINE, { id }),
    preview: (id: number, previewJson: string) => callSkillFactory<ComponentPreviewResult>(SkillFactoryMethod.COMPONENT_PREVIEW, {
        id,
        previewJson,
    }),
    renderPreview: (params: ComponentRenderPreviewParams) => callSkillFactory<ComponentRenderPreviewResult>(SkillFactoryMethod.COMPONENT_RENDER_PREVIEW, compact(params)),
    bizRenderPreview: (params: ComponentRenderPreviewParams) => callSkillFactoryBizRender<ComponentRenderPreviewResult>(SkillFactoryMethod.COMPONENT_RENDER_PREVIEW, compact(params)),
    streamAssetAuthoring: (params: Record<string, unknown>, onEvent: (event: SkillFactoryCodingEvent) => void, options?: StreamOptions) => streamSkillFactoryEvents({
        ...params,
        bizKey: SKILL_FACTORY_CHAT_BIZ_KEYS.COMPONENT_CENTER_AUTHORING,
        authoringDomain: 'COMPONENT_CENTER',
    }, onEvent, options),
};
function a2uiCatalogComponentWriteParams(component: A2uiCatalogComponentContract): Record<string, string> {
    return {
        componentJson: jsonStringify(component) || '{}',
    };
}
export const a2uiCatalogComponentApi = {
    list: (query: A2uiCatalogComponentQuery = {}) => callSkillFactory<A2uiCatalogComponentRecord[]>(SkillFactoryMethod.A2UI_CATALOG_COMPONENT_LIST, compact(query)),
    detail: (id: string) => callSkillFactory<A2uiCatalogComponentRecord>(SkillFactoryMethod.A2UI_CATALOG_COMPONENT_DETAIL, {
        id,
    }),
    create: (component: A2uiCatalogComponentContract) => callSkillFactory<A2uiCatalogComponentRecord>(SkillFactoryMethod.A2UI_CATALOG_COMPONENT_CREATE, a2uiCatalogComponentWriteParams(component)),
    update: (id: string, component: A2uiCatalogComponentContract) => callSkillFactory<A2uiCatalogComponentRecord>(SkillFactoryMethod.A2UI_CATALOG_COMPONENT_UPDATE, {
        id,
        ...a2uiCatalogComponentWriteParams(component),
    }),
};
function a2uiCatalogWriteParams(catalog: A2uiCatalogAuthoringJson): Record<string, string> {
    const catalogJson = jsonStringify(catalog) || '{}';
    const parsed = parseA2uiCatalogAuthoringJson(catalogJson);
    if (parsed.ok === false) {
        throw new Error(parsed.errors?.join?.(','));
    }
    return {
        catalogJson,
    };
}
export const a2uiCatalogApi = {
    list: (query: A2uiCatalogQuery = {}) => callSkillFactory<A2uiCatalogRecord[]>(SkillFactoryMethod.A2UI_CATALOG_LIST, compact(query)),
    detail: (id: string) => callSkillFactory<A2uiCatalogRecord>(SkillFactoryMethod.A2UI_CATALOG_DETAIL, { id }),
    create: (catalog: A2uiCatalogAuthoringJson) => callSkillFactory<A2uiCatalogRecord>(SkillFactoryMethod.A2UI_CATALOG_CREATE, a2uiCatalogWriteParams(catalog)),
    update: (id: string, catalog: A2uiCatalogAuthoringJson) => callSkillFactory<A2uiCatalogRecord>(SkillFactoryMethod.A2UI_CATALOG_UPDATE, {
        id,
        ...a2uiCatalogWriteParams(catalog),
    }),
    importManaged: (sourceUrl: string) => {
        return callSkillFactory<A2uiManagedCatalogImportResult>(SkillFactoryMethod.A2UI_CATALOG_MANAGED_IMPORT, a2uiManagedCatalogImportParams(sourceUrl));
    },
};
export function a2uiManagedCatalogImportParams(sourceUrl: string): {
    sourceUrl: string;
} {
    const normalizedSourceUrl = sourceUrl.trim();
    if (!normalizedSourceUrl)
        throw new Error('请输入 Catalog JSON sourceUrl');
    return { sourceUrl: normalizedSourceUrl };
}
export function a2uiApplicationWriteParams(application: A2uiApplicationDraft): Record<string, string> {
    return {
        applicationJson: jsonStringify(toA2uiApplicationAuthoringPayload(application)) || '{}',
    };
}
export const a2uiApplicationApi = {
    list: async (query: A2uiApplicationQuery = {}) => {
        const applications = await callSkillFactory<A2uiApplicationRecord[]>(SkillFactoryMethod.A2UI_APPLICATION_LIST, compact(query));
        return applications.map(normalizeA2uiApplicationDraft);
    },
    detail: async (id: string) => normalizeA2uiApplicationDraft(await callSkillFactory<A2uiApplicationRecord>(SkillFactoryMethod.A2UI_APPLICATION_DETAIL, {
        id,
    })),
    create: async (application: A2uiApplicationDraft) => normalizeA2uiApplicationDraft(await callSkillFactory<A2uiApplicationRecord>(SkillFactoryMethod.A2UI_APPLICATION_CREATE, a2uiApplicationWriteParams(application))),
    update: async (id: string, application: A2uiApplicationDraft) => normalizeA2uiApplicationDraft(await callSkillFactory<A2uiApplicationRecord>(SkillFactoryMethod.A2UI_APPLICATION_UPDATE, {
        id,
        ...a2uiApplicationWriteParams(application),
    })),
    listBlueprints: async () => {
        const source = await callSkillFactory<unknown>(SkillFactoryMethod.A2UI_APPLICATION_BLUEPRINT_LIST, {});
        return projectA2uiApplicationBlueprintOptions(source);
    },
    importBlueprint: async (blueprintCode: A2uiApplicationBlueprintCode) => {
        const source = await callSkillFactory<A2uiApplicationBlueprintWireSource>(SkillFactoryMethod.A2UI_APPLICATION_BLUEPRINT_IMPORT, { blueprintCode });
        return projectA2uiApplicationBlueprintWireSource(source);
    },
    scanActions: async (application: A2uiApplicationDraft) => {
        const source = await callSkillFactory<unknown>(SkillFactoryMethod.A2UI_APPLICATION_ACTION_SCAN, a2uiApplicationWriteParams(application));
        return projectA2uiApplicationActionScanResult(source);
    },
};
export const skillBindingCandidateApi = {
    componentList: (query: ComponentAssetQuery = {}) => callSkillFactory<SkillFactoryComponentAsset[]>(SkillFactoryMethod.SKILL_COMPONENT_CANDIDATE_LIST, compact(query)),
    capabilityList: (keyword?: string) => callSkillFactory<CapabilityActionDraft[]>(SkillFactoryMethod.SKILL_CAPABILITY_CANDIDATE_LIST, compact({ keyword })),
};
export const capabilityCenterApi = {
    list: (query: CapabilityCatalogQuery = {}) => callSkillFactory<CapabilityActionDraft[]>(SkillFactoryMethod.CAPABILITY_LIST, compact(query)),
    publishedList: (keyword?: string) => callSkillFactory<CapabilityActionDraft[]>(SkillFactoryMethod.CAPABILITY_PUBLISHED_LIST, compact({ keyword })),
    create: (draft: CapabilityActionDraftData, selection?: CapabilityClassificationSelection) => callSkillFactory<CapabilityActionDraft>(SkillFactoryMethod.CAPABILITY_DRAFT_CREATE, selection
        ? {
            draftJson: jsonStringify(draft) || '{}',
            businessDomain: selection.businessDomain,
            capabilityDomain: selection.capabilityDomain,
            specialistIds: selection.specialistIds?.join?.(','),
        }
        : {
            draftJson: jsonStringify(draft) || '{}',
        }),
    detail: (draftId: string) => callSkillFactory<CapabilityActionDraft>(SkillFactoryMethod.CAPABILITY_DRAFT_DETAIL, {
        draftId,
    }),
    save: (draftId: string, baseRevision: number, draft: CapabilityActionDraftData, selection: CapabilityClassificationSelection) => callSkillFactory<CapabilityActionDraft>(SkillFactoryMethod.CAPABILITY_DRAFT_SAVE, {
        draftId,
        baseRevision,
        draftJson: jsonStringify(draft) || '{}',
        businessDomain: selection.businessDomain,
        capabilityDomain: selection.capabilityDomain,
        specialistIds: selection.specialistIds?.join?.(','),
    }),
    validate: (draftId: string) => callSkillFactory<CapabilityActionValidationResult>(SkillFactoryMethod.CAPABILITY_VALIDATE, {
        draftId,
    }),
    dryRun: (draftId: string, revision: number, environment: CapabilityActionDryRunEnvironment, clientType: CapabilityClient) => callSkillFactory<CapabilityActionDryRunResult>(SkillFactoryMethod.CAPABILITY_DRY_RUN, {
        draftId,
        revision,
        environment,
        clientType,
    }),
    publish: (draftId: string) => callSkillFactory<CapabilityActionDraft>(SkillFactoryMethod.CAPABILITY_PUBLISH, { draftId }),
};
export interface CapabilityClassificationSelection {
    businessDomain: string;
    capabilityDomain: string;
    specialistIds: string[];
}
export interface CapabilityCatalogQuery {
    keyword?: string;
    businessDomain?: string;
    capabilityDomain?: string;
    specialistId?: string;
    publishStatus?: 'EDITING' | 'ONLINE';
}
