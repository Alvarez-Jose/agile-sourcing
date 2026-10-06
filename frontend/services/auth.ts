import { GoogleAuthProvider, signInWithCredential, signOut as firebaseSignOut } from "firebase/auth";
import { auth } from "../firebase/firebaseConfig";
import { UserProfile, StoredAuthData } from "../types/auth";

export const CLIENT_ID =
  import.meta.env.VITE_GOOGLE_CLIENT_ID ||
  "933132683609-minc10snome0g6gv56nsd03tviqseoon.apps.googleusercontent.com";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

/**
 * Exchange ID token with backend session endpoint.
 * Stubs a fallback mock profile if the backend endpoint is not yet live.
 */
export async function establishSession(idToken: string): Promise<UserProfile> {
  try {
    const res = await fetch(`${API_BASE_URL}/auth/session`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${idToken}`,
      },
    });

    if (!res.ok) {
      throw new Error(`Session establishment failed with HTTP status ${res.status}`);
    }

    const profile: UserProfile = await res.json();
    await chrome.storage.local.set({ userProfile: profile });
    return profile;
  } catch (error) {
    console.warn(
      `[Auth Service] Backend /auth/session endpoint unreachable or returned error. Using fallback mock profile for development:`,
      error
    );

    // Mock fallback profile during local development
    const currentUser = auth.currentUser;
    const mockProfile: UserProfile = {
      uid: currentUser?.uid || "mock-user-uid",
      email: currentUser?.email || "cruzbuy-user@ucsc.edu",
      name: currentUser?.displayName || "CruzBuy User",
      photoURL: currentUser?.photoURL || undefined,
      is_approved: false, // Default to pending approval to test approval states
      role: "buyer",
      created_at: new Date().toISOString(),
    };

    // Check if we already have a saved local approval state to preserve testing toggles
    const existing = (await chrome.storage.local.get("userProfile")) as { userProfile?: UserProfile };
    const finalProfile: UserProfile = existing.userProfile
      ? { ...mockProfile, is_approved: existing.userProfile.is_approved }
      : mockProfile;

    await chrome.storage.local.set({ userProfile: finalProfile });
    return finalProfile;
  }
}

/**
 * Step 1: Sign in with Google (account chooser) via Chrome Identity API.
 * Extracts access token, exchanges for Firebase credential, retrieves Firebase ID token,
 * persists to chrome.storage.local, and establishes backend session.
 */
export async function signInWithGoogle(): Promise<{
  idToken: string;
  profile: UserProfile;
}> {
  const token = await new Promise<string>((resolve, reject) => {
    chrome.identity.getAuthToken({ interactive: true }, (token) => {
      if (chrome.runtime.lastError || !token) {
        reject(
          new Error(
            chrome.runtime.lastError?.message || "No Google access token returned"
          )
        );
      } else {
        resolve(token as string);
      }
    });
  });

  const credential = GoogleAuthProvider.credential(null, token);
  const result = await signInWithCredential(auth, credential);
  const idToken = await result.user.getIdToken(true);

  // Save token to chrome.storage.local
  await chrome.storage.local.set({ idToken });

  // Call session endpoint stub
  const profile = await establishSession(idToken);

  return { idToken, profile };
}

/**
 * Step 1: Sign in with email hint via Chrome Web Auth Flow (for pre-filled SSO/2FA).
 * Parses redirect URL fragment for access_token, exchanges for Firebase credential,
 * retrieves Firebase ID token, persists to chrome.storage.local, and establishes session.
 */
export async function signInWithEmailHint(email: string): Promise<{
  idToken: string;
  profile: UserProfile;
}> {
  const redirectUri = chrome.identity.getRedirectURL();
  const authUrl =
    `https://accounts.google.com/o/oauth2/auth` +
    `?client_id=${CLIENT_ID}` +
    `&response_type=token` +
    `&redirect_uri=${encodeURIComponent(redirectUri)}` +
    `&scope=${encodeURIComponent("openid email profile")}` +
    `&login_hint=${encodeURIComponent(email)}`;

  const responseUrl = await new Promise<string>((resolve, reject) => {
    chrome.identity.launchWebAuthFlow(
      { url: authUrl, interactive: true },
      (responseUrl) => {
        if (chrome.runtime.lastError || !responseUrl) {
          reject(
            new Error(
              chrome.runtime.lastError?.message || "Web Auth Flow failed"
            )
          );
        } else {
          resolve(responseUrl);
        }
      }
    );
  });

  // Extract access_token from the redirect URL fragment (#access_token=...)
  const hash = responseUrl.split("#")[1];
  if (!hash) {
    throw new Error("No URL fragment received in redirect response");
  }

  const params = new URLSearchParams(hash);
  const accessToken = params.get("access_token");
  if (!accessToken) {
    const errorParam = params.get("error");
    throw new Error(
      errorParam
        ? `Authentication error: ${errorParam}`
        : "No access token found in redirect URL"
    );
  }

  const credential = GoogleAuthProvider.credential(null, accessToken);
  const result = await signInWithCredential(auth, credential);
  const idToken = await result.user.getIdToken(true);

  // Store token in chrome.storage.local
  await chrome.storage.local.set({ idToken });

  // Call session establishment stub
  const profile = await establishSession(idToken);

  return { idToken, profile };
}

/**
 * Retrieve persisted auth data from chrome.storage.local.
 */
export async function getStoredAuth(): Promise<StoredAuthData> {
  const data = (await chrome.storage.local.get(["idToken", "userProfile"])) as StoredAuthData;
  return {
    idToken: data.idToken,
    userProfile: data.userProfile,
  };
}

/**
 * Sign out and clear extension storage.
 */
export async function signOutUser(): Promise<void> {
  try {
    await firebaseSignOut(auth);
  } catch (e) {
    console.error("Firebase sign-out error:", e);
  }
  await chrome.storage.local.remove(["idToken", "userProfile"]);
}

/**
 * Development Helper: Manually toggle is_approved status for UI state testing.
 */
export async function setMockApproval(isApproved: boolean): Promise<UserProfile> {
  const { userProfile } = await getStoredAuth();
  const updated: UserProfile = userProfile
    ? { ...userProfile, is_approved: isApproved }
    : {
        uid: "test-user-uid",
        email: "test-user@ucsc.edu",
        name: "Test User",
        is_approved: isApproved,
      };

  await chrome.storage.local.set({ userProfile: updated });
  return updated;
}
