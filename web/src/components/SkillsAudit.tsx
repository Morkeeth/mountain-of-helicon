import { useEffect, useState } from 'react';
import { api, type SkillsAudit as SkillsAuditData } from '../api';

/* Audits the local Agent-Skills library — the newest durable agent-memory
   surface. Nobody regression-tests skills; Helicon does. Real data, no fixture. */

function Stat({ value, label, warn }: { value: number; label: string; warn?: boolean }) {
  return (
    <div style={{ flex: 1 }}>
      <div
        style={{
          fontFamily: 'var(--helicon-serif)',
          fontSize: 28,
          fontWeight: 400,
          fontVariationSettings: "'opsz' 144",
          color: warn && value > 0 ? 'var(--helicon-accent)' : 'var(--helicon-ink)',
        }}
      >
        {value}
      </div>
      <div style={{ fontSize: 9.5, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--helicon-muted)' }}>
        {label}
      </div>
    </div>
  );
}

export default function SkillsAudit() {
  const [data, setData] = useState<SkillsAuditData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.getSkillsAudit().then((d) => alive && setData(d)).catch((e) => alive && setError(String(e)));
    return () => { alive = false; };
  }, []);

  return (
    <div
      className="rounded-2xl p-7"
      style={{ background: 'var(--helicon-bg)', color: 'var(--helicon-ink)', boxShadow: '0 20px 60px rgba(50,40,28,.14)' }}
    >
      <div className="flex items-baseline gap-3 mb-1">
        <b style={{ fontFamily: 'var(--helicon-serif)', fontWeight: 300, fontSize: 22, letterSpacing: '0.02em', textTransform: 'uppercase', fontVariationSettings: "'opsz' 144" }}>
          Skills
        </b>
        <em style={{ fontStyle: 'normal', fontSize: 9.5, letterSpacing: '0.36em', textTransform: 'uppercase', color: 'var(--helicon-accent)', opacity: 0.85 }}>
          library audit
        </em>
      </div>
      <div style={{ fontSize: 12.5, lineHeight: 1.6, color: '#6f665a', maxWidth: '46ch', margin: '10px 0 20px' }}>
        Skills (SKILL.md) are the newest agent-memory surface, and they rot like any memory: duplicated, colliding, or too thin to fire. Nobody audits a skills library. Helicon does.
      </div>

      {error && <div style={{ fontSize: 12, color: 'var(--helicon-accent)' }}>Could not load skills audit: {error}</div>}
      {!data && !error && <div style={{ fontSize: 12, color: 'var(--helicon-muted)' }}>Scanning your skills library…</div>}

      {data && (
        <>
          <div
            className="flex gap-4"
            style={{ background: 'var(--helicon-panel)', border: '1px solid var(--helicon-line)', borderRadius: 14, padding: '18px 22px', marginBottom: 18 }}
          >
            <Stat value={data.files} label="skill files" />
            <Stat value={data.unique} label="unique" />
            <Stat value={data.summary.duplicated} label="duplicated" warn />
            <Stat value={data.summary.collisions} label="collisions" warn />
            <Stat value={data.summary.thin} label="thin triggers" warn />
          </div>

          {data.thin.length > 0 && (
            <>
              <div style={{ fontSize: 9.5, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--helicon-muted)', margin: '4px 0 4px' }}>
                Thin triggers — too short to route reliably
              </div>
              {data.thin.slice(0, 8).map((t) => (
                <div key={t.name} className="flex items-center gap-3" style={{ fontSize: 13, padding: '9px 0', borderTop: '1px solid var(--helicon-line)', color: '#443e36' }}>
                  <span style={{ width: 7, height: 7, borderRadius: 1, flex: 'none', background: 'var(--helicon-stale)' }} />
                  <span style={{ fontWeight: 600 }}>{t.name}</span>
                  <span style={{ color: 'var(--helicon-muted)' }}>· {t.desc_len === 0 ? 'no description' : `${t.desc_len} chars`}</span>
                </div>
              ))}
            </>
          )}

          {data.collisions.length > 0 && (
            <>
              <div style={{ fontSize: 9.5, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--helicon-muted)', margin: '18px 0 4px' }}>
                Trigger collisions — skills that will fight to fire
              </div>
              {data.collisions.slice(0, 6).map((c) => (
                <div key={c.a + c.b} className="flex items-center gap-3" style={{ fontSize: 13, padding: '9px 0', borderTop: '1px solid var(--helicon-line)', color: '#443e36' }}>
                  <span style={{ width: 7, height: 7, borderRadius: 1, flex: 'none', background: 'var(--helicon-accent)' }} />
                  <span style={{ fontWeight: 600 }}>{c.a}</span>
                  <span style={{ color: 'var(--helicon-muted)' }}>⟷ {c.b} · {Math.round(c.overlap * 100)}% overlap</span>
                </div>
              ))}
            </>
          )}

          {data.duplicates.length > 0 && (
            <div style={{ fontSize: 11, color: 'var(--helicon-muted)', marginTop: 18 }}>
              {data.duplicates.length} skills installed more than once (e.g. {data.duplicates.slice(0, 3).map((d) => `${d.name} ×${d.count}`).join(', ')}).
            </div>
          )}
        </>
      )}
    </div>
  );
}
