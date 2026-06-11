import { useState, useCallback } from "react";
import { api } from "../lib/api";

/**
 * useChat — manages chat history and message sending.
 */
export function useChat() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const addMessage = useCallback((message) => {
    setMessages((prev) => [...prev, message]);
  }, []);

  const updateLastAssistantMessage = useCallback((updater) => {
    setMessages((prev) => {
      const copy = [...prev];
      const lastIdx = copy.length - 1;
      if (lastIdx >= 0 && copy[lastIdx].role === "assistant") {
        copy[lastIdx] = { ...copy[lastIdx], ...updater(copy[lastIdx]) };
      }
      return copy;
    });
  }, []);

  const sendMessage = useCallback(
    async (question, voice = false) => {
      if (!question.trim() || isLoading) return;

      setError(null);
      setIsLoading(true);

      // Add user message
      addMessage({ id: Date.now(), role: "user", content: question });

      // Add placeholder assistant message
      const assistantId = Date.now() + 1;
      addMessage({
        id: assistantId,
        role: "assistant",
        content: "",
        sources: [],
        grounded: false,
        audio_base64: null,
        loading: true,
      });

      try {
        const data = await api.ask(question, voice);

        // Replace placeholder with real response
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: data.answer,
                  sources: data.sources || [],
                  grounded: data.grounded,
                  audio_base64: data.audio_base64 || null,
                  loading: false,
                }
              : m
          )
        );
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: "",
                  error: err.message || "Failed to get answer. Please try again.",
                  loading: false,
                }
              : m
          )
        );
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading, addMessage]
  );

  const clearHistory = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  const retryLast = useCallback(() => {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (lastUser) {
      setMessages((prev) => prev.slice(0, -2)); // remove last user + assistant
      sendMessage(lastUser.content);
    }
  }, [messages, sendMessage]);

  return {
    messages,
    isLoading,
    error,
    sendMessage,
    clearHistory,
    retryLast,
  };
}
