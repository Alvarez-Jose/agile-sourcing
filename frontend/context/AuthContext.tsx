import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { onIdTokenChanged } from "firebase/auth";
import { browser } from "wxt/browser";
import { UserProfile } from "../types/auth";
import { auth } from "../firebase/firebaseConfig";
import {
  signInWithGoogle,
  signOutUser,
  establishSession,
  getFreshIdToken,
  SessionError,
} from "../services/auth";

interface AuthContextType {
  userProfile: UserProfile | null;
  idToken: string | null;
  isLoading: boolean;
  sessionError: string | null;
  isAuthenticated: boolean;
  isApproved: boolean;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [idToken, setIdToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const revision = useRef(0);

  const clearProfile = useCallback(async () => {
    setUserProfile(null);
    setIdToken(null);
    await browser.storage.local.remove(["idToken", "userProfile"]);
  }, []);

  const handleError = useCallback(async (error: unknown) => {
    setSessionError(error instanceof Error ? error.message : "Could not load your account.");
    await clearProfile();
    if (error instanceof SessionError && error.status === 401) {
      await signOutUser();
    }
  }, [clearProfile]);

  useEffect(() => {
    // Firebase restores identity; cached extension profiles do not establish a session.
    const unsubscribe = onIdTokenChanged(auth, async (user) => {
      const currentRevision = ++revision.current;
      setIsLoading(true);
      setUserProfile(null);
      setIdToken(null);
      try {
        if (!user) {
          await clearProfile();
          return;
        }
        const token = await user.getIdToken();
        const profile = await establishSession(token);
        if (currentRevision !== revision.current) return;
        setIdToken(token);
        setUserProfile(profile);
        setSessionError(null);
      } catch (error) {
        if (currentRevision === revision.current) await handleError(error);
      } finally {
        if (currentRevision === revision.current) setIsLoading(false);
      }
    });
    return () => {
      revision.current++;
      unsubscribe();
    };
  }, [clearProfile, handleError]);

  const login = async () => {
    setIsLoading(true);
    setSessionError(null);
    try {
      const result = await signInWithGoogle();
      revision.current++;
      setIdToken(result.idToken);
      setUserProfile(result.profile);
    } catch (error) {
      revision.current++;
      await handleError(error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    revision.current++;
    setIsLoading(true);
    setSessionError(null);
    await clearProfile();
    try {
      await signOutUser();
    } finally {
      setIsLoading(false);
    }
  };

  const refreshSession = async () => {
    setIsLoading(true);
    setSessionError(null);
    try {
      const token = await getFreshIdToken(true);
      const profile = await establishSession(token);
      revision.current++;
      setIdToken(token);
      setUserProfile(profile);
    } catch (error) {
      revision.current++;
      await handleError(error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthContext.Provider value={{
      userProfile,
      idToken,
      isLoading,
      sessionError,
      isAuthenticated: !!userProfile,
      isApproved: userProfile?.is_approved === true,
      loginWithGoogle: login,
      logout,
      refreshSession,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
}
