import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { productApi, type ChatCard } from '../productApi';
const A2uiSnapshotCard = lazy(() => import('./A2uiSnapshotCard').then(module => ({ default: module.A2uiSnapshotCard })));

export function ChatApplications({ conversationId, refreshKey, active }: { conversationId: string; refreshKey: number; active: boolean }) {
  const [cards, setCards] = useState<ChatCard[]>([]);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [manualRevision, setManualRevision] = useState(0);
  const manualReload = useRef(false);
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
        if (manualReload.current) { manualReload.current = false; setManualRevision(value => value + 1); }
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
    {cards.length || error ? <button className="secondary" onClick={() => { manualReload.current = true; reload(); }}>重新读取卡片</button> : null}
    {error ? <p role="alert">{error}</p> : null}
    <Suspense fallback={<p role="status">正在加载卡片组件…</p>}>
      {cards.map(card => <A2uiSnapshotCard key={`${card.cardId}:${card.revision}:${manualRevision}`} card={card} onUpdate={updated => setCards(items => items.map(item => item.cardId === updated.cardId && updated.revision >= item.revision ? updated : item))} />)}
    </Suspense>
  </section>;
}
