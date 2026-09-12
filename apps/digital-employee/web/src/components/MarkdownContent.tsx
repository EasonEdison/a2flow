import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

type MarkdownContentProps = {
  markdown: string;
};

const safeUrl = (url: string) => (/^(https?:|mailto:)/i.test(url) ? url : '');

export function MarkdownContent({ markdown }: MarkdownContentProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      skipHtml
      urlTransform={safeUrl}
      components={{
        a: ({ href, children }) =>
          href ? (
            <a href={href} target="_blank" rel="noreferrer">
              {children}
            </a>
          ) : (
            <>{children}</>
          ),
      }}
    >
      {markdown}
    </ReactMarkdown>
  );
}
