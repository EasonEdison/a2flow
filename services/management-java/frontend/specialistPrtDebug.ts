export const SKILL_FACTORY_TAB_ITEMS = [
  { key: 'overview', label: '基础信息' },
  { key: 'capabilities', label: '业务能力' },
  { key: 'components', label: '渲染组件' },
  { key: 'files', label: '文件处理' },
  { key: 'release', label: '打包发布' },
  { key: 'binding', label: '调试页面' },
] as const;

export type SpecialistPrtVersionAction = 'REUSE' | 'CREATE' | 'BLOCKED';
export type SpecialistPrtBindingOperation = 'QUERY' | 'PUBLISH';

export interface SpecialistDebugEmployeeSource {
  employeeId?: string | number;
  employeeCode?: string;
  content?: {
    name?: string;
  };
}

export interface SpecialistDebugOption {
  value: string;
  label: string;
  employeeName: string;
}

const SKILL_HANDLER_PATH = '/api/management/v2/handler';

const SPECIALIST_PRT_BINDING_METHOD = {
  QUERY: 'QUERY_EMPLOYEE_PRT_SKILL_BINDING',
  PUBLISH: 'BIND_AND_PUBLISH_EMPLOYEE_PRT_SKILL',
} as const;

export function buildSpecialistDebugOptions(
  employees: SpecialistDebugEmployeeSource[],
): SpecialistDebugOption[] {
  const seen = new Set<string>();
  return (employees || []).flatMap((employee) => {
    const employeeId = String(employee?.employeeId || '').trim();
    if (!employeeId || seen.has(employeeId)) return [];
    seen.add(employeeId);
    const employeeName =
      String(employee?.content?.name || '').trim() ||
      String(employee?.employeeCode || '').trim() ||
      `专员 ${employeeId}`;
    return [
      {
        value: employeeId,
        label: `${employeeName}（employeeId=${employeeId}）`,
        employeeName,
      },
    ];
  });
}

export function resolveSpecialistDebugSelection(
  selectedEmployeeId: string,
  currentEmployeeIds: string[],
  options: SpecialistDebugOption[],
): string {
  const optionIds = new Set((options || []).map((option) => option.value));
  if (selectedEmployeeId && optionIds.has(selectedEmployeeId)) {
    return selectedEmployeeId;
  }
  return (currentEmployeeIds || []).find((employeeId) => optionIds.has(employeeId)) || '';
}

export function resolveSpecialistPrtAction(state: {
  versionAction?: SpecialistPrtVersionAction;
  prtEffective?: boolean;
}) {
  if (state.prtEffective) {
    return undefined;
  }
  if (state.versionAction === 'REUSE') {
    return {
      action: 'REUSE' as const,
      label: '绑定到当前 PRT 变更并发布',
    };
  }
  if (state.versionAction === 'CREATE') {
    return {
      action: 'CREATE' as const,
      label: '新建 PRT 变更并绑定发布',
    };
  }
  return undefined;
}

export function buildSpecialistManagementUrl(employeeId: string | number) {
  return `/employee/${encodeURIComponent(String(employeeId))}`;
}

export function buildSpecialistPrtBindingRequest(
  operation: SpecialistPrtBindingOperation,
  employeeId: string | number,
  skillCode: string,
  operator: string,
) {
  return {
    path: SKILL_HANDLER_PATH,
    body: {
      userName: operator,
      method: SPECIALIST_PRT_BINDING_METHOD[operation],
      params: {
        employeeId: String(employeeId),
        skillCode,
      },
    },
  };
}
