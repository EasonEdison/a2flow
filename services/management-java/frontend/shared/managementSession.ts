export class ManagementSessionError extends Error {
  constructor(public readonly status: 401 | 403, message: string) { super(message); }
}

const listeners = new Set<() => void>();
let loginRequired = false;

export const isManagementLoginRequired = () => loginRequired;

export function subscribeManagementSession(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** Only authenticated management APIs use this wrapper, never external renderer assets. */
export async function managementFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, init);
  if (response.status === 401) {
    if (!loginRequired) {
      loginRequired = true;
      listeners.forEach(listener => listener());
    }
    // Do not navigate or replay writes: the page may contain an unsaved draft.
    throw new ManagementSessionError(401, '尚未登录或登录已过期，请通过管理台登录入口重新登录');
  }
  if (response.status === 403) {
    throw new ManagementSessionError(403, '没有执行此操作的权限（403），请联系管理员；重新登录不会自动授予权限');
  }
  return response;
}
