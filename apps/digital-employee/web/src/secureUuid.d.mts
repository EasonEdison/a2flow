export type RandomValuesSource = {
  getRandomValues<T extends ArrayBufferView>(array: T): T;
};
export function createUuidV4(source?: RandomValuesSource): string;
