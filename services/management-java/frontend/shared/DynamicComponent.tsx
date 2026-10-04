import React, { useEffect, useRef, useState } from 'react';
import { parse } from 'acorn';
import { isValidElementType } from 'react-is';

type Dependencies = Record<string, unknown>;
type RemoteComponent = React.ComponentType<Record<string, unknown>>;

/** Executes trusted, published component bundles. This is not a sandbox. */
export function evaluateComponent(source: string, componentName: string, dependencies: Dependencies): RemoteComponent {
  const ast = parse(source, { ecmaVersion: 'latest', sourceType: 'script' });
  const names: string[] = [];
  for (const node of ast.body) {
    if (node.type === 'VariableDeclaration') {
      for (const declaration of node.declarations) if (declaration.id.type === 'Identifier') names.push(declaration.id.name);
    } else if ((node.type === 'FunctionDeclaration' || node.type === 'ClassDeclaration') && node.id) names.push(node.id.name);
  }
  const module: { exports: unknown } = { exports: {} };
  const globals: Record<string, unknown> = { ...dependencies };
  const requireModule = (name: string): unknown => {
    if (Object.prototype.hasOwnProperty.call(dependencies, name)) return dependencies[name];
    throw new Error(`Bundle dependency "${name}" is not available`);
  };
  const define = (...args: unknown[]) => {
    if (typeof args[0] === 'string') args.shift();
    const factory = args.pop();
    const ids = Array.isArray(args[0]) ? args[0] as string[] : ['require', 'exports', 'module'];
    const result = typeof factory === 'function' ? factory(...ids.map((id) => id === 'require' ? requireModule : id === 'exports' ? module.exports : id === 'module' ? module : requireModule(id))) : factory;
    if (result !== undefined) module.exports = result;
  };
  define.amd = {};
  const evaluate = new Function('module', 'exports', 'require', 'define', 'window', 'self', 'globalThis', 'React', 'ReactDOM', `${source}\n;return [${names.map((name) => `typeof ${name} === 'undefined' ? undefined : ${name}`).join(',')}];`);
  const lexical: unknown[] = evaluate(module, module.exports, requireModule, define, globals, globals, globals, dependencies.React, dependencies.ReactDOM);
  const roots: unknown[] = [module.exports, globals, ...lexical];
  const seen = new Set<unknown>();
  for (const root of roots) {
    if (!root || seen.has(root)) continue;
    seen.add(root);
    if ((typeof root === 'object' || typeof root === 'function')) {
      const record = root as Record<string, unknown>;
      const named = record[componentName];
      if (named && isValidElementType(named)) return named as RemoteComponent;
      if (record.default && isValidElementType(record.default)) return record.default as RemoteComponent;
      if (record.default) roots.push(record.default);
      if (root === globals) roots.push(...Object.values(record));
    }
    if (root === module.exports && isValidElementType(root)) return root as RemoteComponent;
    if (typeof root === 'function' && root.name === componentName) return root as RemoteComponent;
  }
  throw new Error(`Component "${componentName}" was not found`);
}

interface Props {
  url: string;
  componentName: string;
  dependencies: Dependencies;
  componentProps: Record<string, unknown>;
  fallback?: React.ReactNode;
  errorFallback?: (error: Error) => React.ReactNode;
  onError?: (error: Error) => void;
}

class RenderBoundary extends React.Component<
  React.PropsWithChildren<Pick<Props, 'onError' | 'errorFallback'>>,
  { error?: Error }
> {
  state: { error?: Error } = {};
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error) { this.props.onError?.(error); }
  render() { return this.state.error ? this.props.errorFallback?.(this.state.error) || null : this.props.children; }
}

export const DynamicComponent: React.FC<Props> = ({ url, componentName, dependencies, componentProps, fallback, errorFallback, onError }) => {
  const [loaded, setLoaded] = useState<{ key: string; component?: RemoteComponent; error?: Error }>();
  const errorHandler = useRef(onError);
  errorHandler.current = onError;
  const key = `${url}\n${componentName}`;
  useEffect(() => {
    const controller = new AbortController();
    setLoaded(undefined);
    void (async () => {
      try {
        const response = await fetch(url, { signal: controller.signal, credentials: 'omit' });
        if (!response.ok) throw new Error(`Bundle load failed: HTTP ${response.status}`);
        const component = evaluateComponent(await response.text(), componentName, dependencies);
        if (!controller.signal.aborted) setLoaded({ key, component });
      } catch (cause) {
        if (controller.signal.aborted) return;
        const error = cause instanceof Error ? cause : new Error(String(cause));
        setLoaded({ key, error });
        errorHandler.current?.(error);
      }
    })();
    return () => controller.abort();
  }, [url, componentName, dependencies, key]);
  if (!loaded || loaded.key !== key) return <>{fallback}</>;
  if (loaded.error) return <>{errorFallback?.(loaded.error)}</>;
  const Component = loaded.component;
  return Component ? <RenderBoundary key={key} onError={onError} errorFallback={errorFallback}><Component {...componentProps} /></RenderBoundary> : null;
};
