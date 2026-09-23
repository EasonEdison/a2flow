import React from 'react';
import { Button, Input, Space, message } from 'antd';
import { jsonStringify } from './safeJson';

const { TextArea } = Input;

export type JsonFormatMode = 'json' | 'template';

interface JsonFormatTextAreaProps {
  value?: string;
  onChange?: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onValueChange?: (value: string) => void;
  placeholder?: string;
  autoSize?: boolean | { minRows?: number; maxRows?: number };
  disabled?: boolean;
  className?: string;
  style?: React.CSSProperties;
  formatMode?: JsonFormatMode;
  buttonText?: string;
}

function parseJson(text: string): { success: true; value: unknown } | { success: false } {
  try {
    return { success: true, value: JSON.parse(text) };
  } catch {
    return { success: false };
  }
}

function formatJsonValue(value: unknown): string {
  return jsonStringify(value, null, 2) || '';
}

function formatStrictJson(text: string): string | null {
  const trimmed = text.trim();
  if (!trimmed) return '';
  const parsed = parseJson(trimmed);
  return parsed.success ? formatJsonValue(parsed.value) : null;
}

function appendNewline(buffer: string[], indent: number): void {
  while (buffer.length && /[ \t]/.test(buffer[buffer.length - 1])) {
    buffer.pop();
  }
  if (buffer[buffer.length - 1] !== '\n') {
    buffer.push('\n');
  }
  buffer.push('  '.repeat(Math.max(indent, 0)));
}

function readTemplateToken(
  text: string,
  index: number,
): { token: string; endIndex: number } | null {
  if (!text.startsWith('{{', index)) return null;
  const endIndex = text.indexOf('}}', index + 2);
  if (endIndex < 0) return null;
  return {
    token: text.slice(index, endIndex + 2),
    endIndex: endIndex + 1,
  };
}

function formatTemplateJsonLike(text: string): string {
  const buffer: string[] = [];
  let indent = 0;
  let inString = false;
  let escaped = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];

    if (inString) {
      buffer.push(char);
      if (escaped) {
        escaped = false;
      } else if (char === '\\') {
        escaped = true;
      } else if (char === '"') {
        inString = false;
      }
      continue;
    }

    const templateToken = readTemplateToken(text, index);
    if (templateToken) {
      const token = templateToken.token.trim();
      if (token.startsWith('{{#') || token.startsWith('{{/')) {
        appendNewline(buffer, indent);
        buffer.push(token);
        appendNewline(buffer, indent);
      } else {
        buffer.push(token);
      }
      index = templateToken.endIndex;
      continue;
    }

    if (/\s/.test(char)) continue;

    if (char === '"') {
      inString = true;
      buffer.push(char);
      continue;
    }
    if (char === '{' || char === '[') {
      buffer.push(char);
      indent += 1;
      appendNewline(buffer, indent);
      continue;
    }
    if (char === '}' || char === ']') {
      indent -= 1;
      appendNewline(buffer, indent);
      buffer.push(char);
      continue;
    }
    if (char === ',') {
      buffer.push(char);
      appendNewline(buffer, indent);
      continue;
    }
    if (char === ':') {
      buffer.push(': ');
      continue;
    }
    buffer.push(char);
  }

  return buffer
    .join('')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function formatByMode(value: string, mode: JsonFormatMode): string | null {
  if (mode === 'template') return formatStrictJson(value) ?? formatTemplateJsonLike(value);
  return formatStrictJson(value);
}

const JsonFormatTextArea: React.FC<JsonFormatTextAreaProps> = ({
  value = '',
  onChange,
  onValueChange,
  placeholder,
  autoSize,
  disabled,
  className,
  style,
  formatMode = 'json',
  buttonText = '格式化 JSON',
}) => {
  const emitValue = (nextValue: string) => {
    if (onValueChange) {
      onValueChange(nextValue);
      return;
    }
    onChange?.({ target: { value: nextValue } } as React.ChangeEvent<HTMLTextAreaElement>);
  };

  const handleFormat = () => {
    const formatted = formatByMode(value, formatMode);
    if (formatted === null) {
      message.error('当前内容不是合法 JSON');
      return;
    }
    emitValue(formatted);
    message.success('已格式化 JSON');
  };

  return (
    <div className="skill-factory-json-format-textarea">
      <Space className="skill-factory-json-format-toolbar">
        <Button size="small" disabled={disabled || !value.trim()} onClick={handleFormat}>
          {buttonText}
        </Button>
      </Space>
      <TextArea
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        autoSize={autoSize}
        disabled={disabled}
        className={className}
        style={style}
      />
    </div>
  );
};

export default JsonFormatTextArea;
