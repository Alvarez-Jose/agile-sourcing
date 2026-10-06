import React, { createContext, useContext, useEffect, useState } from "react";
import { UserProfile } from "../types/auth";
import {
  getStoredAuth,
  signInWithGoogle as authServiceSignInWithGoogle,
  signInWithEmailHint as authServiceSignInWithEmailHint,
  signOutUser,
  establishSession,
  setMockApproval,
} from "../services/auth";
import { auth } from "../firebase/firebaseConfig";
import { onAuthStateChanged } from "firebase/auth";

interface AuthContextType {
  userProfile: UserProfile | null;
  idToken: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isApproved: boolean;
  loginWithGoogle: () => Promise<void>;
  loginWithEmail: (email: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
  toggleMockApproval: (approved?: boolean) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [idToken, setIdToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Sync state with chrome.storage.local
  const loadStoredAuth = async () => {
    try {
      const data = await getStoredAuth();
      if (data.userProfile) {
        setUserProfile(data.userProfile);
      }
      if (data.idToken) {
        setIdToken(data.idToken);
      }
    } catch (err) {
      console.error("Failed to load stored auth:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStoredAuth();

    // Listen for storage changes across different extension pages/views
    const handleStorageChange = (
      changes: { [key: string]: chrome.storage.StorageChange },
      areaName: string
    ) => {
      if (areaName === "local") {
        if (changes.userProfile) {
          const newProfile = changes.userProfile.newValue as UserProfile | undefined;
          setUserProfile(newProfile || null);
        }
        if (changes.idToken) {
          const newToken = changes.idToken.newValue as string | undefined;
          setIdToken(newToken || null);
        }
      }
    };

    chrome.storage.onChanged.addListener(handleStorageChange);

    // Also observe Firebase auth state
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      if (firebaseUser) {
        try {
          const token = await firebaseUser.getIdToken();
          setIdToken(token);
          await chrome.storage.local.set({ idToken: token });
        } catch (e) {
          console.warn("Could not get fresh ID token on auth change:", e);
        }
      }
    });

    return () => {
      chrome.storage.onChanged.removeListener(handleStorageChange);
      unsubscribe();
    };
  }, []);

  const loginWithGoogle = async () => {
    setIsLoading(true);
    try {
      const { idToken: token, profile } = await authServiceSignInWithGoogle();
      setIdToken(token);
      setUserProfile(profile);
    } finally {
      setIsLoading(false);
    }
  };

  const loginWithEmail = async (email: string) => {
    setIsLoading(true);
    try {
      const { idToken: token, profile } = await authServiceSignInWithEmailHint(email);
      setIdToken(token);
      setUserProfile(profile);
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    setIsLoading(true);
    try {
      await signOutUser();
      setUserProfile(null);
      setIdToken(null);
    } finally {
      setIsLoading(false);
    }
  };

  const refreshSession = async () => {
    if (!idToken && !auth.currentUser) return;
    setIsLoading(true);
    try {
      const token = idToken || (await auth.currentUser?.getIdToken(true)) || "";
      if (token) {
        const profile = await establishSession(token);
        setUserProfile(profile);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const toggleMockApproval = async (approved?: boolean) => {
    const target = approved !== undefined ? approved : !userProfile?.is_approved;
    const updated = await setMockApproval(target);
    setUserProfile(updated);
  };

  const isAuthenticated = !!userProfile;
  const isApproved = !!userProfile?.is_approved;

  return (
    <AuthContext.Provider
      value={{
        userProfile,
        idToken,
        isLoading,
        isAuthenticated,
        isApproved,
        loginWithGoogle,
        loginWithEmail,
        logout,
        refreshSession,
        toggleMockApproval,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
