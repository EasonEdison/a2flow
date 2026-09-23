import React, { useMemo } from 'react';
import parseDiff from 'parse-diff';
import type { ReleaseDiffHunk, ReleaseDiffLine } from '../../types';
import UnifiedDiffCode from './UnifiedDiffCode';

interface PatchDiffPreviewProps {
  changeType?: string;
  diff: string;
}

function changeContent(content: string): string {
  const marker = content.charAt(0);
  return marker === ' ' || marker === '+' || marker === '-' ? content.slice(1) : content;
}

function parsePatchHunks(diff: string): ReleaseDiffHunk[] {
  if (!diff.trim()) return [];
  return parseDiff(diff).flatMap((file) =>
    file.chunks.map((chunk) => ({
      oldStart: chunk.oldStart,
      oldLines: chunk.oldLines,
      newStart: chunk.newStart,
      newLines: chunk.newLines,
      header: chunk.content,
      lines: chunk.changes.map<ReleaseDiffLine>((change) => {
        if (change.content.startsWith('\\ No newline at end of file')) {
          return {
            type: 'CONTEXT',
            content: change.content,
          };
        }
        if (change.type === 'add') {
          return {
            type: 'ADD',
            newLineNumber: change.ln,
            content: changeContent(change.content),
          };
        }
        if (change.type === 'del') {
          return {
            type: 'DELETE',
            oldLineNumber: change.ln,
            content: changeContent(change.content),
          };
        }
        return {
          type: 'CONTEXT',
          oldLineNumber: change.ln1,
          newLineNumber: change.ln2,
          content: changeContent(change.content),
        };
      }),
    })),
  );
}

function parseSingleSidedHunk(diff: string, changeType?: string): ReleaseDiffHunk[] {
  const type = String(changeType || '').toUpperCase();
  if (type !== 'ADD' && type !== 'DELETE') return [];
  const marker = type === 'ADD' ? '+' : '-';
  const sourceLines = diff.replace(/\r\n/g, '\n').split('\n');
  if (sourceLines.at(-1) === '') sourceLines.pop();
  if (!sourceLines.length || sourceLines.some((line) => !line.startsWith(marker))) return [];
  const lines = sourceLines.map<ReleaseDiffLine>((line, index) => ({
    type,
    oldLineNumber: type === 'DELETE' ? index + 1 : undefined,
    newLineNumber: type === 'ADD' ? index + 1 : undefined,
    content: line.slice(1).replace(/^ /, ''),
  }));
  return [
    {
      oldStart: type === 'DELETE' ? 1 : 0,
      oldLines: type === 'DELETE' ? lines.length : 0,
      newStart: type === 'ADD' ? 1 : 0,
      newLines: type === 'ADD' ? lines.length : 0,
      header: type === 'ADD' ? `@@ -0,0 +1,${lines.length} @@` : `@@ -1,${lines.length} +0,0 @@`,
      lines,
    },
  ];
}

const PatchDiffPreview: React.FC<PatchDiffPreviewProps> = ({ changeType, diff }) => {
  const hunks = useMemo(() => {
    try {
      const parsedHunks = parsePatchHunks(diff);
      return parsedHunks.length ? parsedHunks : parseSingleSidedHunk(diff, changeType);
    } catch {
      return [];
    }
  }, [changeType, diff]);

  if (!hunks.length) {
    return (
      <div className="skill-factory-patch-diff-fallback">
        <span>旧版 Patch 预览缺少行坐标，重新生成后可显示行号</span>
        <pre>{diff || '暂无 Diff 内容'}</pre>
      </div>
    );
  }
  return <UnifiedDiffCode hunks={hunks} />;
};

export default PatchDiffPreview;
