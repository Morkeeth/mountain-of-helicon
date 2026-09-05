import {useEffect, useState} from 'react';

type Packet = {id: string; review_id: string; state: string; source_status: string; recipient: {run_id: string; provider: string; project: string}; consumption?: {consumed_at: string; transport: string}; behavior: {verdict: string; evidence: string; artifact: string; artifact_sha256: string; artifact_current: boolean}[]};
type Props = {projectId: string; projectPath?: string; snapshotId: string; sources?: {id: string; path: string; status: string; sha256: string}[]; disabled: boolean; onBusyChange: (busy: boolean) => void};

async function call(path: string, data?: unknown) {
  const response = await fetch('/api/context-review/' + path, {method: data ? 'POST' : 'GET', headers: {'X-Helicon-Local':'1', ...(data ? {'Content-Type':'application/json'} : {})}, ...(data ? {body:JSON.stringify(data)} : {})});
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Could not read the packet record.');
  return result;
}

export default function ContextPacketPanel({projectId,projectPath,snapshotId,sources,disabled,onBusyChange}: Props) {
  const [selected,setSelected] = useState<string[]>([]);
  const [run,setRun] = useState('');
  const [provider,setProvider] = useState('');
  const [packets,setPackets] = useState<Packet[]>();
  const [error,setError] = useState('');
  const [busy,setBusy] = useState(false);
  const eligible = sources?.filter((s,i,all) => s.path.startsWith((projectPath ?? '') + '/') && ['available','empty'].includes(s.status) && all.findIndex(other => other.path === s.path) === i) ?? [];
  const style = {background:'var(--helicon-bg)',border:'1px solid var(--helicon-line)',color:'var(--helicon-ink)'};
  useEffect(() => {setSelected([]);}, [snapshotId]);
  useEffect(() => {
    if (!projectId) return;
    let current = true;
    setPackets(undefined); setError('');
    call('packets?project_id=' + encodeURIComponent(projectId)).then(data => {if (current) {setPackets(data.packets);setError(data.errors?.join(' ') ?? '');}}).catch(e => {if(current) setError(String(e));});
    return () => {current=false;};
  }, [projectId]);
  async function refresh() {
    const data = await call('packets?project_id=' + encodeURIComponent(projectId));
    setPackets(data.packets); setError(data.errors?.join(' ') ?? '');
  }
  return <details className="text-sm my-5"><summary className="cursor-pointer">Context for the next run</summary>
    <p className="my-3">Choose only the project sources this run needs. Preparation saves a local packet; it does not launch an agent or deliver it.</p>
    {snapshotId ? <>
      {eligible.map(s => <label key={s.id} className="block my-2 break-words"><input type="checkbox" disabled={busy || disabled} checked={selected.includes(s.id)} onChange={e => setSelected(e.target.checked ? [...selected,s.id] : selected.filter(id => id !== s.id))} /> {s.path}</label>)}
      <label className="block my-3">Receiving run ID<input aria-label="Receiving run ID" className="block w-full p-2 mt-1 rounded" style={style} disabled={busy || disabled} value={run} onChange={e=>setRun(e.target.value)} /></label>
      <label className="block my-3">Provider<input aria-label="Packet provider" placeholder="For example, codex" className="block w-full p-2 mt-1 rounded" style={style} disabled={busy || disabled} value={provider} onChange={e=>setProvider(e.target.value)} /></label>
      <button className="border rounded px-3 py-2 disabled:opacity-40" disabled={busy || disabled || !selected.length || !run.trim() || !provider.trim()} onClick={() => {void (async () => {
        setBusy(true);onBusyChange(true);setError('');
        try {await call('packets',{project_id:projectId,snapshot_id:snapshotId,source_ids:selected,run_id:run.trim(),provider:provider.trim()}); await refresh();}
        catch(e){setError(String(e));} finally{setBusy(false);onBusyChange(false);}
      })();}}>Prepare local packet</button>
    </> : <p className="my-3">Save a current review to select its source versions.</p>}
    {error && <p role="alert" className="my-3">{error}</p>}
    <button className="underline block my-4" disabled={busy || disabled} onClick={() => {setBusy(true);onBusyChange(true);void refresh().catch(e=>setError(String(e))).finally(()=>{setBusy(false);onBusyChange(false);});}}>Check run receipts</button>
    {packets?.length === 0 && !error && <p>No packets prepared for this project.</p>}
    {packets?.map(p => <details className="my-4" key={p.id}><summary className="cursor-pointer break-words">{p.recipient.run_id} · {p.state === 'consumed' ? 'Packet received' : 'Prepared, not delivered'}</summary>
      <p className="my-2">Provider: {p.recipient.provider}. Source revision: {p.source_status}.</p>
      <p className="my-2">{p.consumption ? `The local interface returned this packet at ${new Date(p.consumption.consumed_at).toLocaleString()} (${p.consumption.transport}). This is not proof of comprehension or compliance.` : 'The named agent must request this packet through the local MCP tool. ZUP or another runtime remains responsible for execution.'}</p>
      <details className="my-2"><summary>Local connection details</summary><p className="my-2">Tool: helicon_context_packet_consume</p><pre className="text-xs whitespace-pre-wrap break-words">{JSON.stringify({packet_id:p.id,recipient:p.recipient},null,2)}</pre></details>
      {p.behavior.length ? p.behavior.map((b,i)=><div key={i} className="my-3"><p>Recorded behavior review: {b.verdict}. {b.artifact_current ? 'Artifact revision still matches.' : 'Artifact changed or is unavailable.'}</p><p className="mt-1">{b.evidence}</p><p className="text-xs break-words mt-1">{b.artifact} · {b.artifact_sha256}</p></div>) : <p className="my-2">Behavior not verified.</p>}
    </details>)}
  </details>;
}
