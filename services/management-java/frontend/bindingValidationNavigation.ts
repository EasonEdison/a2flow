export const BINDING_DEBUG_PAGE_URL = '/employee/';
export const BINDING_TRACE_PAGE_URL =
  '/employee/';

type WindowOpen = (url: string, target: string) => unknown;

const defaultWindowOpen: WindowOpen = (url, target) => window.open(url, target);

export function openBindingDebugPage(openWindow: WindowOpen = defaultWindowOpen): unknown {
  return openWindow(BINDING_DEBUG_PAGE_URL, '_blank');
}

export function openBindingTracePage(openWindow: WindowOpen = defaultWindowOpen): unknown {
  return openWindow(BINDING_TRACE_PAGE_URL, '_blank');
}
