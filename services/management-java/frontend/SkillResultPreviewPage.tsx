import React, { useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Empty,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import { ArrowLeftOutlined, EyeOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { jsonParse, jsonStringify } from './shared/safeJson';
import { useNavigate } from 'react-router-dom';
import { componentCenterApi } from './api';
import JsonFormatTextArea from './shared/JsonFormatTextArea';
import DynamicCardContainerPreview from './shared/DynamicCardContainerPreview';
import type { ComponentRenderPreviewParams, ComponentRenderPreviewResult } from './types';
import { DSL_TYPE_BUSINESS_DSL, DSL_TYPE_CARD_CONTAINER } from './cardContainerTemplate';

const { Text } = Typography;

const DEFAULT_INPUT =
  jsonStringify(
    {
      dslType: DSL_TYPE_CARD_CONTAINER,
      componentName: 'StoreDiagnostic',
      params: {
        description: '今日已为您诊断出以下问题，请及时处理：',
        cards: [
          {
            iconUrl: 'https://example.com/icon_score.png',
            imageUrl: '',
            description: '店铺体验分较昨日下降0.30分，请关注降分原因并及时改善。',
            buttons: [
              {
                text: '立即诊断',
                sendText: '帮我诊断店铺体验分下降原因',
                actionType: 'SEND_TEXT',
                pcUrl: '',
                mobileUrl: '',
              },
            ],
          },
        ],
      },
    },
    null,
    2,
  ) || '{}';

const clientTypeOptions = [
  { label: 'PC', value: 'PC' },
  { label: 'APP', value: 'APP' },
];

function recordOf(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function stringOf(value: unknown): string {
  if (value === undefined || value === null) return '';
  return String(value);
}

function formatJson(value: unknown): string {
  if (typeof value === 'string') {
    const parsed = jsonParse(value, null);
    return parsed ? jsonStringify(parsed, null, 2) || value : value;
  }
  return jsonStringify(value ?? {}, null, 2) || '{}';
}

function parseInput(value: string): {
  rawLength: number;
  parseableJson: boolean;
  inferredMode: string;
  parsed?: Record<string, unknown>;
} {
  const raw = value || '';
  const parsed = jsonParse(raw.trim(), null);
  const parsedRecord = recordOf(parsed);
  let inferredMode = 'INVALID_TOOL_ARGUMENTS';
  if (parsedRecord?.dslType === DSL_TYPE_BUSINESS_DSL) inferredMode = 'BUSINESS_DSL';
  if (parsedRecord?.dslType === DSL_TYPE_CARD_CONTAINER) inferredMode = 'CARD_CONTAINER';
  return {
    rawLength: raw.length,
    parseableJson: Boolean(parsedRecord),
    inferredMode,
    parsed: parsedRecord || undefined,
  };
}

function stringField(record: Record<string, unknown> | undefined, fields: string[]): string {
  if (!record) return '';
  for (const field of fields) {
    const value = record[field];
    if (typeof value === 'string' && value.trim()) return value;
    if (typeof value === 'number') return String(value);
  }
  return '';
}

function compactRequest(params: ComponentRenderPreviewParams): ComponentRenderPreviewParams {
  return Object.entries(params).reduce<Record<string, unknown>>((acc, [key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      acc[key] = value;
    }
    return acc;
  }, {}) as ComponentRenderPreviewParams;
}

function buildPreviewRequest(
  toolArgsJson: string,
  clientType: string,
): ComponentRenderPreviewParams {
  return compactRequest({
    source: 'component-center-skill-result-preview',
    clientType,
    toolArgsJson,
  });
}

function firstRecord(...values: unknown[]): Record<string, unknown> {
  for (const value of values) {
    const record = recordOf(value);
    if (record) return record;
  }
  return {};
}

function resultPayloadForPreview(result?: ComponentRenderPreviewResult): unknown {
  if (!result) return undefined;
  if (result.messages?.length) return result.messages;
  if (result.data !== undefined && result.data !== null) return result.data;
  return undefined;
}

const JsonBlock: React.FC<{ value: unknown; maxHeight?: number }> = ({
  value,
  maxHeight = 260,
}) => (
  <pre className="skill-result-json-block" style={{ maxHeight }}>
    {formatJson(value)}
  </pre>
);

const ProcessStep: React.FC<{
  title: string;
  status: 'READY' | 'WAITING' | 'ERROR';
  children: React.ReactNode;
}> = ({ title, status, children }) => (
  <div className="skill-result-process-step">
    <div className="skill-result-process-head">
      <strong>{title}</strong>
      <Tag color={status === 'READY' ? 'success' : status === 'ERROR' ? 'error' : 'default'}>
        {status}
      </Tag>
    </div>
    {children}
  </div>
);

const DataPreview: React.FC<{ value: unknown }> = ({ value }) => {
  if (Array.isArray(value)) {
    return (
      <div className="skill-result-data-list">
        {value.slice(0, 6).map((item, index) => {
          const record = recordOf(item) || {};
          const title =
            stringField(record, ['title', 'name', 'label', 'componentName']) || `#${index + 1}`;
          const desc = stringField(record, ['desc', 'description', 'summary', 'text']);
          return (
            <div className="skill-result-data-row" key={`${title}-${index}`}>
              <strong>{title}</strong>
              {desc ? <span>{desc}</span> : <Text code>{formatJson(record)}</Text>}
            </div>
          );
        })}
      </div>
    );
  }

  const record = recordOf(value);
  if (!record) {
    return <div className="skill-result-render-text">{stringOf(value) || '-'}</div>;
  }

  const entries = Object.entries(record).slice(0, 8);
  return (
    <div className="skill-result-key-values">
      {entries.map(([key, val]) => (
        <div key={key}>
          <Text type="secondary">{key}</Text>
          {typeof val === 'object' && val !== null ? (
            <Text code>{Array.isArray(val) ? `${val.length} items` : 'object'}</Text>
          ) : (
            <span>{stringOf(val) || '-'}</span>
          )}
        </div>
      ))}
    </div>
  );
};

const MessagePreview: React.FC<{ messageValue: Record<string, unknown>; index: number }> = ({
  messageValue,
  index,
}) => {
  const payload = firstRecord(
    messageValue.payload,
    messageValue.content,
    messageValue.data,
    messageValue.value,
  );
  const createSurface = recordOf(messageValue.createSurface) || recordOf(payload.createSurface);
  const updateDataModel =
    recordOf(messageValue.updateDataModel) || recordOf(payload.updateDataModel);
  const surfaceProperties = recordOf(createSurface?.surfaceProperties);
  const dataModel = updateDataModel?.value || payload.dataModel || messageValue.data || payload;
  const title =
    stringField(surfaceProperties || undefined, ['title']) ||
    stringField(messageValue, ['title', 'componentName', 'eventType', 'method', 'type']) ||
    `A2UI message ${index + 1}`;
  const messageType =
    stringField(messageValue, ['messageType', 'type', 'method', 'eventType']) ||
    stringField(payload, ['messageType', 'type', 'method', 'eventType']) ||
    'message';

  return (
    <div className="skill-result-message-card">
      <div className="skill-result-message-head">
        <Tag color="magenta">{messageType}</Tag>
        <strong>{title}</strong>
      </div>
      <DataPreview value={dataModel} />
    </div>
  );
};

const RenderSurface: React.FC<{
  result?: ComponentRenderPreviewResult;
  clientType: 'PC' | 'APP';
}> = ({ result, clientType }) => {
  if (!result) return <Empty description="暂无预览结果" />;
  if (!result.valid) {
    return (
      <div className="skill-result-render-error">
        <Tag color="error">校验失败</Tag>
        {result.errors?.map?.((item) => (
          <p key={item}>{item}</p>
        ))}
      </div>
    );
  }

  if (result.messages?.length) {
    return (
      <div className="skill-result-render-surface">
        <div className="skill-result-render-toolbar">
          <Tag color="magenta">A2UI</Tag>
          <Text type="secondary">{result.protocolVersion || result.renderProtocol || '-'}</Text>
        </div>
        {result.messages.map((item, index) => (
          <MessagePreview
            messageValue={item}
            index={index}
            key={`${index}-${formatJson(item).slice(0, 24)}`}
          />
        ))}
      </div>
    );
  }

  if (result.data !== undefined && result.data !== null) {
    if (
      result.dslType === DSL_TYPE_CARD_CONTAINER ||
      result.renderProtocol === DSL_TYPE_CARD_CONTAINER
    ) {
      return <DynamicCardContainerPreview result={result} clientType={clientType} />;
    }
    return (
      <div className="skill-result-render-surface card">
        <div className="skill-result-render-toolbar">
          <Tag color="blue">{result.renderProtocol || 'DATA'}</Tag>
          <Text type="secondary">{result.componentName || result.agentUiDsl || '-'}</Text>
        </div>
        <DataPreview value={result.data} />
      </div>
    );
  }

  return <Empty description="后端未返回可渲染 payload" />;
};

const SkillResultPreviewPage: React.FC = () => {
  const navigate = useNavigate();
  const [renderText, setRenderText] = useState(DEFAULT_INPUT);
  const [clientType, setClientType] = useState<'PC' | 'APP'>('PC');
  const [previewResult, setPreviewResult] = useState<ComponentRenderPreviewResult>();
  const [loading, setLoading] = useState(false);

  const inputSummary = useMemo(() => parseInput(renderText), [renderText]);
  const previewRequest = useMemo(
    () => buildPreviewRequest(renderText, clientType),
    [clientType, renderText],
  );

  const handlePreview = async () => {
    if (!renderText.trim()) {
      message.warning('请输入模型 Tool 调用参数');
      return;
    }
    setLoading(true);
    try {
      const result = await componentCenterApi.bizRenderPreview(previewRequest);
      setPreviewResult(result);
      if (result.valid) {
        message.success('Tool 结果预览通过');
      } else {
        message.warning('Tool 结果预览存在错误');
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Tool 结果预览失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-container component-center-page skill-result-preview-page">
      <div className="page-header component-center-header">
        <div>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/management/components')}
          >
            返回组件中心
          </Button>
          <h1 className="page-title">render_component 结果预览</h1>
          <p className="page-subtitle">
            粘贴模型 Tool arguments，调用与生产一致的 Adviser executor 查看最终渲染 payload
          </p>
        </div>
        <Space>
          <Button onClick={() => setRenderText(DEFAULT_INPUT)}>填入示例</Button>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={loading}
            onClick={handlePreview}
          >
            预览
          </Button>
        </Space>
      </div>

      <Alert
        type="info"
        message="只允许 dslType + componentName/agentUiDsl + params；bundle、模板、身份和 clientType 均由宿主与 ONLINE 资产补齐。"
        style={{ marginBottom: 16 }}
      />

      <div className="skill-result-preview-layout">
        <Card
          title="模型 Tool 调用参数"
          extra={
            <Space>
              <Select
                value={clientType}
                options={clientTypeOptions}
                style={{ width: 88 }}
                onChange={(value) => setClientType(String(value) as 'PC' | 'APP')}
              />
            </Space>
          }
        >
          <JsonFormatTextArea
            value={renderText}
            onChange={(event) => setRenderText(event.target.value)}
            onValueChange={setRenderText}
            placeholder='粘贴 {"dslType":"CARD_CONTAINER","componentName":"StoreDiagnostic","params":{...}}'
            autoSize={{ minRows: 18, maxRows: 30 }}
          />
          <div className="skill-result-input-meta">
            <Tag>{inputSummary.inferredMode}</Tag>
            <Tag color={inputSummary.parseableJson ? 'success' : 'default'}>
              {inputSummary.parseableJson ? 'JSON' : 'TEXT'}
            </Tag>
            <Text type="secondary">{inputSummary.rawLength} chars</Text>
          </div>
        </Card>

        <div className="skill-result-side">
          <Card title="运行结果">
            {previewResult ? (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Space wrap>
                  <Tag color={previewResult.valid ? 'success' : 'error'}>
                    {previewResult.valid ? 'READY' : 'ERROR'}
                  </Tag>
                  <Tag>{previewResult.renderProtocol || '-'}</Tag>
                  {previewResult.dslType ? <Tag>{previewResult.dslType}</Tag> : null}
                  {previewResult.agentUiDsl ? <Tag>{previewResult.agentUiDsl}</Tag> : null}
                  {previewResult.paramsValid !== undefined ? (
                    <Tag color={previewResult.paramsValid ? 'success' : 'error'}>params</Tag>
                  ) : null}
                </Space>
                {previewResult.errors?.length ? (
                  <div className="skill-result-errors">
                    {previewResult.errors.map((item) => (
                      <p key={item}>{item}</p>
                    ))}
                  </div>
                ) : null}
              </Space>
            ) : (
              <Empty description="等待预览" />
            )}
          </Card>

          <Card title="最终前端展示" extra={<EyeOutlined />}>
            <Spin spinning={loading}>
              <RenderSurface result={previewResult} clientType={clientType} />
            </Spin>
          </Card>
        </div>
      </div>

      <div className="skill-result-process-grid">
        <Card title="中间转换过程 JSON">
          <div className="skill-result-process-list">
            <ProcessStep title="输入识别" status="READY">
              <JsonBlock value={inputSummary} />
            </ProcessStep>
            <ProcessStep title="预览请求" status="READY">
              <JsonBlock value={previewRequest} />
            </ProcessStep>
            <ProcessStep
              title="转换响应"
              status={!previewResult ? 'WAITING' : previewResult.valid ? 'READY' : 'ERROR'}
            >
              <JsonBlock value={previewResult || {}} />
            </ProcessStep>
          </div>
        </Card>
        <Card title="可渲染 Payload">
          {previewResult ? (
            <JsonBlock value={resultPayloadForPreview(previewResult)} maxHeight={520} />
          ) : (
            <Empty description="预览后展示 messages 或 data" />
          )}
        </Card>
      </div>
    </div>
  );
};

export default SkillResultPreviewPage;
