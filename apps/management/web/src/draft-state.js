export function shouldChangeKind(current, next) {
  return current !== next;
}

export function publicationConfirmation(target) {
  const users = target.grayUserIds.length ? target.grayUserIds.join(', ') : '无';
  const stableWarning = target.channel === 'STABLE' ? '\n警告：切换 STABLE 会清除当前灰度。' : '';
  return `确认显式发布？\n环境：${target.environment}\n通道：${target.channel}\n版本：${target.versionId}\n灰度用户：${users}${stableWarning}`;
}

export function rollbackTarget(environment, versionId) {
  return { environment, versionId, channel: environment === 'PRT' ? 'CURRENT' : 'STABLE', grayUserIds: [] };
}

export function rollbackConfirmation(target) {
  const stableWarning = target.channel === 'STABLE' ? '\n警告：切换 STABLE 会清除当前灰度。' : '';
  return `确认回滚配置？\n环境：${target.environment}\n通道：${target.channel}\n版本：${target.versionId}\n灰度用户：无${stableWarning}\n仅改变配置选择，不补偿任何业务操作。`;
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
