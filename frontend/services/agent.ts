import { API_BASE_URL, getFreshIdToken, SessionError } from "./auth";

export interface AskResponse {
  answer: string;
  sources: Array<{ policy: string; page: string | number }>;
}

export async function askQuestion(question: string): Promise<AskResponse> {
  const token = await getFreshIdToken();
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ question }),
      signal: AbortSignal.timeout(180000),
    });
  } catch {
    throw new Error("The assistant server could not be reached or took too long to respond.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new SessionError(
      typeof body?.detail === "string" ? body.detail : "The assistant could not answer. Please retry.",
      response.status,
    );
  }
  return response.json();
}
