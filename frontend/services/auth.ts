import { GoogleAuthProvider, signInWithCredential, signOut as firebaseSignOut } from "firebase/auth";
import { auth } from "../firebase/firebaseConfig";
import { UserProfile } from "../types/auth";
import { browser } from "wxt/browser";

export const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

/**
 * Builds standard Google OAuth 2.0 URL for launchWebAuthFlow.
 * Uses response_type: "id_token" with nonce to exchange directly for Firebase credential.
 */
function buildGoogleAuthUrl(): string {
  if (!CLIENT_ID) {
    throw new Error("Missing VITE_GOOGLE_CLIENT_ID in secret/.env");
  }
  const redirectUri = browser.identity.getRedirectURL();
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    response_type: "id_token",
    redirect_uri: redirectUri,
    scope: "openid email profile",
    nonce: crypto.randomUUID(), // Required when requesting id_token via implicit flow
  });

  return `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
}

/**
 * Executes Chrome Web Auth Flow, parses Google id_token from redirect URL fragment,
 * signs in to Firebase with the credential, saves the token, and establishes a backend session.
 */
async function executeGoogleAuthFlow(): Promise<{
  idToken: string;
  profile: UserProfile;
}> {
  const authUrl = buildGoogleAuthUrl();
  const responseUrl = await browser.identity.launchWebAuthFlow({
    url: authUrl,
    interactive: true,
  });

  if (!responseUrl) {
    throw new Error("Authentication flow was cancelled or failed");
  }
  // Google returns id_token in the URL fragment (#id_token=...&token_type=Bearer...)
  const url = new URL(responseUrl);
  const params = new URLSearchParams(url.hash.substring(1));
  const googleIdToken = params.get("id_token");

  if (!googleIdToken) {
    const errorParam = params.get("error");
    throw new Error(
      errorParam
        ? `Google Authentication Error: ${errorParam}`
        : "No id_token returned from Google"
    );
  }

  // Exchange Google ID Token for Firebase Credential
  const credential = GoogleAuthProvider.credential(googleIdToken);
  const result = await signInWithCredential(auth, credential);
  const idToken = await result.user.getIdToken(true);

  // Only persist a session after the server verifies identity and loads its profile.
  const profile = await establishSession(idToken);

  return { idToken, profile };
}

/**
 * Sign in with Google (account chooser) via launchWebAuthFlow.
 */
export async function signInWithGoogle(): Promise<{
  idToken: string;
  profile: UserProfile;
}> {
  return executeGoogleAuthFlow();
}

/**
 * Exchange a Firebase ID token for a server-owned Firestore profile.
 */
export async function establishSession(idToken: string): Promise<UserProfile> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/auth/session`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${idToken}`,
      },
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    throw new Error("Cannot reach the sign-in server. Check that FastAPI is running, then retry.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new SessionError(
      typeof body?.detail === "string" ? body.detail : `Sign-in server returned HTTP ${res.status}.`,
      res.status,
    );
  }
  const profile: UserProfile = await res.json();
  if (profile.uid !== auth.currentUser?.uid || typeof profile.email !== "string" ||
      typeof profile.is_approved !== "boolean") {
    throw new Error("The sign-in server returned an invalid user profile.");
  }
  await browser.storage.local.set({ idToken, userProfile: profile });
  return profile;
}

export class SessionError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

export async function getFreshIdToken(forceRefresh = false): Promise<string> {
  await auth.authStateReady();
  if (!auth.currentUser) throw new Error("Please sign in to continue.");
  return auth.currentUser.getIdToken(forceRefresh);
}

/**
 * Sign out and clear extension storage.
 */
export async function signOutUser(): Promise<void> {
  try {
    await firebaseSignOut(auth);
  } finally {
    await browser.storage.local.remove(["idToken", "userProfile"]);
  }
}
