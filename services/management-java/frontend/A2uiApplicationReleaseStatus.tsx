import React from 'react';
import { Space, Tag } from 'antd';
import type { A2uiApplicationRecord, A2uiApplicationStatus } from './a2uiApplicationContracts';

export const applicationStatusOptions = [
  { label: '全部状态', value: 'ALL' },
  { label: '未发布', value: 'DRAFT' },
  { label: '已预发', value: 'PRT' },
  { label: '已上线', value: 'ONLINE' },
];

const statusColor: Record<A2uiApplicationStatus, string | undefined> = {
  DRAFT: undefined,
  VALIDATED: 'blue',
  PRT: 'blue',
  ONLINE: 'green',
};

const statusLabel: Record<A2uiApplicationStatus, string> = {
  DRAFT: '未发布',
  VALIDATED: '已校验',
  PRT: '已预发',
  ONLINE: '已上线',
};

export const A2uiApplicationReleaseStatus: React.FC<{ record: A2uiApplicationRecord }> = ({
  record,
}) => (
  <Space direction="vertical" size={4}>
    <Space wrap size={4}>
      <Tag color={statusColor[record.status]}>{statusLabel[record.status]}</Tag>
      {record.hasUnpublishedChanges ? <Tag color="orange">有未发布修改</Tag> : null}
    </Space>
    <Space wrap size={4}>
      {(['PRT', 'ONLINE'] as const)?.map((environment) => {
        const release = record.releases?.[environment];
        return release?.enabled && release.version != null ? (
          <Tag key={environment}>
            {environment === 'ONLINE' ? '线上' : '预发'} v{release.version}
          </Tag>
        ) : null;
      })}
    </Space>
  </Space>
);
