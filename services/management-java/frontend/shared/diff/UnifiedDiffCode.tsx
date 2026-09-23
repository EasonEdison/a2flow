import React from 'react';
import type { ReleaseDiffHunk } from '../../types';

interface UnifiedDiffCodeProps {
  hunks: ReleaseDiffHunk[];
}

const UnifiedDiffCode: React.FC<UnifiedDiffCodeProps> = ({ hunks }) => (
  <div className="release-diff-code">
    {hunks.map((hunk, hunkIndex) => (
      <details className="release-diff-hunk" key={`${hunk.header}-${hunkIndex}`} open>
        <summary>{hunk.header}</summary>
        <div className="release-diff-unified">
          {hunk.lines.map((line, lineIndex) => (
            <div
              className={`release-diff-line ${line.type.toLowerCase()}`}
              key={`${line.type}-${line.oldLineNumber}-${line.newLineNumber}-${lineIndex}`}
            >
              <span className="release-diff-line-number">{line.oldLineNumber ?? ''}</span>
              <span className="release-diff-line-number">{line.newLineNumber ?? ''}</span>
              <span className="release-diff-line-marker">
                {line.type === 'ADD' ? '+' : line.type === 'DELETE' ? '-' : ' '}
              </span>
              <code>{line.content || ' '}</code>
            </div>
          ))}
        </div>
      </details>
    ))}
  </div>
);

export default UnifiedDiffCode;
