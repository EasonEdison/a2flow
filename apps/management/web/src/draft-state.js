export function shouldChangeKind(current, next) {
  return current !== next;
}

export function settleSaveBuffer(current, submittedText, saved) {
  const changedDuringSave = current.text !== submittedText;
  return {
    text: changedDuringSave ? current.text : JSON.stringify(saved.document, null, 2),
    revision: saved.revision,
    dirty: changedDuringSave,
    conflict: false,
    contentDigest: saved.contentDigest,
    updatedBy: saved.updatedBy,
  };
}
