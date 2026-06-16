import { useEffect, useState } from "react";
import {
  Detail,
  getPreferenceValues,
  showToast,
  Toast,
  ActionPanel,
  Action,
  Icon,
  LaunchProps,
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

interface Arguments {
  url: string;
}

/**
 * Normalize LLM-generated text for Raycast's Markdown renderer.
 * The goal is purely better paragraph / line-break separation without assuming
 * any particular template or section names (user prompts + LLM output vary).
 */
function normalizeForRaycast(text: string): string {
  if (!text) return "";

  let s = text.replace(/\r\n/g, "\n").trim();

  // Collapse 3+ consecutive newlines to exactly 2 (prevents huge gaps)
  s = s.replace(/\n{3,}/g, "\n\n");

  // Turn single newlines between plain text into paragraph breaks.
  // Conservative: we only insert a blank line when the next line starts with
  // regular text (not a list, heading, code fence, blockquote, or whitespace).
  // This helps when the LLM returns dense single-\n paragraphs but leaves
  // proper structure (lists, headings, code) alone.
  s = s.replace(/([^\n])\n(?!\n|\s|[-*+]\s|\d+\.\s|#{1,6}\s|`|>|```|~~~)/g, "$1\n\n");

  return s;
}

export default function SummarizeCommand(props: LaunchProps<{ arguments: Arguments }>) {
  const [markdown, setMarkdown] = useState<string>("");
  const [result, setResult] = useState<SummarizeResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    async function run() {
      try {
        const preferences = getPreferenceValues<Preferences>();
        const endpoint = (preferences.apiEndpoint || "http://localhost:8000").replace(/\/$/, "");

        const urlArg = props.arguments?.url?.trim();
        if (!urlArg) {
          setMarkdown("# No URL provided\n\nType or paste a video URL when running this command.");
          setIsLoading(false);
          return;
        }

        const source = urlArg;
        setMarkdown(`Sending to ${endpoint}/summarize...`);

        const body: Record<string, unknown> = {
          source,
          output_format: "json",
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

        // When we request output_format=json, the top-level summary field is a JSON string
        // containing the raw model output (no extra "Summary for:" wrapper).
        let rawSummary = data.summary;
        if (data.format === "json") {
          try {
            const parsed = JSON.parse(data.summary);
            rawSummary = parsed.summary ?? data.summary;
          } catch {
            // fall back to whatever we received
          }
        }

        const cleaned = normalizeForRaycast(rawSummary);

        setResult(data);
        setMarkdown(cleaned);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        setMarkdown(`# Error\n\n${message}`);
        await showToast({ style: Toast.Style.Failure, title: "Summarization failed", message });
      } finally {
        setIsLoading(false);
      }
    }

    run();
  }, [props.arguments?.url]);

  return (
    <Detail
      markdown={markdown || "Preparing..."}
      isLoading={isLoading}
      metadata={
        result ? (
          <Detail.Metadata>
            <Detail.Metadata.Label title="Source" text={result.source} />
            {result.model ? <Detail.Metadata.Label title="Model" text={result.model} /> : null}
            {result.prompt_type ? <Detail.Metadata.Label title="Style" text={result.prompt_type} /> : null}
            <Detail.Metadata.Label title="Processed in" text={`${result.processing_time_seconds}s`} />
          </Detail.Metadata>
        ) : undefined
      }
      actions={
        <ActionPanel>
          <Action.CopyToClipboard title="Copy Summary" content={markdown} icon={Icon.Clipboard} />
          <Action.Paste title="Paste Summary" content={markdown} icon={Icon.Text} />
        </ActionPanel>
      }
    />
  );
}
