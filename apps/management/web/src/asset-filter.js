export function filterAssets(assets, query) {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  if (!normalizedQuery) return assets;

  return assets.filter((asset) => [
    asset.name,
    asset.key,
    asset.skillKey,
    asset.assetId,
    asset.versionId,
  ].some((value) => typeof value === 'string' && value.toLocaleLowerCase().includes(normalizedQuery)));
}
