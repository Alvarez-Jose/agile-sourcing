import { API_BASE_URL, getFreshIdToken, SessionError } from "./auth";

interface ItemFlag {
  item: string;
  relevant: boolean;
  reason: string;
}

interface RelevanceResponse {
  flags: ItemFlag[];
  relevant_count: number;
  irrelevant_count: number;
  elapsed_ms: number;
}

export async function checkRelevance(search: string, items: string[]): Promise<RelevanceResponse> {
  const token = await getFreshIdToken();
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/relevance`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ search, items }),
      signal: AbortSignal.timeout(120000),
    });
  } catch {
    throw new Error("Relevance server could not be reached.");
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new SessionError(
      typeof body?.detail === "string" ? body.detail : `Relevance check failed (HTTP ${response.status}).`,
      response.status,
    );
  }

  const result: RelevanceResponse = await response.json();

  // Console output (browser-side)
  console.group(`\ud83d\udd0d Relevance: "${search}" (${result.flags.length} items, ${result.elapsed_ms}ms)`);
  for (const f of result.flags) {
    const tag = f.relevant ? "\u2705 MATCH " : "\ud83d\udea9 FLAG  ";
    console.log(`  ${tag} ${f.item}  \u2014 ${f.reason}`);
  }
  console.log(`  ${result.relevant_count} relevant, ${result.irrelevant_count} flagged`);
  console.groupEnd();

  return result;
}