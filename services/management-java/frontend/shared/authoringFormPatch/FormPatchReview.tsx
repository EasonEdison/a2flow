import React, { useMemo } from 'react';
import { Empty, Space, Tag, Typography } from 'antd';
import AuthoringChangeReviewFrame, { type ChangeReviewAdapter } from '../authoringChangeReview';
import type { FormPatchConflictChoice, FormPatchReview } from './index';

const { Text } = Typography;

interface FormPatchReviewProps<TForm> {
  review: FormPatchReview<TForm>;
  selectedChangeIds: Set<string>;
  conflictChoices: Record<string, FormPatchConflictChoice>;
  onToggleChange: (changeId: string, selected: boolean) => void;
  onConflictChoice: (changeId: string, choice: FormPatchConflictChoice) => void;
  adapter: ChangeReviewAdapter;
}

function valueText(value: unknown): string {
  if (value === undefined) return '未定义';
  if (value === null) return 'null';
  if (typeof value === 'string') return value || '空字符串';
  try {
    const text = JSON.stringify(value, null, 2);
    return text.length > 420 ? `${text.slice(0, 420)}...` : text;
  } catch {
    return String(value);
  }
}

function FormPatchReviewPanel<TForm>({
  review,
  selectedChangeIds,
  conflictChoices,
  onToggleChange,
  onConflictChoice,
  adapter,
}: FormPatchReviewProps<TForm>) {
  const groupedChanges = useMemo(
    () =>
      Array.from(new Set(review.changes.map((change) => change.section))).map((section) => ({
        section,
        changes: review.changes.filter((change) => change.section === section),
      })),
    [review.changes],
  );
  const conflictCount = review.changes.filter((change) => change.status === 'conflict').length;
  const unresolvedCount = review.changes.filter(
    (change) => change.status === 'conflict' && !conflictChoices[change.id],
  ).length;
  const selectedCount = review.changes.filter((change) =>
    change.status === 'safe'
      ? selectedChangeIds.has(change.id)
      : conflictChoices[change.id] === 'ai',
  ).length;

  return (
    <AuthoringChangeReviewFrame
      title="表单修改建议"
      summary={review.proposal.summary || 'AI 已生成表单修改建议'}
      metadata={
        <Space wrap>
          <Tag>基于 r{review.proposal.baseRevision}</Tag>
          <Tag color="success">可应用 {review.changes.length - conflictCount}</Tag>
          {conflictCount ? <Tag color="warning">冲突 {conflictCount}</Tag> : null}
        </Space>
      }
      adapter={{
        ...adapter,
        applyDisabled: adapter.applyDisabled || unresolvedCount > 0 || !review.changes.length,
      }}
      footerNote={
        <>
          <span>已选择 {selectedCount} 项</span>
          {unresolvedCount ? <span>还有 {unresolvedCount} 个冲突未选择</span> : null}
        </>
      }
    >
      <div className="authoring-form-review-list">
        {groupedChanges.length ? (
          groupedChanges.map((group) => (
            <section key={group.section} className="authoring-form-review-group">
              <div className="authoring-form-review-group-title">{group.section}</div>
              {group.changes.map((change) => (
                <article
                  key={change.id}
                  className={`authoring-form-review-change ${change.status}`}
                >
                  <div className="authoring-form-review-change-head">
                    {change.status === 'safe' ? (
                      <input
                        aria-label={`选择 ${change.label}`}
                        checked={selectedChangeIds.has(change.id)}
                        onChange={(event) => onToggleChange(change.id, event.target.checked)}
                        type="checkbox"
                      />
                    ) : (
                      <span className="authoring-form-review-conflict">!</span>
                    )}
                    <div>
                      <Text strong>{change.label}</Text>
                      <div className="authoring-form-review-path">{change.path}</div>
                    </div>
                  </div>
                  {change.status === 'safe' ? (
                    <div className="authoring-form-review-diff">
                      <div>
                        <span>当前值</span>
                        <pre>{valueText(change.currentValue)}</pre>
                      </div>
                      <div>
                        <span>AI 建议</span>
                        <pre>{valueText(change.aiValue)}</pre>
                      </div>
                    </div>
                  ) : (
                    <div className="authoring-form-review-choices">
                      <button
                        className={conflictChoices[change.id] === 'user' ? 'selected' : ''}
                        onClick={() => onConflictChoice(change.id, 'user')}
                        type="button"
                      >
                        <span>保留当前</span>
                        <pre>{valueText(change.currentValue)}</pre>
                      </button>
                      <button
                        className={conflictChoices[change.id] === 'ai' ? 'selected' : ''}
                        onClick={() => onConflictChoice(change.id, 'ai')}
                        type="button"
                      >
                        <span>采用 AI</span>
                        <pre>{valueText(change.aiValue)}</pre>
                      </button>
                    </div>
                  )}
                </article>
              ))}
            </section>
          ))
        ) : (
          <Empty description="AI 建议与当前表单没有差异" />
        )}
      </div>
    </AuthoringChangeReviewFrame>
  );
}

export default FormPatchReviewPanel;
