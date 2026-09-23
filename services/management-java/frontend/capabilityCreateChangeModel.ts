interface CapabilityReleaseVersionOptionSource {
  version: number;
}

interface ResolveCapabilityCreateChangeViewInput {
  canEdit: boolean;
  readonlyReason: string;
  allowedActions: string[];
  versions: CapabilityReleaseVersionOptionSource[];
  baseVersion?: number;
  changeName: string;
}

const RELEASE_ACTION_CREATE_CHANGE = 'CREATE_CHANGE';

export interface CapabilityCreateChangeView {
  canCreateChange: boolean;
  defaultBaseVersion?: number;
  versionOptions: Array<{ label: string; value: number }>;
  submitDisabled: boolean;
  submitLabel: string;
  submitTitle: string;
}

/**
 * 把后端发布动作和页面输入转换成创建变更面板状态。
 *
 * 页面不推断资产是否可新建变更，只有后端明确返回 CREATE_CHANGE 且当前用户可编辑时才放开。
 */
export const resolveCapabilityCreateChangeView = (
  input: ResolveCapabilityCreateChangeViewInput,
): CapabilityCreateChangeView => {
  const versionOptions = [...input.versions]
    ?.sort((left, right) => right.version - left.version)
    ?.map?.((item) => ({ label: String(item.version), value: item.version }));
  const canCreateChange =
    input.canEdit && input.allowedActions.includes(RELEASE_ACTION_CREATE_CHANGE);
  const normalizedName = input.changeName?.trim?.();

  return {
    canCreateChange,
    defaultBaseVersion: versionOptions?.[0]?.value,
    versionOptions,
    submitDisabled: !canCreateChange || !normalizedName,
    submitLabel: input.baseVersion === undefined ? '新建变更' : '恢复并新建变更',
    submitTitle: !canCreateChange
      ? input.readonlyReason || '当前状态不允许新建变更'
      : normalizedName
      ? '新建变更'
      : '请先填写变更名称',
  };
};
