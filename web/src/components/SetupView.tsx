import { useEffect, useState } from 'react';

type Check = { id: string; question: string; status: string; interpretation: string; action: string; source?: string; query: string; rows: Record<string, unknown>[] };
type Finding = {kind: string; title?: string; consequence?: string; action?: string; project?: string; projects?: string[]; checks?: string[]};
type Stage = {id: string; title: string; state: string; summary: string; source: string; watermark?: string; limit: string; checks: string[]};
type Report = {
  project_review?: { status: string; reason?: string; projects: {id: string; state: string; source?: string; observed_at?: string; evidence?: string; evidence_status?: string}[]; findings: Finding[]; observed_at: string };
  memory_review?: { observed_at: string; checks: Check[]; stages?: Stage[]; findings?: Finding[]; relationship?: string };
};

function recordedTime(value: string) {
  if (!/(Z|[+-]\d\d:\d\d)$/.test(value)) return `${value} (time zone not recorded)`;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Invalid recorded date' : date.toLocaleString();
}

export default function SetupView() {
  const [report, setReport] = useState<Report>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  async function refresh() {
    setLoading(true);
    try {
      const response = await fetch('/api/setup/review');
      if (!response.ok) throw new Error(`Review unavailable (${response.status})`);
      setReport(await response.json()); setError('');
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }
  useEffect(() => { void refresh(); }, []);
  const projects = report?.project_review;
  const backed = projects?.projects.filter(p => ['event', 'ruling'].includes(p.evidence_status ?? '')) ?? [];
  const checks = report?.memory_review?.checks ?? [];
  const findings: Finding[] = [...(report?.memory_review?.findings ?? []), ...(projects?.findings ?? [])]
    .sort((a, b) => priority(a) - priority(b));
  function priority(f: Finding) {
    if (f.kind === 'source-unavailable') return 0;
    if (['projection-disagrees-with-event', 'missing-event', 'settled-project-reopened-in-queue', 'duplicate-project-id', 'duplicate-project-identity', 'zup-reported-conflict'].includes(f.kind)) return 1;
    return f.kind === 'missing-vectors' ? 3 : 2;
  }
  function evidence(check: Check) {
    return <details key={check.id} className="py-3">
      <summary className="cursor-pointer">{check.question} · {check.status}</summary>
      <p className="my-3">{check.interpretation}</p>
      {check.rows.map((row, i) => <dl key={i} className="my-4 pl-3" style={{borderLeft:'1px solid var(--helicon-line)'}}>
        {Object.entries(row).map(([key, value]) => <div key={key} className="my-1 break-words"><dt className="inline" style={{color:'var(--helicon-muted)'}}>{key.replaceAll('_', ' ')}: </dt><dd className="inline">{value == null ? 'Not recorded' : typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd></div>)}
      </dl>)}
      <p className="my-3">Next: {check.action}</p>
      <details className="text-xs"><summary>Source query</summary><p className="mt-2 break-words">{check.source}</p><pre className="mt-2 whitespace-pre-wrap break-words">{check.query}</pre></details>
    </details>;
  }
  function affectedProjects(finding: Finding) {
    const ids = finding.projects ?? (finding.project ? [finding.project] : []);
    if (!ids.length) return null;
    return <details className="text-sm mt-2">
      <summary className="cursor-pointer">Inspect affected projects</summary>
      {ids.map(id => {
        const project = projects?.projects.find(p => p.id === id);
        return <div key={id} className="my-4 pl-3" style={{borderLeft:'1px solid var(--helicon-line)'}}>
          <p className="font-medium">{id}</p>
          <p className="mt-1">State: {project?.state ?? 'Not recorded'}</p>
          <p className="mt-1" style={{color:'var(--helicon-muted)'}}>State source: {project?.source ?? 'Not recorded'}</p>
          {project?.observed_at && <p className="mt-1">Recorded: {recordedTime(project.observed_at)}</p>}
          {project?.evidence && <p className="mt-1">{project.evidence}</p>}
        </div>;
      })}
    </details>;
  }
  return <div className="max-w-2xl mx-auto pb-12" style={{color: 'var(--helicon-ink)'}}>
    <div className="flex justify-between items-center mb-8">
      <h1 className="text-[28px]" style={{fontFamily: 'var(--helicon-serif)'}}>Your setup</h1>
      <button className="text-sm" disabled={loading} onClick={() => void refresh()}>{loading ? 'Checking…' : 'Check now'}</button>
    </div>
    {error && <p role="alert" className="mb-5">{error}. Any earlier reading below is not current.</p>}
    {!report ? <p>{loading ? 'Reading the local sources…' : 'No review is available. Try Check now.'}</p> : <>
      <section className="mb-7">
        <h2 className="text-lg mb-2">What needs attention</h2>
        {(!projects || projects.status === 'unmeasured') && <p className="text-sm">Project checks are unavailable. {projects?.reason}</p>}
        {findings.length ? findings.slice(0, 3).map((finding, i) => <div key={i} className="my-5">
          <p className="text-sm font-medium">{finding.title ?? 'Project records disagree'}{finding.project ? `: ${finding.project}` : ''}</p>
          <p className="text-sm mt-1">{finding.consequence}</p>
          <p className="text-sm mt-1" style={{color: 'var(--helicon-muted)'}}>{finding.action}</p>
          {finding.checks && <details className="text-sm mt-2"><summary className="cursor-pointer">Inspect evidence</summary>{checks.filter(c => finding.checks?.includes(c.id)).map(evidence)}</details>}
          {affectedProjects(finding)}
        </div>) : projects?.status === 'measured' && report.memory_review && <p className="text-sm">No issues found by the checks run. Memory correctness and benefit remain unmeasured.</p>}
        {!report.memory_review && <p className="text-sm">Memory checks are unavailable. No memory-quality conclusion can be drawn.</p>}
        {findings.length > 3 && <details className="text-sm"><summary>{findings.length - 3} more findings</summary>{findings.slice(3).map((f,i)=><div key={i} className="my-4"><p>{f.title}</p><p className="mt-1">{f.consequence}</p><p className="mt-1">{f.action}</p>{checks.filter(c => f.checks?.includes(c.id)).map(evidence)}{affectedProjects(f)}</div>)}</details>}
      </section>
      <section className="mb-7">
        <details className="text-sm">
          <summary className="cursor-pointer text-lg">How your memory works</summary>
          <p className="my-4" style={{color:'var(--helicon-muted)'}}>{report.memory_review?.relationship ?? 'Memory review unavailable.'}</p>
          {report.memory_review?.stages?.map(stage => <details key={stage.id} className="py-4" style={{borderTop:'1px solid var(--helicon-line)'}}>
            <summary className="cursor-pointer">{stage.title}<span className="block mt-1 text-sm" style={{color:'var(--helicon-muted)'}}>{stage.summary}{stage.state === 'empty' ? ' · empty' : ''}</span></summary>
            <p className="mt-4">Source: {stage.source}</p>
            <p className="mt-2">{stage.limit}</p>
            {stage.watermark && <p className="mt-2">Newest recorded event: {recordedTime(stage.watermark)}</p>}
            {checks.filter(c => stage.checks.includes(c.id)).map(evidence)}
          </details>)}
        </details>
      </section>
      <details className="text-sm" style={{borderTop: '1px solid var(--helicon-line)', paddingTop: 16}}>
        <summary className="cursor-pointer">Evidence and technical details</summary>
        <p className="my-4" style={{color:'var(--helicon-muted)'}}>Sources: ZUP's local project events and board; Helicon's memory store; Transcripto's conversation index. Checked {projects?.observed_at ?? report.memory_review?.observed_at ?? 'at an unknown time'}.</p>
        {backed.map(p => <p key={p.id} className="my-3">{p.id}: {p.state}. {p.evidence}</p>)}
        {projects?.findings.map((f, i) => <pre className="whitespace-pre-wrap break-words" key={i}>{JSON.stringify(f, null, 2)}</pre>)}
        {checks.map(evidence)}
      </details>
    </>}
  </div>;
}
