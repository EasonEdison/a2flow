import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { assetAccessApi } from '../api';
import type { AssetAccessResult, AssetPermissions, ReleaseAssetType } from '../types';

const deniedPermissions: AssetPermissions = {
  canView: false,
  canEdit: false,
  canPublish: false,
  canForcePublish: false,
  canOffline: false,
  canManageOwner: false,
};

export interface AssetAccessState {
  access?: AssetAccessResult;
  permissions: AssetPermissions;
  loading: boolean;
  error: string;
  readonlyReason: string;
  refresh: () => Promise<AssetAccessResult | undefined>;
}

const AssetAccessContext = createContext<AssetAccessState | null>(null);

export function useAssetAccess(assetType: ReleaseAssetType, assetKey?: string): AssetAccessState {
  const [access, setAccess] = useState<AssetAccessResult>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const requestSequence = useRef(0);

  const refresh = useCallback(async () => {
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    if (!assetKey) {
      setAccess(undefined);
      setError('');
      setLoading(false);
      return undefined;
    }
    setLoading(true);
    setError('');
    try {
      const result = await assetAccessApi.get(assetType, assetKey);
      if (requestSequence.current === sequence) setAccess(result);
      return result;
    } catch (cause) {
      const reason = cause instanceof Error ? cause.message : '资产权限加载失败';
      if (requestSequence.current === sequence) {
        setAccess(undefined);
        setError(reason);
      }
      return undefined;
    } finally {
      if (requestSequence.current === sequence) setLoading(false);
    }
  }, [assetKey, assetType]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return useMemo(() => {
    const permissions = access?.permissions || deniedPermissions;
    const readonlyReason =
      access?.reason || error || (assetKey && loading ? '正在加载资产权限' : '');
    return {
      access,
      permissions,
      loading,
      error,
      readonlyReason,
      refresh,
    };
  }, [access, assetKey, error, loading, refresh]);
}

export const AssetAccessProvider: React.FC<{
  assetType: ReleaseAssetType;
  assetKey?: string;
  children: React.ReactNode;
}> = ({ assetType, assetKey, children }) => {
  const value = useAssetAccess(assetType, assetKey);
  return <AssetAccessContext.Provider value={value}>{children}</AssetAccessContext.Provider>;
};

export function useAssetAccessContext(): AssetAccessState {
  const value = useContext(AssetAccessContext);
  if (!value) {
    throw new Error('useAssetAccessContext 必须在 AssetAccessProvider 内使用');
  }
  return value;
}
