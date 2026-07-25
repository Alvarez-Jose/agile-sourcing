import { useState } from "react";
import { GoogleAuthProvider, signInWithCredential } from "firebase/auth";
import { auth } from "../../firebase/firebaseConfig";

type LoginProps = {
    isOpen: boolean;
    onClose: () => void;
};

const CLIENT_ID = "YOUR_CLIENT_ID.apps.googleusercontent.com"; // same one from wxt.config.ts

export default function Login({ isOpen, onClose }: LoginProps) {
    const [email, setEmail] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    if (!isOpen) return null;

    // Generic Google sign-in (account chooser, no email pre-filled)
    const handleGoogle = async () => {
        if (isLoading) return;
        setIsLoading(true);
        setError(null);

        try {
            const token = await new Promise<string>((resolve, reject) => {
                chrome.identity.getAuthToken({ interactive: true }, (token) => {
                    if (chrome.runtime.lastError || !token) {
                        reject(new Error(chrome.runtime.lastError?.message || "No token returned"));
                    } else {
                        resolve(token as string);
                    }
                });
            });

            const credential = GoogleAuthProvider.credential(null, token);
            const result = await signInWithCredential(auth, credential);
            console.log("Signed in:", result.user.email);
            onClose();
        } catch (err: any) {
            console.error("Google sign-in failed:", err);
            setError(`Sign-in failed: ${err.message || err}`);
        } finally {
            setIsLoading(false);
        }
    };

    // Email-specific sign-in — routes straight to that account's SSO/2FA
    const handleEmailSubmit = async () => {
        if (isLoading || !email) return;
        setIsLoading(true);
        setError(null);

        try {
            const redirectUri = chrome.identity.getRedirectURL();
            const authUrl =
                `https://accounts.google.com/o/oauth2/auth` +
                `?client_id=${CLIENT_ID}` +
                `&response_type=token` +
                `&redirect_uri=${encodeURIComponent(redirectUri)}` +
                `&scope=${encodeURIComponent("openid email profile")}` +
                `&login_hint=${encodeURIComponent(email)}`; // <-- pre-fills/routes to this account

            const responseUrl = await new Promise<string>((resolve, reject) => {
                chrome.identity.launchWebAuthFlow(
                    { url: authUrl, interactive: true },
                    (responseUrl) => {
                        if (chrome.runtime.lastError || !responseUrl) {
                            reject(new Error(chrome.runtime.lastError?.message || "Auth flow failed"));
                        } else {
                            resolve(responseUrl);
                        }
                    }
                );
            });

            // Extract access_token from the redirect URL fragment
            const params = new URLSearchParams(responseUrl.split("#")[1]);
            const token = params.get("access_token");
            if (!token) throw new Error("No access token returned");

            const credential = GoogleAuthProvider.credential(null, token);
            const result = await signInWithCredential(auth, credential);
            console.log("Signed in:", result.user.email);
            onClose();
        } catch (err: any) {
            console.error("Email sign-in failed:", err);
            setError(`Sign-in failed: ${err.message || err}`);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div
            className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
            onClick={onClose}
        >
            <div
                className="bg-[#eefbf1] border border-gray-800 rounded-md p-10 max-w-md w-full mx-4 flex flex-col items-center gap-6"
                onClick={(e) => e.stopPropagation()}
            >
                <h2 className="text-3xl font-serif text-[#2e1a3e]">
                    Log in or create an account
                </h2>

                <div className="w-full">
                    <label className="block font-serif text-lg mb-2">Email Address:</label>
                    <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        className="w-full rounded-full bg-[#1f4e8c] text-white px-5 py-3 outline-none placeholder-white/70"
                    />
                </div>

                <button
                    onClick={handleEmailSubmit}
                    disabled={isLoading || !email}
                    className="w-full rounded-full bg-[#1f4e8c] text-white px-5 py-2 font-serif text-lg hover:bg-[#173d6b] disabled:opacity-50"
                >
                    {isLoading ? "Signing in..." : "Submit"}
                </button>

                <div className="w-full flex items-center gap-4">
                    <div className="flex-1 border-t border-gray-700" />
                    <span className="font-serif text-lg">Or</span>
                    <div className="flex-1 border-t border-gray-700" />
                </div>

                <button
                    onClick={handleGoogle}
                    disabled={isLoading}
                    className="w-full border border-gray-800 bg-white rounded-md px-5 py-3 flex items-center justify-center gap-3 font-serif text-2xl hover:bg-gray-50 disabled:opacity-50"
                >
                    <span className="w-8 h-8 rounded-full bg-gray-300 inline-block" />
                    {isLoading ? "Signing in..." : "Sign in with Google"}
                </button>

                {error && <p className="text-red-500 text-sm">{error}</p>}
            </div>
        </div>
    );
}