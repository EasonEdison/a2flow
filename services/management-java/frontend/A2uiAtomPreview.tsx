import React, { Component, useEffect, useState, type ReactNode } from 'react';
import { Alert, Empty, Tag } from 'antd';
import { A2uiSurface, MarkdownContext, basicCatalog } from '@a2ui/react/v0_9';
import { renderMarkdown } from '@a2ui/markdown-it';
import { MessageProcessor } from '@a2ui/web_core/v0_9';
import { OFFICIAL_BASIC_CATALOG_ID, parseA2uiAtomPreviewDocument } from './a2uiAtomPreviewModel';
import './node_modules/@a2ui/react/v0_9/index.css';
import '@fontsource/material-symbols-outlined/400.css';

class A2uiPreviewBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? (
      <Alert type="error" showIcon message="组件渲染失败，已停止预览，请核对注册示例与 Catalog 实现。" />
    ) : this.props.children;
  }
}

interface A2uiAtomPreviewProps {
  componentType: string;
  json: string;
}

function createPreviewProcessor() {
  return new MessageProcessor([basicCatalog], undefined, { version: 'v0.9.1' });
}

type PreviewProcessor = ReturnType<typeof createPreviewProcessor>;

const A2uiAtomPreview: React.FC<A2uiAtomPreviewProps> = ({ componentType, json }) => {
  const [processor, setProcessor] = useState<PreviewProcessor>();
  const [error, setError] = useState('');
  const [lastAction, setLastAction] = useState('');

  useEffect(() => {
    let disposed = false;
    let next: PreviewProcessor | undefined;
    const subscriptions: Array<{ unsubscribe: () => void }> = [];
    try {
      if (!basicCatalog.components.has(componentType)) {
        throw new Error(`前端未注册 Catalog 组件实现：${componentType}`);
      }
      const document = parseA2uiAtomPreviewDocument(json);
      next = createPreviewProcessor();
      next.processMessages([
        { version: 'v0.9.1', createSurface: { surfaceId: 'component-preview', catalogId: OFFICIAL_BASIC_CATALOG_ID } },
        { version: 'v0.9.1', updateComponents: { surfaceId: 'component-preview', components: document.components } },
        ...(document.dataModel
          ? [{ version: 'v0.9.1' as const, updateDataModel: { surfaceId: 'component-preview', path: '/', value: document.dataModel } }]
          : []),
      ]);
      for (const surface of next.model.surfacesMap.values()) {
        subscriptions.push(surface.onError.subscribe(() => {
          if (!disposed) setError('组件绑定失败，已停止预览，请核对示例数据。');
        }));
        subscriptions.push(surface.onAction.subscribe((event) => {
          if (!disposed) setLastAction(`已在本地触发：${event.name}`);
        }));
      }
      setError('');
      setLastAction('');
      setProcessor(next);
    } catch (reason) {
      next?.model.dispose();
      setProcessor(undefined);
      setError(reason instanceof Error ? reason.message : 'A2UI 预览数据无效');
    }
    return () => {
      disposed = true;
      subscriptions.forEach((subscription) => subscription.unsubscribe());
      next?.model.dispose();
    };
  }, [componentType, json]);

  if (error) return <Alert type="error" showIcon message={error} />;
  if (!processor) return <Empty description="没有可渲染的 A2UI Surface" />;

  return (
    <A2uiPreviewBoundary key={`${componentType}:${json}`}>
      <MarkdownContext.Provider value={renderMarkdown}>
        <div className="component-center-a2ui-preview">
          {Array.from(processor.model.surfacesMap.values()).map((surface) => (
            <A2uiSurface key={surface.id} surface={surface} />
          ))}
        </div>
      </MarkdownContext.Provider>
      {lastAction ? <Tag color="success" style={{ marginTop: 12 }}>{lastAction}（未发送业务请求）</Tag> : null}
    </A2uiPreviewBoundary>
  );
};

export default A2uiAtomPreview;
