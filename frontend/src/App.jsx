import { useState } from "react";
import ChatInterface from "./components/ChatInterface";
import HealthBadge from "./components/HealthBadge";
import Sidebar from "./components/Sidebar";
import AuthPage from "./components/AuthPage";
import { useSessions } from "./hooks/useSessions";
import { useAuth } from "./hooks/useAuth";

export default function App() {
  const { user, jwt, isLoading: authLoading, error: authError, login, signup, loginWithGoogle, logout } = useAuth();

  const {
    sessions,
    currentSessionId,
    isLoading: sessionsLoading,
    startNewSession,
    selectSession,
    onSessionCreated,
    removeSession,
    refreshSessions,
  } = useSessions(jwt);

  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleSelectSession = (id) => {
    selectSession(id);
    setSidebarOpen(false);
  };

  const handleNewChat = () => {
    startNewSession();
    setSidebarOpen(false);
  };

  const handleSessionCreated = (id, title) => {
    onSessionCreated(id, title);
    setTimeout(refreshSessions, 800);
  };

  // ── Loading splash (initial auth restore) ─────────────────────────────────
  if (authLoading) {
    return (
      <div className="auth-loading-screen">
        <div className="auth-loading-inner">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
            <defs>
              <linearGradient id="loadGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#6366f1" />
                <stop offset="100%" stopColor="#8b5cf6" />
              </linearGradient>
            </defs>
            <rect width="24" height="24" rx="7" fill="url(#loadGrad)" />
            <text x="4" y="17" fontSize="13" fontWeight="bold" fill="white" fontFamily="monospace">Py</text>
          </svg>
          <span className="spinner" style={{ width: 24, height: 24 }} />
        </div>
      </div>
    );
  }

  // ── Auth gate ─────────────────────────────────────────────────────────────
  if (!user) {
    return (
      <AuthPage
        onLogin={login}
        onSignup={signup}
        onGoogleLogin={loginWithGoogle}
        isLoading={authLoading}
        error={authError}
      />
    );
  }

  // ── Main app (authenticated) ──────────────────────────────────────────────
  return (
    <div className="app-shell">
      {/* Sidebar */}
      <Sidebar
        sessions={sessions}
        currentSessionId={currentSessionId}
        isLoading={sessionsLoading}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
        onDeleteSession={removeSession}
        isMobileOpen={sidebarOpen}
        onMobileClose={() => setSidebarOpen(false)}
        user={user}
        onLogout={logout}
      />

      {/* Main panel */}
      <div className="main-panel">
        {/* Header */}
        <header className="app-header">
          <div className="header-left">
            {/* Mobile sidebar toggle */}
            <button
              className="sidebar-toggle-btn"
              onClick={() => setSidebarOpen((v) => !v)}
              aria-label="Toggle sidebar"
              id="sidebar-toggle"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>

            <div className="logo">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                <defs>
                  <linearGradient id="logoGrad" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor="#6366f1" />
                    <stop offset="100%" stopColor="#8b5cf6" />
                  </linearGradient>
                </defs>
                <rect width="24" height="24" rx="6" fill="url(#logoGrad)" />
                <text x="4" y="17" fontSize="14" fontWeight="bold" fill="white" fontFamily="monospace">
                  Py
                </text>
              </svg>
            </div>
            <div className="header-text">
              <h1 className="header-title">Python Q&amp;A Assistant</h1>
              <span className="header-sub">Pinecone · GPT-4o · LangGraph · Supabase</span>
            </div>
          </div>
          <div className="header-right">
            {/* User avatar chip in header */}
            <div className="header-user-chip">
              <div className="header-user-avatar">
                {user.email?.[0]?.toUpperCase() ?? "U"}
              </div>
              <span className="header-user-email">{user.email}</span>
            </div>
            <HealthBadge />
          </div>
        </header>

        {/* Main chat */}
        <main className="app-main">
          <ChatInterface
            sessionId={currentSessionId}
            jwt={jwt}
            onSessionCreated={handleSessionCreated}
          />
        </main>
      </div>
    </div>
  );
}
