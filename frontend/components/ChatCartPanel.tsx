import React from 'react';
import type {ChatContext} from '../services/chat';

interface Props {
  context: ChatContext;
  disabled: boolean;
  onRefresh: () => void;
  onClear: () => void;
}

// Read-only context; all missing purchase information is collected in chat.
export function ChatCartPanel({context, disabled, onRefresh, onClear}: Props) {
  const {cart} = context;
  return <details className="mb-3 rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs">
    <summary className="cursor-pointer font-semibold text-slate-800">Cart context · {cart.items.length} item(s) · {context.suppliers.length} supplier(s)</summary>
    <p className="mt-1 text-slate-600">Read at {new Date(context.captured_at).toLocaleTimeString()}. Ask me to refresh the cart after changes in CruzBuy.</p>
    <ul className="my-2">{cart.items.map((item, i) => <li key={i}>{item.supplier}: {item.description} · {item.quantity} × ${item.unit_price} = ${item.line_total}</li>)}</ul>
    <p>Subtotal: ${cart.subtotal} · Displayed total: {cart.total === null ? 'Unknown' : `$${cart.total}`} USD</p>
    <div className="mt-2 flex gap-3"><button type="button" disabled={disabled} onClick={onRefresh} className="text-blue-800 underline">Refresh cart</button><button type="button" disabled={disabled} onClick={onClear} className="text-blue-800 underline">Remove cart</button></div>
  </details>;
}
