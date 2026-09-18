export function bindingKey(asset) {
  const key = asset?.key ?? asset?.skillKey;
  return typeof key === 'string' && key ? key : null;
}

export function filterBindingAssets(assets, query) {
  const normalized = query.trim().toLocaleLowerCase();
  return assets.filter((asset) => {
    const key = bindingKey(asset);
    if (!key) return false;
    if (!normalized) return true;
    return [key, asset.name, asset.description].some(
      (value) => typeof value === 'string' && value.toLocaleLowerCase().includes(normalized),
    );
  });
}

export function bindingRows(values, assets) {
  const known = new Map(assets.map((asset) => [bindingKey(asset), asset]).filter(([key]) => key));
  const occurrences = new Map();
  return values.map((value, index) => {
    if (typeof value !== 'string') {
      return { identity: `malformed:${index}`, value, key: null, asset: undefined, status: 'malformed' };
    }
    const occurrence = occurrences.get(value) ?? 0;
    occurrences.set(value, occurrence + 1);
    const asset = known.get(value);
    return {
      identity: `binding:${value}:${occurrence}`,
      value,
      key: value,
      asset,
      status: occurrence > 0 ? 'duplicate' : asset ? 'available' : 'unavailable',
    };
  });
}

export function addBinding(values, key) {
  const normalized = key.trim();
  if (!normalized || values.includes(normalized)) return values;
  return [...values, normalized];
}

export function removeBinding(values, identity) {
  const rows = bindingRows(values, []);
  const index = rows.findIndex((row) => row.identity === identity);
  return index < 0 ? values : values.filter((_, itemIndex) => itemIndex !== index);
}
