import React from 'react';
import { Alert, Button, Select, Space, Tag, Typography } from 'antd';
import {
  CAPABILITY_CLIENT_MODE_OPTIONS,
  resolveCapabilityClientVariantView,
  type CapabilityClient,
  type CapabilityClientMode,
} from './capabilityClientVariantLayout';

const { Text } = Typography;

type CapabilityClientTechnicalNavigationProps = {
  activeClient: CapabilityClient;
  clientMode: CapabilityClientMode;
  onActiveClientChange: (client: CapabilityClient) => void;
  onClientModeChange: (mode: CapabilityClientMode) => void;
};

const CapabilityClientTechnicalNavigation: React.FC<CapabilityClientTechnicalNavigationProps> = ({
  activeClient,
  clientMode,
  onActiveClientChange,
  onClientModeChange,
}) => {
  const view = resolveCapabilityClientVariantView(clientMode, activeClient);

  return (
    <section className="capability-client-technical-navigation">
      <div className="capability-client-variant-head">
        <div>
          <Space size={8}>
            <h3>端侧技术配置</h3>
            <Tag color="green">{view.activeClient} 保存协议</Tag>
          </Space>
          <Text type="secondary">
            参数契约与执行绑定共用这一处端侧选择；切换后编辑当前端的完整技术细节。
          </Text>
        </div>
        <div className="capability-client-technical-controls">
          <label>
            支持端
            <Select
              value={view.mode}
              options={CAPABILITY_CLIENT_MODE_OPTIONS}
              onChange={(value) => onClientModeChange(value as CapabilityClientMode)}
            />
          </label>
          {view.showClientSwitch ? (
            <div className="capability-client-switch" role="tablist" aria-label="端侧技术配置">
              {view.supportedClients?.map?.((client) => (
                <Button
                  aria-selected={view.activeClient === client}
                  className={view.activeClient === client ? 'active' : ''}
                  key={client}
                  onClick={() => onActiveClientChange(client)}
                  role="tab"
                  type={view.activeClient === client ? 'primary' : 'default'}
                >
                  {client}
                </Button>
              ))}
            </div>
          ) : (
            <Tag className="capability-single-client-label">{view.singleClientLabel}</Tag>
          )}
        </div>
      </div>
      <Alert
        type="info"
        showIcon
        message={`${view.singleClientLabel || view.activeClient} 技术契约独立保存`}
        description="下拉选项互斥保存；通用模式只保存 COMMON 契约，端之间不会复制、继承或回退。"
      />
    </section>
  );
};

export default CapabilityClientTechnicalNavigation;
