import React, { useMemo, useState } from 'react';
import { Alert, Button, Drawer, Input, Select, Space, Tag, Typography } from 'antd';
import { DeleteOutlined, PlusOutlined, SettingOutlined } from '@ant-design/icons';
import type { CapabilityActionDraftData, CapabilityActionInputField } from './api';

const { Text } = Typography;

type ExecutionBinding = CapabilityActionDraftData['executionBinding'];

type MappingEntry = {
  key: string;
  value: string;
};

type MappingEditorProps = {
  title: string;
  description: string;
  keyLabel: string;
  valueLabel: string;
  value?: string;
  jsonValue?: boolean;
  onChange: (value: string) => void;
};

type CapabilityExecutionBindingEditorProps = {
  value: ExecutionBinding;
  inputFields: CapabilityActionInputField[];
  sourceType?: string;
  onChange: (patch: Partial<ExecutionBinding>) => void;
};

function parseMapping(value?: string): { entries: MappingEntry[]; invalid: boolean } {
  if (!value?.trim()) return { entries: [], invalid: false };
  try {
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { entries: [], invalid: true };
    }
    return {
      entries: Object.entries(parsed).map(([key, item]) => ({
        key,
        value: typeof item === 'string' ? item : JSON.stringify(item),
      })),
      invalid: false,
    };
  } catch {
    return { entries: [], invalid: true };
  }
}

function mappingJson(entries: MappingEntry[], jsonValue = false): string {
  const result: Record<string, unknown> = {};
  entries.forEach((entry) => {
    const key = entry.key?.trim?.();
    if (!key) return;
    if (!jsonValue) {
      result[key] = entry.value;
      return;
    }
    try {
      result[key] = JSON.parse(entry.value);
    } catch {
      result[key] = entry.value;
    }
  });
  return JSON.stringify(result, null, 2);
}

function mappingCount(value: ExecutionBinding, inputFields: CapabilityActionInputField[]): number {
  const parsed = parseMapping(value.requestMappingsJson);
  if (!parsed.invalid && parsed.entries.length) return parsed.entries?.length;
  return inputFields?.filter((field) => field.toolField?.trim())?.length;
}

const MappingEditor: React.FC<MappingEditorProps> = ({
  title,
  description,
  keyLabel,
  valueLabel,
  value,
  jsonValue,
  onChange,
}) => {
  const parsed = useMemo(() => parseMapping(value), [value]);
  const [entries, setEntries] = useState<MappingEntry[]>(parsed.entries);

  React.useEffect(() => setEntries(parsed.entries), [value]);

  const updateEntries = (next: MappingEntry[]) => {
    setEntries(next);
    onChange(mappingJson(next, jsonValue));
  };

  return (
    <section className="capability-binding-map-editor">
      <div className="capability-binding-map-header">
        <div>
          <strong>{title}</strong>
          <Text type="secondary">{description}</Text>
        </div>
        <Button
          size="small"
          icon={<PlusOutlined />}
          onClick={() => updateEntries([...entries, { key: '', value: '' }])}
        >
          添加
        </Button>
      </div>
      {parsed.invalid ? (
        <Alert
          type="warning"
          showIcon
          message="当前配置不是合法 JSON 对象"
          description="点击“重置配置”后再使用结构化字段重新录入。"
          action={
            <Button size="small" onClick={() => updateEntries([])}>
              重置配置
            </Button>
          }
        />
      ) : null}
      <div className="capability-binding-map-columns">
        <Text type="secondary">{keyLabel}</Text>
        <Text type="secondary">{valueLabel}</Text>
        <span />
      </div>
      {entries.length ? (
        entries.map((entry, index) => (
          <div className="capability-binding-map-row" key={`${title}-${index}`}>
            <Input
              value={entry.key}
              placeholder={keyLabel}
              onChange={(event) =>
                updateEntries(
                  entries.map((item, itemIndex) =>
                    itemIndex === index ? { ...item, key: event.target.value } : item,
                  ),
                )
              }
            />
            <Input
              value={entry.value}
              placeholder={valueLabel}
              onChange={(event) =>
                updateEntries(
                  entries.map((item, itemIndex) =>
                    itemIndex === index ? { ...item, value: event.target.value } : item,
                  ),
                )
              }
            />
            <Button
              icon={<DeleteOutlined />}
              aria-label={`删除${title}第${index + 1}项`}
              onClick={() => updateEntries(entries.filter((_, itemIndex) => itemIndex !== index))}
            />
          </div>
        ))
      ) : (
        <Text type="secondary">暂无配置，系统将使用安全默认值。</Text>
      )}
    </section>
  );
};

const CapabilityExecutionBindingEditor: React.FC<CapabilityExecutionBindingEditorProps> = ({ value, inputFields, onChange }) => {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const target = value.target || {};
  const updateTarget = (patch: NonNullable<ExecutionBinding['target']>) => onChange({ target: { ...target, ...patch } });
  return (
    <>
      <div className="capability-binding-summary">
        <div className="capability-binding-summary-head">
          <div><h3>执行摘要</h3><Text type="secondary">通过 gRPC 调用业务服务；目标地址和可信身份由平台配置。</Text></div>
          <Button icon={<SettingOutlined />} onClick={() => setAdvancedOpen(true)}>高级配置</Button>
        </div>
        <div className="capability-binding-summary-grid">
          <div><Text type="secondary">调用协议</Text><Tag color="blue">gRPC · Unary</Tag></div>
          <div><Text type="secondary">服务方法</Text><Text>{target.serviceName || '待填写服务'} / {target.methodName || '待填写方法'}</Text></div>
          <div><Text type="secondary">环境路由配置键</Text><Text>{target.targetKey || '待填写配置键'}</Text></div>
          <div><Text type="secondary">可信身份</Text><Text>由 Host 注入，不接受浏览器覆盖</Text></div>
          <div><Text type="secondary">参数映射</Text><Text>{mappingCount(value, inputFields)} 个字段</Text></div>
        </div>
      </div>
      <div className="capability-form-grid capability-binding-advanced-fields">
        <label>业务服务配置键<Input value={target.targetKey} placeholder="例如 order-service" onChange={(event) => updateTarget({ targetKey: event.target.value })} /></label>
        <label>完整服务名<Input value={target.serviceName} placeholder="例如 a2flow.orders.OrderService" onChange={(event) => updateTarget({ serviceName: event.target.value })} /></label>
        <label>方法名<Input value={target.methodName} placeholder="例如 QueryOrders" onChange={(event) => updateTarget({ methodName: event.target.value })} /></label>
        <label>身份上下文字段<Input value={target.contextField || 'context'} onChange={(event) => updateTarget({ contextField: event.target.value })} /></label>
        <label className="capability-form-field-wide">协议描述文件（Base64）
          <Input.TextArea value={target.descriptorSetBase64} autoSize={{ minRows: 3, maxRows: 7 }} placeholder="粘贴包含依赖的 FileDescriptorSet 的 Base64 编码" onChange={(event) => updateTarget({ descriptorSetBase64: event.target.value })} />
          <Text type="secondary">使用 protoc --include_imports 生成 FileDescriptorSet；仅支持一元请求/响应。实际服务、方法与字段由后端解析描述文件校验。</Text>
        </label>
      </div>
      <MappingEditor title="请求字段映射" description="模型字段 → Protobuf 请求字段路径；参数类型必须与协议描述一致。" keyLabel="模型字段" valueLabel="请求字段路径" value={value.requestMappingsJson} onChange={(requestMappingsJson) => onChange({ requestMappingsJson })} />
      <Drawer title="执行绑定高级配置" visible={advancedOpen} width={760} onClose={() => setAdvancedOpen(false)}>
        <Alert type="info" showIcon message="环境地址和 TLS 由平台配置" description="PRT / ONLINE 按业务服务配置键分别解析。草稿只登记服务、方法和协议；不包含访问凭证或环境地址。" />
        <div className="capability-form-grid capability-binding-advanced-fields">
          <label>超时毫秒（1—120000）<Input type="number" min={1} max={120000} value={value.timeoutMs} onChange={(event) => onChange({ timeoutMs: event.target.value })} /></label>
          <label>最大响应字节（最多 5 MiB）<Input type="number" min={1} max={5242880} value={value.maxResponseBytes} onChange={(event) => onChange({ maxResponseBytes: event.target.value })} /></label>
          <label>重试策略<Input value="不自动重试" disabled /></label>
          <label>响应策略<Input value="保留原始响应（ProtoJSON）" disabled /></label>
        </div>
        <Alert type="info" showIcon message="常量和系统变量由参数契约维护" description="可信系统上下文由 Host 注入。int64 字段使用十进制字符串，避免 JavaScript 数值精度丢失。" />
      </Drawer>
    </>
  );
};

export default CapabilityExecutionBindingEditor;
