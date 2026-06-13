/**
 * API client for the Python Q&A Assistant backend.
 * All protected calls pass the user's JWT as: Authorization: Bearer <token>
 */

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

/** Build auth headers from a JWT string. */
function authHeaders(jwt) {
  return jwt
    ? { "Content-Type": "application/json", Authorization: `Bearer ${jwt}` }
    : { "Content-Type": "application/json" };
}

export const api = {
  // ── Core Q&A ──────────────────────────────────────────────────────────────

  /** POST /ask — get a full answer (optionally with TTS audio) */
  async ask(question, sessionId = null, jwt = null) {
    const res = await fetch(`${API_URL}/ask`, {
      method: "POST",
      headers: authHeaders(jwt),
      body: JSON.stringify({
        question,
        session_id: sessionId,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    return res.json();
  },

  /** GET /health — check API status (unauthenticated) */
  async health() {
    const res = await fetch(`${API_URL}/health`);
    if (!res.ok) throw new Error("API offline");
    return res.json();
  },

  /** GET /sources — retrieve matching docs (requires auth) */
  async sources(question, limit = 5, jwt = null) {
    const params = new URLSearchParams({ question, limit });
    const res = await fetch(`${API_URL}/sources?${params}`, {
      headers: authHeaders(jwt),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },


  // ── Chat Sessions ─────────────────────────────────────────────────────────

  /** GET /sessions — list sessions for the current user */
  async getSessions(jwt = null) {
    const res = await fetch(`${API_URL}/sessions`, {
      headers: authHeaders(jwt),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  /** POST /sessions — create a new session */
  async createSession(title = "New Chat", jwt = null) {
    const res = await fetch(`${API_URL}/sessions`, {
      method: "POST",
      headers: authHeaders(jwt),
      body: JSON.stringify({ title }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json(); // { session_id, title, created_at }
  },

  /** GET /sessions/{id}/messages — load message history */
  async getMessages(sessionId, jwt = null) {
    const res = await fetch(`${API_URL}/sessions/${sessionId}/messages`, {
      headers: authHeaders(jwt),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  /** POST /sessions/{id}/summarize — generate AI summary */
  async summarize(sessionId, jwt = null) {
    const res = await fetch(`${API_URL}/sessions/${sessionId}/summarize`, {
      method: "POST",
      headers: authHeaders(jwt),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json(); // { session_id, summary }
  },

  /** DELETE /sessions/{id} — delete a session */
  async deleteSession(sessionId, jwt = null) {
    const res = await fetch(`${API_URL}/sessions/${sessionId}`, {
      method: "DELETE",
      headers: authHeaders(jwt),
    });
    if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`);
  },
};
