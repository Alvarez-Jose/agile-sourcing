import { useState } from "react";
import { useAuth } from "../../context/AuthContext";

type LoginProps = {
    isOpen: boolean;
    onClose: () => void;
};

export default function Login({ isOpen, onClose }: LoginProps) {
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const { loginWithGoogle } = useAuth();

    if (!isOpen) return null;

    const handleGoogle = async () => {
        if (submitting) return;
        setSubmitting(true);
        setError(null);

        try {
            await loginWithGoogle();
            onClose();
        } catch (err: any) {
            console.error("Google sign-in failed:", err);
            setError(`Sign-in failed: ${err.message || err}`);
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div
            className="fixed inset-0 bg-black/50 backdrop-blur-xs flex items-center justify-center z-50 p-4 transition-all"
            onClick={onClose}
        >
            <div
                className="bg-[#eefbf1] border border-gray-800 rounded-xl p-8 max-w-md w-full mx-auto flex flex-col items-center gap-6 shadow-2xl relative"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Close Button */}
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 text-gray-500 hover:text-gray-800 p-1 rounded-full hover:bg-gray-200/60 transition-colors"
                    aria-label="Close modal"
                >
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>

                <h2 className="text-2xl sm:text-3xl font-serif text-[#2e1a3e] text-center">
                    Sign in to CruzBuy
                </h2>

                <button
                    onClick={handleGoogle}
                    disabled={submitting}
                    className="w-full border border-gray-800 bg-white rounded-lg px-5 py-3 flex items-center justify-center gap-3 font-serif text-lg sm:text-xl hover:bg-gray-50 disabled:opacity-50 transition-all cursor-pointer shadow-xs active:scale-[0.99]"
                >
                    <svg className="w-5 h-5" viewBox="0 0 24 24">
                        <path
                            fill="#4285F4"
                            d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                        />
                        <path
                            fill="#34A853"
                            d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                        />
                        <path
                            fill="#FBBC05"
                            d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                        />
                        <path
                            fill="#EA4335"
                            d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                        />
                    </svg>
                    <span>{submitting ? "Signing in..." : "Sign in with Google"}</span>
                </button>

                {error && (
                    <div className="w-full p-3 bg-red-100 border border-red-300 text-red-700 text-sm rounded-lg text-center">
                        {error}
                    </div>
                )}
            </div>
        </div>
    );
}
