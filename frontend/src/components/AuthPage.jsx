import { useState } from "react";

/**
 * AuthPage — full-screen login / signup with glassmorphism design.
 * Matches the dark purple/indigo theme of the rest of the app.
 *
 * Props:
 *   onLogin(email, password) — async
 *   onSignup(email, password) — async
 *   onGoogleLogin() — async
 *   isLoading — bool
 *   error — string | null
 */
export default function AuthPage({ onLogin, onSignup, onGoogleLogin, isLoading, error }) {
  const [tab, setTab] = useState("login"); // "login" | "signup"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [localError, setLocalError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError(null);
    setSuccessMsg(null);

    if (!email.trim() || !password) {
      setLocalError("Email and password are required.");
      return;
    }

    if (tab === "signup") {
      if (password.length < 6) {
        setLocalError("Password must be at least 6 characters.");
        return;
      }
      if (password !== confirmPassword) {
        setLocalError("Passwords do not match.");
        return;
      }
      try {
        await onSignup(email, password);
        setSuccessMsg("Account created! Check your inbox to confirm your email, then log in.");
        setTab("login");
        setPassword("");
        setConfirmPassword("");
      } catch (err) {
        setLocalError(err.message || "Signup failed. Please try again.");
      }
    } else {
      try {
        await onLogin(email, password);
        // success — App.jsx will re-render with user set
      } catch (err) {
        setLocalError(err.message || "Login failed. Check your credentials.");
      }
    }
  };

  const displayError = localError || error;

  return (
    <div className="auth-page">
      {/* Animated background orbs */}
      <div className="auth-bg">
        <div className="auth-orb auth-orb-1" />
        <div className="auth-orb auth-orb-2" />
        <div className="auth-orb auth-orb-3" />
      </div>

      <div className="auth-card">
        {/* Logo */}
        <div className="auth-logo">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
            <defs>
              <linearGradient id="authLogoGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#6366f1" />
                <stop offset="100%" stopColor="#8b5cf6" />
              </linearGradient>
            </defs>
            <rect width="24" height="24" rx="7" fill="url(#authLogoGrad)" />
            <text x="4" y="17" fontSize="13" fontWeight="bold" fill="white" fontFamily="monospace">
              Py
            </text>
          </svg>
          <div className="auth-logo-text">
            <h1 className="auth-title">Python Q&amp;A Assistant</h1>
            <p className="auth-subtitle">Powered by GPT-4o · Pinecone · LangGraph</p>
          </div>
        </div>

        {/* Tab switcher */}
        <div className="auth-tabs" role="tablist">
          <button
            role="tab"
            aria-selected={tab === "login"}
            className={`auth-tab ${tab === "login" ? "auth-tab-active" : ""}`}
            onClick={() => { setTab("login"); setLocalError(null); setSuccessMsg(null); }}
            id="tab-login"
          >
            Sign In
          </button>
          <button
            role="tab"
            aria-selected={tab === "signup"}
            className={`auth-tab ${tab === "signup" ? "auth-tab-active" : ""}`}
            onClick={() => { setTab("signup"); setLocalError(null); setSuccessMsg(null); }}
            id="tab-signup"
          >
            Sign Up
          </button>
        </div>

        {/* Form */}
        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          {/* Error banner */}
          {displayError && (
            <div className="auth-alert auth-alert-error" role="alert">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
              </svg>
              {displayError}
            </div>
          )}

          {/* Success banner */}
          {successMsg && (
            <div className="auth-alert auth-alert-success" role="status">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14l-4-4 1.41-1.41L10 13.17l6.59-6.59L18 8l-8 8z"/>
              </svg>
              {successMsg}
            </div>
          )}

          {/* Email */}
          <div className="auth-field">
            <label htmlFor="auth-email" className="auth-label">Email address</label>
            <div className="auth-input-wrap">
              <svg className="auth-input-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                <polyline points="22,6 12,13 2,6"/>
              </svg>
              <input
                id="auth-email"
                type="email"
                className="auth-input"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
                disabled={isLoading}
              />
            </div>
          </div>

          {/* Password */}
          <div className="auth-field">
            <label htmlFor="auth-password" className="auth-label">Password</label>
            <div className="auth-input-wrap">
              <svg className="auth-input-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
              </svg>
              <input
                id="auth-password"
                type={showPassword ? "text" : "password"}
                className="auth-input"
                placeholder={tab === "signup" ? "At least 6 characters" : "Your password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={tab === "signup" ? "new-password" : "current-password"}
                required
                disabled={isLoading}
              />
              <button
                type="button"
                className="auth-eye-btn"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                tabIndex={-1}
              >
                {showPassword ? (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
                    <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
                    <line x1="1" y1="1" x2="23" y2="23"/>
                  </svg>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                )}
              </button>
            </div>
          </div>

          {/* Confirm Password (signup only) */}
          {tab === "signup" && (
            <div className="auth-field">
              <label htmlFor="auth-confirm" className="auth-label">Confirm password</label>
              <div className="auth-input-wrap">
                <svg className="auth-input-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 12l2 2 4-4"/>
                  <path d="M12 22c5.52 0 10-4.48 10-10S17.52 2 12 2 2 6.48 2 12s4.48 10 10 10z"/>
                </svg>
                <input
                  id="auth-confirm"
                  type={showPassword ? "text" : "password"}
                  className="auth-input"
                  placeholder="Repeat your password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                  disabled={isLoading}
                />
              </div>
            </div>
          )}

          {/* Submit button */}
          <button
            type="submit"
            className="auth-submit-btn"
            disabled={isLoading}
            id={tab === "login" ? "login-btn" : "signup-btn"}
          >
            {isLoading ? (
              <>
                <span className="spinner-sm" />
                {tab === "login" ? "Signing in…" : "Creating account…"}
              </>
            ) : (
              tab === "login" ? "Sign In" : "Create Account"
            )}
          </button>

          {/* Divider */}
          <div className="auth-divider">
            <span>or continue with</span>
          </div>

          {/* Google OAuth */}
          <button
            type="button"
            className="auth-google-btn"
            onClick={onGoogleLogin}
            disabled={isLoading}
            id="google-login-btn"
          >
            <svg width="18" height="18" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Continue with Google
          </button>
        </form>

        <p className="auth-footer-note">
          By continuing, you agree to our Terms of Service and Privacy Policy.
        </p>
      </div>
    </div>
  );
}
