import React from 'react';
import { Space, Tag, Typography } from 'antd';
import type { CapabilityActionDraftData } from './api';
import type { CapabilityClient } from './capabilityClientVariantLayout';

const { Text } = Typography;

type CapabilityClientVariantReviewProps = {
  activeClient: CapabilityClient;
  draft: CapabilityActionDraftData;
};

function sourceLabel(sourceType?: string): string {
  return sourceType === 'GRPC' ? 'gRPC 服务' : '不支持的来源';
}

function bindingTarget(draft: CapabilityActionDraftData): string {
  const target = draft.executionBinding?.target || {};
  return [target.serviceName || '待填写服务', target.methodName || '待填写方法'].join(' / ');
}

const CapabilityClientVariantReview: React.FC<CapabilityClientVariantReviewProps> = ({
  activeClient,
  draft,
}) => {
  const keyOutputCount = draft.resultContract?.keyOutputFields?.length || 0;
  const mappingCount = (() => {
    try {
      const parsed = JSON.parse(draft.executionBinding?.requestMappingsJson || '{}') as unknown;
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
        ? Object.keys(parsed as Record<string, unknown>).length
        : 0;
    } catch {
      return 0;
    }
  })();

  return (
    <section className="capability-client-variant-review">
      <div className="capability-client-variant-head">
        <div>
          <Space size={8}>
            <h3>{activeClient} 配置概览</h3>
            <Tag color="green">独立保存协议</Tag>
          </Space>
          <Text type="secondary">
            当前端的参数、API 来源、执行绑定和响应契约互相配套，不与另一端混用。
          </Text>
        </div>
      </div>

      <div className="capability-client-variant-grid">
        <article>
          <div className="capability-client-variant-card-head">
            <Text type="secondary">API 来源</Text>
            <Tag>{activeClient}</Tag>
          </div>
          <strong>{sourceLabel(draft.apiSource?.sourceType)}</strong>
          <Text type="secondary">{draft.executionBinding?.target?.targetKey || '待填写业务服务配置键'}</Text>
        </article>

        <article>
          <div className="capability-client-variant-card-head">
            <Text type="secondary">执行绑定</Text>
            <Tag color={mappingCount ? 'green' : 'orange'}>{mappingCount} 个映射</Tag>
          </div>
          <strong>{draft.executionBinding?.bindingType || 'GRPC'}</strong>
          <Text type="secondary">{bindingTarget(draft)}</Text>
        </article>

        <article>
          <div className="capability-client-variant-card-head">
            <Text type="secondary">响应契约</Text>
            <Tag color={draft.resultContract?.responseDemoJson ? 'green' : 'orange'}>
              {draft.resultContract?.responseDemoJson ? '已有 Demo' : '待配置'}
            </Tag>
          </div>
          <strong>{keyOutputCount} 个关键出参</strong>
          <Text type="secondary">响应 Demo 和关键路径在当前端参数契约中维护。</Text>
        </article>

        <article>
          <div className="capability-client-variant-card-head">
            <Text type="secondary">环境校验</Text>
            <Tag color="blue">按端校验</Tag>
          </div>
          <Space size={6} wrap>
            <Tag>PRT 未校验</Tag>
            <Tag>ONLINE 未校验</Tag>
          </Space>
          <Text type="secondary">最终按 {activeClient} × PRT/ONLINE 分别形成准出证据。</Text>
        </article>
      </div>
    </section>
  );
};

export default CapabilityClientVariantReview;
