import type { SkillFactoryComponentAsset } from './types';
import type {
  AuthoringFormAdapter,
  FormPatchIssue,
  JsonPatchOperation,
} from './shared/authoringFormPatch';

export const COMPONENT_FORM_KEYS = {
  CARD_COMPONENT: 'component-center.card-component.v1',
  BUSINESS_DSL: 'component-center.business-dsl.v1',
} as const;

type ComponentAssetDraft = Partial<SkillFactoryComponentAsset> & {
  mode?: 'CREATE' | 'UPDATE';
  enableable?: boolean;
  status?: string;
};

const cardCreatePaths = [
  '/componentName',
  '/componentNameCn',
  '/interactionMode',
  '/bundleUrl',
  '/appBundleUrl',
  '/owner',
  '/scene',
  '/messageDemoJson',
  '/officialDemoJson',
  '/paramsSchemaJson',
  '/renderTemplateJson',
  '/allowedActionsJson',
  '/runtimeConfigJson',
  '/integrationPrompt',
];
const cardEditPaths = cardCreatePaths.filter((path) => path !== '/componentName');
const businessDslCreatePaths = [
  '/componentName',
  '/componentNameCn',
  '/agentUiDsl',
  '/owner',
  '/scene',
  '/paramsSchemaJson',
  '/renderTemplateJson',
  '/officialDemoJson',
  '/messageDemoJson',
  '/allowedActionsJson',
  '/integrationPrompt',
  '/runtimeConfigJson',
  '/enabled',
];
const businessDslEditPaths = businessDslCreatePaths.filter(
  (path) => !['/componentName', '/agentUiDsl'].includes(path),
);
const executableMarkers = [
  '<script',
  'javascript:',
  'eval(',
  'new function(',
  'runtime.exec(',
  'processbuilder(',
  'groovyshell',
];
const fieldDescriptions: Record<string, { label: string; section: string }> = {
  '/componentName': { label: '组件 code', section: '基础信息' },
  '/componentNameCn': { label: '组件中文名', section: '基础信息' },
  '/agentUiDsl': { label: 'agentUiDsl', section: '基础信息' },
  '/bundleUrl': { label: 'bundleUrl', section: '基础信息' },
  '/appBundleUrl': { label: 'APP bundleUrl', section: '基础信息' },
  '/interactionMode': { label: '交互类型', section: '基础信息' },
  '/owner': { label: '负责人', section: '基础信息' },
  '/scene': { label: '适用场景', section: '基础信息' },
  '/paramsSchemaJson': { label: '参数 Schema', section: '模板配置' },
  '/messageDemoJson': { label: '模型 Tool 调用参数', section: '模板配置' },
  '/officialDemoJson': { label: '官方渲染 Demo', section: '模板配置' },
  '/renderTemplateJson': { label: '转换模板', section: '模板配置' },
  '/allowedActionsJson': { label: '允许动作', section: '协议配置' },
  '/integrationPrompt': { label: '集成提示词', section: '模板配置' },
  '/runtimeConfigJson': { label: '运行配置', section: '协议配置' },
  '/enabled': { label: '是否启用', section: '资产状态' },
};

function containsExecutable(value: unknown): boolean {
  if (typeof value === 'string') {
    const normalized = value.toLowerCase();
    return executableMarkers.some((marker) => normalized.includes(marker));
  }
  if (Array.isArray(value)) return value.some(containsExecutable);
  if (value && typeof value === 'object') return Object.values(value).some(containsExecutable);
  return false;
}

function validateOperation(
  operation: JsonPatchOperation,
  allowedPaths: readonly string[],
): FormPatchIssue[] {
  if (!allowedPaths.includes(operation.path)) {
    return [{ path: operation.path, message: `字段不允许由 AI 修改：${operation.path}` }];
  }
  if (operation.op !== 'remove' && containsExecutable(operation.value)) {
    return [{ path: operation.path, message: '组件表单不允许写入可执行代码或脚本协议' }];
  }
  if (
    operation.path === '/enabled' &&
    operation.op !== 'remove' &&
    typeof operation.value !== 'boolean'
  ) {
    return [{ path: operation.path, message: 'enabled 必须是布尔值' }];
  }
  if (
    operation.path === '/interactionMode' &&
    operation.op !== 'remove' &&
    !['DISPLAY_ONLY', 'INTERACTIVE'].includes(String(operation.value))
  ) {
    return [{ path: operation.path, message: '交互类型只支持纯展示或需交互' }];
  }
  if (
    operation.path !== '/enabled' &&
    operation.op !== 'remove' &&
    typeof operation.value !== 'string'
  ) {
    return [
      {
        path: operation.path,
        message: `${fieldDescriptions[operation.path]?.label || operation.path} 必须是字符串`,
      },
    ];
  }
  return [];
}

export function createComponentFormPatchAdapter(options: {
  draft: ComponentAssetDraft;
  entityId: string;
  revision: number;
  editMode: boolean;
  apply: (next: ComponentAssetDraft) => void;
}): AuthoringFormAdapter<ComponentAssetDraft> {
  const businessDsl = options.draft?.assetType === 'BUSINESS_DSL';
  const allowedPaths = businessDsl
    ? options.editMode
      ? businessDslEditPaths
      : businessDslCreatePaths
    : options.editMode
    ? cardEditPaths
    : cardCreatePaths;
  return {
    formKey: businessDsl ? COMPONENT_FORM_KEYS.BUSINESS_DSL : COMPONENT_FORM_KEYS.CARD_COMPONENT,
    entityId: options.entityId,
    revision: options.revision,
    schema: {
      type: 'object',
      properties: Object.fromEntries(
        allowedPaths.map((path) => [
          path.slice(1),
          {
            type: path === '/enabled' ? 'boolean' : 'string',
          },
        ]),
      ),
    },
    allowedPaths,
    snapshot: () => options.draft,
    normalize: (value) => ({
      ...(value as ComponentAssetDraft),
      assetType: options.draft?.assetType,
    }),
    validateOperation: (operation) => validateOperation(operation, allowedPaths),
    describePath: (path) => fieldDescriptions[path] || { label: path, section: '表单字段' },
    apply: options.apply,
  };
}
