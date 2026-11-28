// frontend/services/chatCache.ts
// browser-session memory survives popup closure, but never establishes identity.
import {browser} from 'wxt/browser';
import type {AskResponse, FormLink} from './agent';
import type {ChatContext, FollowUp} from './chat';

export interface ChatMessage {sender: 'user' | 'bot'; text: string; sources?: AskResponse['sources']; detailText?: string; formLinks?: FormLink[]}
export interface ChatDraft {
  messages: ChatMessage[];
  input: string;
  context: ChatContext | null;
  followUp: FollowUp | null;
  interrupted: boolean;
}
const KEY = 'agile_chat_session_v1';
let revision = 0;
let writes: Promise<void> = Promise.resolve();

function enqueue(operation: () => Promise<void>): Promise<void> {
  const next = writes.catch(() => {}).then(operation);
  writes = next;
  return next;
}

export async function loadChatDraft(owner: string): Promise<ChatDraft | null> {
  await writes.catch(() => {});
  const value = (await browser.storage.session.get(KEY))[KEY] as
    {owner?: unknown; version?: unknown; draft?: unknown} | undefined;
  if (!value || value.owner !== owner || value.version !== 1) return null;
  const draft = value.draft as ChatDraft;
  // Cache failures must not prevent ordinary chat. The API revalidates the full
  // purchase context before using any of these client-owned facts.
  if (!draft || !Array.isArray(draft.messages) || typeof draft.input !== 'string' ||
      typeof draft.interrupted !== 'boolean') return null;
  for (const message of draft.messages) {
    if (!message || !['user', 'bot'].includes(message.sender) || typeof message.text !== 'string') return null;
    if (message.detailText !== undefined && typeof message.detailText !== 'string') return null;
    if (message.formLinks !== undefined && (!Array.isArray(message.formLinks) || !message.formLinks.every(link =>
      link && typeof link.title === 'string' && typeof link.url === 'string' && Array.isArray(link.aliases)))) return null;
    if (message.sources !== undefined) {
      if (!Array.isArray(message.sources)) return null;
      for (const source of message.sources) {
        if (!source || typeof source.policy !== 'string') return null;
        if (source.evidence !== undefined && (!Array.isArray(source.evidence) ||
            !source.evidence.every(e => e && typeof e.quote === 'string'))) return null;
      }
    }
  }
  if (draft.context && (!draft.context.cart || !Array.isArray(draft.context.cart.items) || !Array.isArray(draft.context.suppliers))) return null;
  if (draft.followUp && (!Array.isArray(draft.followUp.choices) || !draft.followUp.choices.every(choice =>
    choice && typeof choice.label === 'string' && typeof choice.value === 'string'))) return null;
  if (draft.context) {
    // Reopening restores information, never a claim that the live cart is current.
    draft.context.cart.reviewed = false;
    draft.context.pending_question ??= draft.context.last_question;
  }
  return draft;
}

export function saveChatDraft(owner: string, draft: ChatDraft): Promise<void> {
  const current = revision;
  // Freeze before queueing; later edits must not change an earlier checkpoint.
  const value = JSON.parse(JSON.stringify({version: 1, owner, draft}));
  return enqueue(async () => {
    if (revision === current) await browser.storage.session.set({[KEY]: value});
  });
}

export function clearChatDraft(): Promise<void> {
  revision++;
  return enqueue(() => browser.storage.session.remove(KEY));
}
