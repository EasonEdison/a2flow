import type { ProcessingSelection, RunReference } from './productApi';
export type PendingChatSend = { clientRequestId: string; text: string; references: RunReference[]; processing?: ProcessingSelection };
export function pendingChatSendKey(owner: string, conversation: string): string;
export function readPendingChatSend(key: string, storage?: Storage): PendingChatSend | null;
export function persistPendingChatSend(key: string, request: PendingChatSend, storage?: Storage): void;
export function acknowledgePendingChatSend(key: string, requestId: string, storage?: Storage): void;
