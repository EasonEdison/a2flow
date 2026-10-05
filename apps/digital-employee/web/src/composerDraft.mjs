export const appendComposerDraft = (current, addition) => {
  if (typeof current !== 'string' || typeof addition !== 'string' || !addition) return null;
  const next = current ? `${current}\n${addition}` : addition;
  return next.length <= 4000 ? next : null;
};
