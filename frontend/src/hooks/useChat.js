import { useState, useCallback, useEffect, useRef } from "react";
import { api } from "../lib/api";

/**
 * useChat — manages messages for a specific session.
 * Conversation memory (context) is handled entirely by the backend:
 *   on every /ask call, the backend fetches the last MEMORY_WINDOW messages
 *   and injects them into the LLM prompt so the model has full context.
 *
 * @param {string|null} sessionId        — current session UUID (null = no session yet)
 * @param {string|null} jwt              — user's Supabase access_token
 * @param {function}    onSessionCreated — called with (id, title) after auto-create
 */
export function useChat({ sessionId, jwt, onSessionCreated } = {}) {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  // Refs so callbacks always see the latest values without stale closures
  const sessionIdRef = useRef(sessionId);
  const jwtRef = useRef(jwt);
  useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);
  useEffect(() => { jwtRef.current = jwt; }, [jwt]);

  // Track the previous sessionId so we only reset messages on real session changes
  const prevSessionIdRef = useRef(sessionId);

  // ── Reset messages when session changes (not when jwt refreshes) ────────────
  useEffect(() => {
    // Only clear + reload when the sessionId itself changes, not on jwt refresh.
    // This prevents the empty-screen flash that occurs when Supabase silently
    // rotates the access token (autoRefreshToken) mid-conversation.
    const prevSid = prevSessionIdRef.current;
    prevSessionIdRef.current = sessionId;

    if (sessionId === prevSid) {
      // jwt changed but session is the same — do nothing, jwtRef is already updated
      return;
    }

    if (!sessionId) {
      setMessages([]);
      return;
    }

    // sessionId changed to a real value — load its history
    let cancelled = false;
    (async () => {
      const currentJwt = jwtRef.current;
      if (!currentJwt) return;
      try {
        const msgs = await api.getMessages(sessionId, currentJwt);
        if (!cancelled) {
          setMessages((prev) => {
            // If we have an optimistic/loading message right now (e.g. we just created this session),
            // don't overwrite it with the (empty) DB history!
            if (prev.some((m) => m.loading)) return prev;

            return msgs.map((m) => ({
              id: m.id,
              role: m.role,
              content: m.content,
              sources: m.sources || [],
              grounded: m.grounded,
              loading: false,
            }));
          });
        }
      } catch (e) {
        if (!cancelled) setError(e.message);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, jwt]);

  // ── Send a message ──────────────────────────────────────────────────────────
  const sendMessage = useCallback(
    async (question, voice = false) => {
      if (!question.trim() || isLoading) return;

      setError(null);
      setIsLoading(true);

      // Add user message
      setMessages((prev) => [
        ...prev,
        {
          id: `user-${Date.now()}`,
          role: "user",
          content: question,
        },
      ]);

      // Assistant placeholder
      const placeholderId = `asst-${Date.now()}`;

      setMessages((prev) => [
        ...prev,
        {
          id: placeholderId,
          role: "assistant",
          content: "",
          sources: [],
          grounded: false,
          loading: true,
        },
      ]);

      try {
        const currentJwt = jwtRef.current;
        let sid = sessionIdRef.current;

        // Auto-create session
        if (!sid) {
          const created = await api.createSession(
            "New Chat",
            currentJwt
          );

          sid = created.session_id;
          sessionIdRef.current = sid;

          onSessionCreated?.(
            sid,
            created.title
          );
        }

        // Call /ask endpoint
        const result = await api.ask(
          question,
          sid,
          currentJwt
        );

        setMessages((prev) =>
          prev.map((m) =>
            m.id === placeholderId
              ? {
                ...m,
                content: result.answer,
                sources: result.sources || [],
                grounded: result.grounded || false,
                loading: false,
              }
              : m
          )
        );
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === placeholderId
              ? {
                ...m,
                content: "",
                error:
                  err.message ||
                  "Failed to get answer.",
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
    [isLoading, onSessionCreated]
  );
  // ── Helpers ─────────────────────────────────────────────────────────────────
  const clearHistory = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  const retryLast = useCallback(() => {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (lastUser) {
      setMessages((prev) => prev.slice(0, -1)); // Remove the failed assistant response (which is the last one)
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
