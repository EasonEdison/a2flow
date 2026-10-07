import { Component, useEffect, useRef, useState, type ReactNode } from 'react';
import { A2uiSurface, MarkdownContext } from '@a2ui/react/v0_9';
import { renderMarkdown } from '@a2ui/markdown-it';
import { actionRequest, actionResponsePending, cardIsOperable, createSnapshotProcessor, persistedSnapshotKey } from '../a2uiSnapshot.mjs';
import { productApi, type ChatCard, type ChatActionResponse, type ComposerDraftEffect } from '../productApi';
import { createUuidV4 } from '../secureUuid.mjs';
import { registeredCatalogs } from './a2uiCatalogs';
import '../../node_modules/@a2ui/react/v0_9/index.css';
import '@fontsource/material-symbols-outlined/400.css';
import './a2ui-card.css';

const labels: Record<string, string> = {
  WAITING_ACTION: '等待你操作', DISPLAY_ONLY: '展示卡片', EXECUTING: '操作执行中或待确认',
  COMPLETED: '交互已完成', UNKNOWN: '操作结果待确认 · 不会自动重试',
};

class RendererBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <p role="alert">组件渲染失败，已禁止操作。请核对 Catalog 实现。</p> : this.props.children; }
}

export function A2uiSnapshotCard({ card, onUpdate, onComposerDraft, onActionStateChange, submitAction, disabled = false }: {
  card: ChatCard;
  onUpdate: (card: ChatCard) => void;
  onComposerDraft: (effect: ComposerDraftEffect) => void;
  onActionStateChange?: (active: boolean) => void;
  submitAction?: (card: ChatCard, requestId: string, actionName: string, inputs: Record<string, unknown>) => Promise<ChatActionResponse>;
  disabled?: boolean;
}) {
  const [processor, setProcessor] = useState<ReturnType<typeof createSnapshotProcessor>>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const current = useRef({ card, onUpdate, onComposerDraft, onActionStateChange, submitAction, disabled });
  current.current = { card, onUpdate, onComposerDraft, onActionStateChange, submitAction, disabled };
  // Polling unchanged snapshots must not erase unsent user edits.
  const displayKey = JSON.stringify(card.display);
  const snapshotKey = persistedSnapshotKey(card);
  useEffect(() => {
    if (!inFlight.current) return;
    if (!actionResponsePending(card)) {
      inFlight.current = false;
      setBusy(false);
    }
  }, [card.status]);
  useEffect(() => {
    let disposed = false;
    let next: ReturnType<typeof createSnapshotProcessor> | undefined;
    const subscriptions: Array<{ unsubscribe: () => void }> = [];
    // A changed persisted display is authoritative and can replace the local processor.
    inFlight.current = false;
    setBusy(false);
    try {
      next = createSnapshotProcessor(JSON.parse(displayKey), registeredCatalogs);
      for (const surface of next.model.surfacesMap.values()) {
        subscriptions.push(surface.onError.subscribe(() => {
          if (!disposed) { inFlight.current = true; setError('组件绑定或表达式失败，已禁止操作。请核对 Catalog 配置。'); setBusy(true); }
        }));
        subscriptions.push(surface.onAction.subscribe(async event => {
          if (disposed || inFlight.current || current.current.disabled || !cardIsOperable(current.current.card)) return;
          const latest = current.current.card;
          let request: ReturnType<typeof actionRequest>;
          let requestId: string;
          try {
            request = actionRequest(latest, event);
            requestId = createUuidV4();
          } catch {
            if (!disposed) setError('提交前校验失败，操作尚未发送。');
            return;
          }
          inFlight.current = true;
          const actionStateCallback = current.current.onActionStateChange;
          actionStateCallback?.(true);
          setBusy(true); setError('');
          try {
            const response = current.current.submitAction
              ? await current.current.submitAction(latest, requestId, request.actionName, request.inputs)
              : await productApi.chatAction(latest.conversationId, latest, requestId, request.actionName, request.inputs);
            if (!disposed) {
              current.current.onUpdate(response.card);
              response.effects.filter(effect => effect.requestId === requestId)
                .forEach(effect => current.current.onComposerDraft(effect));
              const pending = actionResponsePending(response.card);
              inFlight.current = pending;
              setBusy(pending);
            }
          } catch {
            if (!disposed) setError('操作结果未确认，请等待状态自动同步；不会自动重试。');
          } finally {
            actionStateCallback?.(false);
          }
          // Transport failures remain locked because the outcome is unknown.
        }));
      }
      setError(''); setProcessor(next);
    } catch (reason) {
      setProcessor(undefined);
      setError(reason instanceof Error ? reason.message : 'A2UI 快照无效');
    }
    return () => { disposed = true; subscriptions.forEach(item => item.unsubscribe()); next?.model.dispose(); };
  }, [displayKey, snapshotKey]);
  const operable = cardIsOperable(card) && !busy && !error && !disabled;
  return <details className="display-card" open={['WAITING_ACTION', 'DISPLAY_ONLY', 'UNKNOWN'].includes(card.status)}>
    <summary>{card.display.applicationKey} · {labels[card.status] ?? '只读卡片'}</summary>
    <RendererBoundary key={snapshotKey}>
      {processor ? <MarkdownContext.Provider value={renderMarkdown}><fieldset className="a2ui-card-content" disabled={!operable} aria-busy={busy}>
        {Array.from(processor.model.surfacesMap.values()).map(surface =>
          <section className="a2ui-surface" key={surface.id} aria-label={surface.id}><A2uiSurface surface={surface} /></section>)}
      </fieldset></MarkdownContext.Provider> : null}
    </RendererBoundary>
    {busy ? <p role="status">等待自动同步已保存的卡片状态</p> : null}
    {card.result !== undefined ? <details><summary>操作结果</summary><pre>{JSON.stringify(card.result, null, 2)}</pre></details> : null}
    {error ? <p role="alert">{error}</p> : null}
  </details>;
}
