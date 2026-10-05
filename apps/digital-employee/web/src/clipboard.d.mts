export type ClipboardEnvironment = {
  isSecureContext?: boolean;
  navigator?: { clipboard?: { writeText?: (text: string) => Promise<void> } };
  document?: {
    body?: { appendChild: (node: unknown) => void };
    createElement?: (name: string) => {
      value: string;
      readOnly: boolean;
      style: Record<string, string>;
      setAttribute: (name: string, value: string) => void;
      focus: () => void;
      select: () => void;
      remove: () => void;
    };
    execCommand?: (command: string) => boolean;
  };
};

export function copyText(text: string, environment?: ClipboardEnvironment): Promise<boolean>;
