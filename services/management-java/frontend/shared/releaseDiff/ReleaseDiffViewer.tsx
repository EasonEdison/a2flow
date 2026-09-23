import React, { useMemo, useState } from 'react';
import { Alert, Empty, Input, Radio, Select, Space, Spin, Tag } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type {
  ReleaseDiffDocument,
  ReleaseDiffEntry,
  ReleaseDiffLine,
  ReleaseDiffViewMode,
} from '../../types';
import UnifiedDiffCode from '../diff/UnifiedDiffCode';

interface ReleaseDiffViewerProps {
  document?: ReleaseDiffDocument;
  detailEntry?: ReleaseDiffEntry;
  selectedPath?: string;
  loading?: boolean;
  detailLoading?: boolean;
  viewMode: ReleaseDiffViewMode;
  contextLines: number;
  onEntrySelect: (path: string) => void;
  onViewModeChange: (viewMode: ReleaseDiffViewMode) => void;
  onContextLinesChange: (contextLines: number) => void;
}

interface SplitRow {
  key: string;
  left?: ReleaseDiffLine;
  right?: ReleaseDiffLine;
}

interface BinaryMetadataProps {
  entry: ReleaseDiffEntry;
  beforeLabel: string;
  afterLabel: string;
}

interface LineCountsProps {
  additions: number | null;
  deletions: number | null;
  partial?: boolean;
}

const SKILL_METADATA_PATH = '.skillfactory/skill-metadata.json';

const displayPath = (path: string) => (path === SKILL_METADATA_PATH ? 'skiil的Description' : path);

const changeTypeLabel: Record<ReleaseDiffEntry['changeType'], string> = {
  ADDED: '新增',
  MODIFIED: '修改',
  DELETED: '删除',
  RENAMED: '重命名',
};

const changeTypeColor: Record<ReleaseDiffEntry['changeType'], string> = {
  ADDED: 'success',
  MODIFIED: 'warning',
  DELETED: 'error',
  RENAMED: 'processing',
};

const splitRows = (lines: ReleaseDiffLine[]): SplitRow[] => {
  const result: SplitRow[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (line.type === 'CONTEXT') {
      result.push({ key: `context-${index}`, left: line, right: line });
      index += 1;
      continue;
    }
    const deleted: ReleaseDiffLine[] = [];
    const added: ReleaseDiffLine[] = [];
    while (index < lines.length && lines[index].type !== 'CONTEXT') {
      if (lines[index]?.type === 'DELETE') deleted.push(lines[index]);
      if (lines[index]?.type === 'ADD') added.push(lines[index]);
      index += 1;
    }
    const rowCount = Math.max(deleted.length, added.length);
    for (let rowIndex = 0; rowIndex < rowCount; rowIndex += 1) {
      result.push({
        key: `change-${index}-${rowIndex}`,
        left: deleted[rowIndex],
        right: added[rowIndex],
      });
    }
  }
  return result;
};

const SplitDiff: React.FC<{ entry: ReleaseDiffEntry }> = ({ entry }) => (
  <div className="release-diff-code">
    {entry.hunks?.map?.((hunk, hunkIndex) => (
      <details className="release-diff-hunk" key={`${hunk.header}-${hunkIndex}`} open>
        <summary>{hunk.header}</summary>
        <div className="release-diff-split">
          {splitRows(hunk.lines)?.map?.((row) => (
            <div className="release-diff-split-row" key={row.key}>
              <div
                className={`release-diff-split-cell ${row.left?.type?.toLowerCase?.() || 'empty'}`}
              >
                <span className="release-diff-line-number">{row.left?.oldLineNumber ?? ''}</span>
                <span className="release-diff-line-marker">
                  {row.left?.type === 'DELETE' ? '-' : ' '}
                </span>
                <code>{row.left?.content || ' '}</code>
              </div>
              <div
                className={`release-diff-split-cell ${row.right?.type?.toLowerCase?.() || 'empty'}`}
              >
                <span className="release-diff-line-number">{row.right?.newLineNumber ?? ''}</span>
                <span className="release-diff-line-marker">
                  {row.right?.type === 'ADD' ? '+' : ' '}
                </span>
                <code>{row.right?.content || ' '}</code>
              </div>
            </div>
          ))}
        </div>
      </details>
    ))}
  </div>
);

const formatFileSize = (size?: number) => {
  if (size === undefined || size === null) return '-';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(2)} KB`;
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
};

const LineCounts: React.FC<LineCountsProps> = ({ additions, deletions, partial }) => {
  if (additions === null || deletions === null) {
    return <span className="release-diff-count-unknown">行数未计算</span>;
  }
  return (
    <span className="release-diff-counts">
      {partial ? <span className="release-diff-partial-label">已统计</span> : null}
      <span className="release-diff-additions">+{additions}</span>
      <span className="release-diff-deletions">-{deletions}</span>
    </span>
  );
};

const BinaryMetadata: React.FC<BinaryMetadataProps> = ({ entry, beforeLabel, afterLabel }) => {
  const sides = [
    {
      label: beforeLabel,
      digest: entry.beforeDigest,
      size: entry.beforeSize,
    },
    {
      label: afterLabel,
      digest: entry.afterDigest,
      size: entry.afterSize,
    },
  ];

  return (
    <div className="release-diff-binary">
      <p>二进制文件不展示内容，仅对比文件元数据。</p>
      <div className="release-diff-binary-grid">
        {sides.map((side) => (
          <div className="release-diff-binary-side" key={side.label}>
            <strong>{side.label}</strong>
            {side.digest || side.size !== undefined ? (
              <>
                <span>大小</span>
                <b>{formatFileSize(side.size)}</b>
                <span>摘要</span>
                <code title={side.digest}>{side.digest || '-'}</code>
              </>
            ) : (
              <div className="release-diff-binary-missing">无文件</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

/**
 * 三类资产共用的 GitHub 风格发布 Diff 查看器。
 *
 * 列表只展示强类型文件元数据，选中文件后展示后端生成的 hunks；组件本身不解析领域 payload，
 * 也不使用原始响应 JSON 兜底。
 */
const ReleaseDiffViewer: React.FC<ReleaseDiffViewerProps> = ({
  document,
  detailEntry,
  selectedPath,
  loading,
  detailLoading,
  viewMode,
  contextLines,
  onEntrySelect,
  onViewModeChange,
  onContextLinesChange,
}) => {
  const [keyword, setKeyword] = useState('');
  const entries = useMemo(() => {
    const normalizedKeyword = keyword?.trim()?.toLowerCase?.();
    if (!normalizedKeyword) return document?.entries || [];
    return (document?.entries || []).filter(
      (entry) =>
        entry?.path?.toLowerCase?.()?.includes?.(normalizedKeyword) ||
        displayPath(entry.path)?.toLowerCase?.()?.includes?.(normalizedKeyword) ||
        entry?.oldPath?.toLowerCase()?.includes?.(normalizedKeyword),
    );
  }, [document?.entries, keyword]);

  if (!document) {
    return <Empty description="请选择正式版本查看 Diff" />;
  }

  const summary = document.summary;
  if (!summary.changedFiles) {
    return (
      <div className="release-diff-empty">
        <Empty description={`${document.from}与${document.to}完全一致`} />
      </div>
    );
  }

  return (
    <div className="release-diff-viewer">
      <div className="release-diff-header">
        <div>
          <strong>
            {document.from} → {document.to}
          </strong>
          <p>
            {summary.changedFiles} files changed，
            <LineCounts
              additions={summary.additions}
              deletions={summary.deletions}
              partial={summary.truncated}
            />
          </p>
        </div>
        <Space wrap>
          <Radio.Group
            buttonStyle="solid"
            optionType="button"
            value={viewMode}
            onChange={(event) => onViewModeChange(event.target.value as ReleaseDiffViewMode)}
          >
            <Radio.Button value="UNIFIED">统一</Radio.Button>
            <Radio.Button value="SPLIT">并排</Radio.Button>
          </Radio.Group>
          <Select
            value={contextLines}
            style={{ width: 112 }}
            options={[
              { label: '3 行上下文', value: 3 },
              { label: '5 行上下文', value: 5 },
              { label: '10 行上下文', value: 10 },
            ]}
            onChange={(value) => onContextLinesChange(value as number)}
          />
        </Space>
      </div>

      {summary.truncated ? (
        <Alert
          type="warning"
          showIcon
          message={`${
            summary.truncatedReason || '部分文件 Diff 已截断'
          }；汇总行数只包含已完成比较的文件`}
        />
      ) : null}

      <div className="release-diff-layout">
        <aside className="release-diff-files">
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索变更文件"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
          />
          <div className="release-diff-file-list">
            {entries.map((entry) => (
              <button
                className={`release-diff-file ${selectedPath === entry.path ? 'selected' : ''}`}
                key={entry.path}
                type="button"
                onClick={() => onEntrySelect(entry.path)}
              >
                <div>
                  <Tag color={changeTypeColor[entry.changeType]}>
                    {changeTypeLabel[entry.changeType]}
                  </Tag>
                  <span className="release-diff-file-path" title={entry.path}>
                    {displayPath(entry.path)}
                  </span>
                </div>
                <LineCounts additions={entry.additions} deletions={entry.deletions} />
              </button>
            ))}
            {!entries.length ? <Empty description="没有匹配的变更文件" /> : null}
          </div>
        </aside>

        <section className="release-diff-detail">
          <Spin spinning={Boolean(loading || detailLoading)}>
            {detailEntry ? (
              <>
                <div className="release-diff-file-heading">
                  <div>
                    <strong title={detailEntry.path}>{displayPath(detailEntry.path)}</strong>
                    {detailEntry.oldPath ? <TextPath oldPath={detailEntry.oldPath} /> : null}
                  </div>
                  <Space align="center">
                    <Tag>
                      {detailEntry.contentType === 'BINARY'
                        ? 'binary'
                        : detailEntry.language || detailEntry.contentType?.toLowerCase?.()}
                    </Tag>
                    <LineCounts
                      additions={detailEntry.additions}
                      deletions={detailEntry.deletions}
                    />
                  </Space>
                </div>
                {detailEntry.truncated ? (
                  <Alert
                    type="warning"
                    showIcon
                    message={detailEntry.truncatedReason || '该文件 Diff 已截断'}
                  />
                ) : null}
                {detailEntry.contentType === 'BINARY' ? (
                  <BinaryMetadata
                    entry={detailEntry}
                    beforeLabel={document.from}
                    afterLabel={document.to}
                  />
                ) : detailEntry.hunks?.length ? (
                  viewMode === 'SPLIT' ? (
                    <SplitDiff entry={detailEntry} />
                  ) : (
                    <UnifiedDiffCode hunks={detailEntry.hunks} />
                  )
                ) : (
                  <Empty description="该文件没有可展示的行级变化" />
                )}
              </>
            ) : (
              <Empty description="选择左侧文件查看变化" />
            )}
          </Spin>
        </section>
      </div>
    </div>
  );
};

const TextPath: React.FC<{ oldPath: string }> = ({ oldPath }) => (
  <p className="release-diff-old-path">原路径：{oldPath}</p>
);

export default ReleaseDiffViewer;
