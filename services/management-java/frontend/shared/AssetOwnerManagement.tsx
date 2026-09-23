import React, { useMemo, useState } from 'react';
import { Button, Input, Modal, Space, Tag, Typography, message } from 'antd';
import { assetAccessApi } from '../api';
import type { AssetAccessResult, ReleaseAssetType } from '../types';
import { buildAssetOwnerManagementView, normalizeAssetOwnerIds } from './assetOwnerManagementModel';

const { Text } = Typography;

const assetTypeLabel: Record<ReleaseAssetType, string> = {
  SKILL: 'Skill',
  COMPONENT: '组件',
  CAPABILITY_ACTION: '业务能力',
  ORCHESTRATION_CONFIG: 'Workflow',
  A2UI_CATALOG: 'A2UI Catalog',
  A2UI_APPLICATION: 'A2UI Application',
};

interface AssetOwnerManagementProps {
  assetType: ReleaseAssetType;
  assetKey: string;
  access?: AssetAccessResult;
  showLabel?: boolean;
  onAccessRefresh: () => Promise<AssetAccessResult | undefined>;
}

const AssetOwnerManagement: React.FC<AssetOwnerManagementProps> = ({
  assetType,
  assetKey,
  access,
  showLabel = true,
  onAccessRefresh,
}) => {
  const [modalOpen, setModalOpen] = useState(false);
  const [ownerInput, setOwnerInput] = useState('');
  const [saving, setSaving] = useState(false);
  const view = useMemo(() => buildAssetOwnerManagementView(access), [access]);

  const openModal = () => {
    setOwnerInput(view.ownerIds?.join?.(','));
    setModalOpen(true);
  };

  const replaceOwners = async () => {
    const ownerIds = normalizeAssetOwnerIds(ownerInput);
    if (!ownerIds.length) {
      message.warning('至少保留一名负责人');
      return;
    }
    setSaving(true);
    try {
      await assetAccessApi.replaceOwners(assetType, assetKey, ownerIds);
      const refreshed = await onAccessRefresh();
      setModalOpen(false);
      if (refreshed) {
        message.success('负责人已更新');
      } else {
        message.warning('负责人已更新，权限刷新失败，请点击刷新');
      }
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : '负责人更新失败');
      await onAccessRefresh();
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Space wrap>
        {showLabel ? <Text type="secondary">负责人</Text> : null}
        {view.ownerIds?.map?.((ownerId) => (
          <Tag key={ownerId}>{ownerId}</Tag>
        ))}
        {!view.ownerIds?.length ? <Text type="secondary">-</Text> : null}
        {view.canManageOwner ? <Button onClick={openModal}>管理负责人</Button> : null}
      </Space>
      <Modal
        title={`管理${assetTypeLabel[assetType]}负责人`}
        visible={modalOpen}
        okText="保存"
        cancelText="取消"
        confirmLoading={saving}
        onCancel={() => setModalOpen(false)}
        onOk={replaceOwners}
      >
        <Text type="secondary">仅管理员可修改。请输入用户 ID，多个负责人用英文逗号分隔。</Text>
        <Input
          autoFocus
          placeholder="tangxiaohan,another-owner"
          value={ownerInput}
          onChange={(event) => setOwnerInput(event.target.value)}
        />
      </Modal>
    </>
  );
};

export default AssetOwnerManagement;
