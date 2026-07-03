import { useEffect, useState } from 'react';
import { api } from '../api';
import type { LogEntry } from '../api';

/* LOG — receipts feed. Every action Helicon took and every call the human
   made, newest first, merged from audit_log / reviews / triage / reconcile.
   Shape from /api/log: {entries: [{ts, actor, action, detail, count?}]}. */

// actor chip palette: human=zinc, helicon=warm stone, qwen=terracotta-tinted
const ACTOR_CHIP: Record<string, { bg: string; color: string }> = {
  human: { bg: 'rgba(85,85,110,0.10)', color: '#55556e' },
  helicon: { bg: 'hsl(40 18% 92%)', color: '#6f665a' },
  qwen: { bg: 'rgba(194,94,58,0.10)', color: 'var(--helicon-accent)' },
};

// action -> short human verb shown as the muted tag (detail carries the full line)
function actionTag(action: string): string {
  if (action.startsWith('audit_flag_')) return `flagged ${action.slice('audit_flag_'.length)}`;
  if (action === 'audit_acted') return 'acted on finding';
  if (action === 'audit_dismissed') return 'dismissed finding';
  if (action.startsWith('audit_')) return action.slice('audit_'.length).replace(/_/g, ' ');
  if (action.startsWith('review_')) return action.slice('review_'.length);
  if (action.startsWith('triage_')) return `auto-${action.slice('triage_'.length)}`;
  if (action === 'reconcile_superseded') return 'reconciled';
  return action.replace(/_/g, ' ');
}

function relTime(ts: string): string {
  const t = new Date(ts).getTime();
  if (Number.isNaN(t)) return ts?.slice(0, 10) || '';
  const diff = Date.now() - t;
  if (diff < 60_000) return 'just now';
  const m = Math.floor(diff / 60_000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return ts.slice(0, 10);
}

export default function LogView() {
  const [entries, setEntries] = useState<LogEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.getLog(100)
      .then(r => alive && setEntries(r.entries))
      .catch(e => alive && setError(String(e)));
    return () => { alive = false; };
  }, []);

  if (error) {
    return <div className="py-16 text-center text-[13px]" style={{ color: 'var(--helicon-accent)' }}>Could not load the log: {error}</div>;
  }
  if (!entries) {
    return <div className="py-20 text-center text-zinc-500 text-sm">Loading receipts…</div>;
  }
  if (entries.length === 0) {
    return <div className="py-20 text-center text-zinc-500 text-sm">No receipts yet. Actions will land here as they happen.</div>;
  }

  return (
    <div className="border border-zinc-800/60 rounded-lg overflow-hidden divide-y divide-zinc-800/30 bg-white shadow-sm">
      {entries.map((e, i) => {
        const chip = ACTOR_CHIP[e.actor] || ACTOR_CHIP.helicon;
        return (
          <div key={`${e.ts}-${e.action}-${i}`} className="flex items-start gap-3 py-2.5 px-4">
            <span
              className="text-[10px] px-2 py-0.5 rounded-full font-medium tracking-wide shrink-0 mt-0.5 w-[58px] text-center"
              style={{ background: chip.bg, color: chip.color }}
            >
              {e.actor}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-[12px] text-zinc-300 leading-snug break-words">
                {e.detail}
                {typeof e.count === 'number' && e.count > 1 && (
                  <span className="text-zinc-600 tabular-nums"> ×{e.count}</span>
                )}
              </p>
              <p className="text-[10px] text-zinc-700 mt-0.5">{actionTag(e.action)}</p>
            </div>
            <span className="text-[10px] text-zinc-600 tabular-nums shrink-0 mt-1">{relTime(e.ts)}</span>
          </div>
        );
      })}
    </div>
  );
}
