export async function copyText(text, environment = globalThis) {
  if (typeof text !== 'string') return false;

  const clipboard = environment.navigator?.clipboard;
  if (environment.isSecureContext === true && typeof clipboard?.writeText === 'function') {
    try {
      await clipboard.writeText(text);
      return true;
    } catch {
      // Public HTTP and denied browser permissions use the explicit selection fallback below.
    }
  }

  const document = environment.document;
  if (!document?.body || typeof document.createElement !== 'function'
    || typeof document.execCommand !== 'function') return false;

  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.readOnly = true;
  textarea.setAttribute('aria-hidden', 'true');
  textarea.style.position = 'fixed';
  textarea.style.inset = '-9999px auto auto -9999px';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  try {
    textarea.focus();
    textarea.select();
    return document.execCommand('copy') === true;
  } catch {
    return false;
  } finally {
    textarea.remove();
  }
}
