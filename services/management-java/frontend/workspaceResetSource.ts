import type {
  PreprodBuildResetSource,
  WorkspaceResetSource,
  WorkspaceResetSourceType,
} from './api';

export interface WorkspaceResetOption {
  value: string;
  label: string;
  displayName: string;
  description: string;
}

export interface WorkspaceResetOptionGroup {
  label: string;
  options: WorkspaceResetOption[];
}

const RESET_SOURCE_TYPES = new Set<WorkspaceResetSourceType>(['BUILD', 'VERSION']);

function resetSourceValue(sourceType: WorkspaceResetSourceType, sourceId: string): string {
  return `${sourceType}:${sourceId}`;
}

function completionText(timestamp?: number): string {
  if (!timestamp || !Number.isFinite(timestamp)) return '完成时间未知';
  return `完成于 ${new Date(timestamp).toLocaleString('zh-CN', { hour12: false })}`;
}

function buildOption(source: PreprodBuildResetSource): WorkspaceResetOption {
  const baseLabel = `PRT Build #${source.buildNumber}（目标版本 ${source.targetVersion}）`;
  const description = [
    completionText(source.completionTime || source.createTime),
    source.operator || '操作人未知',
    source.packageDigest,
  ].join(' · ');
  return {
    value: resetSourceValue('BUILD', source.sourceId),
    label: `${baseLabel} · ${description}`,
    displayName: baseLabel,
    description,
  };
}

export function buildWorkspaceResetOptionGroups(
  preprodBuildResetSources: PreprodBuildResetSource[] = [],
  releaseVersions: Array<number | string> = [],
): WorkspaceResetOptionGroup[] {
  const buildOptions = preprodBuildResetSources
    ?.filter((source) => source?.sourceType === 'BUILD' && Boolean(source.sourceId))
    ?.map?.(buildOption);
  const onlineOptions = Array.from(
    new Set(
      releaseVersions
        ?.map((version) => Number(version))
        ?.filter?.((version) => Number.isInteger(version) && version > 0),
    ),
  )
    ?.sort((left, right) => right - left)
    ?.map?.((version) => ({
      value: resetSourceValue('VERSION', String(version)),
      label: `线上正式版本 ${version}`,
      displayName: `线上正式版本 ${version}`,
      description: `线上正式版本 ${version}`,
    }));
  const groups: WorkspaceResetOptionGroup[] = [];
  if (buildOptions.length) groups.push({ label: 'PRT 成功 Build', options: buildOptions });
  if (onlineOptions.length) groups.push({ label: '线上正式版本', options: onlineOptions });
  return groups;
}

export function defaultWorkspaceResetValue(groups: WorkspaceResetOptionGroup[]): string {
  return groups?.[0]?.options?.[0]?.value || '';
}

export function parseWorkspaceResetValue(value?: string): WorkspaceResetSource | null {
  const separatorIndex = String(value || '').indexOf(':');
  if (separatorIndex <= 0) return null;
  const sourceType = String(value).slice(0, separatorIndex) as WorkspaceResetSourceType;
  const sourceId = String(value).slice(separatorIndex + 1);
  if (!RESET_SOURCE_TYPES.has(sourceType) || !sourceId) return null;
  return { sourceType, sourceId };
}

export function findWorkspaceResetOption(
  groups: WorkspaceResetOptionGroup[],
  value?: string,
): WorkspaceResetOption | undefined {
  return groups?.flatMap((group) => group.options)?.find?.((option) => option.value === value);
}

export function resetSourceDisplayName(source: WorkspaceResetSource): string {
  return source.sourceType === 'BUILD'
    ? `PRT Build ${source.sourceId}`
    : `线上正式版本 ${source.sourceId}`;
}
