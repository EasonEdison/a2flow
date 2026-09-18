export type AssetKind = 'SKILL' | 'ABILITY' | 'APPLICATION' | 'WORKFLOW';
export type Environment = 'PRT' | 'ONLINE';
export type JsonObject = Record<string, unknown>;

export interface ManagementSession {
  userId: string;
  environment: Environment;
  registeredKinds: AssetKind[];
  canAuthor: boolean;
}

export interface AssetSummary extends JsonObject {
  kind?: AssetKind;
  key?: string;
  skillKey?: string;
  assetId?: string;
  versionId?: string;
  contentDigest?: string;
  selection?: string;
  name?: string;
  description?: string;
  draftOnly?: boolean;
  draftRevision?: number;
}

export interface ManagedDraft {
  kind: AssetKind;
  key: string;
  revision: number;
  document: JsonObject;
  contentDigest: string;
  updatedBy: string;
}

export interface ValidationIssue {
  code: string;
  path?: string;
  message?: string;
}

export interface ValidationReport {
  valid: boolean;
  issues: ValidationIssue[];
  normalized?: JsonObject;
}

export interface PublicationTarget {
  environment: Environment;
  versionId: string;
  channel: string;
  grayUserIds: string[];
}

export interface PublicationPlan extends JsonObject {
  kind: AssetKind;
  key: string;
  draftRevision: number;
  contentDigest: string;
  target: PublicationTarget;
  status: 'PREPARED_NOT_PUBLISHED';
  published: false;
  candidate: JsonObject;
}

export interface PublicationHistory {
  kind: AssetKind;
  key: string;
  versions: Array<{ versionId: string; assetId: string; contentDigest: string }>;
  serving: JsonObject;
  servingDigest: string;
}

export interface PublicationResult extends JsonObject {
  status: 'PUBLISHED' | 'ROLLED_BACK';
  published: true;
  businessCompensated: false;
}

export interface RetainedVersion {
  kind: AssetKind;
  key: string;
  versionId: string;
  contentDigest: string;
  document: JsonObject;
}

export interface ReferenceCatalog {
  loading: boolean;
  errors: Record<string, string>;
  assets: Partial<Record<AssetKind, AssetSummary[]>>;
  histories: Record<string, PublicationHistory>;
  retry?: () => void;
}

export interface DraftBuffer {
  text: string;
  revision: number;
  dirty: boolean;
  conflict: boolean;
  contentDigest: string;
  updatedBy: string;
}

export interface PendingResourceEdit {
  identity: string;
  base: string;
  text: string;
  conflict?: boolean;
}

export type PendingResourceEdits = Record<string, PendingResourceEdit>;

export const KIND_COPY: Record<AssetKind, { label: string; short: string; guidance: string }> = {
  SKILL: {
    label: 'Skill',
    short: 'SK',
    guidance: '检查指令、工具绑定和资源清单；草稿只描述候选内容，不改变已发布版本。',
  },
  ABILITY: {
    label: 'Ability',
    short: 'AB',
    guidance: '核对适配操作、参数结构和结果解释策略；管理台不会执行真实能力调用。',
  },
  APPLICATION: {
    label: 'Application',
    short: 'AP',
    guidance: '检查界面定义、交互 Action 与依赖；此处不扩展任意组件运行时。',
  },
  WORKFLOW: {
    label: 'Workflow',
    short: 'WF',
    guidance: '检查节点与 Skill 引用；当前运行时仅接受后端验证通过的拓扑。',
  },
};

export function assetKeyOf(asset: AssetSummary): string {
  const key = asset.key ?? asset.skillKey;
  if (!key) throw new Error('ASSET_KEY_MISSING');
  return key;
}

export function bufferId(kind: AssetKind, key: string): string {
  return kind + ':' + key;
}

export function createDraftBuffer(draft: ManagedDraft): DraftBuffer {
  return {
    text: JSON.stringify(draft.document, null, 2),
    revision: draft.revision,
    dirty: false,
    conflict: false,
    contentDigest: draft.contentDigest,
    updatedBy: draft.updatedBy,
  };
}
