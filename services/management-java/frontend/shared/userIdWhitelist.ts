/** Canonical decimal strings preserve the complete signed 64-bit identity range. */
export function normalizeUserIdWhitelist(value: string): string | undefined {
  if (!value.trim()) return '';
  const ids = value.split(',').map((item) => item.trim());
  if (ids.some((id) => !/^(0|-?[1-9][0-9]*)$/.test(id) ||
      BigInt(id) < -9223372036854775808n || BigInt(id) > 9223372036854775807n)) return undefined;
  return Array.from(new Set(ids)).sort((left, right) => BigInt(left) < BigInt(right) ? -1 : BigInt(left) > BigInt(right) ? 1 : 0).join(',');
}
