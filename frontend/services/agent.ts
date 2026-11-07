import { API_BASE_URL, getFreshIdToken, SessionError } from "./auth";

export interface AskResponse {
  answer: string;
  sources: Array<{
    citation_id: number;
    policy: string;
    section: string;
    page: string;
    source_url: string | null;
    is_full_section?: boolean;
    evidence: Array<{ quote: string; start?: number; end?: number }>;
  }>;
}

export function citationUrl(source: AskResponse['sources'][number]): string | undefined {
  if (!source.source_url) return undefined;
  try {
    const url = new URL(source.source_url);
    if (url.protocol !== 'https:') return undefined;
    if (source.page && url.pathname.toLowerCase().endsWith('.pdf')) {
      url.hash = `page=${source.page.split('-')[0]}`;
    }
    return url.toString();
  } catch {
    return undefined;
  }
}

export async function askQuestion(question: string): Promise<AskResponse> {
  const token = await getFreshIdToken();
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ question }),
      signal: AbortSignal.timeout(360000),
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
