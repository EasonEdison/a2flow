function requireRecord(value, name) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`Invalid function contract: ${name} must be an object`);
  }
  return value;
}

export function contractFunctionCodes(contract) {
  return Object.freeze(Object.keys(requireRecord(contract?.functions, 'functions')));
}

export function officialFunctionCodes(contract) {
  const codes = contractFunctionCodes(contract);
  const extensions = requireRecord(contract?.sdkExtensions, 'sdkExtensions');
  for (const extensionCode of Object.keys(extensions)) {
    if (!codes.includes(extensionCode)) {
      throw new Error(`Invalid function contract: extension ${extensionCode} has no schema`);
    }
  }
  return Object.freeze(codes.filter(code => !Object.hasOwn(extensions, code)));
}

export function selectFunctionImplementations(codes, sdkFunctions, extensionFunctions = {}) {
  return codes.map(code => {
    const implementation = Object.hasOwn(extensionFunctions, code)
      ? extensionFunctions[code]
      : sdkFunctions.get(code);
    if (!implementation || implementation.name !== code) {
      throw new Error(`Missing A2UI function implementation: ${code}`);
    }
    return implementation;
  });
}
