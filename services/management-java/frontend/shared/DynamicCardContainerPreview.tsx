import React, { useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom';
import * as JSXRuntime from 'react/jsx-runtime';
import { DynamicComponent } from './DynamicComponent';
import * as SafeJSON from './safeJson';
import * as PreviewImage from './PreviewImage';
import { Alert, Empty, Spin, message } from 'antd';
import type { ComponentRenderPreviewResult } from '../types';

const dynamicComponentDependencies = {
  react: React,
  React,
  ReactDOM,
  'react-dom': ReactDOM,
  'react/jsx-runtime': JSXRuntime,
  '@a2flow/image': PreviewImage,
  'safe-json-parse-and-stringify': SafeJSON,
};

function recordOf(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function stringOf(value: unknown): string {
  if (value === undefined || value === null) return '';
  return String(value);
}

function dynamicRenderErrorMessage(error: string, clientType: 'PC' | 'APP'): string {
  const componentMissing = error.match(/Component "([^"]+)" was not found/i);
  if (componentMissing) {
    return `组件包中找不到「${componentMissing[1]}」。请确认组件 code 与 ${clientType} bundle 导出的组件名完全一致，或更新 ${clientType} bundleUrl 后重试。`;
  }
  if (/failed to fetch|load failed|networkerror|network request failed/i.test(error)) {
    return `${clientType} 组件包加载失败。请检查 ${clientType} bundleUrl 是否可访问、版本是否已发布，以及当前环境是否有访问权限。`;
  }
  return `${clientType} 动态组件渲染失败：${
    error || '未知错误'
  }。请检查组件 code、${clientType} bundleUrl 和转换结果，修复后重新运行预览。`;
}

const DynamicCardContainerPreview: React.FC<{
  result?: ComponentRenderPreviewResult;
  clientType?: 'PC' | 'APP';
}> = ({ result, clientType = 'PC' }) => {
  const [renderError, setRenderError] = useState('');
  const payload = useMemo(() => {
    const rawData = recordOf(result?.data);
    if (!rawData) return null;
    if (rawData.bundleUrl || rawData.appBundleUrl || rawData.componentName || rawData.data) {
      return rawData;
    }
    return {
      bundleUrl: result?.bundleUrl,
      appBundleUrl: result?.appBundleUrl,
      componentName: result?.componentName,
      data: rawData,
      type: 'bundle',
    };
  }, [result]);
  const componentName = stringOf(payload?.componentName || result?.componentName);
  const bundleUrl =
    clientType === 'APP'
      ? stringOf(payload?.appBundleUrl || result?.appBundleUrl)
      : stringOf(payload?.bundleUrl || result?.bundleUrl);
  const componentData = useMemo(() => recordOf(payload?.data) || {}, [payload]);
  const componentProps = useMemo(
    () => ({
      ...componentData,
      sendMessage: (text?: unknown) => {
        const content = stringOf(text);
        if (content) {
          message.info(`模拟发送：${content}`);
        }
      },
      source: clientType,
      collectShow: () => undefined,
      collectClick: () => undefined,
    }),
    [clientType, componentData],
  );

  useEffect(() => {
    setRenderError('');
  }, [bundleUrl, componentName, result?.data]);

  if (!result) {
    return <Empty description="点击预览后展示真实前端渲染" />;
  }
  if (!result.valid) {
    return <Empty description={result.errors?.[0] || '预览校验未通过'} />;
  }
  if (!payload || !componentName || !bundleUrl) {
    return <Empty description={`转换结果缺少 ${clientType} bundleUrl 或 componentName`} />;
  }

  return (
    <div className="component-card-real-render">
      <DynamicComponent
        dependencies={dynamicComponentDependencies}
        componentProps={componentProps}
        url={bundleUrl}
        componentName={componentName}
        fallback={<Spin />}
        errorFallback={() => null}
        onError={(error) => setRenderError(error.message)}
      />
      {renderError ? (
        <Alert
          type="error"
          message={dynamicRenderErrorMessage(renderError, clientType)}
          style={{ marginTop: 12 }}
        />
      ) : null}
    </div>
  );
};

export default DynamicCardContainerPreview;
