import { useEffect, useState } from "react";
import {
  Clipboard,
  Detail,
  getPreferenceValues,
  showToast,
  Toast,
  ActionPanel,
  Action,
  Icon,
} from "@raycast/api";

interface Preferences {
  apiEndpoint: string;
  provider?: string;
  promptType?: string;
}

interface SummarizeResponse {
  success: boolean;
  source: string;
  summary: string;
  format: string;
  model?: string;
  prompt_type?: string;
  processing_time_seconds: number;
  error?: string;
  error_type?: string;
}

export default function SummarizeClipboardCommand() {
  const [markdown, setMarkdown] = useState<string>("Reading clipboard...");
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    async function run() {
      try {
        const preferences = getPreferenceValues<Preferences>();
        const endpoint = (preferences.apiEndpoint || "http://localhost:8000").replace(/\/$/, "");

        const clipboardText = await Clipboard.readText();
        if (!clipboardText || clipboardText.trim().length === 0) {
          setMarkdown("# No URL in clipboard\n\nCopy a video URL to summarize.");
          setIsLoading(false);
          return;
        }

        const source = clipboardText.trim();
        setMarkdown(`Sending to ${endpoint}/summarize...`);

        const body: Record<string, unknown> = {
          source,
        };

        if (preferences.provider) {
          body.provider = preferences.provider;
        }
        if (preferences.promptType) {
          body.prompt_type = preferences.promptType;
        }

        const response = await fetch(`${endpoint}/summarize`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });

        if (!response.ok) {
          const text = await response.text().catch(() => "Unknown error");
          throw new Error(`HTTP ${response.status}: ${text}`);
        }

        const data = (await response.json()) as SummarizeResponse;

        if (!data.success) {
          throw new Error(data.error || "Summarization failed");
        }

        const header = data.model
          ? `# Summary\n\n_Source:_ ${data.source}  \n_Model:_ ${data.model}  \n_Time:_ ${data.processing_time_seconds}s\n\n---\n\n`
          : `# Summary\n\n_Source:_ ${data.source}  \n_Time:_ ${data.processing_time_seconds}s\n\n---\n\n`;

        setMarkdown(header + data.summary);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        setMarkdown(`# Error\n\n${message}`);
        await showToast({ style: Toast.Style.Failure, title: "Summarization failed", message });
      } finally {
        setIsLoading(false);
      }
    }

    run();
  }, []);

  return (
    <Detail
      markdown={markdown}
      isLoading={isLoading}
      actions={
        <ActionPanel>
          <Action.CopyToClipboard title="Copy Summary" content={markdown} icon={Icon.Clipboard} />
          <Action.Paste title="Paste Summary" content={markdown} icon={Icon.Text} />
        </ActionPanel>
      }
    />
  );
}
