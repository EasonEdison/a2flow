export type ComponentAssetType = 'CARD_COMPONENT' | 'BUSINESS_DSL' | 'A2UI_ATOM';
export type ComponentRenderProtocol = 'CARD_CONTAINER' | 'UI_DSL' | 'A2UI_ATOM' | 'A2UI';
export type ComponentDslType = 'CARD_CONTAINER' | 'BUSINESS_DSL';
export type ComponentInteractionMode = 'DISPLAY_ONLY' | 'INTERACTIVE';
export interface SkillFactoryComponentAsset {
    id?: number;
    assetType: ComponentAssetType;
    componentName: string;
    componentNameCn?: string;
    dslType?: ComponentDslType;
    agentUiDsl?: string;
    protocolVersion: number;
    interactionMode?: ComponentInteractionMode;
    bundleUrl?: string;
    appBundleUrl?: string;
    owner?: string;
    scene?: string;
    paramsSchemaJson?: string;
    renderTemplateJson?: string;
    officialDemoJson?: string;
    messageDemoJson?: string;
    integrationPrompt?: string;
    allowedActionsJson?: string;
    runtimeConfigJson?: string;
    supportClients?: string[];
    enabled: boolean;
    attribute?: string;
    published?: boolean;
    publishedVersion?: number;
    releaseEnvironmentFacts?: AssetReleaseEnvironmentFacts;
    operator?: string;
    createTime?: number;
    updateTime?: number;
}
export interface ComponentAssetQuery {
    keyword?: string;
    assetType?: ComponentAssetType | 'ALL';
    dslType?: ComponentDslType | 'ALL';
    enabledOnly?: boolean;
}
export interface ComponentPreviewResult {
    valid: boolean;
    assetId: number;
    componentName: string;
    assetType?: ComponentAssetType;
    dslType?: string;
    agentUiDsl?: string;
    previewJson: string;
    paramsValid?: boolean;
    renderTemplateValid?: boolean;
    actionValid?: boolean;
    a2uiMessagesPreview?: Array<Record<string, unknown>>;
    contextSummaryPreview?: string;
    errors: string[];
}
export interface ComponentRenderPreviewParams {
    assetType?: ComponentAssetType;
    componentName?: string;
    componentNameCn?: string;
    agentUiDsl?: string;
    dslType?: string;
    protocolVersion?: number;
    interactionMode?: ComponentInteractionMode;
    inputMode?: 'BUSINESS_DSL' | 'CARD_CONTAINER' | 'RAW_TEXT';
    source?: string;
    clientType?: string;
    toolArgsJson?: string;
    paramsSchemaJson?: string;
    renderTemplateJson?: string;
    officialDemoJson?: string;
    allowedActionsJson?: string;
    runtimeConfigJson?: string;
    bundleUrl?: string;
    appBundleUrl?: string;
    params?: string;
    data?: string;
}
export interface ComponentRenderPreviewResult {
    valid: boolean;
    assetId?: number;
    assetType?: ComponentAssetType;
    componentName?: string;
    componentNameCn?: string;
    renderProtocol?: ComponentRenderProtocol | string;
    protocolVersion?: number;
    interactionMode?: ComponentInteractionMode;
    bundleUrl?: string;
    appBundleUrl?: string;
    dslType?: string;
    agentUiDsl?: string;
    paramsValid?: boolean;
    data?: unknown;
    messages?: Array<Record<string, unknown>>;
    errors?: string[];
    warnings?: string[];
    normalizedInput?: Record<string, unknown>;
    renderedContent?: string;
    renderedJson?: string;
}
export interface SkillFactoryCommonResponse {
    result: number;
    errorMsg?: string;
    error_msg?: string;
    data?: string;
    traceId?: string;
    trace_id?: string;
    isList?: boolean;
    is_list?: boolean;
}
export type ReleaseAssetType = 'SKILL' | 'COMPONENT' | 'CAPABILITY_ACTION' | 'ORCHESTRATION_CONFIG' | 'A2UI_CATALOG' | 'A2UI_APPLICATION';
export type ReleaseEnvironment = 'PRT' | 'ONLINE';
export interface AssetReleaseSourceFact {
    environment?: ReleaseEnvironment;
    requestedEnvironment?: ReleaseEnvironment;
    resolvedEnvironment?: ReleaseEnvironment;
    status?: string;
    available?: boolean;
    sourceType?: string;
    sourceId?: string;
    version?: number;
    digest?: string;
    errorCode?: string;
    message?: string;
}
export interface AssetReleaseEnvironmentFacts {
    preprod?: AssetReleaseSourceFact;
    online?: AssetReleaseSourceFact;
    effectivePreprod?: AssetReleaseSourceFact;
    onlineBlocked?: boolean;
    onlineBlockedReason?: string;
}
export type AssetAccessRole = 'OWNER' | 'ADMIN' | 'VIEWER';
export interface AssetPrincipal {
    principalType: 'USER' | string;
    principalId: string;
    roleType: 'OWNER' | string;
}
export interface AssetPermissions {
    canView: boolean;
    canEdit: boolean;
    canPublish: boolean;
    canForcePublish: boolean;
    canOffline: boolean;
    canManageOwner: boolean;
}
export interface AssetAccessResult {
    assetType: ReleaseAssetType;
    assetKey: string;
    owners: AssetPrincipal[];
    role: AssetAccessRole;
    permissions: AssetPermissions;
    reason?: string;
}
export interface ReleaseAssetSnapshot {
    assetType: ReleaseAssetType;
    assetKey: string;
    digest: string;
    artifactRef?: string;
    summary: Record<string, unknown>;
    payloadJson?: string;
}
export interface ReleaseGateResult {
    code: string;
    label: string;
    status: 'PASSED' | 'FAILED' | string;
    required: boolean;
    message: string;
}
export interface AssetReleaseChange {
    changeId: string;
    changeName: string;
    targetVersion: number;
    baseVersion?: number;
    status: string;
    sourceDigest: string;
    operator: string;
    createTime: number;
    updateTime: number;
}
export interface AssetReleaseBuild {
    buildId: string;
    changeId: string;
    targetVersion: number;
    buildNumber: number;
    inputDigest?: string;
    sourceDigest: string;
    status: string;
    gates: ReleaseGateResult[];
    operator: string;
    createTime: number;
}
export interface AssetReleaseVersion {
    version: number;
    versionId: string;
    sourceBuildId: string;
    inputDigest?: string;
    sourceDigest: string;
    operator: string;
    createTime: number;
}
export interface AssetReleaseDeployment {
    deploymentId: string;
    requestId: string;
    environment: ReleaseEnvironment;
    sourceType: 'BUILD' | 'VERSION';
    sourceId: string;
    sourceVersion?: number;
    sourceDigest: string;
    status: string;
    currentStage?: string;
    retryable?: boolean;
    errorCode?: string;
    error?: string;
    message?: string;
    forced?: boolean;
    forceReason?: string;
    publishMode?: ReleasePublishMode;
    artifact?: Record<string, unknown>;
    domainResult?: Record<string, unknown>;
    gates: ReleaseGateResult[];
    operator: string;
    createTime: number;
    updateTime: number;
}
export interface AssetReleaseOperationResult {
    operationId: string;
    status: string;
    message: string;
}
export type ReleasePublishMode = 'NORMAL' | 'FORCE' | 'HISTORICAL' | 'GRAY';
export interface ReleaseEnvironmentState {
    environment: ReleaseEnvironment;
    sourceType: 'BUILD' | 'VERSION';
    sourceId: string;
    version?: number;
    digest: string;
    deploymentId: string;
    updateTime: number;
    candidate?: ReleaseEnvironmentPointer;
    grayRule?: ReleaseGrayRule;
    grayStatus?: 'STABLE' | 'GRAYING';
}
export interface ReleaseEnvironmentPointer {
    sourceType: 'BUILD' | 'VERSION';
    sourceId: string;
    version?: number;
    digest: string;
    deploymentId?: string;
    updateTime?: number;
}
export interface ReleaseGrayRule {
    percentage: number;
    userIdWhitelist: string[];
}
export interface AssetReleaseOverview {
    grayReleaseSupported?: boolean;
    grayReleasePolicy?: 'DISABLED' | 'PERCENTAGE_AND_WHITELIST';
    nextVersion?: number;
    currentSnapshot: ReleaseAssetSnapshot;
    activeChange?: AssetReleaseChange;
    builds: AssetReleaseBuild[];
    versions: AssetReleaseVersion[];
    deployments: AssetReleaseDeployment[];
    environments: Partial<Record<ReleaseEnvironment, ReleaseEnvironmentState>>;
    gates: ReleaseGateResult[];
    environmentGates?: Partial<Record<ReleaseEnvironment, ReleaseGateResult[]>>;
    allowedActions: string[];
    blockedReasons: string[];
}
export type ReleaseDiffChangeType = 'ADDED' | 'MODIFIED' | 'DELETED' | 'RENAMED';
export type ReleaseDiffContentType = 'TEXT' | 'JSON' | 'BINARY';
export type ReleaseDiffLineType = 'CONTEXT' | 'ADD' | 'DELETE';
export type ReleaseDiffViewMode = 'UNIFIED' | 'SPLIT';
export interface ReleaseDiffLine {
    type: ReleaseDiffLineType;
    oldLineNumber?: number;
    newLineNumber?: number;
    content: string;
}
export interface ReleaseDiffHunk {
    oldStart: number;
    oldLines: number;
    newStart: number;
    newLines: number;
    header: string;
    lines: ReleaseDiffLine[];
}
export interface ReleaseDiffEntry {
    path: string;
    oldPath?: string;
    changeType: ReleaseDiffChangeType;
    contentType: ReleaseDiffContentType;
    language: string;
    beforeDigest?: string;
    afterDigest?: string;
    beforeSize?: number;
    afterSize?: number;
    additions: number | null;
    deletions: number | null;
    truncated: boolean;
    truncatedReason?: string;
    hunks: ReleaseDiffHunk[];
}
export interface ReleaseDiffSummary {
    changedFiles: number;
    additions: number;
    deletions: number;
    truncated: boolean;
    truncatedReason?: string;
}
export interface ReleaseDiffDocument {
    assetType: ReleaseAssetType;
    assetKey: string;
    currentDigest: string;
    targetVersion?: number;
    hasTarget: boolean;
    from: string;
    to: string;
    requestedEntryPath?: string;
    viewMode: ReleaseDiffViewMode;
    summary: ReleaseDiffSummary;
    entries: ReleaseDiffEntry[];
}
export interface ReleaseDiffQuery {
    entryPath?: string;
    viewMode?: ReleaseDiffViewMode;
    contextLines?: number;
}
