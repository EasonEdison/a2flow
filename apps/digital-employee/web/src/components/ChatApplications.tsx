import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { productApi, type ChatCard } from '../productApi';
const A2uiSnapshotCard = lazy(() => import('./A2uiSnapshotCard').then(module => ({ default: module.A2uiSnapshotCard })));

export function ChatApplications({ conversationId, refreshKey, active }: { conversationId: string; refreshKey: number; active: boolean }) {
  const [cards, setCards] = useState<ChatCard[]>([]);
  const [error, setError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [manualReloadKey, setManualReloadKey] = useState(0);
  const manualReload = useRef(false);
  const generation = useRef(0);
  const reload = useCallback(() => setReloadKey(value => value + 1), []);
  const updateCard = useCallback((updated: ChatCard) => {
    // An Action response is newer than every GET that started before it.
    generation.current++;
    setCards(items => items.map(item => item.cardId === updated.cardId ? updated : item));
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    const current = ++generation.current;
    productApi.chatCards(conversationId, abort.signal).then(result => {
      if (current === generation.current) {
        setCards(result.cards);
        setError('');
        if (manualReload.current) { manualReload.current = false; setManualReloadKey(value => value + 1); }
      }
    }).catch(() => { if (!abort.signal.aborted) setError('卡片读取失败，请重新读取。'); });
    return () => { generation.current++; abort.abort(); };
  }, [conversationId, refreshKey, reloadKey]);
  const waiting = cards.some(card => card.status === 'EXECUTING' || card.status === 'WAITING_ACTION');
  useEffect(() => {
    if (!active && !waiting) return;
    const timer = setInterval(reload, 5000);
    return () => clearInterval(timer);
  }, [active, waiting, reload]);
  return <section aria-label="对话中的 Skill 卡片">
    {cards.length || error ? <button className="secondary" onClick={() => { manualReload.current = true; reload(); }}>重新读取卡片</button> : null}
    {error ? <p role="alert">{error}</p> : null}
    <Suspense fallback={<p role="status">正在加载卡片组件…</p>}>
      {cards.map(card => <A2uiSnapshotCard key={`${card.cardId}:${manualReloadKey}`} card={card} onUpdate={updateCard} />)}
    </Suspense>
  </section>;
}
