import { useState, useEffect, useCallback } from "react";
import { supabase } from "../lib/supabaseClient";

/**
 * useAuth — manages Supabase Auth state.
 *
 * Returns:
 *   user        — the current Supabase User object (null if logged out)
 *   session     — the full Supabase Session object (contains access_token)
 *   jwt         — shortcut to session.access_token (string | null)
 *   isLoading   — true while the initial session check is running
 *   error       — latest auth error message (string | null)
 *   login()     — sign in with email + password
 *   signup()    — create a new account
 *   loginWithGoogle() — OAuth redirect to Google
 *   logout()    — sign out and clear session
 */
export function useAuth() {
  const [user, setUser] = useState(null);
  const [session, setSession] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // On mount: restore existing session + subscribe to auth changes.
  // We use onAuthStateChange as the single source of truth because:
  //   • It fires INITIAL_SESSION synchronously for cached sessions in localStorage
  //   • It fires SIGNED_IN after parsing the #access_token hash (implicit flow)
  //   • It fires SIGNED_IN after PKCE code exchange (when the real anon key is set)
  // A safety-net timeout prevents a permanent loading screen if Supabase never fires.
  useEffect(() => {
    let mounted = true;
    let resolved = false;

    const resolve = () => {
      if (mounted && !resolved) {
        resolved = true;
        setIsLoading(false);
      }
    };

    // Safety net: force isLoading=false after 1s if Supabase never fires an event.
    // INITIAL_SESSION fires in milliseconds when a cached token exists in localStorage,
    // so 1s is more than enough without causing a long loading screen on refresh.
    const safetyTimer = setTimeout(resolve, 1000);

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (event, session) => {
        if (!mounted) return;

        setSession(session);
        setUser(session?.user ?? null);

        // INITIAL_SESSION = cached session restored; SIGNED_IN = fresh login
        if (event === "INITIAL_SESSION" || event === "SIGNED_IN" || event === "SIGNED_OUT") {
          resolve();
        }

        // Clean the URL immediately after OAuth sign-in so no token/code lingers
        if (
          event === "SIGNED_IN" &&
          (window.location.hash.includes("access_token") ||
            window.location.hash.includes("error_description") ||
            window.location.search.includes("code="))
        ) {
          window.history.replaceState({}, document.title, window.location.pathname);
        }
      }
    );

    return () => {
      mounted = false;
      clearTimeout(safetyTimer);
      subscription.unsubscribe();
    };
  }, []);


  // ── Sign up ──────────────────────────────────────────────────────────────
  const signup = useCallback(async (email, password) => {
    setError(null);
    setIsLoading(true);
    try {
      const { data, error } = await supabase.auth.signUp({ email, password });
      if (error) throw error;
      // If email confirmation is disabled, session is set immediately
      setSession(data.session);
      setUser(data.user);
      return { user: data.user, session: data.session };
    } catch (e) {
      setError(e.message);
      throw e;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // ── Sign in ──────────────────────────────────────────────────────────────
  const login = useCallback(async (email, password) => {
    setError(null);
    setIsLoading(true);
    try {
      const { data, error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
      setSession(data.session);
      setUser(data.user);
      return { user: data.user, session: data.session };
    } catch (e) {
      setError(e.message);
      throw e;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // ── Google OAuth ─────────────────────────────────────────────────────────
  const loginWithGoogle = useCallback(async () => {
    setError(null);
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: window.location.origin,
        },
      });
      if (error) throw error;
      // Browser will redirect — no further handling needed here
    } catch (e) {
      setError(e.message);
      throw e;
    }
  }, []);

  // ── Sign out ─────────────────────────────────────────────────────────────
  const logout = useCallback(async () => {
    setError(null);
    try {
      await supabase.auth.signOut();
      setSession(null);
      setUser(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  return {
    user,
    session,
    jwt: session?.access_token ?? null,
    isLoading,
    error,
    login,
    signup,
    loginWithGoogle,
    logout,
  };
}
