export const MAX_TEXT_DOWNLOAD_BYTES: number;
export type TextDownloadPayload = { filename: string; mediaType: string; content: string };
export function validateTextDownload(payload: TextDownloadPayload): string;
export function textDownloadError(payload: TextDownloadPayload, isValid?: boolean, validationErrors?: string[]): string;
export function downloadText(payload: TextDownloadPayload): void;
