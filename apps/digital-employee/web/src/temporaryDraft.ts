import { createContext } from 'react';
import type { ChatCard } from './productApi';

/** Supplied only by the authenticated /session response, never by card metadata. */
export const TemporaryDraftOwner = createContext<string | null>(null);
const prefix = 'a2flow.temporary-draft.v1:';
const object = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

export function temporaryDraftKey(owner: string | null, card: ChatCard): string | undefined {
  if (!owner || !/^\d+$/.test(owner) || card.display.definitionSource !== 'TEMPORARY'
    || card.display.protocolProfile !== 'a2flow.temporary.v1') return undefined;
  return prefix + [owner, card.conversationId, card.cardId].map(encodeURIComponent).join(':');
}

function inputsOnly(value: unknown, card: ChatCard): Record<string, unknown> {
  const properties = card.display.inputSchema?.properties;
  if (!object(value) || !object(properties)) return {};
  return Object.fromEntries(Object.keys(properties)
    .filter(key => !['__proto__', 'constructor', 'prototype'].includes(key) && Object.hasOwn(value, key))
    .map(key => [key, value[key]]));
}

export function readTemporaryDraft(key: string, card: ChatCard): Record<string, unknown> | undefined {
  const raw = localStorage.getItem(key);
  if (!raw) return undefined;
  if (raw.length > 65536) throw new Error('INVALID_DRAFT');
  const saved: unknown = JSON.parse(raw);
  if (!object(saved) || saved.version !== 1
    || saved.schema !== JSON.stringify(card.display.inputSchema) || !object(saved.inputs)) {
    localStorage.removeItem(key);
    return undefined;
  }
  return inputsOnly(saved.inputs, card);
}

export function writeTemporaryDraft(key: string, card: ChatCard, inputs: unknown): void {
  const text = JSON.stringify({ version: 1, schema: JSON.stringify(card.display.inputSchema),
    inputs: inputsOnly(inputs, card) });
  if (text.length > 65536) throw new Error('DRAFT_TOO_LARGE');
  localStorage.setItem(key, text);
}

export function clearTemporaryDraft(key: string): void {
  localStorage.removeItem(key);
}
