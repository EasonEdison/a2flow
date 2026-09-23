import SafeJSON from 'safe-json-parse-and-stringify';

// The upstream CommonJS package exposes getters that Node cannot detect as named exports.
export const { jsonParse, jsonStringify, cloneDeep } = SafeJSON;
