import { Fragment } from 'react';

type MarkdownContentProps = {
  markdown: string;
};

const safeUrl = (url: string) => (/^(https?:|mailto:)/i.test(url) ? url : null);

function inline(text: string, key: string) {
  const parts = text.split(/(\`[^\`]*\`|\[[^\]]+\]\([^\s)]+\))/g);
  return parts.map((part, index) => {
    const partKey = `${key}-${index}`;
    const code = /^\`([^\`]*)\`$/.exec(part);
    if (code) {
      return <code key={partKey}>{code[1]}</code>;
    }
    const link = /^\[([^\]]+)\]\(([^\s)]+)\)$/.exec(part);
    if (link) {
      const href = safeUrl(link[2]);
      return href ? <a key={partKey} href={href} target="_blank" rel="noreferrer">{link[1]}</a> : link[1];
    }
    return <Fragment key={partKey}>{part}</Fragment>;
  });
}

export function MarkdownContent({ markdown }: MarkdownContentProps) {
  const blocks = markdown.replace(/\r\n/g, '\n').split(/\n\n+/);

  return blocks.map((block, index) => {
    const key = `markdown-${index}`;
    const fenced = /^\`\`\`[^\n]*\n([\s\S]*?)\n?\`\`\`$/.exec(block);
    if (fenced) {
      return <pre key={key}><code>{fenced[1]}</code></pre>;
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(block);
    if (heading) {
      const level = heading[1].length;
      const content = inline(heading[2], key);
      if (level === 1) return <h1 key={key}>{content}</h1>;
      if (level === 2) return <h2 key={key}>{content}</h2>;
      return <h3 key={key}>{content}</h3>;
    }
    const lines = block.split('\n');
    if (lines.every((line) => /^[-*]\s+/.test(line))) {
      return <ul key={key}>{lines.map((line, lineIndex) => <li key={lineIndex}>{inline(line.replace(/^[-*]\s+/, ''), `${key}-${lineIndex}`)}</li>)}</ul>;
    }
    return <p key={key}>{lines.map((line, lineIndex) => <Fragment key={lineIndex}>{lineIndex ? <br /> : null}{inline(line, `${key}-${lineIndex}`)}</Fragment>)}</p>;
  });
}
