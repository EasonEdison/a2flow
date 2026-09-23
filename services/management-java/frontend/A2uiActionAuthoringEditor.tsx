import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Input,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import { jsonStringify } from './shared/safeJson';
import type {
  A2uiActionBinding,
  A2uiBusinessPredicateClause,
  A2uiBusinessSuccessPredicate,
  A2uiMessage,
  A2uiMessageTemplateBinding,
  A2uiRequestMapping,
  A2uiResultAdapter,
  A2uiResultOutcome,
} from './a2uiApplicationContracts';
import {
  createA2uiActionBindingFromDeclaration,
  resolveA2uiMessageTemplateAdapter,
  upsertA2uiActionBinding,
  type A2uiActionClosureRow,
} from './a2uiApplicationEditorModel';
import { serverMessageKey } from './a2uiApplicationShowAst';
import { A2uiJsonValueEditor } from './A2uiShowAuthoringEditor';
import JsonFormatTextArea from './shared/JsonFormatTextArea';

const { Paragraph, Text } = Typography;

type A2uiOutcomeKind = 'success' | 'failure';
type A2uiMessageType = 'createSurface' | 'updateComponents' | 'updateDataModel' | 'deleteSurface';

const RESULT_SOURCE_OPTIONS: Array<{
  value: A2uiMessageTemplateBinding['source'];
  label: string;
}> = [
  { value: 'CAPABILITY_DATA', label: '业务响应 data' },
  { value: 'CAPABILITY_META', label: 'Tool 元数据' },
  { value: 'TRUSTED_CONTEXT', label: '可信上下文' },
  { value: 'CONSTANT', label: '常量' },
];

const PASSTHROUGH_SOURCE_OPTIONS: Array<{
  value: NonNullable<A2uiResultAdapter['source']>;
  label: string;
}> = [
  { value: 'CAPABILITY_DATA', label: '业务响应 data' },
  { value: 'CAPABILITY_META', label: 'Tool 元数据' },
];

interface A2uiActionAuthoringEditorProps {
  rows: A2uiActionClosureRow[];
  actionBindings: A2uiActionBinding[];
  catalogOptions: Array<{ value: string; label: string }>;
  capabilityActionOptions: Array<{ value: string; label: string }>;
  onActionBindingsChange: (bindings: A2uiActionBinding[]) => void;
}

function previewJson(value: unknown): string {
  return jsonStringify(value, null, 2) || '{}';
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && !Array.isArray(value) && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : {};
}

function parseDemoJson(
  value: string,
  label: string,
  rejectDataField = false,
): {
  value: Record<string, unknown>;
  error: string;
} {
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
      return { value: {}, error: `${label}必须是 JSON object` };
    }
    const record = parsed as Record<string, unknown>;
    if (rejectDataField && Object.prototype.hasOwnProperty.call(record, 'data')) {
      return { value: {}, error: `${label}不能包含 data；业务响应请填写在“业务响应 data Demo”` };
    }
    return { value: record, error: '' };
  } catch {
    return { value: {}, error: `${label}不是合法 JSON` };
  }
}

function defaultMessage(type: A2uiMessageType, surfaceId: string): A2uiMessage {
  const version = 'v0.9.1' as const;
  switch (type) {
    case 'createSurface':
      return { version, createSurface: { surfaceId, catalogId: '' } };
    case 'updateComponents':
      return { version, updateComponents: { surfaceId, components: [] } };
    case 'updateDataModel':
      return { version, updateDataModel: { surfaceId, path: '/', value: null } };
    case 'deleteSurface':
      return { version, deleteSurface: { surfaceId } };
    default:
      return { version };
  }
}

function nextAdapterId(binding: A2uiActionBinding, outcome: A2uiOutcomeKind): string {
  const adapters = outcome === 'success' ? binding.resultAdapters : binding.failureResultAdapters;
  const prefix = `${binding.bindingId}-${outcome}`;
  let index = adapters.length + 1;
  while (adapters.some((adapter) => adapter.adapterId === `${prefix}-${index}`)) index += 1;
  return `${prefix}-${index}`;
}

function createMessageAdapter(
  binding: A2uiActionBinding,
  outcome: A2uiOutcomeKind,
  type: A2uiMessageType,
): A2uiResultAdapter {
  const adapters = outcome === 'success' ? binding.resultAdapters : binding.failureResultAdapters;
  return {
    adapterId: nextAdapterId(binding, outcome),
    order: adapters.length + 1,
    type: 'MESSAGE_TEMPLATE',
    messageTemplate: defaultMessage(type, binding.surfaceId),
    bindings: [],
  };
}

function createPassthroughAdapter(
  binding: A2uiActionBinding,
  outcome: A2uiOutcomeKind,
): A2uiResultAdapter {
  const adapters = outcome === 'success' ? binding.resultAdapters : binding.failureResultAdapters;
  return {
    adapterId: nextAdapterId(binding, outcome),
    order: adapters.length + 1,
    type: 'A2UI_PASSTHROUGH',
    source: 'CAPABILITY_DATA',
    sourcePath: '/a2uiMessages',
    cardinality: 'MANY',
    required: true,
    emittedActionDeclarations: [],
  };
}

function createBusinessSuccessPredicate(): A2uiBusinessSuccessPredicate {
  return { version: 'JSON_POINTER_V1', allOf: [] };
}

function createBusinessPredicateClause(): A2uiBusinessPredicateClause {
  return {
    source: 'CAPABILITY_DATA',
    sourcePath: '',
    operator: 'EQUALS',
    expectedValue: null,
  };
}

interface AdapterPipelineEditorProps {
  outcome: A2uiOutcomeKind;
  binding: A2uiActionBinding;
  catalogOptions: Array<{ value: string; label: string }>;
  demoCapabilityData: Record<string, unknown>;
  demoCapabilityMeta: Record<string, unknown>;
  onChange: (binding: A2uiActionBinding) => void;
}

const AdapterPipelineEditor: React.FC<AdapterPipelineEditorProps> = ({
  outcome,
  binding,
  catalogOptions,
  demoCapabilityData,
  demoCapabilityMeta,
  onChange,
}) => {
  const outcomeField = outcome === 'success' ? 'successOutcome' : 'failureOutcome';
  const adaptersField = outcome === 'success' ? 'resultAdapters' : 'failureResultAdapters';
  const adapters = binding[adaptersField];
  const outcomeValue = binding[outcomeField] || 'ADAPTER_PIPELINE';

  const updateAdapters = (next: A2uiResultAdapter[]) =>
    onChange({
      ...binding,
      [adaptersField]: next,
    });
  const updateAdapter = (index: number, patch: Partial<A2uiResultAdapter>) =>
    updateAdapters(
      adapters.map((adapter, adapterIndex) =>
        adapterIndex === index ? { ...adapter, ...patch } : adapter,
      ),
    );
  const updateTemplatePayload = (
    index: number,
    type: A2uiMessageType,
    patch: Record<string, unknown>,
  ) => {
    const adapter = adapters[index];
    const current = objectValue(adapter?.messageTemplate?.[type]);
    updateAdapter(index, {
      messageTemplate: { version: 'v0.9.1', [type]: { ...current, ...patch } },
    });
  };
  const updateTemplateBindings = (index: number, bindings: A2uiMessageTemplateBinding[]) =>
    updateAdapter(index, { bindings });

  return (
    <Card
      size="small"
      title={outcome === 'success' ? '成功结果' : '失败结果'}
      extra={
        <Select
          size="small"
          value={outcomeValue}
          style={{ width: 180 }}
          options={['ADAPTER_PIPELINE', 'NO_UI_MESSAGES'].map((value) => ({ value, label: value }))}
          onChange={(value) => onChange({ ...binding, [outcomeField]: value as A2uiResultOutcome })}
        />
      }
    >
      {outcomeValue === 'NO_UI_MESSAGES' ? (
        <Alert type="info" message="该分支显式不返回 UI Message" />
      ) : (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space wrap>
            <Button
              size="small"
              onClick={() =>
                updateAdapters([
                  ...adapters,
                  createMessageAdapter(binding, outcome, 'updateDataModel'),
                ])
              }
            >
              新增 updateDataModel
            </Button>
            <Button
              size="small"
              onClick={() =>
                updateAdapters([
                  ...adapters,
                  createMessageAdapter(binding, outcome, 'updateComponents'),
                ])
              }
            >
              新增 updateComponents
            </Button>
            <Button
              size="small"
              onClick={() =>
                updateAdapters([...adapters, createPassthroughAdapter(binding, outcome)])
              }
            >
              新增 A2UI_PASSTHROUGH
            </Button>
          </Space>
          {adapters.map((adapter, index) => {
            const type = adapter.messageTemplate
              ? (serverMessageKey(adapter.messageTemplate) as A2uiMessageType | undefined)
              : undefined;
            const payload = type ? objectValue(adapter.messageTemplate?.[type]) : {};
            const resolution =
              adapter.type === 'MESSAGE_TEMPLATE'
                ? resolveA2uiMessageTemplateAdapter(adapter, demoCapabilityData, demoCapabilityMeta)
                : undefined;
            return (
              <Card
                key={`${adapter.adapterId}:${index}`}
                size="small"
                title={
                  <Space>
                    <Tag color="blue">#{adapter.order}</Tag>
                    <Input
                      value={adapter.adapterId}
                      style={{ width: 260 }}
                      onChange={(event) => updateAdapter(index, { adapterId: event.target.value })}
                    />
                    <Tag>{adapter.type}</Tag>
                  </Space>
                }
                extra={
                  <Button
                    size="small"
                    danger
                    onClick={() =>
                      updateAdapters(
                        adapters.filter((_item, adapterIndex) => adapterIndex !== index),
                      )
                    }
                  >
                    删除
                  </Button>
                }
              >
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <Input
                    addonBefore="执行顺序"
                    value={String(adapter.order)}
                    onChange={(event) =>
                      updateAdapter(index, { order: Number(event.target.value) || 0 })
                    }
                  />
                  {adapter.type === 'MESSAGE_TEMPLATE' ? (
                    <>
                      <Select
                        value={type}
                        placeholder="选择 A2UI Message 类型"
                        style={{ width: 260 }}
                        options={[
                          'createSurface',
                          'updateComponents',
                          'updateDataModel',
                          'deleteSurface',
                        ].map((value) => ({ value, label: value }))}
                        onChange={(value) =>
                          updateAdapter(index, {
                            messageTemplate: defaultMessage(
                              value as A2uiMessageType,
                              binding.surfaceId,
                            ),
                          })
                        }
                      />
                      {type ? (
                        <Input
                          addonBefore="surfaceId"
                          value={String(payload.surfaceId || '')}
                          onChange={(event) =>
                            updateTemplatePayload(index, type, { surfaceId: event.target.value })
                          }
                        />
                      ) : null}
                      {type === 'createSurface' ? (
                        <Select
                          showSearch
                          optionFilterProp="label"
                          value={String(payload.catalogId || '') || undefined}
                          placeholder="选择已发布 Catalog"
                          disabled={!catalogOptions.length}
                          options={catalogOptions}
                          style={{ width: '100%' }}
                          onChange={(catalogId) =>
                            updateTemplatePayload(index, type, { catalogId })
                          }
                        />
                      ) : null}
                      {type === 'updateDataModel' ? (
                        <>
                          <Input
                            addonBefore="path"
                            value={String(payload.path || '')}
                            onChange={(event) =>
                              updateTemplatePayload(index, type, { path: event.target.value })
                            }
                          />
                          <A2uiJsonValueEditor
                            value={payload.value}
                            onApply={(value) => updateTemplatePayload(index, type, { value })}
                          />
                        </>
                      ) : null}
                      {type === 'updateComponents' ? (
                        <A2uiJsonValueEditor
                          expectedArray
                          value={payload.components || []}
                          onApply={(components) =>
                            updateTemplatePayload(index, type, { components })
                          }
                        />
                      ) : null}
                      <Table<A2uiMessageTemplateBinding>
                        rowKey={(_item, bindingIndex) => String(bindingIndex)}
                        dataSource={adapter.bindings || []}
                        pagination={false}
                        columns={[
                          {
                            title: '目标 JSON Pointer',
                            render: (_value, item, bindingIndex) => (
                              <Input
                                value={item.targetPath}
                                onChange={(event) =>
                                  updateTemplateBindings(
                                    index,
                                    (adapter.bindings || []).map((candidate, itemIndex) =>
                                      itemIndex === bindingIndex
                                        ? { ...candidate, targetPath: event.target.value }
                                        : candidate,
                                    ),
                                  )
                                }
                              />
                            ),
                          },
                          {
                            title: '来源',
                            width: 190,
                            render: (_value, item, bindingIndex) => (
                              <Select
                                value={item.source}
                                style={{ width: '100%' }}
                                options={RESULT_SOURCE_OPTIONS}
                                onChange={(value) =>
                                  updateTemplateBindings(
                                    index,
                                    (adapter.bindings || []).map((candidate, itemIndex) =>
                                      itemIndex === bindingIndex
                                        ? {
                                            ...candidate,
                                            source: value as A2uiMessageTemplateBinding['source'],
                                          }
                                        : candidate,
                                    ),
                                  )
                                }
                              />
                            ),
                          },
                          {
                            title: '来源 JSON Pointer / 常量 JSON',
                            render: (_value, item, bindingIndex) =>
                              item.source === 'CONSTANT' ? (
                                <A2uiJsonValueEditor
                                  value={item.constantValue}
                                  onApply={(constantValue) =>
                                    updateTemplateBindings(
                                      index,
                                      (adapter.bindings || []).map((candidate, itemIndex) =>
                                        itemIndex === bindingIndex
                                          ? { ...candidate, constantValue }
                                          : candidate,
                                      ),
                                    )
                                  }
                                />
                              ) : (
                                <Input
                                  value={item.sourcePath}
                                  onChange={(event) =>
                                    updateTemplateBindings(
                                      index,
                                      (adapter.bindings || []).map((candidate, itemIndex) =>
                                        itemIndex === bindingIndex
                                          ? { ...candidate, sourcePath: event.target.value }
                                          : candidate,
                                      ),
                                    )
                                  }
                                />
                              ),
                          },
                          {
                            title: '必填',
                            width: 70,
                            render: (_value, item, bindingIndex) => (
                              <Checkbox
                                checked={item.required}
                                onChange={(event) =>
                                  updateTemplateBindings(
                                    index,
                                    (adapter.bindings || []).map((candidate, itemIndex) =>
                                      itemIndex === bindingIndex
                                        ? { ...candidate, required: event.target.checked }
                                        : candidate,
                                    ),
                                  )
                                }
                              />
                            ),
                          },
                          {
                            title: '操作',
                            width: 80,
                            render: (_value, _item, bindingIndex) => (
                              <Button
                                size="small"
                                danger
                                onClick={() =>
                                  updateTemplateBindings(
                                    index,
                                    (adapter.bindings || []).filter(
                                      (_candidate, itemIndex) => itemIndex !== bindingIndex,
                                    ),
                                  )
                                }
                              >
                                删除
                              </Button>
                            ),
                          },
                        ]}
                      />
                      <Button
                        size="small"
                        onClick={() =>
                          updateTemplateBindings(index, [
                            ...(adapter.bindings || []),
                            {
                              targetPath:
                                type === 'updateComponents'
                                  ? '/updateComponents/components/0'
                                  : '/updateDataModel/value',
                              source: 'CAPABILITY_DATA',
                              sourcePath: '/',
                              required: true,
                            },
                          ])
                        }
                      >
                        新增结果绑定
                      </Button>
                      <Card size="small" title="当前显式结果根展开结果">
                        {resolution?.issues?.length ? (
                          <Alert
                            type="error"
                            message="Adapter 绑定未闭合"
                            description={previewJson(resolution.issues)}
                          />
                        ) : null}
                        <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                          {previewJson(resolution?.message)}
                        </pre>
                      </Card>
                    </>
                  ) : (
                    <>
                      <Space style={{ width: '100%' }}>
                        <Text>来源根</Text>
                        <Select
                          value={adapter.source}
                          style={{ width: 280 }}
                          options={PASSTHROUGH_SOURCE_OPTIONS}
                          onChange={(source) => updateAdapter(index, { source })}
                        />
                      </Space>
                      <Input
                        addonBefore="相对来源根的 JSON Pointer"
                        value={adapter.sourcePath}
                        onChange={(event) =>
                          updateAdapter(index, { sourcePath: event.target.value })
                        }
                      />
                      <Select
                        value={adapter.cardinality || 'MANY'}
                        style={{ width: 180 }}
                        options={['ONE', 'MANY'].map((value) => ({ value, label: value }))}
                        onChange={(cardinality) =>
                          updateAdapter(index, { cardinality: cardinality as 'ONE' | 'MANY' })
                        }
                      />
                      <Checkbox
                        checked={adapter.required}
                        onChange={(event) =>
                          updateAdapter(index, { required: event.target.checked })
                        }
                      >
                        required
                      </Checkbox>
                      <Alert
                        type="info"
                        message="PASSTHROUGH 只从选定的显式来源根读取完整 A2UI Messages"
                        description="若可能产生新 Action，必须在高级 JSON 中显式维护 emittedActionDeclarations；demo/runtime payload 不会成为声明权威。"
                      />
                    </>
                  )}
                </Space>
              </Card>
            );
          })}
          {!adapters.length ? (
            <Alert type="warning" message="当前 outcome 还没有 ResultAdapter" />
          ) : null}
        </Space>
      )}
    </Card>
  );
};

const A2uiActionAuthoringEditor: React.FC<A2uiActionAuthoringEditorProps> = ({
  rows,
  actionBindings,
  catalogOptions,
  capabilityActionOptions,
  onActionBindingsChange,
}) => {
  const [selectedStableKey, setSelectedStableKey] = useState('');
  const [demoCapabilityDataJson, setDemoCapabilityDataJson] = useState('{}');
  const [demoCapabilityMetaJson, setDemoCapabilityMetaJson] = useState(
    '{\n  "success": true,\n  "status": "SUCCEEDED"\n}',
  );
  useEffect(() => {
    if (!rows.some((row) => row.stableKey === selectedStableKey)) {
      setSelectedStableKey(rows?.[0]?.stableKey || '');
    }
  }, [rows, selectedStableKey]);
  const selectedRow = rows.find((row) => row.stableKey === selectedStableKey);
  const demoCapabilityData = useMemo(
    () => parseDemoJson(demoCapabilityDataJson, '业务响应 data Demo'),
    [demoCapabilityDataJson],
  );
  const demoCapabilityMeta = useMemo(
    () => parseDemoJson(demoCapabilityMetaJson, 'Tool 元数据 Demo', true),
    [demoCapabilityMetaJson],
  );

  const updateBinding = (binding: A2uiActionBinding) =>
    onActionBindingsChange(upsertA2uiActionBinding(actionBindings, binding));
  const binding = selectedRow?.binding;

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {!rows.length ? (
        <Alert
          type="warning"
          message="尚未扫描到 ActionDeclaration"
          description="先在展示编排中配置按钮 action.event.name/context，再点击右上角“扫描 Action”。"
        />
      ) : (
        <Table<A2uiActionClosureRow>
          rowKey={(row) => row.stableKey}
          dataSource={rows}
          pagination={false}
          columns={[
            {
              title: '交互点',
              render: (_value, row) =>
                `${row.declaration?.surfaceId} / ${row.declaration?.sourceComponentId}`,
            },
            {
              title: 'actionCode',
              render: (_value, row) => <Text code>{row.declaration?.actionCode}</Text>,
            },
            {
              title: '状态',
              width: 150,
              render: (_value, row) => (
                <Tag
                  color={
                    row.status === 'BOUND'
                      ? 'success'
                      : row.status === 'RESERVED'
                      ? 'error'
                      : 'warning'
                  }
                >
                  {row.status}
                </Tag>
              ),
            },
            {
              title: 'CapabilityAction',
              render: (_value, row) => row.capabilityAction || <Text type="secondary">待配置</Text>,
            },
            {
              title: '操作',
              width: 100,
              render: (_value, row) => (
                <Button
                  size="small"
                  type={selectedStableKey === row.stableKey ? 'primary' : 'default'}
                  disabled={!row.configurable}
                  onClick={() => setSelectedStableKey(row.stableKey)}
                >
                  配置
                </Button>
              ),
            },
          ]}
        />
      )}

      {selectedRow?.status === 'RESERVED' ? (
        <Alert
          type="error"
          message="Workflow 保留 Action 只能由 Adviser Engine 处理，普通 Application 不可配置"
        />
      ) : null}

      {selectedRow?.configurable && !binding ? (
        <Card size="small" title={`${selectedRow.declaration?.actionCode} · 尚未绑定`}>
          <Button
            type="primary"
            onClick={() =>
              updateBinding(createA2uiActionBindingFromDeclaration(selectedRow.declaration))
            }
          >
            创建 ActionBinding
          </Button>
        </Card>
      ) : null}

      {binding ? (
        <>
          <Card size="small" title={`${binding.actionCode} · 动作与请求解析`}>
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Space wrap>
                <Tag>Surface {binding.surfaceId}</Tag>
                <Tag>组件 {binding.sourceComponentId}</Tag>
                <Tag>Binding {binding.bindingId}</Tag>
              </Space>
              <Select
                showSearch
                optionFilterProp="label"
                value={binding.capability?.actionCode || undefined}
                placeholder="按 actionCode 搜索当前环境可用 CapabilityAction"
                disabled={!capabilityActionOptions.length}
                options={capabilityActionOptions}
                style={{ width: '100%' }}
                filterOption={(keyword, option) =>
                  String(option?.value || '')
                    ?.toLowerCase()
                    ?.includes?.(keyword?.trim()?.toLowerCase?.())
                }
                onChange={(actionCode) =>
                  updateBinding({
                    ...binding,
                    capability: { actionCode },
                  })
                }
              />
              <Paragraph type="secondary">
                Capability 版本由运行时解析当前生效版本；这里不填写
                endpoint、版本、身份、Cookie、权限、审批或幂等策略。
              </Paragraph>
              <Checkbox
                checked={binding.completeWorkflowInteractionOnSuccess === true}
                onChange={(event) =>
                  updateBinding({
                    ...binding,
                    completeWorkflowInteractionOnSuccess: event.target.checked,
                  })
                }
              >
                成功后完成 Workflow 交互
              </Checkbox>
              <Paragraph type="secondary">
                仅 INTERACTIVE Application 可勾选；transport
                成功且下方业务成功判定全部成立后才完成当前交互，失败时不会完成。
              </Paragraph>
              <Card
                size="small"
                title="业务成功判定（transport 成功后）"
                extra={
                  binding.businessSuccessPredicate ? (
                    <Button
                      size="small"
                      danger
                      onClick={() =>
                        updateBinding({
                          ...binding,
                          businessSuccessPredicate: undefined,
                        })
                      }
                    >
                      移除判定
                    </Button>
                  ) : (
                    <Button
                      size="small"
                      onClick={() =>
                        updateBinding({
                          ...binding,
                          businessSuccessPredicate: createBusinessSuccessPredicate(),
                        })
                      }
                    >
                      启用判定
                    </Button>
                  )
                }
              >
                {binding.businessSuccessPredicate ? (
                  <Space direction="vertical" size={10} style={{ width: '100%' }}>
                    <Alert
                      type="info"
                      message="JSON_POINTER_V1 · allOf"
                      description="只读取业务响应 data；任一条件缺值、类型不兼容或不成立都选择失败结果，不执行脚本或 fallback。"
                    />
                    <Table<A2uiBusinessPredicateClause>
                      rowKey={(_item, index) => String(index)}
                      dataSource={binding.businessSuccessPredicate?.allOf}
                      pagination={false}
                      columns={[
                        {
                          title: '来源',
                          width: 180,
                          render: () => <Tag>CAPABILITY_DATA</Tag>,
                        },
                        {
                          title: '来源 JSON Pointer',
                          render: (_value, item, index) => (
                            <Input
                              value={item.sourcePath}
                              placeholder="例如 /result"
                              onChange={(event) =>
                                updateBinding({
                                  ...binding,
                                  businessSuccessPredicate: {
                                    ...binding.businessSuccessPredicate!,
                                    allOf: binding.businessSuccessPredicate!.allOf?.map?.(
                                      (candidate, itemIndex) =>
                                        itemIndex === index
                                          ? { ...candidate, sourcePath: event.target.value }
                                          : candidate,
                                    ),
                                  },
                                })
                              }
                            />
                          ),
                        },
                        {
                          title: '比较',
                          width: 190,
                          render: (_value, item, index) => (
                            <Select
                              value={item.operator}
                              style={{ width: '100%' }}
                              options={['EQUALS', 'GREATER_THAN'].map((value) => ({
                                value,
                                label: value,
                              }))}
                              onChange={(operator) =>
                                updateBinding({
                                  ...binding,
                                  businessSuccessPredicate: {
                                    ...binding.businessSuccessPredicate!,
                                    allOf: binding.businessSuccessPredicate!.allOf?.map?.(
                                      (candidate, itemIndex) =>
                                        itemIndex === index
                                          ? { ...candidate, operator }
                                          : candidate,
                                    ),
                                  },
                                })
                              }
                            />
                          ),
                        },
                        {
                          title: '期望 JSON 值',
                          render: (_value, item, index) => (
                            <A2uiJsonValueEditor
                              value={item.expectedValue}
                              onApply={(expectedValue) =>
                                updateBinding({
                                  ...binding,
                                  businessSuccessPredicate: {
                                    ...binding.businessSuccessPredicate!,
                                    allOf: binding.businessSuccessPredicate!.allOf?.map?.(
                                      (candidate, itemIndex) =>
                                        itemIndex === index
                                          ? { ...candidate, expectedValue }
                                          : candidate,
                                    ),
                                  },
                                })
                              }
                            />
                          ),
                        },
                        {
                          title: '操作',
                          width: 80,
                          render: (_value, _item, index) => (
                            <Button
                              size="small"
                              danger
                              onClick={() =>
                                updateBinding({
                                  ...binding,
                                  businessSuccessPredicate: {
                                    ...binding.businessSuccessPredicate!,
                                    allOf: binding.businessSuccessPredicate!.allOf?.filter?.(
                                      (_candidate, itemIndex) => itemIndex !== index,
                                    ),
                                  },
                                })
                              }
                            >
                              删除
                            </Button>
                          ),
                        },
                      ]}
                    />
                    <Button
                      size="small"
                      onClick={() =>
                        updateBinding({
                          ...binding,
                          businessSuccessPredicate: {
                            ...binding.businessSuccessPredicate!,
                            allOf: [
                              ...binding.businessSuccessPredicate!.allOf,
                              createBusinessPredicateClause(),
                            ],
                          },
                        })
                      }
                    >
                      新增 allOf 条件
                    </Button>
                  </Space>
                ) : (
                  <Alert
                    type={binding.completeWorkflowInteractionOnSuccess ? 'error' : 'warning'}
                    message={
                      binding.completeWorkflowInteractionOnSuccess
                        ? '完成型 Action 必须配置业务成功判定'
                        : '未配置时仅按 transport success 选择结果；该 Binding 不能完成 Workflow 交互'
                    }
                  />
                )}
              </Card>
              <Table<A2uiRequestMapping>
                rowKey={(_item, index) => String(index)}
                dataSource={binding.requestMappings}
                pagination={false}
                columns={[
                  {
                    title: '来源',
                    width: 220,
                    render: (_value, item, index) => (
                      <Select
                        value={item.source}
                        style={{ width: '100%' }}
                        options={[
                          'ACTION_CONTEXT',
                          'APP_PARAMS',
                          'TRUSTED_CONTEXT',
                          'CONSTANT',
                          'CAPABILITY_PREVIOUS_RESULT',
                        ].map((value) => ({ value, label: value }))}
                        onChange={(value) =>
                          updateBinding({
                            ...binding,
                            requestMappings: binding.requestMappings?.map?.(
                              (candidate, itemIndex) =>
                                itemIndex === index
                                  ? { ...candidate, source: value as A2uiRequestMapping['source'] }
                                  : candidate,
                            ),
                          })
                        }
                      />
                    ),
                  },
                  {
                    title: '来源 JSON Pointer / 常量 JSON',
                    render: (_value, item, index) =>
                      item.source === 'CONSTANT' ? (
                        <A2uiJsonValueEditor
                          value={item.constantValue}
                          onApply={(constantValue) =>
                            updateBinding({
                              ...binding,
                              requestMappings: binding.requestMappings?.map?.(
                                (candidate, itemIndex) =>
                                  itemIndex === index ? { ...candidate, constantValue } : candidate,
                              ),
                            })
                          }
                        />
                      ) : (
                        <Input
                          value={item.sourcePath}
                          onChange={(event) =>
                            updateBinding({
                              ...binding,
                              requestMappings: binding.requestMappings?.map?.(
                                (candidate, itemIndex) =>
                                  itemIndex === index
                                    ? { ...candidate, sourcePath: event.target.value }
                                    : candidate,
                              ),
                            })
                          }
                        />
                      ),
                  },
                  {
                    title: 'Capability 请求 JSON Pointer',
                    render: (_value, item, index) => (
                      <Input
                        value={item.targetPath}
                        onChange={(event) =>
                          updateBinding({
                            ...binding,
                            requestMappings: binding.requestMappings?.map?.(
                              (candidate, itemIndex) =>
                                itemIndex === index
                                  ? { ...candidate, targetPath: event.target.value }
                                  : candidate,
                            ),
                          })
                        }
                      />
                    ),
                  },
                  {
                    title: '操作',
                    width: 80,
                    render: (_value, _item, index) => (
                      <Button
                        size="small"
                        danger
                        onClick={() =>
                          updateBinding({
                            ...binding,
                            requestMappings: binding.requestMappings?.filter?.(
                              (_candidate, itemIndex) => itemIndex !== index,
                            ),
                          })
                        }
                      >
                        删除
                      </Button>
                    ),
                  },
                ]}
              />
              <Button
                size="small"
                onClick={() =>
                  updateBinding({
                    ...binding,
                    requestMappings: [
                      ...binding.requestMappings,
                      {
                        source: 'ACTION_CONTEXT',
                        sourcePath: '/',
                        targetPath: '/',
                      },
                    ],
                  })
                }
              >
                新增请求映射
              </Button>
            </Space>
          </Card>

          <Card size="small" title="显式结果根 Demo（仅当前会话）">
            <Paragraph type="secondary">
              业务 JSON Pointer 相对原始业务响应 data；Tool 元数据不包含业务
              data，两个根不会互相回退。
            </Paragraph>
            <Text strong>业务响应 data Demo</Text>
            <JsonFormatTextArea
              value={demoCapabilityDataJson}
              onChange={(event) => setDemoCapabilityDataJson(event.target.value)}
              onValueChange={setDemoCapabilityDataJson}
              autoSize={{ minRows: 5, maxRows: 14 }}
            />
            {demoCapabilityData.error ? (
              <Alert type="error" message={demoCapabilityData.error} />
            ) : null}
            <Text strong>Tool 元数据 Demo</Text>
            <JsonFormatTextArea
              value={demoCapabilityMetaJson}
              onChange={(event) => setDemoCapabilityMetaJson(event.target.value)}
              onValueChange={setDemoCapabilityMetaJson}
              autoSize={{ minRows: 4, maxRows: 10 }}
            />
            {demoCapabilityMeta.error ? (
              <Alert type="error" message={demoCapabilityMeta.error} />
            ) : null}
          </Card>

          <AdapterPipelineEditor
            outcome="success"
            binding={binding}
            catalogOptions={catalogOptions}
            demoCapabilityData={demoCapabilityData.value}
            demoCapabilityMeta={demoCapabilityMeta.value}
            onChange={updateBinding}
          />
          <AdapterPipelineEditor
            outcome="failure"
            binding={binding}
            catalogOptions={catalogOptions}
            demoCapabilityData={demoCapabilityData.value}
            demoCapabilityMeta={demoCapabilityMeta.value}
            onChange={updateBinding}
          />
        </>
      ) : null}
    </Space>
  );
};

export default A2uiActionAuthoringEditor;
