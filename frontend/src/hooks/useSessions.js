import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../lib/api";

const CACHE_KEY_PREFIX = "pyqa_sessions_";

function getCacheKey(jwt) {
  // Use the first 16 chars of the JWT signature as a user-scoped key
  try {
    const parts = jwt.split(".");
    return CACHE_KEY_PREFIX + (parts[1]?.slice(0, 16) ?? "anon");
  } catch {
    return CACHE_KEY_PREFIX + "anon";
  }
}

function readCache(jwt) {
  try {
    const raw = localStorage.getItem(getCacheKey(jwt));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeCache(jwt, sessions) {
  try {
    localStorage.setItem(getCacheKey(jwt), JSON.stringify(sessions));
  } catch {
    // storage quota exceeded — ignore
  }
}

function clearCache(jwt) {
  try {
    if (jwt) localStorage.removeItem(getCacheKey(jwt));
  } catch {
    // ignore
  }
}

/**
 * useSessions — manages the list of chat sessions and selection state.
 * Sessions are cached in localStorage so the sidebar renders instantly
 * on page refresh, then silently updates from the API in the background.
 *
 * @param {string|null} jwt — user's Supabase access_token
 */
export function useSessions(jwt = null) {
  const [sessions, setSessions] = useState(() => {
    // ── Instant boot from cache ───────────────────────────────────────────
    // On first render, try to read the cached session list so the sidebar
    // is populated before the API responds. JWT may not be available yet
    // (auth still restoring), so we probe localStorage directly.
    try {
      const keys = Object.keys(localStorage).filter((k) =>
        k.startsWith(CACHE_KEY_PREFIX)
      );
      if (keys.length > 0) {
        const raw = localStorage.getItem(keys[0]);
        return raw ? JSON.parse(raw) : [];
      }
    } catch {
      // ignore
    }
    return [];
  });
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const jwtRef = useRef(jwt);
  useEffect(() => { jwtRef.current = jwt; }, [jwt]);

  const loadSessions = useCallback(async (showSpinner = true) => {
    const currentJwt = jwtRef.current;
    if (!currentJwt) return;

    if (showSpinner) setIsLoading(true);
    try {
      const data = await api.getSessions(currentJwt);
      setSessions(data);
      writeCache(currentJwt, data);  // update cache with fresh data
    } catch (e) {
      console.error("Failed to load sessions:", e);
    } finally {
      if (showSpinner) setIsLoading(false);
    }
  }, []);

  // Reload sessions whenever jwt becomes available (login / page refresh)
  useEffect(() => {
    if (jwt) {
      // Check if we already have a matching cache for this user
      const cached = readCache(jwt);
      if (cached && cached.length > 0) {
        // Show cached sessions immediately, then silently refresh
        setSessions(cached);
        loadSessions(false); // background refresh, no spinner
      } else {
        loadSessions(true);  // no cache — show spinner while loading
      }
    } else {
      setSessions([]);
      setCurrentSessionId(null);
    }
  }, [jwt, loadSessions]);

  const startNewSession = useCallback(() => {
    setCurrentSessionId(null);
  }, []);

  const selectSession = useCallback((id) => {
    setCurrentSessionId(id);
  }, []);

  const onSessionCreated = useCallback((id, title) => {
    setCurrentSessionId(id);
    setSessions((prev) => {
      const updated = [
        {
          id,
          title: title || "New Chat",
          summary: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        ...prev,
      ];
      writeCache(jwtRef.current, updated);
      return updated;
    });
  }, []);

  const onSummaryUpdate = useCallback((summary) => {
    setSessions((prev) => {
      const updated = prev.map((s) =>
        s.id === currentSessionId ? { ...s, summary } : s
      );
      writeCache(jwtRef.current, updated);
      return updated;
    });
  }, [currentSessionId]);

  const removeSession = useCallback(async (id) => {
    console.log("Deleting session:", id);

    const currentJwt = jwtRef.current;

    try {
      await api.deleteSession(id, currentJwt);

      console.log("Delete API successful");

      setSessions((prev) => {
        console.log("Before delete:", prev.length);

        const updated = prev.filter((s) => s.id !== id);

        console.log("After delete:", updated.length);

        writeCache(currentJwt, updated);

        return updated;
      });

      if (currentSessionId === id) {
        setCurrentSessionId(null);
      }
    } catch (e) {
      console.error("Failed to delete session:", e);
    }
  }, [currentSessionId]);

  const refreshSessions = useCallback(() => {
    loadSessions(false); // always silent refresh
  }, [loadSessions]);

  return {
    sessions,
    currentSessionId,
    isLoading,
    startNewSession,
    selectSession,
    onSessionCreated,
    onSummaryUpdate,
    removeSession,
    refreshSessions,
  };
}
