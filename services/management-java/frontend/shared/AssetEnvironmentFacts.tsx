import React from 'react';
import { Tag } from 'antd';
import type {
  AssetReleaseEnvironmentFacts,
  AssetReleaseSourceFact,
  ReleaseEnvironment,
} from '../types';

interface AssetEnvironmentFactsProps {
  facts?: AssetReleaseEnvironmentFacts;
}

const RELEASE_ENVIRONMENT_TEXT: Record<string, string> = {
  PRT: '预发',
  ONLINE: '线上',
};

const RELEASE_ERROR_TEXT: Record<string, string> = {
  RELEASE_ENVIRONMENT_REQUIRED: '未指定发布环境',
  RELEASE_ENVIRONMENT_INVALID: '发布环境无效',
  ASSET_REFERENCE_INVALID: '资产引用无效',
  ASSET_TYPE_UNSUPPORTED: '暂不支持该资产类型',
  ASSET_RELEASE_NOT_AVAILABLE: '暂无可用发布版本',
  PREPROD_POINTER_INVALID: '预发发布信息异常',
  ONLINE_POINTER_REQUIRED: '尚未发布线上版本',
  ONLINE_POINTER_INVALID: '线上发布信息异常',
  ASSET_DISABLED: '资产已禁用',
  DEPENDENCY_EXPANSION_FAILED: '依赖解析失败',
  DEPENDENCY_CYCLE: '存在循环依赖',
  DEPENDENCY_DEPTH_EXCEEDED: '依赖层级过深',
  DEPENDENCY_SELECTION_AMBIGUOUS: '依赖版本信息冲突',
};

const RELEASE_MESSAGE_TEXT: Record<string, string> = {
  资产没有可用的PRT或ONLINE发布版本: '暂无可用的预发或线上发布版本',
  PRT指针或Build快照不完整: '预发发布信息或构建快照不完整',
  资产尚未发布ONLINE版本: '资产尚未发布线上版本',
  ONLINE指针或Version快照不完整: '线上发布信息或版本快照不完整',
  '该依赖仅在 PRT 可用，将阻塞 Skill 发布到线上':
    '该依赖仅在预发环境可用，将阻塞 Skill 发布到线上',
};

function releaseEnvironmentText(environment?: string): string {
  return RELEASE_ENVIRONMENT_TEXT[String(environment || '').toUpperCase()] || '未知环境';
}

function releaseFailureText(fact?: AssetReleaseSourceFact): string {
  const errorCode = String(fact?.errorCode || '').toUpperCase();
  if (errorCode && RELEASE_ERROR_TEXT[errorCode]) return RELEASE_ERROR_TEXT[errorCode];
  const message = String(fact?.message || '').trim();
  if (message) return RELEASE_MESSAGE_TEXT[message] || message;
  if (fact?.status === 'SUCCEEDED') return '可用';
  return '暂无可用版本';
}

function shortDigest(digest?: string): string {
  const value = String(digest || '').replace(/^sha256:/, '');
  return value ? value.slice(0, 8) : '';
}

function releaseSourceText(fact?: AssetReleaseSourceFact): string {
  if (!fact?.available) {
    return releaseFailureText(fact);
  }
  const sourceType = fact.sourceType === 'BUILD' ? '构建' : '版本';
  const version = fact.version ? ` v${fact.version}` : '';
  const digest = shortDigest(fact.digest);
  return `${sourceType}${version}${digest ? ` · ${digest}` : ''}`;
}

function environmentFact(
  environment: ReleaseEnvironment,
  fact?: AssetReleaseSourceFact,
): React.ReactNode {
  const available = fact?.available === true;
  return (
    <div className="skill-factory-environment-fact">
      <span>{releaseEnvironmentText(environment)}</span>
      <Tag color={available ? 'success' : fact?.errorCode ? 'error' : undefined}>
        {releaseSourceText(fact)}
      </Tag>
    </div>
  );
}

const AssetEnvironmentFacts: React.FC<AssetEnvironmentFactsProps> = ({ facts }) => {
  if (!facts) return null;
  const effective = facts.effectivePreprod;
  const effectiveText = effective?.available
    ? `${releaseEnvironmentText(
        effective.resolvedEnvironment || effective.environment || 'PRT',
      )} · ${releaseSourceText(effective)}`
    : releaseSourceText(effective);
  return (
    <div className="skill-factory-environment-facts">
      <div className="skill-factory-environment-fact-grid">
        {environmentFact('PRT', facts.preprod)}
        {environmentFact('ONLINE', facts.online)}
      </div>
      <div className="skill-factory-effective-prt">
        <span>预发实际选择</span>
        <strong>{effectiveText}</strong>
      </div>
      {facts.onlineBlocked ? (
        <div className="skill-factory-online-block-warning">
          {RELEASE_MESSAGE_TEXT[facts.onlineBlockedReason || ''] ||
            facts.onlineBlockedReason ||
            '该依赖仅在预发环境可用，将阻塞 Skill 发布到线上'}
        </div>
      ) : null}
    </div>
  );
};

export default AssetEnvironmentFacts;
