import type { RunReference } from './productApi';

export type ChatDraft = { text: string; references: RunReference[]; updatedAt: number };
const prefix = 'a2flow:chat-draft:v1:';
const maxAge = 7 * 24 * 60 * 60 * 1000;
export const chatDraftKey = (owner: string, conversation: string) => `${prefix}${encodeURIComponent(owner)}:${encodeURIComponent(conversation)}`;
export function readChatDraft(key: string): ChatDraft {
  const empty = { text: '', references: [], updatedAt: Date.now() };
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(key) || 'null');
    if (!value || typeof value !== 'object') return empty;
    const draft = value as ChatDraft;
    if (typeof draft.updatedAt !== 'number' || Date.now() - draft.updatedAt > maxAge) { sessionStorage.removeItem(key); return empty; }
    return { text: typeof draft.text === 'string' ? draft.text.slice(0, 4000) : '', updatedAt: draft.updatedAt,
      references: Array.isArray(draft.references) ? draft.references.filter(item => item && typeof item.activityId === 'string' && typeof item.workflowName === 'string' && typeof item.createdAt === 'string').slice(0, 3) : [] };
  } catch { return empty; }
}
export function saveChatDraft(key: string, text: string, references: RunReference[]): boolean {
  try {
    const keys = Object.keys(sessionStorage).filter(item => item.startsWith(prefix));
    const updatedAt = (item: string) => { try { return Number(JSON.parse(sessionStorage.getItem(item) || 'null')?.updatedAt) || 0; } catch { return 0; } };
    keys.sort((a, b) => updatedAt(b) - updatedAt(a));
    for (const stale of keys.filter(item => item !== key).slice(19)) sessionStorage.removeItem(stale);
    if (!text && !references.length) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, JSON.stringify({ text: text.slice(0, 4000), references: references.slice(0, 3), updatedAt: Date.now() }));
    return true;
  } catch { return false; }
}
