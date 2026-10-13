import { Component, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { A2uiSurface, MarkdownContext } from '@a2ui/react/v0_9';
import { renderMarkdown } from '@a2ui/markdown-it';
import { actionRequest, actionResponsePending, cardIsOperable, createSnapshotProcessor, persistedSnapshotKey } from '../a2uiSnapshot.mjs';
import { productApi, type ChatCard, type ChatActionResponse, type ComposerDraftEffect } from '../productApi';
import { TemporaryDraftOwner, temporaryDraftKey, readTemporaryDraft, writeTemporaryDraft, clearTemporaryDraft } from '../temporaryDraft';
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

export function A2uiSnapshotCard({ card, onUpdate, onComposerDraft, onActionStateChange, submitAction, disabled = false, title, initiallyExpanded }: {
  card: ChatCard;
  onUpdate: (card: ChatCard) => void;
  onComposerDraft: (effect: ComposerDraftEffect) => void;
  onActionStateChange?: (active: boolean) => void;
  submitAction?: (card: ChatCard, requestId: string, actionName: string, inputs: Record<string, unknown>) => Promise<ChatActionResponse>;
  disabled?: boolean;
  title?: string;
  initiallyExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(initiallyExpanded ?? ['WAITING_ACTION', 'DISPLAY_ONLY', 'UNKNOWN'].includes(card.status));
  const [processor, setProcessor] = useState<ReturnType<typeof createSnapshotProcessor>>();
  const [error, setError] = useState('');
  const [draftNotice, setDraftNotice] = useState('');
  const draftOwner = useContext(TemporaryDraftOwner);
  const draftKey = temporaryDraftKey(draftOwner, card);
  const temporary = card.display.definitionSource === 'TEMPORARY';
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const current = useRef({ card, onUpdate, onComposerDraft, onActionStateChange, submitAction, disabled });
  current.current = { card, onUpdate, onComposerDraft, onActionStateChange, submitAction, disabled };
  // Polling unchanged snapshots must not erase unsent user edits.
  const displayKey = JSON.stringify(card.display);
  const snapshotKey = persistedSnapshotKey(card);
  useEffect(() => {
    if (draftKey && card.status === 'COMPLETED') {
      try { clearTemporaryDraft(draftKey); setDraftNotice(''); }
      catch { setDraftNotice('交互已提交，但本地草稿未能清除。'); }
    }
  }, [draftKey, card.status]);
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
        if (draftKey && surface.id === 'main' && cardIsOperable(current.current.card)) {
          try {
            const draft = readTemporaryDraft(draftKey, current.current.card);
            if (draft) surface.dataModel.set('/inputs', { ...surface.dataModel.get('/inputs'), ...draft });
            setDraftNotice(draft ? '已恢复本浏览器中当前账号的未提交草稿。' : '未提交草稿仅保存在本浏览器，按当前账号隔离。');
          } catch { setDraftNotice('无法恢复本地草稿，当前显示已保存的卡片内容。'); }
          subscriptions.push(surface.dataModel.subscribe('/inputs', inputs => {
            if (disposed || !cardIsOperable(current.current.card)) return;
            try { writeTemporaryDraft(draftKey, current.current.card, inputs); }
            catch { if (!disposed) setDraftNotice('无法保存本地草稿，刷新将丢失未提交内容。'); }
          }));
        }
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
              if (response.continuation?.status === 'UNKNOWN' || response.continuation?.status === 'FAILED') {
                setError('交互结果已保存，但助手续轮未成功完成；不会自动重跑。');
              }
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
  }, [displayKey, snapshotKey, draftKey]);
  const operable = cardIsOperable(card) && !busy && !error && !disabled;
  return <details className="display-card" open={expanded} onToggle={event => setExpanded(event.currentTarget.open)}>
    <summary>{title ?? card.display.title ?? card.display.applicationKey}{temporary ? (card.display.mode === 'DISPLAY_ONLY' ? ' · 临时展示' : ' · 临时交互') : card.display.definitionSource === 'GENERATED' ? ' · AI 生成布局' : ''} · {disabled ? '只读历史' : labels[card.status] ?? '只读卡片'}</summary>
    <RendererBoundary key={snapshotKey}>
      {processor ? <MarkdownContext.Provider value={renderMarkdown}><fieldset className="a2ui-card-content" disabled={!operable} aria-busy={busy}>
        {Array.from(processor.model.surfacesMap.values()).map(surface =>
          <section className="a2ui-surface" key={surface.id} aria-label={surface.id}><A2uiSurface surface={surface} /></section>)}
      </fieldset></MarkdownContext.Provider> : null}
    </RendererBoundary>
    {busy ? <p role="status">等待自动同步已保存的卡片状态</p> : null}
    {draftNotice && card.status !== 'COMPLETED' ? <p className="muted" role="status">{draftNotice}</p> : null}
    {temporary && card.status === 'COMPLETED' ? <TemporarySubmission card={card} />
      : card.result !== undefined ? <details><summary>操作结果</summary><pre>{JSON.stringify(card.result, null, 2)}</pre></details> : null}
    {title ? <details className="workflow-debug"><summary>卡片技术信息</summary><p>Application：{card.display.applicationKey}</p><p>卡片 ID：{card.cardId}</p></details> : null}
    {error ? <p role="alert">{error}</p> : null}
  </details>;
}

function TemporarySubmission({ card }: { card: ChatCard }) {
  const result = card.result as { status?: unknown; values?: unknown } | undefined;
  if (!result || result.status !== 'SUBMITTED' || !result.values
    || typeof result.values !== 'object' || Array.isArray(result.values)) return null;
  const properties = card.display.inputSchema?.properties as Record<string, { title?: unknown }> | undefined;
  return <details className="temporary-submission"><summary>已提交给助手的内容</summary>
    <dl>{Object.entries(result.values).map(([field, value]) => <div key={field}>
      <dt>{typeof properties?.[field]?.title === 'string' ? properties[field].title : field}</dt>
      <dd>{typeof value === 'string' ? value : JSON.stringify(value)}</dd>
    </div>)}</dl>
  </details>;
}
