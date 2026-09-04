import { useEffect, useState } from 'react';

type Check = { id: string; question: string; status: string; interpretation: string; query: string; rows: Record<string, unknown>[] };
type Report = {
  project_review?: { status: string; reason?: string; projects: {id: string; state: string; evidence?: string; evidence_status?: string}[]; findings: {kind: string; title?: string; consequence?: string; action?: string; project?: string}[]; observed_at: string };
  memory_review?: { observed_at: string; checks: Check[] };
};

export default function SetupView() {
  const [report, setReport] = useState<Report>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  async function refresh() {
    setLoading(true);
    try {
      const response = await fetch('/api/setup?fresh=1');
      if (!response.ok) throw new Error(`Review unavailable (${response.status})`);
      setReport(await response.json()); setError('');
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }
  useEffect(() => { void refresh(); }, []);
  const projects = report?.project_review;
  const backed = projects?.projects.filter(p => ['event', 'ruling'].includes(p.evidence_status ?? '')) ?? [];
  const checks = report?.memory_review?.checks ?? [];
  const embeddings = checks.find(c => c.id === 'embeddings')?.rows[0];
  const index = checks.find(c => c.id === 'transcript-index');
  return <main className="max-w-2xl mx-auto pb-12" style={{color: 'var(--helicon-ink)'}}>
    <div className="flex justify-between items-center mb-8">
      <h1 className="text-[28px]" style={{fontFamily: 'var(--helicon-serif)'}}>Your setup</h1>
      <button className="text-sm" disabled={loading} onClick={() => void refresh()}>{loading ? 'Checking…' : 'Check now'}</button>
    </div>
    {error && <p role="alert" className="mb-5">{error}. Any earlier reading below is not current.</p>}
    {!report ? <p>Reading the local sources…</p> : <>
      <section className="mb-7">
        <h2 className="text-lg mb-2">What needs attention</h2>
        {!projects || projects.status === 'unmeasured' ? <p className="text-sm">Project checks are unavailable. {projects?.reason}</p> : projects.findings.length ? projects.findings.slice(0, 3).map((finding, i) => <div key={i} className="my-4">
          <p className="text-sm font-medium">{finding.title ?? 'Project records disagree'}{finding.project ? `: ${finding.project}` : ''}</p>
          <p className="text-sm mt-1">{finding.consequence}</p>
          <p className="text-sm mt-1" style={{color: 'var(--helicon-muted)'}}>{finding.action}</p>
        </div>) : <p className="text-sm">No conflicts found in the project checks run. This does not verify every source or prove memory quality.</p>}
      </section>
      <section className="mb-7">
        <h2 className="text-lg mb-2">Memory is stored. Its usefulness is not proven.</h2>
        <p className="text-sm">{index?.status === 'measured' ? 'Conversation history is available.' : 'The conversation index could not be checked.'} {embeddings && Number(embeddings.with_embeddings) < Number(embeddings.live_memories) ? 'Some memories lack search vectors.' : ''} We have no reliable test showing that this memory improves completed work.</p>
      </section>
      <section className="mb-8">
        <h2 className="text-lg mb-2">What matters next</h2>
        <p className="text-sm">Keep old project instructions out of ZUP. Check retrieval on real questions before adding more memory or treating its counts as progress.</p>
      </section>
      <details className="text-sm" style={{borderTop: '1px solid var(--helicon-line)', paddingTop: 16}}>
        <summary className="cursor-pointer">Evidence and technical details</summary>
        <p className="my-4" style={{color:'var(--helicon-muted)'}}>Sources: ZUP's local project events and board; Helicon's memory store; Transcripto's conversation index. Checked {projects?.observed_at ?? report.memory_review?.observed_at ?? 'at an unknown time'}.</p>
        {backed.map(p => <p key={p.id} className="my-3">{p.id}: {p.state}. {p.evidence}</p>)}
        {projects?.findings.map((f, i) => <pre className="whitespace-pre-wrap break-words" key={i}>{JSON.stringify(f, null, 2)}</pre>)}
        {checks.map(c => <details key={c.id} className="py-3">
          <summary>{c.question}</summary>
          <p className="my-2">{c.status}: {c.interpretation}</p>
          <pre className="text-xs whitespace-pre-wrap break-words">{JSON.stringify(c.rows, null, 2)}</pre>
          <p className="text-xs mt-2 break-words">{c.query}</p>
        </details>)}
      </details>
    </>}
  </main>;
}
