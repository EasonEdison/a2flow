import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function MarkdownPreview({ markdown }: { markdown: string }) {
  return <div className="markdown-preview" aria-label="SKILL.md 安全预览">
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      skipHtml
      urlTransform={() => ''}
      components={{
        a: ({ children }) => <span className="preview-link">{children}</span>,
        img: () => null,
      }}
    >{markdown}</ReactMarkdown>
  </div>;
}
