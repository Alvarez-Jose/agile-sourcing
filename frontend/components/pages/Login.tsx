import { useState } from "react";
import { GoogleAuthProvider, signInWithCredential } from "firebase/auth";
import { auth } from "../../firebase/firebaseConfig";

export default function Login() {
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

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
            const idToken = await result.user.getIdToken();

            console.log("Signed in:", result.user.email);
            console.log("ID token:", idToken); // temporary, for testing — remove later

            // TODO: send idToken to your FastAPI backend for verification
            // await fetch("http://localhost:8000/auth/verify", {
            //   method: "POST",
            //   headers: { "Content-Type": "application/json" },
            //   body: JSON.stringify({ idToken }),
            // });

        } catch (err: any) {
            console.error("Google sign-in failed:", err);
            setError(`Sign-in failed: ${err.message || err}`);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="pt-36 w-full flex flex-col items-center gap-3">
            <button
                onClick={handleGoogle}
                disabled={isLoading}
                className="mx-auto border-4 bg-green-500 text-white rounded-full px-5 disabled:opacity-50"
            >
                {isLoading ? "Signing in..." : "Login"}
            </button>
            {error && <p className="text-red-500 text-sm">{error}</p>}
        </div>
    );
}