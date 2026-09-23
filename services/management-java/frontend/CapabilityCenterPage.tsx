import React, { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Card,
  Drawer,
  Empty,
  Form,
  Input,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  capabilityCenterApi,
  skillFactoryApi,
  type CapabilityActionDraft,
  type CapabilityCatalogQuery,
  type SkillFactoryPageConfig,
} from './api';
import {
  CAPABILITY_API_SOURCE_TYPE,
  registerCapabilityDraftWithName,
  visibleCapabilityDrafts,
} from './capabilityDraftLifecycle';
import { capabilitySideEffectText, capabilitySourceText } from './shared/capabilityDisplayText';

const { Text } = Typography;

const publishStatusOptions = [
  { value: 'EDITING', label: '编辑中' },
  { value: 'ONLINE', label: '已上线' },
];

function domainOptions(value: SkillFactoryPageConfig['businessDomains']) {
  return (value || [])
    .map((item) => ({
      value: String(item.value || item.code || item.id || '').trim(),
      label: String(item.label || item.name || item.value || '').trim(),
    }))
    .filter((item) => item.value && item.label);
}

function actionCodeOf(item: CapabilityActionDraft): string {
  return item.draft?.basicInfo?.actionCode || '未填写 actionCode';
}

function nameOf(item: CapabilityActionDraft): string {
  return item.draft?.basicInfo?.nameCn || '未命名能力';
}

const CapabilityCenterPage: React.FC = () => {
  const navigate = useNavigate();
  const [keyword, setKeyword] = useState('');
  const [filters, setFilters] = useState<CapabilityCatalogQuery>({});
  const [config, setConfig] = useState<SkillFactoryPageConfig>({});
  const [items, setItems] = useState<CapabilityActionDraft[]>([]);
  const [loading, setLoading] = useState(false);
  const [registrationOpen, setRegistrationOpen] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [registrationForm] = Form.useForm<{ nameCn: string }>();

  const load = useCallback(async (query: CapabilityCatalogQuery) => {
    setLoading(true);
    try {
      setItems(visibleCapabilityDrafts(await capabilityCenterApi.list(query)));
    } catch (error) {
      message.error(error instanceof Error ? error.message : '能力列表加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load({});
    skillFactoryApi
      .config()
      .then(setConfig)
      .catch(() => setConfig({}));
  }, [load]);

  const currentQuery = (): CapabilityCatalogQuery => ({ ...filters, keyword });

  const reset = () => {
    setKeyword('');
    setFilters({});
    load({});
  };

  const openRegistration = () => {
    registrationForm.resetFields();
    setRegistrationOpen(true);
  };

  const confirmRegistration = async () => {
    try {
      const { nameCn } = await registrationForm.validateFields();
      setRegistering(true);
      await registerCapabilityDraftWithName({
        nameCn,
        create: (draft) => capabilityCenterApi.create(draft),
        openEditor: (draftId) => {
          setRegistrationOpen(false);
          navigate(`/management/capabilities/edit?draftId=${draftId}`);
        },
      });
    } catch (error) {
      if (error instanceof Error) {
        message.error(error.message || '能力注册失败');
      }
    } finally {
      setRegistering(false);
    }
  };

  return (
    <div className="page-container capability-center-page">
      <div className="page-header capability-center-header">
        <div>
          <h1 className="page-title">业务能力中心</h1>
          <p className="page-subtitle">
            把技术接口、业务语义和受控执行绑定整理为可复用的 CapabilityAction 草稿。
          </p>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => load(currentQuery())}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openRegistration}>
            注册能力
          </Button>
        </Space>
      </div>

      <Card className="capability-center-filter-card">
        <Space wrap>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索 actionCode 或中文名"
            value={keyword}
            style={{ width: 360 }}
            onChange={(event) => setKeyword(event.target.value)}
            onPressEnter={() => load(currentQuery())}
          />
          <Select
            allowClear
            placeholder="业务域"
            value={filters.businessDomain}
            options={domainOptions(config.businessDomains)}
            style={{ width: 180 }}
            onChange={(value) => setFilters((current) => ({ ...current, businessDomain: value }))}
          />
          <Select
            allowClear
            placeholder="能力域"
            value={filters.capabilityDomain}
            options={domainOptions(config.capabilityDomains)}
            style={{ width: 180 }}
            onChange={(value) => setFilters((current) => ({ ...current, capabilityDomain: value }))}
          />
          <Select
            allowClear
            placeholder="所属专员"
            value={filters.specialistId}
            options={(config.specialists || [])
              .map((item) => ({
                value: String(item.id || item.specialistId || item.value || '').trim(),
                label: String(item.name || item.specialistName || item.label || '').trim(),
              }))
              .filter((item) => item.value && item.label)}
            style={{ width: 180 }}
            onChange={(value) => setFilters((current) => ({ ...current, specialistId: value }))}
          />
          <Select
            allowClear
            placeholder="发布状态"
            value={filters.publishStatus}
            options={publishStatusOptions}
            style={{ width: 180 }}
            onChange={(value) => setFilters((current) => ({ ...current, publishStatus: value }))}
          />
          <Button type="primary" onClick={() => load(currentQuery())}>
            搜索
          </Button>
          <Button onClick={reset}>重置</Button>
          <Text type="secondary">发布状态可独立筛选；已上线且存在编辑中变更时会同时命中。</Text>
        </Space>
      </Card>

      <Spin spinning={loading}>
        {items.length ? (
          <div className="capability-center-grid">
            {items.map((item) => (
              <Card className="capability-center-item" key={item.draftId}>
                <div className="capability-center-item-head">
                  <div>
                    <strong>{nameOf(item)}</strong>
                    <div className="capability-center-action-code">{actionCodeOf(item)}</div>
                  </div>
                  <Space>
                    {item.editing ? <Tag color="processing">编辑中</Tag> : null}
                    {item.online ? <Tag color="success">已上线</Tag> : null}
                  </Space>
                </div>
                <p>{item.draft?.basicInfo?.description || '等待补充业务目标和模型调用边界。'}</p>
                <div className="capability-center-item-meta">
                  <span>{item.businessDomainName || item.businessDomain || '未设置业务域'}</span>
                  <span>
                    {item.capabilityDomainName || item.capabilityDomain || '未设置能力域'}
                  </span>
                  <span>{item.specialistName || '未设置所属专员'}</span>
                  <span>
                    {capabilitySourceText(
                      item.draft?.apiSource?.sourceType || CAPABILITY_API_SOURCE_TYPE,
                    )}
                  </span>
                  <span>{capabilitySideEffectText(item.draft?.governance?.sideEffectLevel)}</span>
                </div>
                <div className="capability-center-item-footer">
                  <Button
                    type="link"
                    onClick={() =>
                      navigate(
                        `/management/capabilities/edit?draftId=${item.draftId}`,
                      )
                    }
                  >
                    打开编辑
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        ) : (
          <Card>
            <Empty description="暂无能力草稿，先注册一个 API Center 能力。" />
          </Card>
        )}
      </Spin>

      <Drawer
        title="注册业务能力"
        visible={registrationOpen}
        onClose={() => setRegistrationOpen(false)}
        width={640}
      >
        <Form form={registrationForm} layout="vertical">
          <Form.Item
            label="中文名称"
            name="nameCn"
            rules={[{ required: true, whitespace: true, message: '请填写中文名称' }]}
          >
            <Input autoFocus placeholder="例如：查询直播计划关联商品" />
          </Form.Item>
          <Text type="secondary">
            确认后会先创建能力草稿，再进入编辑页；其余信息可通过 AI 辅助或表单继续补充。
          </Text>
          <div className="component-center-drawer-footer">
            <Button onClick={() => setRegistrationOpen(false)}>取消</Button>
            <Button type="primary" loading={registering} onClick={confirmRegistration}>
              确认并开始编辑
            </Button>
          </div>
        </Form>
      </Drawer>
    </div>
  );
};

export default CapabilityCenterPage;
