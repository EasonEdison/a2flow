import React from 'react';
import { Button, Space, Tag, Typography } from 'antd';
import type { ChangeReviewStatus } from './patchProjection';

const { Text } = Typography;

export type { ChangeReviewStatus } from './patchProjection';

/**
 * 领域 Adapter 决定变更写入目标和操作语义，模型事件不能覆盖这些可信配置。
 */
export interface ChangeReviewAdapter {
  targetLabel: string;
  applyLabel: string;
  appliedLabel: string;
  applyDescription: string;
  onApply: () => void | Promise<void>;
  onDiscard: () => void | Promise<void>;
  status?: ChangeReviewStatus;
  discardLabel?: string;
  discardedLabel?: string;
  conflictedLabel?: string;
  applying?: boolean;
  discarding?: boolean;
  applyDisabled?: boolean;
  discardDisabled?: boolean;
}

interface AuthoringChangeReviewFrameProps {
  title: React.ReactNode;
  summary?: React.ReactNode;
  metadata?: React.ReactNode;
  children: React.ReactNode;
  footerNote?: React.ReactNode;
  adapter: ChangeReviewAdapter;
}

/**
 * Skill、组件和业务能力共用的修改审阅外壳。
 *
 * <p>本组件只负责布局、状态和操作入口；真正的 workspace/form 写入由领域 Adapter 执行。
 */
const AuthoringChangeReviewFrame: React.FC<AuthoringChangeReviewFrameProps> = ({
  title,
  summary,
  metadata,
  children,
  footerNote,
  adapter,
}) => {
  const status = adapter.status || 'PENDING';
  const settledText =
    status === 'APPLIED'
      ? adapter.appliedLabel
      : status === 'DISCARDED'
      ? adapter.discardedLabel || '已丢弃'
      : status === 'CONFLICTED'
      ? adapter.conflictedLabel || '变更已冲突'
      : '';
  const statusColor =
    status === 'APPLIED'
      ? 'success'
      : status === 'CONFLICTED'
      ? 'error'
      : status === 'PENDING'
      ? 'warning'
      : 'default';
  return (
    <div className="authoring-change-review">
      <div className="authoring-form-review-summary">
        <div className="authoring-change-review-title">
          <Text className="authoring-change-review-heading" strong>
            {title}
          </Text>
          <Tag className="authoring-change-review-status" color={statusColor}>
            {status === 'PENDING' ? '待审阅' : settledText}
          </Tag>
        </div>
        {summary ? <Text type="secondary">{summary}</Text> : null}
        {metadata}
        <div className="authoring-change-review-target">
          <Text type="secondary">写入目标</Text>
          <Text className="authoring-change-review-target-value" strong>
            {adapter.targetLabel}
          </Text>
        </div>
      </div>
      <div className="authoring-change-review-content">{children}</div>
      <div className="authoring-form-review-actions">
        <div>
          <Text type="secondary">{adapter.applyDescription}</Text>
          {footerNote}
        </div>
        {status === 'PENDING' ? (
          <Space>
            <Button
              disabled={adapter.discardDisabled}
              loading={adapter.discarding}
              onClick={adapter.onDiscard}
            >
              {adapter.discardLabel || '丢弃建议'}
            </Button>
            <Button
              disabled={adapter.applyDisabled}
              loading={adapter.applying}
              onClick={adapter.onApply}
              type="primary"
            >
              {adapter.applyLabel}
            </Button>
          </Space>
        ) : (
          <Tag color={statusColor}>{settledText}</Tag>
        )}
      </div>
    </div>
  );
};

export default AuthoringChangeReviewFrame;
