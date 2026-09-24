import { useState } from 'react';
import { downloadText, textDownloadError } from '../textDownload.mjs';

export type TextDownloadProps = {
  label?: string;
  filename?: string;
  mediaType?: string;
  content?: string;
  isValid?: boolean;
  validationErrors?: string[];
};

export function TextDownload({
  label, filename, mediaType, content, isValid, validationErrors,
}: TextDownloadProps) {
  const [localError, setLocalError] = useState('');
  const payload = { filename: filename ?? '', mediaType: mediaType ?? '', content: content ?? '' };
  const error = localError || textDownloadError(payload, isValid, validationErrors);
  return <div className="a2ui-text-download">
    <button type="button" disabled={Boolean(error)} onClick={() => {
      setLocalError('');
      try { downloadText(payload); }
      catch (reason) { setLocalError(reason instanceof Error ? reason.message : '下载失败'); }
    }}>{label || '下载文本'}</button>
    {error ? <small role="status">{error}</small> : null}
  </div>;
}
