/**
 * API client for the Python Q&A Assistant backend.
 */

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const api = {
  /**
   * POST /ask — get a full answer (optionally with TTS audio)
   */
  async ask(question, voice = false) {
    const res = await fetch(`${API_URL}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, voice }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  /**
   * GET /health — check API status
   */
  async health() {
    const res = await fetch(`${API_URL}/health`);
    if (!res.ok) throw new Error("API offline");
    return res.json();
  },

  /**
   * GET /sources — retrieve matching docs without generating an answer
   */
  async sources(question, limit = 5) {
    const params = new URLSearchParams({ question, limit });
    const res = await fetch(`${API_URL}/sources?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  /**
   * Returns the base URL for SSE streaming (/ask/stream)
   */
  getStreamUrl() {
    return `${API_URL}/ask/stream`;
  },
};
