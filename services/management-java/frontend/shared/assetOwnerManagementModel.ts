import type { AssetAccessResult } from '../types';

export interface AssetOwnerManagementView {
  ownerIds: string[];
  canManageOwner: boolean;
}

export const normalizeAssetOwnerIds = (input: string): string[] =>
  Array.from(
    new Set(
      input
        ?.split(',')
        ?.map?.((item) => item.trim())
        ?.filter?.(Boolean),
    ),
  );

export const buildAssetOwnerManagementView = (
  access?: AssetAccessResult,
): AssetOwnerManagementView => ({
  ownerIds: (access?.owners || []).map((owner) => owner.principalId),
  canManageOwner: access?.permissions?.canManageOwner === true,
});
