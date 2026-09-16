import type { AssetKind, DraftBuffer, ManagedDraft } from './contracts';

export function shouldChangeKind(current: AssetKind | null, next: AssetKind): boolean;

export function settleSaveBuffer(
  current: DraftBuffer,
  submittedText: string,
  saved: ManagedDraft,
): DraftBuffer;
