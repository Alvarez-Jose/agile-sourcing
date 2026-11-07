import { browser } from 'wxt/browser';
import { API_BASE_URL, getFreshIdToken, SessionError } from './auth';
import type { AskResponse } from './agent';

export interface CartSnapshot {
  items: Array<{description: string; supplier: string; quantity: string; unit_price: string; line_total: string}>;
  currency: 'USD'; subtotal: string; tax: string | null; shipping: string | null;
  handling: string | null; total: string | null;
}
export interface CartGuide {
  answer: string; status: 'needs_details' | 'checked'; sources: AskResponse['sources'];
  forms: Array<{name: string; url: string}>; questions: string[]; scope: string;
}

// This function is injected only on a user click. Keep every helper inside it:
// Chrome serializes the function without its surrounding module/imports.
export function readCruzBuyCart(): CartSnapshot {
  if (location.hostname !== 'solutions.sciquest.com' ||
      !/^\/apps\/Router\/SimpleCart\/?$/i.test(location.pathname)) {
    throw new Error('Open the CruzBuy Simple Shopping Cart, then click Use my cart.');
  }
  const text = (node: Element | null) => node?.textContent?.replace(/\s+/g, ' ').trim() || '';
  const money = (value: string): string => {
    const cleaned = value.replace(/\bUSD\b|\$|,/g, '').trim();
    if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) throw new Error('A cart amount could not be read safely.');
    return Number(cleaned).toFixed(2);
  };
  const rows = Array.from(document.querySelectorAll('.document__cell__item[id^="LineItemSixPack"]'));
  if (!rows.length || rows.length > 100) throw new Error('No supported cart item rows found. Refresh the cart; this layout may need an updated reader.');
  const items = rows.map(row => {
    const description = text(row.querySelector('.ProductDescription'));
    const supplier = text(row.closest('.card--cart')?.querySelector('.cart__cell__supplier__name a') || null);
    const quantity = row.querySelector<HTMLInputElement>('input[name^="Req_ProductHdrQuantity:"]')?.value || '';
    const unit_price = money(text(row.querySelector('[id^="UnitPriceValueBlock:"]')));
    const line_total = money(text(row.querySelector('[id^="LineExtendedPriceValueBlock:"]')));
    const currency = row.querySelector<HTMLInputElement>('input[name^="LinePriceValue_Currency:"]')?.value;
    if (currency !== 'USD') throw new Error('This demo supports USD carts only.');
    if (!description || !supplier || !/^\d+(\.\d+)?$/.test(quantity) || Number(quantity) <= 0)
      throw new Error('An item description, supplier, or quantity could not be read.');
    return {description, supplier, quantity, unit_price, line_total};
  });
  const summary = document.getElementById('MaterialCheckout_TotalSection_Collapsible');
  if (!summary) throw new Error('Expand the cart total section and try again.');
  const subtotal = money(text(summary.querySelector('.card--total__value')));
  const totalNode = summary.querySelector('.card--total__total--bottom');
  const amounts: Record<string, string> = {};
  for (const row of Array.from(summary.querySelectorAll('tr'))) {
    const cells = row.querySelectorAll('td');
    if (cells.length === 2 && text(cells[0])) amounts[text(cells[0]).toLowerCase()] = money(text(cells[1]));
  }
  const taxValues = Object.entries(amounts).filter(([key]) => /^tax\d*$/.test(key));
  const tax = taxValues.length ? (taxValues.reduce((sum, [,v]) => sum + Math.round(Number(v) * 100), 0) / 100).toFixed(2) : null;
  // Absence of a shipping/handling row is unknown, never an implicit zero.
  const shipping = amounts['shipping'] ?? null;
  const handling = amounts['handling'] ?? null;
  return {items, currency: 'USD', subtotal, tax, shipping, handling, total: totalNode ? money(text(totalNode)) : null};
}

export async function captureCart(): Promise<CartSnapshot> {
  const [tab] = await browser.tabs.query({active: true, currentWindow: true});
  if (!tab?.id) throw new Error('Open the extension popup while viewing the CruzBuy cart.');
  const results = await browser.scripting.executeScript({target: {tabId: tab.id}, func: readCruzBuyCart});
  if (!results[0]?.result) throw new Error('Could not read the cart. Reload the extension and try from its popup on the cart page.');
  return results[0].result as CartSnapshot;
}

export async function requestCartGuide(cart: CartSnapshot, funding: string, reviewed: boolean, single_purchase: boolean): Promise<CartGuide> {
  const token = await getFreshIdToken();
  const response = await fetch(`${API_BASE_URL}/api/cart/guide`, {
    method: 'POST', headers: {'Content-Type': 'application/json', Authorization: `Bearer ${token}`},
    body: JSON.stringify({...cart, funding, reviewed, single_purchase}), signal: AbortSignal.timeout(30000),
  });
  const body = await response.json();
  if (!response.ok) throw new SessionError(typeof body.detail === 'string' ? body.detail : 'Cart amounts need review. Check that the whole cart and all charges were captured.', response.status);
  return body;
}
