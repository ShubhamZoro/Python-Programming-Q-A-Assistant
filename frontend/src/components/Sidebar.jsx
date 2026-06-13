import { useState } from "react";

/**
 * Relative time formatter (e.g. "2 hours ago", "just now")
 */
function timeAgo(dateStr) {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diff = Math.floor((now - then) / 1000);

  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

/**
 * Sidebar — shows list of past chat sessions + "New Chat" button.
 */
export default function Sidebar({
  sessions = [],
  currentSessionId,
  isLoading,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  isMobileOpen,
  onMobileClose,
  user,
  onLogout,
}) {
  const [deletingId, setDeletingId] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);

  const handleDelete = async (e, id) => {
    e.stopPropagation();
    if (confirmDeleteId === id) {
      setDeletingId(id);
      setConfirmDeleteId(null);
      await onDeleteSession(id);
      setDeletingId(null);
    } else {
      setConfirmDeleteId(id);
      // Auto-reset confirm after 3s
      setTimeout(() => setConfirmDeleteId(null), 3000);
    }
  };

  return (
    <>
      {/* Mobile overlay */}
      {isMobileOpen && (
        <div className="sidebar-overlay" onClick={onMobileClose} />
      )}

      <aside className={`sidebar ${isMobileOpen ? "sidebar-open" : ""}`}>
        {/* Header */}
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
              <defs>
                <linearGradient id="sidebarGrad" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stopColor="#6366f1" />
                  <stop offset="100%" stopColor="#8b5cf6" />
                </linearGradient>
              </defs>
              <rect width="24" height="24" rx="6" fill="url(#sidebarGrad)" />
              <text x="4" y="17" fontSize="12" fontWeight="bold" fill="white" fontFamily="monospace">
                Py
              </text>
            </svg>
            <span className="sidebar-logo-text">PyAssist</span>
          </div>
          {/* Mobile close */}
          <button className="sidebar-close-btn" onClick={onMobileClose} aria-label="Close sidebar">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* New Chat button */}
        <button className="new-chat-btn" onClick={onNewChat} id="new-chat-btn">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M12 5v14M5 12h14" />
          </svg>
          New Chat
        </button>

        {/* Sessions list */}
        <div className="sessions-list">
          {isLoading && sessions.length === 0 ? (
            // ── Skeleton placeholders ──────────────────────────────────────────
            <div className="sessions-skeleton">
              {[72, 55, 88, 60].map((w, i) => (
                <div key={i} className="skeleton-item">
                  <div className="skeleton-icon" />
                  <div className="skeleton-lines">
                    <div className="skeleton-line" style={{ width: `${w}%` }} />
                    <div className="skeleton-line skeleton-line-sm" style={{ width: `${w * 0.55}%` }} />
                  </div>
                </div>
              ))}
            </div>
          ) : sessions.length === 0 ? (
            <div className="sessions-empty">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.4">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
              <p>No conversations yet.</p>
              <p>Start by asking a Python question!</p>
            </div>
          ) : (
            <>
              <p className="sessions-label">Recent</p>
              {sessions.map((session) => (
                <div
                  key={session.id}
                  className={`session-item ${currentSessionId === session.id ? "session-active" : ""} ${deletingId === session.id ? "session-deleting" : ""}`}
                  onClick={() => onSelectSession(session.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && onSelectSession(session.id)}
                  id={`session-${session.id}`}
                >
                  <div className="session-icon">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                    </svg>
                  </div>

                  <div className="session-content">
                    <div className="session-title">
                      {session.title || "New Chat"}
                    </div>
                    {session.summary && (
                      <div className="session-summary">
                        {session.summary.slice(0, 80)}
                        {session.summary.length > 80 ? "…" : ""}
                      </div>
                    )}
                    <div className="session-time">
                      {timeAgo(session.updated_at || session.created_at)}
                    </div>
                  </div>

                  <button
                    className={`session-delete-btn ${confirmDeleteId === session.id ? "session-delete-confirm" : ""}`}
                    onClick={(e) => handleDelete(e, session.id)}
                    title={confirmDeleteId === session.id ? "Click again to confirm" : "Delete chat"}
                    aria-label="Delete chat"
                  >
                    {confirmDeleteId === session.id ? (
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <path d="M20 6L9 17l-5-5" />
                      </svg>
                    ) : (
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="3 6 5 6 21 6" />
                        <path d="M19 6l-1 14H6L5 6" />
                        <path d="M9 6V4h6v2" />
                      </svg>
                    )}
                  </button>
                </div>
              ))}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="sidebar-footer">
          {/* User info + logout */}
          {user && (
            <div className="sidebar-user">
              <div className="sidebar-user-avatar">
                {user.email?.[0]?.toUpperCase() ?? "U"}
              </div>
              <div className="sidebar-user-info">
                <span className="sidebar-user-email" title={user.email}>
                  {user.email}
                </span>
              </div>
              <button
                className="sidebar-logout-btn"
                onClick={onLogout}
                title="Sign out"
                aria-label="Sign out"
                id="logout-btn"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                  <polyline points="16 17 21 12 16 7" />
                  <line x1="21" y1="12" x2="9" y2="12" />
                </svg>
              </button>
            </div>
          )}
          <div className="sidebar-footer-badges">
            <span className="footer-badge">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
                <circle cx="12" cy="12" r="10" />
              </svg>
              Pinecone
            </span>
            <span className="footer-badge">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
                <circle cx="12" cy="12" r="10" />
              </svg>
              GPT-4o
            </span>
          </div>
          <p className="sidebar-footer-text">Python Q&amp;A Assistant v3</p>
        </div>
      </aside>
    </>
  );
}
