import { useEffect, useState } from 'react';

/* INSPECT — render an agent's actual produced artifact in its native review
   form, not a description of it. Dependency-free and injection-safe: no
   dangerouslySetInnerHTML, no markdown lib. The visual center of review. */

const INK = 'var(--helicon-ink)';
const MUTED = 'var(--helicon-muted)';
const FAINT = 'var(--helicon-faint)';
const ACCENT = 'var(--helicon-accent)';
const SERIF = 'var(--helicon-serif)';
const MONO = 'var(--helicon-mono)';

export type ArtifactRef = { type: string; label: string; ref: string; note?: string; content_hash?: string };
type Loaded = { type: string; label?: string; text: string; why?: string };

export function ArtifactView({ repoPath, art }: { repoPath: string; art: ArtifactRef }) {
  const [data, setData] = useState<Loaded | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setData(null); setErr(null);
    const q = new URLSearchParams({ repo_path: repoPath, kind: art.type, ref: art.ref });
    if (art.content_hash) q.set('expected_hash', art.content_hash);
    fetch(`/api/cockpit/artifact?${q}`)
      .then(r => r.json())
      .then(d => { if (live) setData(d); })
      .catch(e => { if (live) setErr(String(e)); });
    return () => { live = false; };
  }, [repoPath, art.type, art.ref, art.content_hash]);

  if (err) return <Note>Could not load the artifact: {err}</Note>;
  if (!data) return <Note>Opening {art.label}…</Note>;
  if (data.type === 'blocked') return <Note>This artifact is not served ({data.why}).</Note>;
  if (!data.text?.trim()) return <Note>The artifact is empty.</Note>;

  if (data.type === 'markdown') return <MarkdownView text={data.text} />;
  if (data.type === 'diff') return <DiffView text={data.text} />;
  return <pre className="text-[11.5px] whitespace-pre-wrap leading-relaxed" style={{ color: MUTED, fontFamily: MONO }}>{data.text}</pre>;
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="text-[12.5px] py-4" style={{ color: FAINT }}>{children}</p>;
}

/* ---- minimal, safe Markdown --------------------------------------------- */
function inline(s: string, key: number) {
  // split on `code`, **bold**, [text](url) — render as React nodes, never HTML
  const parts: React.ReactNode[] = [];
  const rx = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g;
  let last = 0, m: RegExpExecArray | null, i = 0;
  while ((m = rx.exec(s))) {
    if (m.index > last) parts.push(s.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith('`')) parts.push(<code key={`${key}-${i}`} style={{ fontFamily: MONO, fontSize: '0.9em', background: 'var(--helicon-accent-dim)', padding: '1px 5px', borderRadius: 5, color: INK }}>{tok.slice(1, -1)}</code>);
    else if (tok.startsWith('**')) parts.push(<strong key={`${key}-${i}`} style={{ color: INK, fontWeight: 600 }}>{tok.slice(2, -2)}</strong>);
    else { const t = tok.slice(1, tok.indexOf(']')); parts.push(<span key={`${key}-${i}`} style={{ color: ACCENT, textDecoration: 'underline' }}>{t}</span>); }
    last = m.index + tok.length; i++;
  }
  if (last < s.length) parts.push(s.slice(last));
  return parts;
}

function MarkdownView({ text }: { text: string }) {
  const lines = text.split('\n');
  const out: React.ReactNode[] = [];
  let inFence = false, fence: string[] = [], list: string[] = [], k = 0;
  const flushList = () => {
    if (list.length) {
      const items = [...list]; const kk = k++;
      out.push(<ul key={`ul-${kk}`} className="my-2 pl-4 space-y-1" style={{ listStyle: 'disc' }}>
        {items.map((li, j) => <li key={j} className="text-[13.5px] leading-relaxed" style={{ color: INK }}>{inline(li, kk * 100 + j)}</li>)}
      </ul>);
      list = [];
    }
  };
  for (const raw of lines) {
    if (raw.trim().startsWith('```')) {
      if (inFence) { const code = [...fence]; out.push(<pre key={`code-${k++}`} className="my-2.5 p-3 rounded-lg overflow-x-auto text-[11.5px] leading-relaxed" style={{ background: 'var(--helicon-ink)', color: 'var(--helicon-on-dark)', fontFamily: MONO }}>{code.join('\n')}</pre>); fence = []; inFence = false; }
      else { flushList(); inFence = true; }
      continue;
    }
    if (inFence) { fence.push(raw); continue; }
    const line = raw.replace(/\s+$/, '');
    if (/^#{1,6}\s/.test(line)) {
      flushList();
      const level = line.match(/^#+/)![0].length;
      const t = line.replace(/^#+\s/, '');
      const size = level <= 1 ? 22 : level === 2 ? 17 : 14;
      out.push(<div key={`h-${k++}`} style={{ fontFamily: SERIF, color: INK, fontWeight: 300, fontSize: size, marginTop: level <= 2 ? 18 : 12, marginBottom: 6, lineHeight: 1.25 }}>{inline(t, k)}</div>);
    } else if (/^\s*[-*]\s/.test(line)) {
      list.push(line.replace(/^\s*[-*]\s/, ''));
    } else if (/^\s*>\s?/.test(line)) {
      flushList();
      out.push(<blockquote key={`q-${k++}`} className="my-2 pl-3 text-[13px] leading-relaxed" style={{ borderLeft: '2px solid var(--helicon-line-2)', color: MUTED }}>{inline(line.replace(/^\s*>\s?/, ''), k)}</blockquote>);
    } else if (!line.trim()) {
      flushList();
    } else {
      flushList();
      out.push(<p key={`p-${k++}`} className="my-1.5 text-[13.5px] leading-relaxed" style={{ color: INK }}>{inline(line, k)}</p>);
    }
  }
  flushList();
  return <div className="max-w-none">{out}</div>;
}

/* ---- unified diff (no green: + is calm improve-amber, − is judgment red) - */
function DiffView({ text }: { text: string }) {
  const lines = text.split('\n');
  return (
    <pre className="text-[11.5px] leading-[1.5] overflow-x-auto rounded-lg p-3" style={{ background: 'var(--helicon-panel-2)', fontFamily: MONO, border: '1px solid var(--helicon-line)' }}>
      {lines.map((l, i) => {
        let color = MUTED, bg = 'transparent', weight = 400;
        if (l.startsWith('+++') || l.startsWith('---')) { color = FAINT; }
        else if (l.startsWith('@@')) { color = ACCENT; weight = 600; }
        else if (l.startsWith('diff --git') || l.startsWith('index ')) { color = FAINT; }
        else if (l.startsWith('+')) { color = '#8a5a26'; bg = 'rgba(198,124,62,0.10)'; }
        else if (l.startsWith('-')) { color = 'var(--helicon-critical)'; bg = 'rgba(169,74,61,0.08)'; }
        return <div key={i} style={{ color, background: bg, fontWeight: weight, padding: '0 4px', whiteSpace: 'pre' }}>{l || ' '}</div>;
      })}
    </pre>
  );
}
