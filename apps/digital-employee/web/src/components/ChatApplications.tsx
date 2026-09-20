import { useCallback, useEffect, useRef, useState } from 'react';
import { productApi, type ChatCard } from '../productApi';
import { MarkdownContent } from './MarkdownContent';

const labels: Record<string, string> = { WAITING_ACTION: '等待你操作', DISPLAY_ONLY: '仅展示',
  EXECUTING: '操作执行中或待确认', COMPLETED: '交互已完成', UNKNOWN: '操作结果待确认 · 不会自动重试' };
const record = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('INVALID_TEMPLATE');
  return value as Record<string, unknown>;
};

// The current registered profile is a flat Column of Text, ChoicePicker and
// Button components. Unknown templates fail closed; never interpret HTML/JS.
function material(card: ChatCard) {
  const display = card.display;
  if (display.protocolProfile !== 'a2flow.mvp08.v1') throw new Error('UNSUPPORTED_PROFILE');
  const root = display.components.find(item => item.id === display.rootId);
  if (root?.component !== 'Column' || !Array.isArray(root.children)) throw new Error('INVALID_TEMPLATE');
  return root.children.map(id => {
    const component = display.components.find(item => item.id === id);
    if (!component || !['Text', 'ChoicePicker', 'Button'].includes(String(component.component))) throw new Error('UNSUPPORTED_COMPONENT');
    return component;
  });
}

function Card({ card, onUpdate }: { card: ChatCard; onUpdate: (card: ChatCard) => void }) {
  const [choice, setChoice] = useState(typeof card.display.data.optionId === 'string' ? card.display.data.optionId : '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const inFlight = useRef(false);
  const operable = card.status === 'WAITING_ACTION' && !busy;
  const selected = operable ? choice : (typeof card.display.data.optionId === 'string' ? card.display.data.optionId : choice);
  let components;
  try { components = material(card); } catch { return <p role="alert">此 Application 暂不支持展示，已禁止操作。</p>; }
  const submit = async (component: Record<string, unknown>) => {
    if (!operable || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError('');
    try {
      const event = record(record(component.action).event);
      if (typeof event.name !== 'string' || !card.display.actions.some(action => action.actionName === event.name)) throw new Error('INVALID_ACTION');
      const inputs: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(record(event.context))) {
        const binding = record(value);
        if (binding.path === '/optionId' && choice) inputs[key] = choice;
        else if (binding.literal === true) inputs[key] = true;
        else throw new Error('UNSUPPORTED_BINDING');
      }
      onUpdate(await productApi.chatAction(card.conversationId, card, crypto.randomUUID(), event.name, inputs));
    } catch {
      setError('操作未确认或配置已变化。请重新读取卡片状态，不要重复提交。');
      // No automatic POST replay. Keep controls blocked until a fresh read.
      return;
    } finally { inFlight.current = false; }
    setBusy(false);
  };
  return <details className="display-card" open={card.status === 'WAITING_ACTION' || card.status === 'DISPLAY_ONLY'}>
    <summary>{card.display.applicationKey} · {labels[card.status] ?? '状态待确认'}</summary>
    {components.map((component, index) => {
      if (component.component === 'Text') {
        const binding = record(component.text);
        const path = typeof binding.path === 'string' && /^\/[^/]+$/.test(binding.path) ? binding.path.slice(1) : '';
        const text = card.display.data[path];
        return typeof text === 'string' ? <MarkdownContent key={index} markdown={text} /> : null;
      }
      if (component.component === 'ChoicePicker') {
        const options = card.display.data.options;
        return <fieldset key={index} disabled={!operable}><legend>请选择</legend>{Array.isArray(options) ? options.map(item => {
          const option = record(item);
          if (typeof option.value !== 'string' || typeof option.label !== 'string') return null;
          return <label className="choice" key={option.value}><input type="radio" name={card.cardId} checked={selected === option.value} onChange={() => setChoice(String(option.value))} />{option.label}</label>;
        }) : null}</fieldset>;
      }
      return <button key={index} className="primary" disabled={!operable || !choice} onClick={() => void submit(component)}>{busy ? '提交中…' : String(component.label ?? '确认')}</button>;
    })}
    {card.result !== undefined ? <details><summary>操作结果</summary><pre>{JSON.stringify(card.result, null, 2)}</pre></details> : null}
    {error ? <p role="alert">{error}</p> : null}
  </details>;
}

export function ChatApplications({ conversationId, refreshKey, active }: { conversationId: string; refreshKey: number; active: boolean }) {
  const [cards, setCards] = useState<ChatCard[]>([]);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [manualRevision, setManualRevision] = useState(0);
  const generation = useRef(0);
  const reload = useCallback(() => setRevision(value => value + 1), []);
  useEffect(() => {
    const abort = new AbortController();
    const current = ++generation.current;
    productApi.chatCards(conversationId, abort.signal).then(result => {
      if (current === generation.current) {
        setCards(previous => result.cards.map(card => {
          const newer = previous.find(item => item.cardId === card.cardId && item.revision > card.revision);
          return newer ?? card;
        }));
        setError('');
      }
    }).catch(() => { if (!abort.signal.aborted) setError('卡片读取失败，请重新读取。'); });
    return () => { generation.current++; abort.abort(); };
  }, [conversationId, refreshKey, revision]);
  const waiting = cards.some(card => card.status === 'EXECUTING' || card.status === 'WAITING_ACTION');
  useEffect(() => {
    if (!active && !waiting) return;
    const timer = setInterval(reload, 5000);
    return () => clearInterval(timer);
  }, [active, waiting, reload]);
  return <section aria-label="对话中的 Skill 卡片">
    {cards.length || error ? <button className="secondary" onClick={() => { setManualRevision(value => value + 1); reload(); }}>重新读取卡片</button> : null}
    {error ? <p role="alert">{error}</p> : null}
    {cards.map(card => <Card key={`${card.cardId}:${card.revision}:${manualRevision}`} card={card} onUpdate={updated => setCards(items => items.map(item => item.cardId === updated.cardId && updated.revision >= item.revision ? updated : item))} />)}
  </section>;
}
