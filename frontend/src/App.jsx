import ChatInterface from "./components/ChatInterface";
import HealthBadge from "./components/HealthBadge";

export default function App() {
  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-left">
          <div className="logo">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
              <defs>
                <linearGradient id="logoGrad" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stopColor="#6366f1"/>
                  <stop offset="100%" stopColor="#8b5cf6"/>
                </linearGradient>
              </defs>
              <rect width="24" height="24" rx="6" fill="url(#logoGrad)"/>
              <text x="4" y="17" fontSize="14" fontWeight="bold" fill="white" fontFamily="monospace">Py</text>
            </svg>
          </div>
          <div className="header-text">
            <h1 className="header-title">Python Q&amp;A Assistant</h1>
            <span className="header-sub">Powered by Stack Overflow · GPT-4o · LangGraph</span>
          </div>
        </div>
        <div className="header-right">
          <HealthBadge />
        </div>
      </header>

      {/* Main */}
      <main className="app-main">
        <ChatInterface />
      </main>
    </div>
  );
}
