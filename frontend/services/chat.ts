// frontend/services/chat.ts
// session-only purchase state; no cart or conversation data is stored on disk.
import type {CartSnapshot} from './cart';

export type Funding = 'unknown' | 'federal' | 'non_federal' | 'federal_grant' | 'federal_contract' | 'mixed';
export interface SupplierDetails {
  supplier: string; funding: Funding;
  funding_confirmed?: boolean;
  tax: string | null; shipping: string | null; handling: string | null;
}
export interface ChatContext {
  cart: CartSnapshot & {reviewed: boolean; funding: 'unknown'; single_purchase: boolean};
  suppliers: SupplierDetails[];
  independent_purchases: boolean;
  captured_at: string;
  pending_question: string | null;
  last_question: string | null;
  purchase_question?: string | null;
  sspr_answer_hash?: string | null;
  awaiting_supplier: string | null;
  awaiting_kind: string | null;
  awaiting_field: 'tax' | 'shipping' | 'handling' | null;
}
export interface FollowUp {
  kind: string; supplier: string | null;
  choices: Array<{label: string; value: string}>;
}
export interface ChatTurn {role: 'user' | 'assistant'; content: string}

export function attachCart(snapshot: CartSnapshot, previous?: ChatContext | null): ChatContext {
  const signature = (cart: CartSnapshot) => JSON.stringify({
    items: cart.items.map(({description, supplier, quantity, unit_price, line_total}) => ({description, supplier, quantity, unit_price, line_total})),
    currency: cart.currency, subtotal: cart.subtotal, tax: cart.tax,
    shipping: cart.shipping, handling: cart.handling, total: cart.total,
  });
  if (previous && signature(snapshot) === signature(previous.cart)) {
    return {...previous, cart: {...previous.cart, reviewed: true}, captured_at: new Date().toISOString()};
  }
  const suppliers = [...new Set(snapshot.items.map(item => item.supplier.toLowerCase()))]
    .map(key => snapshot.items.find(item => item.supplier.toLowerCase() === key)!.supplier);
  return {
    cart: {...snapshot, reviewed: true, funding: 'unknown', single_purchase: false},
    suppliers: suppliers.map(supplier => ({supplier, funding: 'unknown',
      tax: suppliers.length === 1 ? snapshot.tax : null,
      shipping: suppliers.length === 1 ? snapshot.shipping : null,
      handling: suppliers.length === 1 ? snapshot.handling : null})),
    independent_purchases: false, captured_at: new Date().toISOString(),
    pending_question: null, last_question: null, awaiting_supplier: null,
    awaiting_kind: null, awaiting_field: null,
  };
}

export function recentHistory(messages: Array<{sender: 'user' | 'bot'; text: string; detailText?: string}>): ChatTurn[] {
  return messages.slice(-8).map(message => ({role: message.sender === 'user' ? 'user' : 'assistant', content: (message.sender === 'bot' ? message.detailText ?? message.text : message.text).slice(0, 4000)}));
}
