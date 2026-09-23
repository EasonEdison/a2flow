import { useCallback, useEffect, useMemo, useState } from 'react';
import { assetReleaseApi } from '../api';
import type { AssetReleaseOverview, ReleaseAssetType } from '../types';

export const isAssetReleaseEditable = (overview?: AssetReleaseOverview): boolean => {
  if (!overview) return false;
  if (overview.activeChange?.status === 'ACTIVE') return true;
  return !overview.versions?.length && !overview.activeChange;
};

export interface AssetReleaseEditability {
  overview?: AssetReleaseOverview;
  editable: boolean;
  loading: boolean;
  error: string;
  refresh: () => Promise<void>;
  acceptOverview: (overview: AssetReleaseOverview) => void;
}

/**
 * 统一读取资产发布状态并计算编辑资格。
 *
 * 新建资产尚无稳定标识时允许填写；已有稳定标识后默认失败关闭，只有后端返回初始可编辑态或
 * ACTIVE 变更时才允许继续编辑。保存接口仍由后端门禁做最终校验。
 */
export const useAssetReleaseEditability = (
  assetType: ReleaseAssetType,
  assetKey?: string,
): AssetReleaseEditability => {
  const [overview, setOverview] = useState<AssetReleaseOverview>();
  const [loading, setLoading] = useState(Boolean(assetKey));
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    if (!assetKey) {
      setOverview(undefined);
      setLoading(false);
      setError('');
      return;
    }
    setLoading(true);
    setError('');
    try {
      setOverview(await assetReleaseApi.overview(assetType, assetKey));
    } catch (reason) {
      setOverview(undefined);
      setError(reason instanceof Error ? reason.message : '发布状态加载失败');
    } finally {
      setLoading(false);
    }
  }, [assetKey, assetType]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return useMemo(
    () => ({
      overview,
      editable: assetKey ? isAssetReleaseEditable(overview) : true,
      loading,
      error,
      refresh,
      acceptOverview: setOverview,
    }),
    [assetKey, error, loading, overview, refresh],
  );
};
