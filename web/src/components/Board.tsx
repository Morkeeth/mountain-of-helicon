import { useCallback, useEffect, useState } from 'react';

/* THE DOORWAY — every repo an agent walks through, the live token cost each one
   loads, and (per repo) every loaded line with an executed-probe verdict:
   UPHELD / CONTRADICTED / UNVERIFIABLE. Lines demote to cold with one click:
   kept forever, loaded never. The counter falls as you work.
   Reads /api/doorway/board and /api/doorway/repo; writes /api/doorway/cold|warm. */

type Repo = { name: string; path: string; loaded_tokens: number; cold_tokens: number; doc_count: number };
type BoardData = { root: string; exists: boolean; repos: Repo[]; repo_count: number; total_loaded_tokens: number };
type Line = { ref: string; line: number | null; tokens: number; cold: boolean; text: string; verdict: string; kind: string | null; why: string; probe: string | null; output: string | null };
type Doc = { file: string; tokens: number; loaded_tokens: number; cold: boolean; via_import: string | null; lines: Line[] };
type Detail = { repo: string; path: string; docs: Doc[]; loaded_tokens: number; verdict_counts: Record<string, number>; contradicted: number; cold_tokens: number };

const SERIF = { fontFamily: '"Fraunces", serif' } as const;
const NUM = { fontFamily: '"Fraunces", serif', fontVariantNumeric: 'tabular-nums' } as const;
const MONO = 'var(--helicon-mono, ui-monospace, monospace)';
const fmt = (n: number) => n.toLocaleString();

const VERDICT_COLOR: Record<string, string> = {
  CONTRADICTED: 'var(--helicon-critical, #a94a3d)',
  UPHELD: 'var(--helicon-good, #4a7c59)',
  UNVERIFIABLE: 'var(--helicon-stale, #b07d2b)',
};

export default function Board() {
  const [selected, setSelected] = useState<string | null>(null);
  if (selected) return <RepoDetail repo={selected} onBack={() => setSelected(null)} />;
  return <BoardList onOpenRepo={setSelected} />;
}

function BoardList({ onOpenRepo }: { onOpenRepo: (name: string) => void }) {
  const [d, setD] = useState<BoardData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch('/api/doorway/board').then(r => r.json())
      .then(x => { if (alive) setD(x); }).catch(e => { if (alive) setErr(String(e)); });
    return () => { alive = false; };
  }, []);

  if (err) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>board unavailable — {err}</div>;
  if (!d) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>reading the doorway…</div>;
  if (!d.exists) return (
    <div style={{ maxWidth: 680, margin: '0 auto', padding: '64px 24px' }}>
      <div style={{ ...SERIF, fontSize: 22, color: 'var(--text-primary)' }}>No repo root at {d.root}</div>
      <p style={{ marginTop: 12, fontSize: 14, color: 'var(--text-muted)', lineHeight: 1.6 }}>
        Point the board with <code>HELICON_CODE_ROOT</code> or the <code>code_root</code> config key.
      </p>
    </div>
  );

  const max = Math.max(1, ...d.repos.map(r => r.loaded_tokens));
  return (
    <div className="max-w-[820px] mx-auto py-7 sm:py-14">
      <div className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-4">
        <span data-testid="board-total" className="text-[48px] sm:text-[76px]" style={{ ...NUM, lineHeight: 1, fontWeight: 300, color: 'var(--text-primary)' }}>{fmt(d.total_loaded_tokens)}</span>
        <span className="text-[16px] sm:text-[20px] leading-snug" style={{ ...SERIF, color: 'var(--text-muted)' }}>tokens loaded into an agent, across {d.repo_count} repo{d.repo_count === 1 ? '' : 's'}</span>
      </div>
      <div className="mt-2 text-[11px] sm:text-[12.5px] break-all" style={{ color: 'var(--text-muted)', fontFamily: MONO }}>{d.root}</div>
      <div style={{ marginTop: 36 }}>
        {d.repos.map(r => (
          <button key={r.path} onClick={() => onOpenRepo(r.name)} style={{ display: 'block', width: '100%', textAlign: 'left', padding: '13px 0', borderTop: '1px solid var(--border, rgba(0,0,0,.08))', background: 'transparent', cursor: 'pointer' }}>
            <div className="grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,1fr)_auto_74px] items-baseline gap-x-3">
              <span style={{ ...SERIF, fontSize: 16, color: 'var(--text-primary)', flex: 1 }}>{r.name}</span>
              <span style={{ ...NUM, fontSize: 15, color: 'var(--text-primary)' }}>{fmt(r.loaded_tokens)}</span>
              <span className="col-span-2 sm:col-span-1 text-left sm:text-right" style={{ fontSize: 12, color: 'var(--text-muted)' }}>{r.doc_count} doc{r.doc_count === 1 ? '' : 's'}</span>
            </div>
            <div style={{ marginTop: 7, height: 4, background: 'var(--border, rgba(0,0,0,.06))', borderRadius: 4 }}>
              <div style={{ width: `${Math.round((r.loaded_tokens / max) * 100)}%`, height: 4, borderRadius: 4, background: 'var(--helicon-accent, #35526d)' }} />
            </div>
            {r.cold_tokens > 0 && <div style={{ marginTop: 4, fontSize: 11.5, color: 'var(--text-muted)' }}>{fmt(r.cold_tokens)} tokens kept cold (loaded: 0)</div>}
          </button>
        ))}
        {d.repos.length === 0 && <div style={{ padding: '24px 0', color: 'var(--text-muted)', fontSize: 14 }}>No repos with agent-rules found under this root.</div>}
      </div>
    </div>
  );
}

function RepoDetail({ repo, onBack }: { repo: string; onBack: () => void }) {
  const [d, setD] = useState<Detail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    fetch(`/api/doorway/repo?repo=${encodeURIComponent(repo)}`).then(r => r.json()).then(setD);
  }, [repo]);
  useEffect(() => { load(); }, [load]);

  const setCold = async (line: Line, cold: boolean) => {
    setBusy(line.ref);
    const url = cold ? '/api/doorway/cold' : '/api/doorway/warm';
    const body = cold
      ? { repo, ref: line.ref, tokens: line.tokens, reason: 'two-part test: rarely act here / recoverable' }
      : { repo, ref: line.ref };
    await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    await load();          // the counter falls (or rises) on the next read
    setBusy(null);
  };

  if (!d) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>opening {repo}…</div>;
  const c = d.verdict_counts || {};
  return (
    <div className="max-w-[900px] mx-auto py-5 sm:py-10">
      <button onClick={onBack} style={{ fontSize: 12.5, color: 'var(--helicon-accent, #35526d)', background: 'transparent' }}>← the doorway</button>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mt-3.5">
        <span style={{ ...SERIF, fontSize: 24, color: 'var(--text-primary)' }}>{d.repo}</span>
        <span data-testid="repo-loaded" style={{ ...NUM, fontSize: 30, fontWeight: 300, color: 'var(--text-primary)' }}>{fmt(d.loaded_tokens)}</span>
        <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>tokens loaded{d.cold_tokens ? ` · ${fmt(d.cold_tokens)} kept cold` : ''}</span>
      </div>
      <div style={{ marginTop: 6, fontSize: 12.5 }}>
        <span style={{ color: VERDICT_COLOR.CONTRADICTED }}>{c.CONTRADICTED || 0} contradicted</span>
        <span style={{ color: 'var(--text-muted)' }}> · {c.UNVERIFIABLE || 0} unverifiable · </span>
        <span style={{ color: VERDICT_COLOR.UPHELD }}>{c.UPHELD || 0} upheld</span>
      </div>

      {d.docs.map(doc => (
        <div key={doc.file} style={{ marginTop: 28 }}>
          <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
            <span className="break-all" style={{ fontFamily: MONO, fontSize: 13, color: 'var(--text-primary)' }}>{doc.file}</span>
            {doc.via_import && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>@imported by {doc.via_import}</span>}
            <span className="w-full sm:w-auto sm:ml-auto" style={{ fontSize: 11, color: 'var(--text-muted)' }}>{fmt(doc.loaded_tokens)} / {fmt(doc.tokens)} tok loaded{doc.cold ? ' · cold' : ''}</span>
          </div>
          <div style={{ marginTop: 8 }}>
            {doc.lines.map(ln => (
              <div key={ln.ref} style={{ padding: '9px 0', borderTop: '1px solid var(--border, rgba(0,0,0,.06))', opacity: ln.cold ? 0.5 : 1 }}>
                <div className="grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[104px_minmax(0,1fr)_auto] gap-x-2.5 gap-y-2 items-baseline">
                  <span style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '.06em', color: VERDICT_COLOR[ln.verdict] || 'var(--text-muted)' }}>{ln.verdict}</span>
                  <span className="col-span-2 sm:col-span-1 row-start-2 sm:row-start-auto break-words" style={{ fontSize: 13.5, color: 'var(--text-primary)', textDecoration: ln.cold ? 'line-through' : 'none' }}>{ln.text}</span>
                  <button disabled={busy === ln.ref} onClick={() => setCold(ln, !ln.cold)}
                    className="row-start-1 col-start-2 sm:col-start-3"
                    style={{ fontSize: 11, padding: '3px 9px', borderRadius: 6, border: '1px solid var(--helicon-line, rgba(0,0,0,.15))', background: 'var(--helicon-panel, #fff)', color: ln.cold ? 'var(--helicon-accent, #35526d)' : 'var(--text-muted)' }}>
                    {ln.cold ? 'warm' : 'demote to cold'}
                  </button>
                </div>
                {ln.verdict === 'CONTRADICTED' && (
                  <div className="sm:ml-[114px]" style={{ marginTop: 6, padding: '8px 10px', borderRadius: 6, background: 'var(--helicon-panel-2, rgba(169,74,61,.06))', border: '1px solid var(--helicon-line, rgba(0,0,0,.1))' }}>
                    <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{ln.why}</div>
                    {ln.probe && <div style={{ marginTop: 4, fontFamily: MONO, fontSize: 11.5, color: 'var(--text-primary)' }}>$ {ln.probe}</div>}
                    {ln.output && <pre style={{ marginTop: 2, fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'pre-wrap' }}>{ln.output}</pre>}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
