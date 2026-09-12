import { useId, useState } from 'react';

import type { InteractiveCard } from '../presentation';
import { MarkdownContent } from './MarkdownContent';

export function ApplicationCard({
  card,
  busy,
  onSubmit,
}: {
  card: InteractiveCard;
  busy: boolean;
  onSubmit: (value: string) => Promise<void>;
}) {
  const group = useId();
  const [choice, setChoice] = useState(card.selected ?? '');
  const [error, setError] = useState('');

  return (
    <section className="choice-card" aria-label={card.prompt}>
      <div className="card-heading">
        <h3>{card.prompt}</h3>
        <span className={'badge ' + (card.operable ? 'waiting' : 'neutral')}>
          {card.operable ? '需要你的确认' : '只读记录'}
        </span>
      </div>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          if (!choice || !card.operable || busy) {
            return;
          }
          setError('');
          try {
            await onSubmit(choice);
          } catch {
            setError('提交未确认，请查看请求状态后再操作。');
          }
        }}
      >
        <fieldset disabled={!card.operable || busy}>
          <legend className="sr-only">选择活动方案</legend>
          <div className="choices">
            {card.choices.map((item) => (
              <label
                key={item.value}
                className={'choice ' + (choice === item.value ? 'selected' : '')}
              >
                <input
                  type="radio"
                  name={group}
                  value={item.value}
                  checked={choice === item.value}
                  onChange={() => setChoice(item.value)}
                />
                <span>
                  <strong>{item.label}</strong>
                  {item.description ? <small>{item.description}</small> : null}
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        {card.operable ? (
          <button className="primary full" disabled={!choice || busy} type="submit">
            {busy ? '正在提交…' : card.buttonLabel}
          </button>
        ) : (
          <p className="readonly-note">此卡片保留供查看，无法继续操作。</p>
        )}
        {error ? <p role="alert" className="inline-error">{error}</p> : null}
      </form>
    </section>
  );
}

export function DisplayApplicationCard({
  title,
  fields,
}: {
  title: string;
  fields: { label: string; markdown: string }[];
}) {
  return (
    <section className="display-card" aria-label={title}>
      <div className="card-heading">
        <h3>{title}</h3>
        <span className="badge neutral">仅展示</span>
      </div>
      {fields.map((field) => (
        <section key={field.label} className="display-field">
          <h4>{field.label}</h4>
          <MarkdownContent markdown={field.markdown} />
        </section>
      ))}
    </section>
  );
}
