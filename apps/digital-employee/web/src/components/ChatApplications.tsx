import {
  createContext,
  lazy,
  Suspense,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { productApi, type ChatCard, type ComposerDraftEffect } from '../productApi';

const A2uiSnapshotCard = lazy(() => import('./A2uiSnapshotCard').then(module => ({
  default: module.A2uiSnapshotCard,
})));

type ChatApplicationsContextValue = {
  cards: ChatCard[];
  error: string;
  manualReloadKey: number;
  reload: () => void;
  updateCard: (card: ChatCard) => void;
  onComposerDraft: (effect: ComposerDraftEffect) => void;
};

const ChatApplicationsContext = createContext<ChatApplicationsContextValue | null>(null);

const useChatApplications = () => {
  const value = useContext(ChatApplicationsContext);
  if (!value) throw new Error('ChatApplicationsProvider is required');
  return value;
};

export function ChatApplicationsProvider({
  conversationId,
  refreshKey,
  active,
  onComposerDraft,
  children,
}: {
  conversationId: string;
  refreshKey: number;
  active: boolean;
  onComposerDraft: (effect: ComposerDraftEffect) => void;
  children: React.ReactNode;
}) {
  const [cards, setCards] = useState<ChatCard[]>([]);
  const [error, setError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [manualReloadKey, setManualReloadKey] = useState(0);
  const manualReload = useRef(false);
  const generation = useRef(0);
  const reload = useCallback(() => setReloadKey(value => value + 1), []);
  const updateCard = useCallback((updated: ChatCard) => {
    generation.current++;
    setCards(items => items.map(item => item.cardId === updated.cardId ? updated : item));
  }, []);

  useEffect(() => {
    const abort = new AbortController();
    const current = ++generation.current;
    void productApi.chatCards(conversationId, abort.signal).then(result => {
      if (current !== generation.current) return;
      setCards(result.cards);
      setError('');
      if (manualReload.current) {
        manualReload.current = false;
        setManualReloadKey(value => value + 1);
      }
    }).catch(() => {
      if (!abort.signal.aborted) setError('卡片读取失败，请重新读取。');
    });
    return () => {
      generation.current++;
      abort.abort();
    };
  }, [conversationId, refreshKey, reloadKey]);

  const waiting = cards.some(card => card.status === 'EXECUTING' || card.status === 'WAITING_ACTION');
  useEffect(() => {
    if (!active && !waiting) return;
    const timer = window.setInterval(reload, 5000);
    return () => window.clearInterval(timer);
  }, [active, waiting, reload]);

  const value = useMemo<ChatApplicationsContextValue>(() => ({
    cards,
    error,
    manualReloadKey,
    reload: () => {
      manualReload.current = true;
      reload();
    },
    updateCard,
    onComposerDraft,
  }), [cards, error, manualReloadKey, onComposerDraft, reload, updateCard]);

  return <ChatApplicationsContext.Provider value={value}>{children}</ChatApplicationsContext.Provider>;
}

export function TurnApplications({ turnId }: { turnId: string }) {
  const { cards } = useChatApplications();
  const turnCards = cards.filter(card => card.turnId === turnId);
  if (!turnCards.length) return null;
  return <section className="turn-applications" aria-label="本轮交互卡片">
    <ApplicationCards cards={turnCards} />
  </section>;
}

function ApplicationCards({ cards }: { cards: ChatCard[] }) {
  const { manualReloadKey, updateCard, onComposerDraft } = useChatApplications();
  return <>
    <Suspense fallback={<p role="status">正在加载卡片组件…</p>}>
      {cards.map(card => (
        <A2uiSnapshotCard
          key={`${card.cardId}:${manualReloadKey}`}
          card={card}
          onUpdate={updateCard}
          onComposerDraft={onComposerDraft}
        />
      ))}
    </Suspense>
  </>;
}

export function ChatApplicationsStatus({ knownTurnIds }: { knownTurnIds: ReadonlySet<string> }) {
  const { cards, error, reload } = useChatApplications();
  const unassigned = cards.filter(card => !knownTurnIds.has(card.turnId));
  if (!cards.length && !error) return null;
  return <section className="chat-applications-status" aria-live="polite">
    {error ? <p role="alert">{error}</p> : null}
    {unassigned.length ? <section className="historical-applications" aria-label="历史交互卡片">
      <h3>历史交互卡片</h3>
      <p>{unassigned.length} 张卡片无法与当前消息的轮次标识匹配，已独立保留。</p>
      <ApplicationCards cards={unassigned} />
    </section> : null}
    <button className="secondary" type="button" onClick={reload}>重新读取卡片</button>
  </section>;
}
