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
  message,
} from 'antd';
import { jsonStringify } from './shared/safeJson';
import type {
  A2uiMessage,
  A2uiShowInputBinding,
  A2uiShowTemplate,
} from './a2uiApplicationContracts';
import {
  buildA2uiParamsSchema,
  readA2uiParameterDefinitions,
  resolveA2uiShowMessages,
  type A2uiParameterDefinition,
  type A2uiParameterType,
} from './a2uiApplicationEditorModel';
import { serverMessageKey } from './a2uiApplicationShowAst';
import JsonFormatTextArea from './shared/JsonFormatTextArea';

const { Paragraph, Text } = Typography;

type A2uiServerMessageType =
  | 'createSurface'
  | 'updateComponents'
  | 'updateDataModel'
  | 'deleteSurface';

interface A2uiShowAuthoringEditorProps {
  showTemplate: A2uiShowTemplate;
  sampleParamsJson: string;
  onShowTemplateChange: (showTemplate: A2uiShowTemplate) => void;
  onSampleParamsChange: (value: string) => void;
}

function previewJson(value: unknown): string {
  return jsonStringify(value, null, 2) || '{}';
}

function parseExample(value: string, type: A2uiParameterType): unknown {
  if (type === 'string') return value;
  if (type === 'boolean') return value === 'true';
  if (type === 'number' || type === 'integer') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : value;
  }
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function exampleText(value: unknown): string {
  return typeof value === 'string' ? value : previewJson(value);
}

function createMessage(type: A2uiServerMessageType): A2uiMessage {
  const version = 'v0.9.1' as const;
  switch (type) {
    case 'createSurface':
      return { version, createSurface: { surfaceId: 'main', catalogId: '' } };
    case 'updateComponents':
      return { version, updateComponents: { surfaceId: 'main', components: [] } };
    case 'updateDataModel':
      return { version, updateDataModel: { surfaceId: 'main', path: '/', value: {} } };
    case 'deleteSurface':
      return { version, deleteSurface: { surfaceId: 'main' } };
    default:
      return { version };
  }
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && !Array.isArray(value) && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : {};
}

interface A2uiJsonValueEditorProps {
  value: unknown;
  expectedArray?: boolean;
  onApply: (value: unknown) => void;
}

export const A2uiJsonValueEditor: React.FC<A2uiJsonValueEditorProps> = ({
  value,
  expectedArray,
  onApply,
}) => {
  const [text, setText] = useState(() => previewJson(value));
  useEffect(() => setText(previewJson(value)), [value]);

  const apply = () => {
    try {
      const parsed = JSON.parse(text) as unknown;
      if (expectedArray && !Array.isArray(parsed)) {
        message.error('components 必须是 JSON array');
        return;
      }
      onApply(parsed);
    } catch {
      message.error('当前内容不是合法 JSON');
    }
  };

  return (
    <div>
      <JsonFormatTextArea
        value={text}
        onChange={(event) => setText(event.target.value)}
        onValueChange={setText}
        autoSize={{ minRows: 5, maxRows: 16 }}
      />
      <Button size="small" onClick={apply}>
        应用 JSON
      </Button>
    </div>
  );
};

const PARAMETER_TYPES: A2uiParameterType[] = [
  'string',
  'number',
  'integer',
  'boolean',
  'object',
  'array',
];

const MESSAGE_TYPES: A2uiServerMessageType[] = [
  'createSurface',
  'updateComponents',
  'updateDataModel',
  'deleteSurface',
];

const A2uiShowAuthoringEditor: React.FC<A2uiShowAuthoringEditorProps> = ({
  showTemplate,
  sampleParamsJson,
  onShowTemplateChange,
  onSampleParamsChange,
}) => {
  const [nextMessageType, setNextMessageType] = useState<A2uiServerMessageType>('updateDataModel');
  const parameters = useMemo(
    () => readA2uiParameterDefinitions(showTemplate.paramsSchema),
    [showTemplate.paramsSchema],
  );
  const sampleParams = useMemo(() => {
    try {
      const parsed = JSON.parse(sampleParamsJson) as unknown;
      return parsed && !Array.isArray(parsed) && typeof parsed === 'object'
        ? { value: parsed as Record<string, unknown>, error: '' }
        : { value: {}, error: 'sample params 必须是 JSON object' };
    } catch {
      return { value: {}, error: 'sample params 不是合法 JSON' };
    }
  }, [sampleParamsJson]);
  const resolution = useMemo(
    () => resolveA2uiShowMessages(showTemplate, sampleParams.value),
    [sampleParams.value, showTemplate],
  );

  const updateParameters = (definitions: A2uiParameterDefinition[]) => {
    onShowTemplateChange({
      ...showTemplate,
      paramsSchema: buildA2uiParamsSchema(definitions),
    });
  };

  const updateParameter = (index: number, patch: Partial<A2uiParameterDefinition>) => {
    updateParameters(
      parameters.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)),
    );
  };

  const updateMessage = (index: number, next: A2uiMessage) => {
    onShowTemplateChange({
      ...showTemplate,
      messageTemplates: showTemplate.messageTemplates?.map?.((item, itemIndex) =>
        itemIndex === index ? next : item,
      ),
    });
  };

  const updateMessagePayload = (
    index: number,
    type: A2uiServerMessageType,
    patch: Record<string, unknown>,
  ) => {
    const current = showTemplate.messageTemplates?.[index];
    updateMessage(index, {
      version: 'v0.9.1',
      [type]: { ...objectValue(current?.[type]), ...patch },
    });
  };

  const updateBindings = (inputBindings: A2uiShowInputBinding[]) => {
    onShowTemplateChange({ ...showTemplate, inputBindings });
  };

  const messageOptions = showTemplate.messageTemplates?.map?.((item, index) => ({
    value: index,
    label: `#${index + 1} ${serverMessageKey(item) || 'invalid message'}`,
  }));

  const fillSampleFromExamples = () => {
    const exampleParams = Object.fromEntries(
      parameters.flatMap((item) => (item.example === undefined ? [] : [[item.name, item.example]])),
    );
    onSampleParamsChange(previewJson(exampleParams));
  };

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        size="small"
        title="1. Application 模型参数"
        extra={
          <Button
            size="small"
            onClick={() =>
              updateParameters([
                ...parameters,
                { name: `param${parameters.length + 1}`, type: 'string', required: false },
              ])
            }
          >
            新增参数
          </Button>
        }
      >
        {parameters.length ? (
          <Table<A2uiParameterDefinition>
            rowKey={(item, index) => `${index}:${item.name}`}
            dataSource={parameters}
            pagination={false}
            columns={[
              {
                title: '参数名',
                render: (_value, item, index) => (
                  <Input
                    value={item.name}
                    onChange={(event) => updateParameter(index, { name: event.target.value })}
                  />
                ),
              },
              {
                title: '类型',
                width: 150,
                render: (_value, item, index) => (
                  <Select
                    value={item.type}
                    style={{ width: '100%' }}
                    options={PARAMETER_TYPES.map((type) => ({ value: type, label: type }))}
                    onChange={(type) => updateParameter(index, { type: type as A2uiParameterType })}
                  />
                ),
              },
              {
                title: '必填',
                width: 80,
                render: (_value, item, index) => (
                  <Checkbox
                    checked={item.required}
                    onChange={(event) => updateParameter(index, { required: event.target.checked })}
                  />
                ),
              },
              {
                title: '说明',
                render: (_value, item, index) => (
                  <Input
                    value={item.description}
                    onChange={(event) =>
                      updateParameter(index, { description: event.target.value })
                    }
                  />
                ),
              },
              {
                title: '示例',
                render: (_value, item, index) => (
                  <Input
                    key={`${item.name}:${item.type}:${exampleText(item.example)}`}
                    defaultValue={item.example === undefined ? '' : exampleText(item.example)}
                    onBlur={(event) =>
                      updateParameter(index, {
                        example: parseExample(event.target.value, item.type),
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
                      updateParameters(
                        parameters.filter((_candidate, itemIndex) => itemIndex !== index),
                      )
                    }
                  >
                    删除
                  </Button>
                ),
              },
            ]}
          />
        ) : (
          <Alert
            type="warning"
            message="当前 Application 未定义任何模型输入参数"
            description="Input Schema 不接收业务 params，因此模型输出不会进入 updateComponents 或 updateDataModel。"
          />
        )}
      </Card>

      <Card
        size="small"
        title="2. 初始 A2UI Messages"
        extra={
          <Space>
            <Select
              size="small"
              value={nextMessageType}
              style={{ width: 180 }}
              options={MESSAGE_TYPES.map((type) => ({ value: type, label: type }))}
              onChange={(type) => setNextMessageType(type as A2uiServerMessageType)}
            />
            <Button
              size="small"
              onClick={() =>
                onShowTemplateChange({
                  ...showTemplate,
                  messageTemplates: [
                    ...showTemplate.messageTemplates,
                    createMessage(nextMessageType),
                  ],
                })
              }
            >
              新增消息
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {showTemplate.messageTemplates?.map?.((item, index) => {
            const type = serverMessageKey(item) as A2uiServerMessageType | undefined;
            const payload = type ? objectValue(item[type]) : {};
            return (
              <Card
                key={`${index}:${type}`}
                size="small"
                title={
                  <Space>
                    <Tag color="blue">#{index + 1}</Tag>
                    <Text code>{type || 'invalid message'}</Text>
                  </Space>
                }
                extra={
                  <Button
                    size="small"
                    danger
                    onClick={() =>
                      onShowTemplateChange({
                        ...showTemplate,
                        messageTemplates: showTemplate.messageTemplates?.filter?.(
                          (_candidate, itemIndex) => itemIndex !== index,
                        ),
                      })
                    }
                  >
                    删除
                  </Button>
                }
              >
                {!type ? (
                  <Alert type="error" message="该消息必须且只能包含一种 v0.9.1 server message" />
                ) : (
                  <Space direction="vertical" size={10} style={{ width: '100%' }}>
                    <Input
                      addonBefore="surfaceId"
                      value={String(payload.surfaceId || '')}
                      onChange={(event) =>
                        updateMessagePayload(index, type, { surfaceId: event.target.value })
                      }
                    />
                    {type === 'createSurface' ? (
                      <Input
                        addonBefore="catalogId"
                        value={String(payload.catalogId || '')}
                        onChange={(event) =>
                          updateMessagePayload(index, type, { catalogId: event.target.value })
                        }
                      />
                    ) : null}
                    {type === 'updateDataModel' ? (
                      <>
                        <Input
                          addonBefore="path"
                          value={String(payload.path || '')}
                          onChange={(event) =>
                            updateMessagePayload(index, type, { path: event.target.value })
                          }
                        />
                        <A2uiJsonValueEditor
                          value={payload.value}
                          onApply={(value) => updateMessagePayload(index, type, { value })}
                        />
                      </>
                    ) : null}
                    {type === 'updateComponents' ? (
                      <A2uiJsonValueEditor
                        expectedArray
                        value={payload.components || []}
                        onApply={(components) => updateMessagePayload(index, type, { components })}
                      />
                    ) : null}
                  </Space>
                )}
              </Card>
            );
          })}
          {!showTemplate.messageTemplates?.length ? (
            <Text type="secondary">尚未配置初始消息。</Text>
          ) : null}
        </Space>
      </Card>

      <Card
        size="small"
        title="3. 模型 params → Message 数据绑定"
        extra={
          <Button
            size="small"
            disabled={!messageOptions.length}
            onClick={() =>
              updateBindings([
                ...showTemplate.inputBindings,
                {
                  targetMessageIndex: 0,
                  targetPath: '/updateDataModel/value',
                  source: 'APP_PARAMS',
                  sourcePath: parameters?.[0]?.name ? `/${parameters?.[0]?.name}` : '/',
                  required: true,
                },
              ])
            }
          >
            新增绑定
          </Button>
        }
      >
        <Table<A2uiShowInputBinding>
          rowKey={(_item, index) => String(index)}
          dataSource={showTemplate.inputBindings}
          pagination={false}
          columns={[
            {
              title: '目标消息',
              width: 190,
              render: (_value, item, index) => (
                <Select
                  value={item.targetMessageIndex}
                  style={{ width: '100%' }}
                  options={messageOptions}
                  onChange={(targetMessageIndex) =>
                    updateBindings(
                      showTemplate.inputBindings?.map?.((binding, itemIndex) =>
                        itemIndex === index
                          ? { ...binding, targetMessageIndex: Number(targetMessageIndex) }
                          : binding,
                      ),
                    )
                  }
                />
              ),
            },
            {
              title: '目标 JSON Pointer',
              render: (_value, item, index) => (
                <Input
                  value={item.targetPath}
                  onChange={(event) =>
                    updateBindings(
                      showTemplate.inputBindings?.map?.((binding, itemIndex) =>
                        itemIndex === index
                          ? { ...binding, targetPath: event.target.value }
                          : binding,
                      ),
                    )
                  }
                />
              ),
            },
            {
              title: '来源',
              width: 170,
              render: (_value, item, index) => (
                <Select
                  value={item.source}
                  style={{ width: '100%' }}
                  options={['APP_PARAMS', 'CONSTANT', 'TRUSTED_CONTEXT'].map((source) => ({
                    value: source,
                    label: source,
                  }))}
                  onChange={(source) =>
                    updateBindings(
                      showTemplate.inputBindings?.map?.((binding, itemIndex) =>
                        itemIndex === index
                          ? { ...binding, source: source as A2uiShowInputBinding['source'] }
                          : binding,
                      ),
                    )
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
                      updateBindings(
                        showTemplate.inputBindings?.map?.((binding, itemIndex) =>
                          itemIndex === index ? { ...binding, constantValue } : binding,
                        ),
                      )
                    }
                  />
                ) : (
                  <Input
                    value={item.sourcePath}
                    onChange={(event) =>
                      updateBindings(
                        showTemplate.inputBindings?.map?.((binding, itemIndex) =>
                          itemIndex === index
                            ? { ...binding, sourcePath: event.target.value }
                            : binding,
                        ),
                      )
                    }
                  />
                ),
            },
            {
              title: '必填',
              width: 70,
              render: (_value, item, index) => (
                <Checkbox
                  checked={item.required}
                  onChange={(event) =>
                    updateBindings(
                      showTemplate.inputBindings?.map?.((binding, itemIndex) =>
                        itemIndex === index
                          ? { ...binding, required: event.target.checked }
                          : binding,
                      ),
                    )
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
                    updateBindings(
                      showTemplate.inputBindings?.filter?.(
                        (_candidate, itemIndex) => itemIndex !== index,
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
      </Card>

      <Card
        size="small"
        title="4. sample params 与绑定后消息"
        extra={
          <Button size="small" onClick={fillSampleFromExamples}>
            使用参数示例
          </Button>
        }
      >
        <JsonFormatTextArea
          value={sampleParamsJson}
          onChange={(event) => onSampleParamsChange(event.target.value)}
          onValueChange={onSampleParamsChange}
          autoSize={{ minRows: 5, maxRows: 14 }}
        />
        <Paragraph type="secondary">
          仅当前联调会话使用，不进入草稿、Build、日志或持久化。
        </Paragraph>
        {sampleParams.error ? (
          <Alert type="error" message={sampleParams.error} style={{ marginBottom: 12 }} />
        ) : null}
        {resolution.issues?.length ? (
          <Alert
            type="error"
            message="模型参数尚未完整写入消息"
            description={
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                {previewJson(resolution.issues)}
              </pre>
            }
            style={{ marginBottom: 12 }}
          />
        ) : (
          <Alert
            type="success"
            message="sample params 已展开到最终 A2UI Messages"
            style={{ marginBottom: 12 }}
          />
        )}
        <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{previewJson(resolution.messages)}</pre>
      </Card>
    </Space>
  );
};

export default A2uiShowAuthoringEditor;
