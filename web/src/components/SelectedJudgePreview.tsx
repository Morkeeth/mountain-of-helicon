import { useEffect, useRef, useState } from 'react';
import { SelectedJevComparison } from './SelectedJevComparison';
import { api } from '../api';
import type { Cube } from '../api';

type Result = {
  observed_at: string; verdict: string; limit: string;
  items: { id: string; title: string; content: string; source_ref: string; content_sha256: string; created_at: string; valid_from: string; source_status: string; review_status: string; merged_into: string | null }[];
  checks: { scope: string; rule: string | null; verdict: string; detail: string; limit: string }[];
};

export function SelectedJudgePreview({ itemId }: { itemId: string }) {
  const [open, setOpen] = useState(false);
  const [against, setAgainst] = useState('');
  const [choices, setChoices] = useState<Cube[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const sequence = useRef(0);
  useEffect(() => { sequence.current++; setOpen(false); setResult(null); setAgainst(''); setError(''); }, [itemId]);

  async function inspect(second: string) {
    const seq = ++sequence.current;
    setBusy(true); setResult(null); setError('');
    try {
      const query = new URLSearchParams({ item: itemId });
      if (second) query.set('against', second);
      const response = await fetch(`/api/judge-preview?${query}`, { headers: { 'X-Helicon-Local': '1' } });
      if (!response.ok) throw new Error('Selected memory could not be inspected. Nothing was changed.');
      const next = await response.json() as Result;
      if (seq === sequence.current) setResult(next);
    } catch (e) { if (seq === sequence.current) setError(e instanceof Error ? e.message : 'Inspection unavailable.'); }
    finally { if (seq === sequence.current) setBusy(false); }
  }
  async function begin() {
    setAgainst(''); setOpen(true); void inspect('');
    try { const data = await api.getCubes({ limit: 200 }); setChoices(data.cubes.filter(c => c.id !== itemId)); }
    catch { setChoices([]); }
  }
  if (!open) return <button className="text-sm underline mt-4 mb-4" onClick={begin}>Inspect local rules and sources</button>;
  return <section className="my-5 p-4 rounded-lg border text-sm" style={{ borderColor: 'var(--helicon-line)', background: 'var(--helicon-panel-2)' }} aria-label="Local rule inspection">
    <div className="flex justify-between gap-3"><strong>Local rule inspection</strong><button className="underline" onClick={() => { sequence.current++; setOpen(false); setResult(null); }}>Back to this review</button></div>
    <p className="mt-2">These local rules make no model calls or SQL changes. SQLite may use sidecar locks.</p>
    <label className="block mt-3">Compare with another saved item (optional)
      <select className="block w-full mt-1 border rounded p-2 bg-white text-black" value={against} disabled={busy}
        onChange={e => { setAgainst(e.target.value); void inspect(e.target.value); }}>
        <option value="">Only the selected item</option>
        {choices.map(c => <option key={c.id} value={c.id}>{c.title} · {c.id}</option>)}
      </select>
    </label>
    <p className="text-xs mt-1">Up to 200 saved items. Nothing is paired automatically.</p>
    {busy && <p role="status" className="mt-3">Reading selected stored bytes…</p>}
    {error && <p role="alert" className="mt-3">{error}</p>}
    {result && <div className="mt-3 space-y-3">
      <p><strong>{result.verdict === 'contradicted' ? 'A local rule found a contradiction' : 'Overall result: unknown'}</strong></p>
      {result.checks.map((c, i) => <div key={i}><strong>{c.rule || 'No applicable pair rule'} · {c.verdict}</strong><p>{c.detail}</p><p className="text-xs mt-1">{c.limit}</p></div>)}
      {result.items.map(item => <details key={item.id} className="break-words"><summary className="cursor-pointer">Stored source: {item.title}</summary>
        <p className="whitespace-pre-wrap mt-2">{item.content}</p><p className="mt-2">{item.source_ref}</p>
        <p className="text-xs break-all">Content SHA256: {item.content_sha256}</p>
        <p className="text-xs">Stored status: {item.review_status}{item.merged_into ? ` · superseded by ${item.merged_into}` : ""}</p>
        <p className="text-xs">Recorded: {item.created_at} · valid from: {item.valid_from}</p><p className="text-xs">{item.source_status}</p>
      </details>)}
      <p className="text-xs">Observed: {result.observed_at}</p><p className="text-xs">{result.limit}</p>
      <button className="underline" onClick={() => void inspect(against)}>Recheck these stored revisions</button>
    </div>}
    <SelectedJevComparison key={itemId} item={itemId} against={against} />
  </section>;
}
