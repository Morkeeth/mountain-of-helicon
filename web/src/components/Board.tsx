import { useEffect, useState } from 'react';

/* THE DOORWAY — every repo an agent walks through, and the live token cost each
   one loads into that agent (CLAUDE.md, its @imports, the other agent-rules
   files). One hero number: total tokens loaded across all repos. It falls as
   lines are demoted to cold. Reads /api/doorway/board. */

type Repo = { name: string; path: string; loaded_tokens: number; cold_tokens: number; doc_count: number };
type BoardData = { root: string; exists: boolean; repos: Repo[]; repo_count: number; total_loaded_tokens: number };

const SERIF = { fontFamily: '"Fraunces", serif' } as const;
const NUM = { fontFamily: '"Fraunces", serif', fontVariantNumeric: 'tabular-nums' } as const;

const fmt = (n: number) => n.toLocaleString();

export default function Board({ onOpenRepo }: { onOpenRepo?: (name: string) => void }) {
  const [d, setD] = useState<BoardData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch('/api/doorway/board')
      .then(r => r.json())
      .then(x => { if (alive) setD(x); })
      .catch(e => { if (alive) setErr(String(e)); });
    return () => { alive = false; };
  }, []);

  if (err) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>board unavailable — {err}</div>;
  if (!d) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>reading the doorway…</div>;

  if (!d.exists) {
    return (
      <div style={{ maxWidth: 680, margin: '0 auto', padding: '64px 24px' }}>
        <div style={{ ...SERIF, fontSize: 22, color: 'var(--text-primary)' }}>No repo root at {d.root}</div>
        <p style={{ marginTop: 12, fontSize: 14, color: 'var(--text-muted)', lineHeight: 1.6 }}>
          Point the board at your code tree with <code>HELICON_CODE_ROOT</code> or the <code>code_root</code> config key,
          then reload. The board maps every repo under it and the token cost each one loads into an agent.
        </p>
      </div>
    );
  }

  const max = Math.max(1, ...d.repos.map(r => r.loaded_tokens));

  return (
    <div style={{ maxWidth: 820, margin: '0 auto', padding: '56px 24px' }}>
      {/* the hero counter */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 16 }}>
        <span data-testid="board-total" style={{ ...NUM, fontSize: 76, lineHeight: 1, fontWeight: 300, color: 'var(--text-primary)' }}>
          {fmt(d.total_loaded_tokens)}
        </span>
        <span style={{ ...SERIF, fontSize: 20, color: 'var(--text-muted)' }}>
          tokens loaded into an agent, across {d.repo_count} repo{d.repo_count === 1 ? '' : 's'}
        </span>
      </div>
      <div style={{ marginTop: 6, fontSize: 12.5, color: 'var(--text-muted)', fontFamily: 'var(--helicon-mono, monospace)' }}>
        {d.root}
      </div>

      {/* the repos, heaviest first */}
      <div style={{ marginTop: 36 }}>
        {d.repos.map(r => (
          <button
            key={r.path}
            onClick={() => onOpenRepo?.(r.name)}
            className="w-full text-left"
            style={{ display: 'block', width: '100%', padding: '13px 0', borderTop: '1px solid var(--border, rgba(0,0,0,.08))', background: 'transparent', cursor: onOpenRepo ? 'pointer' : 'default' }}
          >
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
              <span style={{ ...SERIF, fontSize: 16, color: 'var(--text-primary)', flex: 1 }}>{r.name}</span>
              <span style={{ ...NUM, fontSize: 15, color: 'var(--text-primary)' }}>{fmt(r.loaded_tokens)}</span>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', width: 74, textAlign: 'right' }}>
                {r.doc_count} doc{r.doc_count === 1 ? '' : 's'}
              </span>
            </div>
            {/* proportion bar */}
            <div style={{ marginTop: 7, height: 4, background: 'var(--border, rgba(0,0,0,.06))', borderRadius: 4 }}>
              <div style={{ width: `${Math.round((r.loaded_tokens / max) * 100)}%`, height: 4, borderRadius: 4, background: 'var(--helicon-accent, #35526d)' }} />
            </div>
            {r.cold_tokens > 0 && (
              <div style={{ marginTop: 4, fontSize: 11.5, color: 'var(--text-muted)' }}>
                {fmt(r.cold_tokens)} tokens kept cold (loaded: 0)
              </div>
            )}
          </button>
        ))}
        {d.repos.length === 0 && (
          <div style={{ padding: '24px 0', color: 'var(--text-muted)', fontSize: 14 }}>
            No repos with agent-rules found under this root.
          </div>
        )}
      </div>
    </div>
  );
}
