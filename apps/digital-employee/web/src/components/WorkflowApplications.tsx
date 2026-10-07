import { lazy, Suspense } from 'react';
import { productApi, type ChatCard, type WorkflowCard } from '../productApi';

const A2uiSnapshotCard = lazy(() => import('./A2uiSnapshotCard').then(module => ({ default: module.A2uiSnapshotCard })));

export function WorkflowApplications({ runId, entries, disabled, onUpdate, onSettled, title }: {
  runId: string;
  title?: string;
  entries: WorkflowCard[];
  disabled: boolean;
  onUpdate: (card: ChatCard) => void;
  onSettled: () => Promise<void>;
}) {
  return <Suspense fallback={<p role="status">正在加载卡片组件…</p>}>
    {entries.map(entry => <A2uiSnapshotCard
      key={entry.card.cardId}
      card={entry.card}
      title={title ? `${title} · 业务卡片` : '业务卡片'}
      initiallyExpanded={!disabled}
      disabled={disabled}
      onUpdate={onUpdate}
      onComposerDraft={() => {}}
      submitAction={async (_card, requestId, actionName, inputs) => {
        const response = await productApi.runCardAction(runId, entry, requestId, actionName, inputs);
        return response;
      }}
      onActionStateChange={active => { if (!active) void onSettled(); }}
    />)}
  </Suspense>;
}
