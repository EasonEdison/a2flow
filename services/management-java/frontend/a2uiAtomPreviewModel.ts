import type { A2uiCatalogComponentRecord } from './a2uiCatalogContracts';

export const OFFICIAL_BASIC_CATALOG_ID =
  'https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json';

export interface A2uiPreviewComponent {
  id: string;
  component: string;
  [key: string]: unknown;
}

export interface A2uiAtomPreviewDocument {
  components: A2uiPreviewComponent[];
  dataModel?: Record<string, unknown>;
}

export type A2uiAtomPreviewSourceKind =
  | 'REGISTERED_EXAMPLE'
  | 'SCHEMA_DERIVED'
  | 'UNAVAILABLE';

export interface A2uiAtomPreviewSource {
  kind: A2uiAtomPreviewSourceKind;
  label: string;
  description: string;
  document?: A2uiAtomPreviewDocument;
}

const text = (id: string, value: string): A2uiPreviewComponent => ({
  id,
  component: 'Text',
  text: value,
});

function schemaDerivedDocument(componentType: string): A2uiAtomPreviewDocument | undefined {
  const mediaPlaceholder = 'data:application/octet-stream;base64,';
  switch (componentType) {
    case 'Text':
      return { components: [{ id: 'root', component: 'Text', text: '**A2UI 文本预览**', variant: 'h3' }] };
    case 'Image':
      return {
        components: [{
          id: 'root',
          component: 'Image',
          url: 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="480" height="180"%3E%3Crect width="100%25" height="100%25" fill="%23e6f4ff"/%3E%3Ctext x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" fill="%231675d1" font-size="22"%3EA2UI Image%3C/text%3E%3C/svg%3E',
          description: 'A2UI Image 契约预览图',
          fit: 'contain',
          variant: 'mediumFeature',
        }],
      };
    case 'Icon':
      return { components: [{ id: 'root', component: 'Icon', name: 'star' }] };
    case 'Video':
      return { components: [{ id: 'root', component: 'Video', url: mediaPlaceholder }] };
    case 'AudioPlayer':
      return {
        components: [{ id: 'root', component: 'AudioPlayer', url: mediaPlaceholder, description: '音频控件预览' }],
      };
    case 'Row':
      return {
        components: [
          { id: 'root', component: 'Row', children: ['row-a', 'row-b'], justify: 'spaceBetween', align: 'center' },
          text('row-a', '左侧内容'),
          text('row-b', '右侧内容'),
        ],
      };
    case 'Column':
      return {
        components: [
          { id: 'root', component: 'Column', children: ['column-a', 'column-b'], align: 'stretch' },
          text('column-a', '第一行'),
          text('column-b', '第二行'),
        ],
      };
    case 'List':
      return {
        components: [
          { id: 'root', component: 'List', children: ['list-a', 'list-b'], direction: 'vertical' },
          text('list-a', '列表项一'),
          text('list-b', '列表项二'),
        ],
      };
    case 'Card':
      return { components: [{ id: 'root', component: 'Card', child: 'card-body' }, text('card-body', 'Card 内容')] };
    case 'Tabs':
      return {
        components: [
          {
            id: 'root',
            component: 'Tabs',
            tabs: [
              { title: '概览', child: 'tab-overview' },
              { title: '详情', child: 'tab-detail' },
            ],
          },
          text('tab-overview', '这是第一个标签页，可点击“详情”切换。'),
          text('tab-detail', '标签页切换由官方 renderer 在本地处理。'),
        ],
      };
    case 'Modal':
      return {
        components: [
          { id: 'root', component: 'Modal', trigger: 'modal-trigger', content: 'modal-content' },
          {
            id: 'modal-trigger',
            component: 'Button',
            child: 'modal-trigger-label',
            action: { event: { name: 'openPreviewModal', context: {} } },
          },
          text('modal-trigger-label', '打开弹窗'),
          text('modal-content', '这是 Modal 的本地预览内容。'),
        ],
      };
    case 'Divider':
      return { components: [{ id: 'root', component: 'Divider', axis: 'horizontal' }] };
    case 'Button':
      return {
        components: [
          {
            id: 'root',
            component: 'Button',
            child: 'button-label',
            variant: 'primary',
            action: { event: { name: 'previewButtonClicked', context: { source: 'component-center' } } },
          },
          text('button-label', '点击测试按钮'),
        ],
      };
    case 'TextField':
      return {
        components: [{ id: 'root', component: 'TextField', label: '示例文本', value: { path: '/text' }, variant: 'shortText' }],
        dataModel: { text: '可在本地修改' },
      };
    case 'CheckBox':
      return {
        components: [{ id: 'root', component: 'CheckBox', label: '确认选择', value: { path: '/checked' } }],
        dataModel: { checked: true },
      };
    case 'ChoicePicker':
      return {
        components: [{
          id: 'root',
          component: 'ChoicePicker',
          label: '选择一个方案',
          variant: 'mutuallyExclusive',
          displayStyle: 'chips',
          options: [{ label: '方案一', value: 'one' }, { label: '方案二', value: 'two' }],
          value: { path: '/choices' },
        }],
        dataModel: { choices: ['one'] },
      };
    case 'Slider':
      return {
        components: [{ id: 'root', component: 'Slider', label: '完成度', min: 0, max: 100, value: { path: '/progress' } }],
        dataModel: { progress: 40 },
      };
    case 'DateTimeInput':
      return {
        components: [{
          id: 'root',
          component: 'DateTimeInput',
          label: '选择时间',
          value: { path: '/dateTime' },
          enableDate: true,
          enableTime: true,
        }],
        dataModel: { dateTime: '2026-10-05T10:30' },
      };
    default:
      return undefined;
  }
}

function registeredExampleDocument(
  componentType: string,
  value?: Record<string, unknown>,
): A2uiAtomPreviewDocument | undefined {
  if (!value || !Object.keys(value).length) return undefined;
  if (Array.isArray(value.components)) {
    return value as unknown as A2uiAtomPreviewDocument;
  }
  if (typeof value.component !== 'string') return undefined;
  const example: Record<string, unknown> = {
    ...value,
    id: typeof value.id === 'string' && value.id ? value.id : 'root',
  };
  if (example.id !== 'root') example.id = 'root';
  if (example.component !== componentType) return undefined;
  return { components: [example as A2uiPreviewComponent] };
}

export function resolveA2uiAtomPreviewSource(
  component: A2uiCatalogComponentRecord,
): A2uiAtomPreviewSource {
  const registered = registeredExampleDocument(component.type, component.validMessageExample);
  if (registered) {
    return {
      kind: 'REGISTERED_EXAMPLE',
      label: '已注册 Catalog 示例',
      description: '示例直接来自组件注册记录的 validMessageExample。',
      document: registered,
    };
  }
  if (component.componentOriginType === 'A2UI_OFFICIAL' && component.officialSchema) {
    const derived = schemaDerivedDocument(component.type);
    if (derived) {
      return {
        kind: 'SCHEMA_DERIVED',
        label: '已注册 Schema 契约示例',
        description: '依据已注册 officialSchema 构造，仅用于本地预览；不是 Google 官方原始 demo。',
        document: derived,
      };
    }
  }
  return {
    kind: 'UNAVAILABLE',
    label: '无可用示例',
    description: '当前注册记录没有可验证示例，或前端尚未实现该 Catalog 组件，已停止预览。',
  };
}

export function parseA2uiAtomPreviewDocument(raw: string): A2uiAtomPreviewDocument {
  const parsed = JSON.parse(raw) as A2uiAtomPreviewDocument;
  if (!parsed || !Array.isArray(parsed.components) || !parsed.components.length) {
    throw new Error('预览 JSON 必须包含非空 components 数组');
  }
  if (!parsed.components.some((component) => component?.id === 'root')) {
    throw new Error('预览 JSON 缺少 id 为 root 的组件');
  }
  return parsed;
}
