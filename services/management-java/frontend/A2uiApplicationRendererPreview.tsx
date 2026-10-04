import React, { Component, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Alert, Empty, Tag } from 'antd';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { A2uiSurface, MarkdownContext, basicCatalog, createComponentImplementation } from '@a2ui/react/v0_9';
import { renderMarkdown } from '@a2ui/markdown-it';
import { Catalog, CommonSchemas, MessageProcessor } from '@a2ui/web_core/v0_9';
import { EqualsImplementation } from '@a2ui/web_core/v0_9/basic_catalog';
import { z } from 'zod';
import type { A2uiMessage } from './a2uiApplicationContracts';
import {
  DIGITAL_EMPLOYEE_CATALOG_ID,
  OFFICIAL_BASIC_CATALOG_ID,
  type A2uiLocalActionEvent,
} from './a2uiApplicationLocalPreview';
import './node_modules/@a2ui/react/v0_9/index.css';
import '@fontsource/material-symbols-outlined/400.css';

const safeUrl = (url: string) => (/^(https?:|mailto:)/i.test(url) ? url : '');

const Markdown = createComponentImplementation(
  { name: 'Markdown', schema: z.object({ content: CommonSchemas.DynamicString }).strict() },
  ({ props }) => (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      skipHtml
      transformLinkUri={safeUrl}
      components={{
        a: ({ href, children }) => (
          <span title={href ? `链接预览（本地不跳转）：${href}` : '链接预览（本地不跳转）'}>
            {children}
          </span>
        ),
      }}
    >
      {props.content || ''}
    </ReactMarkdown>
  ),
);

const TextDownloadPreview: React.FC<{
  label?: string;
  isValid?: boolean;
}> = ({ label, isValid }) => {
  const [clicked, setClicked] = useState(false);
  return (
    <span>
      <button type="button" disabled={isValid === false} onClick={() => setClicked(true)}>
        下载预览（不下载）：{label || '文本'}
      </button>
      {clicked ? <Tag color="success" style={{ marginLeft: 8 }}>已触发本地预览，不会创建文件</Tag> : null}
    </span>
  );
};

const TextDownload = createComponentImplementation(
  {
    name: 'TextDownload',
    schema: z.object({
      ...CommonSchemas.Checkable.shape,
      label: CommonSchemas.DynamicString,
      filename: CommonSchemas.DynamicString,
      mediaType: CommonSchemas.DynamicString,
      content: CommonSchemas.DynamicString,
    }).strict(),
  },
  ({ props }) => <TextDownloadPreview label={props.label} isValid={props.isValid} />,
);

const digitalEmployeeCatalog = new Catalog(
  DIGITAL_EMPLOYEE_CATALOG_ID,
  [...basicCatalog.components.values(), Markdown, TextDownload],
  [...basicCatalog.functions.values(), EqualsImplementation],
  basicCatalog.themeSchema,
);

function catalogFor(catalogId: string) {
  if (catalogId === OFFICIAL_BASIC_CATALOG_ID) return basicCatalog;
  if (catalogId === DIGITAL_EMPLOYEE_CATALOG_ID) return digitalEmployeeCatalog;
  throw new Error(`本地 renderer 尚未注册 Catalog：${catalogId}`);
}

class PreviewBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed
      ? <Alert type="error" showIcon message="Application 组件渲染失败，已停止本地预览。" />
      : this.props.children;
  }
}

interface Props {
  catalogId: string;
  messages: A2uiMessage[];
  onAction: (event: A2uiLocalActionEvent) => void;
}

function createProcessor(catalog: ReturnType<typeof catalogFor>) {
  return new MessageProcessor([catalog], undefined, { version: 'v0.9.1' });
}

type PreviewProcessor = ReturnType<typeof createProcessor>;

const A2uiApplicationRendererPreview: React.FC<Props> = ({ catalogId, messages, onAction }) => {
  const [processor, setProcessor] = useState<PreviewProcessor>();
  const [error, setError] = useState('');
  const messageKey = useMemo(() => JSON.stringify(messages), [messages]);

  useEffect(() => {
    let disposed = false;
    let next: PreviewProcessor | undefined;
    const subscriptions: Array<{ unsubscribe: () => void }> = [];
    try {
      const catalog = catalogFor(catalogId);
      for (const message of messages) {
        const update = message.updateComponents as { components?: Array<{ component?: string }> } | undefined;
        for (const component of update?.components || []) {
          if (!component.component || !catalog.components.has(component.component)) {
            throw new Error(`Catalog ${catalogId} 没有本地实现：${component.component || '<empty>'}`);
          }
        }
      }
      next = createProcessor(catalog);
      next.processMessages(JSON.parse(messageKey));
      if (!next.model.surfacesMap.size) throw new Error('Application 没有可展示的 Surface');
      for (const surface of next.model.surfacesMap.values()) {
        subscriptions.push(surface.onError.subscribe(() => {
          if (!disposed) setError('Application 数据绑定失败，已停止本地预览。');
        }));
        subscriptions.push(surface.onAction.subscribe((event) => {
          if (!disposed) onAction({
            name: event.name,
            surfaceId: event.surfaceId,
            sourceComponentId: event.sourceComponentId,
            context: event.context,
          });
        }));
      }
      setError('');
      setProcessor(next);
    } catch (reason) {
      next?.model.dispose();
      setProcessor(undefined);
      setError(reason instanceof Error ? reason.message : 'Application 本地预览失败');
    }
    return () => {
      disposed = true;
      subscriptions.forEach((item) => item.unsubscribe());
      next?.model.dispose();
    };
  }, [catalogId, messageKey, messages, onAction]);

  if (error) return <Alert type="error" showIcon message={error} />;
  if (!processor) return <Empty description="没有可展示的 Application Surface" />;
  return (
    <PreviewBoundary key={`${catalogId}:${messageKey}`}>
      <MarkdownContext.Provider value={renderMarkdown}>
        <div className="component-center-a2ui-preview">
          {Array.from(processor.model.surfacesMap.values()).map((surface) => (
            <section key={surface.id} aria-label={surface.id}>
              <A2uiSurface surface={surface} />
            </section>
          ))}
        </div>
      </MarkdownContext.Provider>
      <Tag style={{ marginTop: 12 }}>本地预览：不会调用 CapabilityAction</Tag>
    </PreviewBoundary>
  );
};

export default A2uiApplicationRendererPreview;
