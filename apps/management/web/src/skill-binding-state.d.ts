import type { AssetSummary } from './contracts';

export type BindingStatus = 'available' | 'unavailable' | 'duplicate' | 'malformed';
export interface BindingRow {
  identity: string;
  value: unknown;
  key: string | null;
  asset?: AssetSummary;
  status: BindingStatus;
}

export function bindingKey(asset: AssetSummary): string | null;
export function filterBindingAssets(assets: AssetSummary[], query: string): AssetSummary[];
export function bindingRows(values: unknown[], assets: AssetSummary[]): BindingRow[];
export function addBinding(values: unknown[], key: string): unknown[];
export function removeBinding(values: unknown[], identity: string): unknown[];
