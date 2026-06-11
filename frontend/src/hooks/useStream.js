import { useState, useCallback, useRef } from "react";
import { api } from "../lib/api";

/**
 * useStream — SSE streaming hook for real-time token streaming.
 */
export function useStream() {
  const [streamContent, setStreamContent] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState(null);
  const abortRef = useRef(null);

  const startStream = useCallback(async (question, onToken, onComplete, onError) => {
    setStreamContent("");
    setStreamError(null);
    setIsStreaming(true);

    // Cancel any ongoing stream
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch(api.getStreamUrl(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value, { stream: true });
        const lines = text.split("\n");

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6).trim();
            if (data === "[START]" || data === "[DONE]") {
              if (data === "[DONE]") {
                onComplete?.(accumulated);
                setIsStreaming(false);
              }
              continue;
            }
            try {
              const parsed = JSON.parse(data);
              if (parsed.token) {
                accumulated += parsed.token;
                setStreamContent(accumulated);
                onToken?.(parsed.token, accumulated);
              } else if (parsed.error) {
                throw new Error(parsed.error);
              }
            } catch (e) {
              // Ignore malformed SSE lines
            }
          }
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        setStreamError(err.message);
        onError?.(err);
      }
    } finally {
      setIsStreaming(false);
    }
  }, []);

  const cancelStream = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      setIsStreaming(false);
    }
  }, []);

  return {
    streamContent,
    isStreaming,
    streamError,
    startStream,
    cancelStream,
  };
}
