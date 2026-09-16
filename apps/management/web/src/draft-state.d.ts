import type { AssetKind, DraftBuffer, ManagedDraft } from './contracts';

export function shouldChangeKind(current: AssetKind | null, next: AssetKind): boolean;

export function publicationConfirmation(target: import('./contracts').PublicationTarget): string;
export function rollbackTarget(environment: import('./contracts').Environment, versionId: string): import('./contracts').PublicationTarget;
export function rollbackConfirmation(target: import('./contracts').PublicationTarget): string;

export function settleSaveBuffer(
  current: DraftBuffer,
  submittedText: string,
  saved: ManagedDraft,
): DraftBuffer;
