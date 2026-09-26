import type { Catalog, MessageProcessor, A2uiClientAction } from '@a2ui/web_core/v0_9';
import type { ReactComponentImplementation } from '@a2ui/react/v0_9';
import type { ChatCard } from './productApi';
export const RPC_PROFILE: string;
export function persistedSnapshotKey(card: ChatCard): string;
export function createSnapshotProcessor(display: ChatCard['display'], catalogs: Catalog<ReactComponentImplementation>[]): MessageProcessor<ReactComponentImplementation>;
export function cardIsOperable(card: ChatCard): boolean;
export function actionRequest(card: ChatCard, event: A2uiClientAction): { actionName: string; inputs: { surfaceId: string; sourceComponentId: string; context: Record<string, unknown> } };
