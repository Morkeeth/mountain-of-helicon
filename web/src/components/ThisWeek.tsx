import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { ThisWeek as ThisWeekData, RotExam, MeasureSeries } from '../api';

/* THE WEEKLY KNOWLEDGE-PALACE READ. The one screen Mount Helicon opens to:
   "is my agentic-engineering setup any good THIS WEEK", in a single read, from
   Oscar's real transcripts, memory, and git.

   Composition, not one fat call: the rot exam (/api/rot, ~16s, already cached)
   is fetched in parallel with /api/thisweek so this page is never a 20s load,
   and each fetch has its own catch — one slow section never blanks the palace.

   Every number prints the source that produced it. A section that cannot be
   probed renders "not wired" with the reason, never a faked zero — the same bar
   the detectors it surfaces were built to hold. */

// ------------------------------------------------------------------- primitives
function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] uppercase tracking-[0.22em]" style={{ color: 'var(--helicon-muted)' }}>
      {children}
    </div>
  );
}

function Source({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-2 text-[10.5px] leading-relaxed" style={{ color: 'var(--helicon-faint)', fontFamily: 'var(--helicon-mono)' }}>
      ↳ {children}
    </div>
  );
}

function Section({ n, title, lede, children }: { n: string; title: string; lede?: string; children: React.ReactNode }) {
  return (
    <section
      className="rounded-2xl px-6 py-5 md:px-7 md:py-6"
      style={{ background: 'var(--helicon-panel)', border: '1px solid var(--helicon-line)' }}
    >
      <div className="flex items-baseline gap-3">
        <span className="text-[11px] tabular-nums" style={{ color: 'var(--helicon-faint)' }}>{n}</span>
        <h2 className="text-[17px] md:text-[19px]" style={{ fontFamily: 'var(--helicon-serif)', fontWeight: 300, fontVariationSettings: "'opsz' 144", color: 'var(--helicon-ink)' }}>
          {title}
        </h2>
      </div>
      {lede && <p className="mt-1.5 text-[12.5px] leading-relaxed" style={{ color: 'var(--helicon-muted)', maxWidth: '62ch' }}>{lede}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Stat({ value, label, tone }: { value: React.ReactNode; label: string; tone?: string }) {
  return (
    <div className="rounded-lg px-3.5 py-3" style={{ background: 'var(--helicon-panel-2)', border: '1px solid var(--helicon-line)' }}>
      <div className="text-[26px] leading-none tabular-nums" style={{ fontFamily: 'var(--helicon-serif)', fontWeight: 300, fontVariationSettings: "'opsz' 144", color: tone || 'var(--helicon-ink)' }}>
        {value}
      </div>
      <div className="mt-1.5 text-[10.5px] uppercase tracking-[0.12em]" style={{ color: 'var(--helicon-muted)' }}>{label}</div>
    </div>
  );
}

function NotWired({ items }: { items?: string[] }) {
  if (!items || !items.length) return null;
  return (
    <div className="mt-3 text-[11px] leading-relaxed" style={{ color: 'var(--helicon-faint)' }}>
      not wired: {items.join(' · ')}
    </div>
  );
}

function Bar({ items, total }: { items: { name: string; count: number }[]; total: number }) {
  const max = Math.max(1, ...items.map(i => i.count));
  return (
    <div className="flex flex-col gap-1.5">
      {items.map(i => (
        <div key={i.name} className="flex items-center gap-2">
          <div className="w-28 shrink-0 truncate text-[11.5px]" style={{ color: 'var(--helicon-ink)' }} title={i.name}>{i.name}</div>
          <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: 'var(--helicon-line)' }}>
            <div className="h-full rounded-full" style={{ width: `${(i.count / max) * 100}%`, background: 'var(--helicon-accent)' }} />
          </div>
          <div className="w-12 text-right text-[11px] tabular-nums" style={{ color: 'var(--helicon-muted)' }}>{i.count}</div>
        </div>
      ))}
      {total > items.reduce((a, b) => a + b.count, 0) && (
        <div className="text-[10.5px] mt-0.5" style={{ color: 'var(--helicon-faint)' }}>of {total.toLocaleString()} total</div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ the surface
export default function ThisWeek() {
  const [data, setData] = useState<ThisWeekData | null>(null);
  const [rot, setRot] = useState<RotExam | null>(null);
  const [measure, setMeasure] = useState<MeasureSeries | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string>('');
  const [recording, setRecording] = useState(false);
  const [recorded, setRecorded] = useState<string>('');

  const load = useCallback(async () => {
    setLoading(true);
    const [w, r, m] = await Promise.allSettled([api.getThisWeek(), api.getRot(), api.getMeasure()]);
    if (w.status === 'fulfilled') setData(w.value);
    else setErr(String(w.reason));
    if (r.status === 'fulfilled') setRot(r.value);
    if (m.status === 'fulfilled') setMeasure(m.value);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const record = async () => {
    setRecording(true);
    try {
      const res = await api.takeReading();
      setRecorded(res.week);
      setMeasure(await api.getMeasure());
    } catch (e) {
      setErr(String(e));
    } finally {
      setRecording(false);
    }
  };

  if (loading && !data) {
    return <div className="py-16 text-center text-[12px]" style={{ color: 'var(--helicon-muted)' }}>Reading this week…</div>;
  }
  if (!data) {
    return <div className="py-16 text-center text-[12px]" style={{ color: 'var(--helicon-accent)' }}>Could not read this week: {err}</div>;
  }

  const sh = data.setup_health;
  const ob = data.overboard;
  const ll = data.learning_ledger;
  const tx = data.transcript_review;
  const openDecisions = sh.identity_forks.count + sh.contradictions.count;

  return (
    <div className="flex flex-col gap-4">
      {/* Header + verdict */}
      <div className="rounded-2xl px-6 py-6 md:px-8 md:py-7" style={{ background: 'var(--helicon-panel)', border: '1px solid var(--helicon-line)' }}>
        <Eyebrow>This week · {data.week}</Eyebrow>
        <h1 className="mt-2 text-[22px] md:text-[27px] leading-tight" style={{ fontFamily: 'var(--helicon-serif)', fontWeight: 300, fontVariationSettings: "'opsz' 144", color: 'var(--helicon-ink)' }}>
          {data.verdict}
        </h1>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]" style={{ color: 'var(--helicon-muted)' }}>
          <span className="tabular-nums">{openDecisions} to rule</span>
          <span style={{ color: 'var(--helicon-faint)' }}>·</span>
          <span>read {data.cached ? 'from cache' : 'live'} {data.ran_at ? new Date(data.ran_at).toLocaleTimeString() : ''}</span>
          <span style={{ color: 'var(--helicon-faint)' }}>·</span>
          <button onClick={load} className="underline underline-offset-2 hover:opacity-70">refresh</button>
        </div>
      </div>

      {/* 1 · Setup health */}
      <Section n="1" title="Setup health" lede="Where your stack disagrees with itself, and what the rot exam found. These are the real things to rule this week.">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
          <Stat value={sh.identity_forks.count} label="Identity forks" tone={sh.identity_forks.count ? 'var(--helicon-stale)' : 'var(--helicon-good)'} />
          <Stat value={sh.contradictions.count} label="Contradictions" tone={sh.contradictions.count ? 'var(--helicon-stale)' : 'var(--helicon-good)'} />
          <Stat value={rot ? rot.rot_found : '—'} label="Rot found" tone={rot && rot.rot_found ? 'var(--helicon-accent)' : 'var(--helicon-good)'} />
          <Stat value={rot ? `${rot.tested}/${rot.classes}` : '—'} label="Exam classes tested" />
        </div>
        {sh.identity_forks.count > 0 && (
          <div className="mt-3 text-[12.5px]" style={{ color: 'var(--helicon-ink)' }}>
            Same name, forked definition: <span style={{ color: 'var(--helicon-stale)' }}>{sh.identity_forks.names.join(', ')}</span>
          </div>
        )}
        <div className="mt-2 text-[11.5px]" style={{ color: 'var(--helicon-muted)' }}>
          Plus {sh.log_fragments.count} read-only memory fragments — a log, not decisions (kept out of the ruling queue).
        </div>
        <Source>{sh.identity_forks.source}</Source>
        {rot && <Source>rot exam R1–R12 · /api/rot · ran {rot.ran_at ? new Date(rot.ran_at).toLocaleTimeString() : ''}{rot.cached ? ' (cached)' : ''}</Source>}
        {!rot && <div className="mt-2 text-[11px]" style={{ color: 'var(--helicon-faint)' }}>rot exam not available (fetch failed) — forks/contradictions above are still live from the db</div>}
      </Section>

      {/* 2 · Overboard */}
      <Section n="2" title="Overboard" lede="What got over-captured this week: repos opened and left, and branches piling up as addresses that look live and are not.">
        {ob.wired ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              <Stat value={ob.repos_touched ?? 0} label={`Repos touched / ${ob.window_days ?? 7}d`} />
              <Stat value={ob.one_day_repos?.length ?? 0} label="Opened & left (AP7)" tone={(ob.one_day_repos?.length ?? 0) ? 'var(--helicon-stale)' : undefined} />
              <Stat value={ob.merged_not_deleted ?? 0} label="Merged, not deleted" />
              <Stat value={ob.abandoned_branches ?? 0} label="Abandoned branches" tone={(ob.abandoned_branches ?? 0) ? 'var(--helicon-stale)' : undefined} />
            </div>
            {!!ob.one_day_repos?.length && (
              <div className="mt-3 text-[12px]" style={{ color: 'var(--helicon-muted)' }}>
                One-day repos: <span style={{ color: 'var(--helicon-ink)' }}>{ob.one_day_repos.slice(0, 12).join(', ')}</span>{ob.one_day_repos.length > 12 ? ` +${ob.one_day_repos.length - 12} more` : ''}
              </div>
            )}
            <div className="mt-2 text-[11px]" style={{ color: 'var(--helicon-faint)' }}>code root: {ob.code_root}</div>
            <Source>{ob.source}</Source>
            <NotWired items={ob.not_wired} />
          </>
        ) : (
          <div className="text-[12px]" style={{ color: 'var(--helicon-faint)' }}>not wired: {ob.reason}</div>
        )}
      </Section>

      {/* 3 · Learning ledger */}
      <Section n="3" title="Learning ledger" lede="The lessons distilled to memory this week. A week with zero captured learnings is a capture gap, not a quiet win.">
        {ll.wired ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
              <Stat value={ll.distilled_this_week ?? 0} label={`Distilled · ${ll.window ?? 'last 7 days'}`} tone={(ll.distilled_this_week ?? 0) ? 'var(--helicon-good)' : 'var(--helicon-stale)'} />
              <Stat value={ll.total_lessons ?? 0} label="Total lessons on file" />
            </div>
            {!!ll.files?.length && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {ll.files.slice(0, 16).map(f => (
                  <span key={f} className="text-[10.5px] px-2 py-0.5 rounded-md" style={{ background: 'var(--helicon-panel-2)', border: '1px solid var(--helicon-line)', color: 'var(--helicon-muted)', fontFamily: 'var(--helicon-mono)' }}>
                    {f.replace(/^feedback_/, '').replace(/\.md$/, '')}
                  </span>
                ))}
                {ll.files.length > 16 && <span className="text-[10.5px]" style={{ color: 'var(--helicon-faint)' }}>+{ll.files.length - 16} more</span>}
              </div>
            )}
            <Source>{ll.source}</Source>
            <NotWired items={ll.not_wired} />
          </>
        ) : (
          <div className="text-[12px]" style={{ color: 'var(--helicon-faint)' }}>not wired: no memory dir found</div>
        )}
      </Section>

      {/* 4 · Agentic-engineering review from transcripts */}
      <Section n="4" title="What you actually did" lede="An honest week-in-review computed from your local transcripts — turn counts, tools, and where things failed. Aggregate only; nothing raw leaves your machine.">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
          <Stat value={(tx.sessions ?? 0).toLocaleString()} label="Sessions" />
          <Stat value={(tx.human_prompts ?? 0).toLocaleString()} label="Your prompts" />
          <Stat value={(tx.tool_calls ?? 0).toLocaleString()} label="Tool calls" />
          <Stat value={tx.tool_success_pct != null ? `${tx.tool_success_pct}%` : '—'} label="Tool success" tone={tx.tool_success_pct != null && tx.tool_success_pct < 90 ? 'var(--helicon-stale)' : 'var(--helicon-good)'} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mt-5">
          <div>
            <Eyebrow>Most-used tools</Eyebrow>
            <div className="mt-3">{tx.top_tools?.length ? <Bar items={tx.top_tools.slice(0, 6)} total={tx.tool_calls ?? 0} /> : <span className="text-[11px]" style={{ color: 'var(--helicon-faint)' }}>none</span>}</div>
          </div>
          <div>
            <Eyebrow>Where it failed ({tx.tool_errors ?? 0} errors)</Eyebrow>
            <div className="mt-3">{tx.errors_by_tool?.length ? <Bar items={tx.errors_by_tool.slice(0, 6)} total={tx.tool_errors ?? 0} /> : <span className="text-[11px]" style={{ color: 'var(--helicon-good)' }}>no tool errors</span>}</div>
          </div>
        </div>

        {!!tx.repos_touched?.length && (
          <div className="mt-5">
            <Eyebrow>Where the work went</Eyebrow>
            <div className="mt-2 text-[12px]" style={{ color: 'var(--helicon-ink)' }}>
              {tx.repos_touched.slice(0, 8).map(r => `${r.name} (${r.turns.toLocaleString()})`).join(' · ')}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-5">
          <ReviewCol title="What you did" items={tx.did} tone="var(--helicon-ink)" />
          <ReviewCol title="What worked" items={tx.worked} tone="var(--helicon-good)" />
          <ReviewCol title="What to improve" items={tx.improve} tone="var(--helicon-stale)" empty="nothing recurring — clean week" />
        </div>
        <Source>{tx.source}</Source>
      </Section>

      {/* 5 · Recommended next improvements */}
      <Section n="5" title="Recommended next" lede="The honest verdict — the highest-leverage moves for the setup this week, each tied to the signal it came from.">
        <ol className="flex flex-col gap-2.5">
          {data.recommendations.map((r, i) => (
            <li key={i} className="flex gap-3">
              <span className="text-[12px] tabular-nums shrink-0 mt-0.5" style={{ color: 'var(--helicon-accent)' }}>{String(i + 1).padStart(2, '0')}</span>
              <div>
                <div className="text-[13px] leading-snug" style={{ color: 'var(--helicon-ink)' }}>{r.text}</div>
                <div className="text-[10.5px] mt-0.5" style={{ color: 'var(--helicon-faint)', fontFamily: 'var(--helicon-mono)' }}>↳ {r.basis}</div>
              </div>
            </li>
          ))}
        </ol>
      </Section>

      {/* Close the week (S5): the explicit record act. A page load never writes;
          recording is a verb with its own button, so a week glanced at four
          times is still one reading. */}
      <div className="rounded-2xl px-6 py-5 md:px-7" style={{ background: 'var(--helicon-panel)', border: '1px solid var(--helicon-line)' }}>
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <Eyebrow>Close the week</Eyebrow>
            <p className="mt-1.5 text-[12px] leading-relaxed" style={{ color: 'var(--helicon-muted)', maxWidth: '52ch' }}>
              {measure?.recorded
                ? 'Record this week\'s reading so the review becomes a series you can watch move.'
                : 'No readings recorded yet. Take the first one — a reading is a number; a measurement is a number with a previous value.'}
            </p>
          </div>
          <button
            onClick={record}
            disabled={recording}
            className="text-[12px] px-4 py-2 rounded-lg text-white transition-opacity hover:opacity-90 disabled:opacity-40 shrink-0"
            style={{ background: 'var(--helicon-accent)' }}
          >
            {recording ? 'recording…' : recorded ? `recorded ${recorded}` : 'Record this week\'s reading'}
          </button>
        </div>

        {measure && !!measure.metrics.length && (
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-2">
            {measure.metrics.map(m => (
              <div key={m.metric} className="flex items-baseline justify-between gap-3 px-3 py-2 rounded-lg" style={{ background: 'var(--helicon-panel-2)', border: '1px solid var(--helicon-line)' }}>
                <span className="text-[11.5px]" style={{ color: 'var(--helicon-muted)' }}>{m.label || m.metric}</span>
                <span className="text-[12px] tabular-nums" style={{ color: 'var(--helicon-ink)' }}>
                  {m.unmeasured ? <em style={{ color: 'var(--helicon-faint)' }}>unmeasured</em> : m.latest ?? '—'}
                  {!m.unmeasured && m.delta == null && m.latest != null && <span style={{ color: 'var(--helicon-faint)' }}> · first reading</span>}
                  {!m.unmeasured && m.delta != null && (
                    <span style={{ color: deltaGood(m) ? 'var(--helicon-good)' : 'var(--helicon-stale)' }}> {m.delta > 0 ? '+' : ''}{m.delta}</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}
        <Source>weekly series stored per ISO week · GET/POST /api/measure (helicon.measure)</Source>
      </div>
    </div>
  );
}

function ReviewCol({ title, items, tone, empty }: { title: string; items?: string[]; tone: string; empty?: string }) {
  return (
    <div className="rounded-lg px-4 py-3" style={{ background: 'var(--helicon-panel-2)', border: '1px solid var(--helicon-line)' }}>
      <div className="text-[10.5px] uppercase tracking-[0.14em]" style={{ color: 'var(--helicon-muted)' }}>{title}</div>
      <ul className="mt-2 flex flex-col gap-1.5">
        {items && items.length ? items.map((t, i) => (
          <li key={i} className="text-[12px] leading-snug" style={{ color: tone }}>{t}</li>
        )) : (
          <li className="text-[11.5px]" style={{ color: 'var(--helicon-faint)' }}>{empty || '—'}</li>
        )}
      </ul>
    </div>
  );
}

// A metric improves when it moves in its declared direction; null direction is
// context, not a score, so it reads neutral (stale tone withheld).
function deltaGood(m: { direction?: string | null; delta: number | null }): boolean {
  if (m.delta == null || !m.direction) return true;
  return m.direction === 'up' ? m.delta >= 0 : m.delta <= 0;
}
