import { useAuth } from "../context/AuthContext";

export function SessionNotice() {
  const { sessionError, isLoading, refreshSession } = useAuth();
  if (!sessionError) return null;
  return (
    <div role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800">
      <p>{sessionError}</p>
      <button onClick={() => refreshSession()} disabled={isLoading}
        className="mt-2 font-semibold underline disabled:opacity-50">
        {isLoading ? "Retrying…" : "Retry connection"}
      </button>
    </div>
  );
}
