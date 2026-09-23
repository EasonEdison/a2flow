import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Empty,
  Input,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  CheckOutlined,
  DeleteOutlined,
  EyeOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { jsonParse, jsonStringify } from './shared/safeJson';
import { useNavigate } from 'react-router-dom';
import {
  componentCenterApi,
  type CapabilityPresentationComponent,
  type CapabilityPresentationUsage,
} from './api';
import { DSL_TYPE_BUSINESS_DSL, DSL_TYPE_CARD_CONTAINER } from './cardContainerTemplate';
import type { ComponentRenderPreviewResult, SkillFactoryComponentAsset } from './types';

const { Text, Paragraph } = Typography;

const ALL_PROTOCOLS = 'ALL';

const protocolOptions = [
  { label: '全部协议', value: ALL_PROTOCOLS },
  { label: 'CARD_CONTAINER', value: 'CARD_CONTAINER' },
  { label: 'BUSINESS_DSL', value: 'BUSINESS_DSL' },
];

const usageOptions: Array<{ label: string; value: CapabilityPresentationUsage }> = [
  { label: '成功结果', value: 'SUCCESS_RESULT' },
  { label: '审批确认', value: 'APPROVAL_INTERACTION' },
  { label: '异常提示', value: 'ERROR_RESULT' },
];

const protocolColors: Record<string, string> = {
  CARD_CONTAINER: 'blue',
  BUSINESS_DSL: 'geekblue',
};

interface CapabilityPresentationComponentsProps {
  value?: CapabilityPresentationComponent[];
  onChange: (components: CapabilityPresentationComponent[]) => void;
}

function assetKey(asset: Pick<SkillFactoryComponentAsset, 'id' | 'componentName'>): string {
  return asset.id ? String(asset.id) : asset.componentName;
}

function referenceKey(
  reference: Pick<CapabilityPresentationComponent, 'assetId' | 'componentName'>,
): string {
  return reference.assetId ? String(reference.assetId) : reference.componentName;
}

function toReference(asset: SkillFactoryComponentAsset): CapabilityPresentationComponent {
  return {
    assetId: asset.id,
    componentName: asset.componentName,
    componentNameCn: asset.componentNameCn,
    assetType: asset.assetType,
    renderProtocol: asset.dslType || asset.assetType,
    dslType: asset.dslType,
    agentUiDsl: asset.agentUiDsl,
    componentVersion: asset.publishedVersion ? String(asset.publishedVersion) : undefined,
    protocolVersion: String(asset.protocolVersion),
    usage: 'SUCCESS_RESULT',
    paramsMapping: {},
  };
}

function previewRequest(asset: SkillFactoryComponentAsset) {
  const cardContainer = asset.dslType === DSL_TYPE_CARD_CONTAINER;
  const toolArgsJson =
    asset.messageDemoJson ||
    (asset.assetType === 'BUSINESS_DSL' ? asset.officialDemoJson : '') ||
    '{}';
  return {
    assetType: asset.assetType,
    componentName: asset.componentName,
    componentNameCn: asset.componentNameCn,
    agentUiDsl: asset.assetType === 'BUSINESS_DSL' ? asset.agentUiDsl : undefined,
    dslType: asset.assetType === 'BUSINESS_DSL' ? DSL_TYPE_BUSINESS_DSL : DSL_TYPE_CARD_CONTAINER,
    protocolVersion: asset.protocolVersion,
    inputMode:
      asset.assetType === 'BUSINESS_DSL'
        ? ('BUSINESS_DSL' as const)
        : cardContainer
        ? ('CARD_CONTAINER' as const)
        : ('RAW_TEXT' as const),
    source: 'capability-center-authoring',
    clientType: 'PC',
    toolArgsJson,
    paramsSchemaJson: asset.paramsSchemaJson,
    renderTemplateJson: asset.renderTemplateJson,
    officialDemoJson: asset.officialDemoJson,
    allowedActionsJson: asset.allowedActionsJson,
    runtimeConfigJson: asset.runtimeConfigJson,
    bundleUrl: asset.bundleUrl,
    appBundleUrl: asset.appBundleUrl,
  };
}

function previewText(result?: ComponentRenderPreviewResult): string {
  if (!result) return '';
  if (result.renderedContent) return result.renderedContent;
  if (result.renderedJson) return result.renderedJson;
  if (result.data) return jsonStringify(result.data, null, 2) || '';
  if (result.messages) return jsonStringify(result.messages, null, 2) || '';
  return jsonStringify(result.normalizedInput, null, 2) || '';
}

function demoSummary(asset?: SkillFactoryComponentAsset): Record<string, unknown> {
  const parsed = jsonParse(asset?.officialDemoJson || '', {}) as unknown;
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
  const record = parsed as Record<string, unknown>;
  const data = record.data;
  return data && typeof data === 'object' && !Array.isArray(data)
    ? (data as Record<string, unknown>)
    : record;
}

const CapabilityPresentationComponents: React.FC<CapabilityPresentationComponentsProps> = ({
  value = [],
  onChange,
}) => {
  const navigate = useNavigate();
  const [assets, setAssets] = useState<SkillFactoryComponentAsset[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [keyword, setKeyword] = useState('');
  const [protocol, setProtocol] = useState(ALL_PROTOCOLS);
  const [previewAsset, setPreviewAsset] = useState<SkillFactoryComponentAsset>();
  const [previewResult, setPreviewResult] = useState<ComponentRenderPreviewResult>();
  const [previewing, setPreviewing] = useState(false);

  const loadAssets = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const list = await componentCenterApi.enabledList({ enabledOnly: true });
      setAssets((list || []).filter((asset) => asset.enabled));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '可引用组件加载失败');
      setAssets([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAssets();
  }, [loadAssets]);

  const selectedKeys = useMemo(() => new Set(value.map(referenceKey)), [value]);
  const filteredAssets = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();
    return assets.filter((asset) => {
      if (protocol !== ALL_PROTOCOLS && asset.dslType !== protocol) return false;
      if (!normalizedKeyword) return true;
      return [asset.componentName, asset.componentNameCn, asset.scene, asset.agentUiDsl]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
        .includes(normalizedKeyword);
    });
  }, [assets, keyword, protocol]);

  const toggleAsset = (asset: SkillFactoryComponentAsset) => {
    const key = assetKey(asset);
    if (selectedKeys.has(key)) {
      onChange(value.filter((item) => referenceKey(item) !== key));
      return;
    }
    onChange([...value, toReference(asset)]);
  };

  const updateReference = (key: string, patch: Partial<CapabilityPresentationComponent>) => {
    onChange(value.map((item) => (referenceKey(item) === key ? { ...item, ...patch } : item)));
  };

  const addParamMapping = (reference: CapabilityPresentationComponent) => {
    const mapping = { ...(reference.paramsMapping || {}) };
    let index = Object.keys(mapping).length + 1;
    let componentParam = `param${index}`;
    while (Object.prototype.hasOwnProperty.call(mapping, componentParam)) {
      index += 1;
      componentParam = `param${index}`;
    }
    mapping[componentParam] = '';
    updateReference(referenceKey(reference), { paramsMapping: mapping });
  };

  const updateParamMapping = (
    reference: CapabilityPresentationComponent,
    currentParam: string,
    nextParam: string,
    resultPath: string,
  ) => {
    const mapping = { ...(reference.paramsMapping || {}) };
    delete mapping[currentParam];
    mapping[nextParam] = resultPath;
    updateReference(referenceKey(reference), { paramsMapping: mapping });
  };

  const removeParamMapping = (
    reference: CapabilityPresentationComponent,
    componentParam: string,
  ) => {
    const mapping = { ...(reference.paramsMapping || {}) };
    delete mapping[componentParam];
    updateReference(referenceKey(reference), { paramsMapping: mapping });
  };

  const preview = async (asset: SkillFactoryComponentAsset) => {
    setPreviewAsset(asset);
    setPreviewResult(undefined);
    setPreviewing(true);
    try {
      const result = await componentCenterApi.bizRenderPreview(previewRequest(asset));
      setPreviewResult(result);
      message[result.valid ? 'success' : 'warning'](
        result.valid ? '组件预览通过' : '组件预览存在校验问题',
      );
    } catch (previewError) {
      message.error(previewError instanceof Error ? previewError.message : '组件预览失败');
    } finally {
      setPreviewing(false);
    }
  };

  const previewData = demoSummary(previewAsset);

  return (
    <div className="capability-presentation-stage">
      <div className="capability-stage-intro">
        <div>
          <h3>包装组件</h3>
          <Paragraph type="secondary">
            为能力结果声明可选展示方案。Skill 绑定时仍可选择“仅执行”或“执行并渲染”；
            组件协议、模板与版本继续由组件中心维护。
          </Paragraph>
        </div>
        <Tag color={value.length ? 'blue' : 'default'}>{value.length} 个已选择</Tag>
      </div>

      {error ? (
        <Alert
          type="error"
          showIcon
          message="组件列表加载失败"
          description={error}
          action={
            <Button size="small" onClick={loadAssets}>
              重试
            </Button>
          }
        />
      ) : null}

      <div className="capability-component-toolbar">
        <Input
          prefix={<SearchOutlined />}
          value={keyword}
          placeholder="搜索组件名称、场景或 agentUiDsl"
          onChange={(event) => setKeyword(event.target.value)}
        />
        <Select
          value={protocol}
          options={protocolOptions}
          onChange={(value) => setProtocol(String(value || ALL_PROTOCOLS))}
        />
        <Button icon={<ReloadOutlined />} loading={loading} onClick={loadAssets}>
          刷新
        </Button>
      </div>

      <Spin spinning={loading}>
        <div className="capability-component-layout">
          <div className="capability-component-catalog">
            {filteredAssets.length ? (
              filteredAssets.map((asset) => {
                const key = assetKey(asset);
                const selected = selectedKeys.has(key);
                return (
                  <div
                    className={`capability-component-item${selected ? ' selected' : ''}`}
                    key={key}
                  >
                    <div className="capability-component-item-head">
                      <div>
                        <strong>{asset.componentNameCn || asset.componentName}</strong>
                        <span>{asset.componentName}</span>
                      </div>
                      {selected ? (
                        <CheckOutlined className="capability-component-selected-icon" />
                      ) : null}
                    </div>
                    <div className="capability-component-tags">
                      <Tag>{asset.assetType}</Tag>
                      <Tag color={protocolColors[asset.dslType || '']}>{asset.dslType || '-'}</Tag>
                      <Tag>协议 v{asset.protocolVersion}</Tag>
                    </div>
                    <p>{asset.scene || asset.integrationPrompt || '暂无使用场景说明'}</p>
                    <div className="capability-component-item-actions">
                      <Button size="small" onClick={() => toggleAsset(asset)}>
                        {selected ? '移除' : '选择'}
                      </Button>
                      <Button size="small" icon={<EyeOutlined />} onClick={() => preview(asset)}>
                        预览
                      </Button>
                      {asset.id ? (
                        <Button
                          size="small"
                          type="link"
                          onClick={() =>
                            navigate(`/management/components/detail?id=${asset.id}`)
                          }
                        >
                          详情
                        </Button>
                      ) : null}
                    </div>
                  </div>
                );
              })
            ) : (
              <Empty description="没有匹配的可引用组件" />
            )}
          </div>

          <div className="capability-component-preview">
            <div className="capability-component-preview-head">
              <strong>组件预览</strong>
              {previewResult ? (
                <Tag color={previewResult.valid ? 'success' : 'error'}>
                  {previewResult.valid ? 'READY' : 'ERROR'}
                </Tag>
              ) : null}
            </div>
            {previewAsset ? (
              <Spin spinning={previewing}>
                <div className="component-center-render-card capability-component-preview-card">
                  <Text type="secondary">{previewAsset.dslType || previewAsset.assetType}</Text>
                  <h3>
                    {String(
                      previewData.title ||
                        previewAsset.componentNameCn ||
                        previewAsset.componentName,
                    )}
                  </h3>
                  <p>
                    {String(
                      previewData.description ||
                        previewData.desc ||
                        previewAsset.scene ||
                        '组件官方示例',
                    )}
                  </p>
                  <Space wrap>
                    <Tag>协议 v{previewAsset.protocolVersion}</Tag>
                    {previewAsset.publishedVersion ? (
                      <Tag>发布 v{previewAsset.publishedVersion}</Tag>
                    ) : null}
                  </Space>
                </div>
                {previewResult?.errors?.length ? (
                  <Alert type="error" showIcon message={previewResult.errors.join('；')} />
                ) : null}
                {previewText(previewResult) ? (
                  <pre className="component-center-json-code capability-component-preview-code">
                    {previewText(previewResult)}
                  </pre>
                ) : null}
              </Spin>
            ) : (
              <Empty description="选择“预览”查看组件包装效果" />
            )}
          </div>
        </div>
      </Spin>

      <div className="capability-selected-components">
        <div className="capability-stage-intro compact">
          <div>
            <h3>可选展示组件</h3>
            <Text type="secondary">
              参数映射方向固定为“组件参数 → 能力结果路径”，保存后随能力草稿恢复。
            </Text>
          </div>
        </div>
        {value.length ? (
          value.map((reference) => {
            const key = referenceKey(reference);
            return (
              <div className="capability-selected-component-row" key={key}>
                <div className="capability-selected-component-identity">
                  <strong>{reference.componentNameCn || reference.componentName}</strong>
                  <span>{reference.componentName}</span>
                </div>
                <Select
                  value={reference.usage}
                  options={usageOptions}
                  onChange={(usage) =>
                    updateReference(key, { usage: usage as CapabilityPresentationUsage })
                  }
                />
                <Button
                  onClick={() => onChange(value.filter((item) => referenceKey(item) !== key))}
                >
                  移除
                </Button>
                <div className="capability-component-param-mappings">
                  <div className="capability-component-param-mappings-head">
                    <div>
                      <strong>组件参数映射</strong>
                      <span>例如 items → data.liveList</span>
                    </div>
                    <Button
                      size="small"
                      icon={<PlusOutlined />}
                      onClick={() => addParamMapping(reference)}
                    >
                      添加映射
                    </Button>
                  </div>
                  {Object.entries(reference.paramsMapping || {}).length ? (
                    Object.entries(reference.paramsMapping || {}).map(
                      ([componentParam, resultPath]) => (
                        <div
                          className="capability-component-param-mapping-row"
                          key={componentParam}
                        >
                          <Input
                            value={componentParam}
                            placeholder="组件参数，如 items"
                            onChange={(event) =>
                              updateParamMapping(
                                reference,
                                componentParam,
                                event.target.value,
                                resultPath,
                              )
                            }
                          />
                          <span>←</span>
                          <Input
                            value={resultPath}
                            placeholder="能力结果路径，如 data.liveList"
                            onChange={(event) =>
                              updateParamMapping(
                                reference,
                                componentParam,
                                componentParam,
                                event.target.value,
                              )
                            }
                          />
                          <Button
                            aria-label="删除参数映射"
                            icon={<DeleteOutlined />}
                            onClick={() => removeParamMapping(reference, componentParam)}
                          />
                        </div>
                      ),
                    )
                  ) : (
                    <Text type="secondary">至少添加一项映射，才能供 Skill 的渲染模式使用。</Text>
                  )}
                </div>
              </div>
            );
          })
        ) : (
          <Empty description="尚未绑定包装组件" />
        )}
      </div>
    </div>
  );
};

export default CapabilityPresentationComponents;
