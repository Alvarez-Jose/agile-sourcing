import { GoogleAuthProvider, signInWithCredential, signOut as firebaseSignOut } from "firebase/auth";
import { auth } from "../firebase/firebaseConfig";
import { UserProfile, StoredAuthData } from "../types/auth";
import { browser } from "wxt/browser";

export const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

/**
 * Builds standard Google OAuth 2.0 URL for launchWebAuthFlow.
 * Uses response_type: "id_token" with nonce to exchange directly for Firebase credential.
 */
function buildGoogleAuthUrl(emailHint?: string): string {
  if (!CLIENT_ID) {
    throw new Error("Missing VITE_GOOGLE_CLIENT_ID in your .env file");
  }
  const redirectUri = browser.identity.getRedirectURL();
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    response_type: "id_token",
    redirect_uri: redirectUri,
    scope: "openid email profile",
    nonce: crypto.randomUUID(), // Required when requesting id_token via implicit flow
  });

  if (emailHint) {
    params.append("login_hint", emailHint);
  }

  return `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
}

/**
 * Executes Chrome Web Auth Flow, parses Google id_token from redirect URL fragment,
 * signs in to Firebase with the credential, saves the token, and establishes a backend session.
 */
async function executeGoogleAuthFlow(emailHint?: string): Promise<{
  idToken: string;
  profile: UserProfile;
}> {
  const authUrl = buildGoogleAuthUrl(emailHint);
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

  // Store in browser.storage.local
  await browser.storage.local.set({ idToken });

  // Call session endpoint stub
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
 * Sign in with specific email hint via launchWebAuthFlow (pre-fills user / SSO).
 */
export async function signInWithEmailHint(email: string): Promise<{
  idToken: string;
  profile: UserProfile;
}> {
  return executeGoogleAuthFlow(email);
}

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
    await browser.storage.local.set({ userProfile: profile });
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
    const existing = (await browser.storage.local.get("userProfile")) as { userProfile?: UserProfile };
    const finalProfile: UserProfile = existing.userProfile
      ? { ...mockProfile, is_approved: existing.userProfile.is_approved }
      : mockProfile;

    await browser.storage.local.set({ userProfile: finalProfile });
    return finalProfile;
  }
}

/**
 * Retrieve persisted auth data from browser.storage.local.
 */
export async function getStoredAuth(): Promise<StoredAuthData> {
  const data = (await browser.storage.local.get(["idToken", "userProfile"])) as StoredAuthData;
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
  await browser.storage.local.remove(["idToken", "userProfile"]);
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

  await browser.storage.local.set({ userProfile: updated });
  return updated;
}
