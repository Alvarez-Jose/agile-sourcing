import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { captureCart, requestCartGuide, CartSnapshot, CartGuide } from '../../services/cart';
import { citationUrl } from '../../services/agent';
import { SessionError } from '../../services/auth';

export default function CartPage() {
  const {userProfile, isApproved, isLoading, refreshSession} = useAuth();
  const [cart, setCart] = useState<CartSnapshot | null>(null);
  const [funding, setFunding] = useState('unknown');
  const [reviewed, setReviewed] = useState(false);
  const [single, setSingle] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CartGuide | null>(null);
  const [error, setError] = useState('');
  const key = `${userProfile?.uid}:${isApproved}:${userProfile?.clearance}`;
  const session = useRef({key, generation: 0});
  if (session.current.key !== key) session.current = {key, generation: session.current.generation + 1};
  useEffect(() => {setCart(null); setResult(null); setError(''); setFunding('unknown'); setReviewed(false); setSingle(false); setBusy(false);}, [key]);

  async function read() {
    const generation = session.current.generation;
    setBusy(true); setError(''); setResult(null); setCart(null); setReviewed(false); setSingle(false); setFunding('unknown');
    try {
      const snapshot = await captureCart();
      if (session.current.generation === generation) setCart(snapshot);
    } catch (e) {
      if (session.current.generation === generation) setError(e instanceof Error ? e.message : 'Could not read the cart.');
    } finally {if (session.current.generation === generation) setBusy(false);}
  }
  async function check(e: React.FormEvent) {
    e.preventDefault();
    if (!cart || !isApproved || busy) return;
    const generation = session.current.generation;
    setBusy(true); setError(''); setResult(null);
    try {
      const answer = await requestCartGuide(cart, funding, reviewed, single);
      if (session.current.generation === generation) setResult(answer);
    } catch (e) {
      if (session.current.generation !== generation) return;
      setError(e instanceof Error ? e.message : 'Could not check the cart.');
      if (e instanceof SessionError && (e.status === 401 || e.status === 403)) await refreshSession();
    } finally {if (session.current.generation === generation) setBusy(false);}
  }
  function amount(field: 'tax' | 'shipping' | 'handling', value: string) {
    if (!cart) return;
    setCart({...cart, [field]: value === '' ? null : value}); setResult(null); setReviewed(false);
  }
  return <div className="max-w-3xl mx-auto space-y-4 text-sm">
    <h1 className="text-xl font-bold text-slate-800">Cart paperwork helper</h1>
    <p>Read your CruzBuy cart, confirm the estimates, and check the reviewed SSPR form.</p>
    <p className="text-xs text-slate-500">Limited progress demo: BUS-43 + SSPR. This does not submit an order or check every possible form. Guidance uses source-backed rules, not a model-generated decision.</p>
    {!isApproved ? <p>Sign in and obtain account approval to use this helper. <Link className="underline" to="/chat.html">Go to sign-in</Link></p> : <>
      <p className="text-xs">Open the extension popup while the CruzBuy Simple Shopping Cart is active. Only item descriptions, suppliers, quantities, and amounts are read. Nothing is sent until you select Check paperwork.</p>
      <button disabled={busy || isLoading} onClick={read} className="bg-[#00539b] text-white rounded px-4 py-2 disabled:opacity-50">{busy ? 'Working…' : 'Use my cart'}</button>
      {cart && <form onSubmit={check} className="space-y-3 rounded-xl border bg-white p-4">
        <h2 className="font-semibold">Confirm your cart</h2>
        <ul>{cart.items.map((item, i) => <li key={i} className="border-b py-2"><strong>{item.description}</strong><br/>{item.supplier} · {item.quantity} × ${item.unit_price} = ${item.line_total}</li>)}</ul>
        <p>Subtotal: <strong>${cart.subtotal}</strong> · Displayed total: <strong>{cart.total === null ? 'Not available' : `$${cart.total}`}</strong> USD</p>
        <p className="text-xs text-amber-800">CruzBuy describes these charges as estimates. Blank means unknown, not zero. Enter 0 only if you have confirmed no charge.</p>
        {(['tax','shipping','handling'] as const).map(field => <label className="block" key={field}>Estimated {field} (USD)
          <input disabled={busy} className="block border rounded p-2 w-full" type="number" min="0" step="0.01" value={cart[field] ?? ''} onChange={e => amount(field,e.target.value)} placeholder="Unknown"/>
        </label>)}
        <label className="block">What funding will pay for this purchase?
          <select disabled={busy} className="block border rounded p-2 w-full" value={funding} onChange={e => {setFunding(e.target.value); setResult(null);}}>
            <option value="unknown">I don't know yet</option><option value="non_federal">Entirely non-federal</option>
            <option value="federal_contract">Federal contract</option><option value="federal_grant">Federal grant / cooperative agreement</option>
            <option value="mixed">Mixed funding — needs further review</option>
          </select>
        </label>
        <label className="flex gap-2"><input disabled={busy} type="checkbox" checked={single} onChange={e => {setSingle(e.target.checked); setResult(null);}}/>This is one standalone goods purchase, not services, a multi-year agreement, or part of related orders.</label>
        <label className="flex gap-2"><input disabled={busy} type="checkbox" checked={reviewed} onChange={e => {setReviewed(e.target.checked); setResult(null);}}/>I checked all items and amounts against the current cart. Send these purchase details to our backend for guidance.</label>
        <button className="bg-[#00539b] text-white rounded px-4 py-2 disabled:opacity-50" disabled={busy || !reviewed || isLoading}>Check paperwork</button>
      </form>}
      {result && <section className="rounded-xl border bg-blue-50 p-4 space-y-3" aria-live="polite">
        <h2 className="font-semibold">Assistant guidance</h2><p className="whitespace-pre-wrap">{result.answer}</p>
        {result.forms.map(form => <p key={form.name}><a className="underline text-blue-800" href={form.url} target="_blank" rel="noopener noreferrer">Open {form.name}</a></p>)}
        {result.sources.map(source => <details key={source.citation_id}><summary>[{source.citation_id}] {source.policy}, p. {source.page}</summary>
          <a href={citationUrl(source)} target="_blank" rel="noopener noreferrer" className="underline">View source</a>
          {source.evidence.map((entry,i) => <blockquote className="border-l-2 pl-2 mt-2" key={i}>{entry.quote}</blockquote>)}
        </details>)}
      </section>}
    </>}
    {error && <p role="alert" className="text-red-700">{error}</p>}
  </div>;
}
