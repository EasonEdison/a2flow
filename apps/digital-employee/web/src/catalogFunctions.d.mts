export interface FunctionContract {
  functions: Record<string, unknown>;
  sdkExtensions: Record<string, unknown>;
}

export interface NamedFunctionImplementation {
  name: string;
}

export function contractFunctionCodes(contract: FunctionContract): readonly string[];
export function officialFunctionCodes(contract: FunctionContract): readonly string[];
export function selectFunctionImplementations<T extends NamedFunctionImplementation>(
  codes: readonly string[],
  sdkFunctions: ReadonlyMap<string, T>,
  extensionFunctions?: Readonly<Record<string, T>>,
): T[];
