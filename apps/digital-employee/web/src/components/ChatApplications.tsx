import { lazy, Suspense } from 'react';

import type {
  ChatApplicationPart,
  ChatCard,
  ComposerDraftEffect,
} from '../productApi';

const A2uiSnapshotCard = lazy(() => import('./A2uiSnapshotCard').then(module => ({
  default: module.A2uiSnapshotCard,
})));

type ApplicationCallbacks = {
  onCardUpdate: (card: ChatCard) => void;
  onCardActionStateChange: (cardId: string, active: boolean) => void;
  onComposerDraft: (effect: ComposerDraftEffect) => void;
};

function ApplicationCard({ card, callbacks }: {
  card: ChatCard;
  callbacks: ApplicationCallbacks;
}) {
  return <Suspense fallback={<p role="status">正在加载卡片组件…</p>}>
    <A2uiSnapshotCard
      card={card}
      onUpdate={callbacks.onCardUpdate}
      onActionStateChange={(active) => callbacks.onCardActionStateChange(card.cardId, active)}
      onComposerDraft={callbacks.onComposerDraft}
    />
  </Suspense>;
}

export function OrderedApplication({ part, ...callbacks }: {
  part: ChatApplicationPart;
} & ApplicationCallbacks) {
  if (!part.card) {
    return <section className="missing-application" role="alert">
      卡片 {part.cardId} 的最新快照不可用，未重新执行生成。
    </section>;
  }
  return <section className="ordered-application" aria-label="交互卡片">
    <ApplicationCard card={part.card} callbacks={callbacks} />
  </section>;
}

export function LegacyApplications({ cards, ...callbacks }: {
  cards: ChatCard[];
} & ApplicationCallbacks) {
  if (!cards.length) return null;
  return <section className="legacy-applications" aria-label="本轮历史交互卡片">
    {cards.map(card => <ApplicationCard key={`legacy:${card.cardId}`} card={card} callbacks={callbacks} />)}
  </section>;
}

export function UnassignedApplications({ cards, ...callbacks }: {
  cards: ChatCard[];
} & ApplicationCallbacks) {
  if (!cards.length) return null;
  return <section className="historical-applications" aria-label="历史交互卡片">
    <h3>历史交互卡片</h3>
    <p>{cards.length} 张旧卡片缺少可靠轮次归属，已独立保留。</p>
    {cards.map(card => <ApplicationCard key={`unassigned:${card.cardId}`} card={card} callbacks={callbacks} />)}
  </section>;
}
