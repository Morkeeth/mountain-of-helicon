import { ComparisonHandoff } from './ComparisonHandoff';
import { useEffect, useRef, useState } from 'react';

type Preview = { acceptance: string; request: unknown; endpoint: string; privacy: string; limit: string; key_available: boolean };
type Recorded = { fixture: boolean; status: string; probability: number | null; observed_at: string; source_matches: boolean; model: string; reported_cost_usd: number | null; billing_status: string; limit: string; authenticity: string; request_sha256: string; checker_sha256: string };

export function SelectedJevComparison({ item, against }: { item: string; against: string }) {
  const storageKey = `helicon-comparison-path:${item}`;
  const [output, setOutput] = useState(() => localStorage.getItem(storageKey) || '');
  const [cap, setCap] = useState('0.01');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<Recorded | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const version = useRef(0);
  useEffect(() => { version.current++; setPreview(null); setResult(null); setError(''); setBusy(false); }, [item, against, cap, output]);
  useEffect(() => () => { version.current++; }, []);
  async function act(action: 'preview' | 'run' | 'read') {
    const seq = ++version.current;
    setBusy(true); setError('');
    if (action !== 'run') setResult(null);
    try {
      const response = await fetch(`/api/judge-compare/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Helicon-Local': '1' },
        body: JSON.stringify({ item, against, output, max_usd: Number(cap), acceptance: action === 'run' ? preview?.acceptance : undefined }) });
      if (!response.ok) throw new Error('Comparison refused. Recheck sources, privacy, key, cap and output path. No automatic retry. Existing results were not overwritten.');
      const data = await response.json();
      if (seq !== version.current) return;
      localStorage.setItem(storageKey, output); // only an explicitly chosen receipt path; no source text or pairing
      if (action === 'preview') setPreview(data); else { setResult(data); setPreview(null); }
    } catch (e) { if (seq === version.current) { setPreview(null); setResult(null); setError(e instanceof Error ? e.message : 'Comparison unavailable.'); } }
    finally { if (seq === version.current) setBusy(false); }
  }
  return <section className="border-t mt-5 pt-4 space-y-3" aria-label="Optional Jev comparison">
    <strong>Optional Jev comparison</strong>
    <p>Choose a second item above, then inspect the complete proposed request. This separate action sends both stored texts to OpenRouter. Human review decisions stay unchanged.</p>
    <label className="block">New local result file (absolute .json path)
      <input className="block w-full p-2 border rounded bg-white text-black" aria-label="Comparison result path" value={output} disabled={busy} onChange={e => setOutput(e.target.value)} placeholder="/your/private/folder/comparison.json" />
    </label>
    <label className="block">Reported-spend cap (USD)
      <input className="block p-2 border rounded bg-white text-black" aria-label="Comparison cap" value={cap} disabled={busy} onChange={e => setCap(e.target.value)} />
    </label>
    <p className="text-xs">One request maximum; its price may exceed this cap. Unknown billing stays unknown. No fallback, retry or memory changes. Only result metadata is saved; SQLite may use sidecar locks.</p>
    <div className="flex gap-4 flex-wrap">
      <button className="underline disabled:opacity-40" disabled={busy || !against || !output} onClick={() => void act('preview')}>Inspect exact Jev request</button>
      <button className="underline disabled:opacity-40" disabled={busy || !against || !output} onClick={() => void act('read')}>Load recorded comparison</button>
    </div>
    {!against && <p>Explicitly choose the second item first. No pair is selected for you.</p>}
    {busy && <p role="status">Processing selected comparison…</p>}
    {error && <p role="alert">{error}</p>}
    {preview && <div className="space-y-3">
      <p>{preview.privacy}</p><p className="break-all">Destination: {preview.endpoint}</p>
      <pre className="text-xs whitespace-pre-wrap break-words p-2 border rounded" aria-label="Exact Jev request">{JSON.stringify(preview.request, null, 2)}</pre>
      <p>{preview.limit}</p><p>Execution key: {preview.key_available ? 'available in server environment' : 'not configured; execution will refuse'}</p>
      <button className="border rounded p-2 disabled:opacity-40" disabled={busy} onClick={() => void act('run')}>Confirm and send this one comparison</button>
    </div>}
    {result && <div className="space-y-2" role="status">
      <strong>{result.fixture ? 'Labelled fake transport — acceptance only' : 'Recorded model observation'}</strong>
      <p>{result.status}</p><p>Current selected bytes: {result.source_matches ? 'match recorded sources' : 'do not match; support is unknown'}</p>
      <p>Estimated contradiction probability: {result.probability === null ? 'unknown' : result.probability}. This is not a human verdict or measured confidence in memory truth.</p>
      <p>Requested model: {result.model} · observed {result.observed_at}</p><p>Billing: {result.billing_status}{result.reported_cost_usd !== null ? ` · $${result.reported_cost_usd}` : ''}</p>
      <details><summary>Recorded provenance</summary><p className="break-all">Request SHA256: {result.request_sha256}</p><p className="break-all">Checker SHA256: {result.checker_sha256}</p></details>
      <p className="text-xs">{result.authenticity} {result.limit}</p>
      <button className="underline" disabled={busy} onClick={() => void act('read')}>Recheck recorded support</button>
      {result.source_matches && <ComparisonHandoff item={item} against={against} receipt={output} />}
    </div>}
  </section>;
}
