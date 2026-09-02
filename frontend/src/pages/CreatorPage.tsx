import { useEffect, useMemo, useState } from 'react';
import { Box, FileJson, Image as ImageIcon, Loader2, Palette, Play, RefreshCw } from 'lucide-react';
import { getAuthToken } from '../api/client';
import { ModelViewer } from '../components/ModelViewer';

type ModuleId = 'brief' | 'image2' | 'model' | 'multicolor' | 'calibrate' | 'analyze';
type ModuleDefinition = {
  id: ModuleId;
  title: string;
  description: string;
  path: string;
  fileLabel?: string;
  accept?: string;
};

const modules: ModuleDefinition[] = [
  { id: 'brief', title: 'Brief preparation', description: 'DeepSeek returns a source-language brief, clarification questions, and printable prompts; no session is created.', path: '/brief/prepare' },
  { id: 'image2', title: 'Image2 style image', description: 'Returns one normalized 1:1 PNG style image.', path: '/image2/generate', fileLabel: 'Optional reference image', accept: 'image/*' },
  { id: 'model', title: 'Image → GLB', description: 'Runs Hunyuan image-to-3D and returns a GLB.', path: '/model/generate', fileLabel: 'Input image', accept: 'image/*' },
  { id: 'multicolor', title: 'GLB → multicolor 3MF', description: 'Runs Meshy conversion with an explicit color-count limit.', path: '/print/multicolor', fileLabel: 'GLB model', accept: '.glb,model/gltf-binary' },
  { id: 'calibrate', title: '3MF color calibration', description: 'DeepSeek matches active filament inventory and returns calibrated 3MF.', path: '/print/calibrate', fileLabel: 'Model 3MF', accept: '.3mf,model/3mf' },
  { id: 'analyze', title: 'GLB print analysis', description: 'Returns Meshy printability and DeepSeek observations as JSON.', path: '/print/analyze', fileLabel: 'GLB model', accept: '.glb,model/gltf-binary' },
];

type Artifact = { url: string; type: 'image' | 'glb' | '3mf'; name: string };
type RunResult = {
  status: number;
  elapsedMs: number;
  headers: Record<string, string>;
  json?: unknown;
  artifact?: Artifact;
};

function artifactType(id: ModuleId): Artifact['type'] {
  return id === 'image2' ? 'image' : id === 'model' ? 'glb' : '3mf';
}

function filenameFromDisposition(value: string | null, fallback: string): string {
  const encoded = value?.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) {
    try { return decodeURIComponent(encoded); } catch { return fallback; }
  }
  return value?.match(/filename="?([^";]+)"?/i)?.[1] || fallback;
}

export function CreatorPage() {
  const [activeId, setActiveId] = useState<ModuleId>('brief');
  const [prompt, setPrompt] = useState('A compact colorful desk figurine, front product view');
  const [brief, setBrief] = useState('{\n  "subject": "cat",\n  "style": "minimal",\n  "product_type": "figurine"\n}');
  const [maxColors, setMaxColors] = useState(4);
  const [file, setFile] = useState<File | null>(null);
  const [reuseUrl, setReuseUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);
  const active = useMemo(() => modules.find((item) => item.id === activeId)!, [activeId]);

  useEffect(() => () => { if (result?.artifact) URL.revokeObjectURL(result.artifact.url); }, [result?.artifact]);

  function selectModule(id: ModuleId) {
    setActiveId(id); setFile(null); setError(null); setResult(null); setReuseUrl('');
  }

  async function run() {
    setBusy(true); setError(null);
    if (result?.artifact) URL.revokeObjectURL(result.artifact.url);
    setResult(null);
    try {
      const headers = new Headers();
      const token = getAuthToken();
      if (token) headers.set('Authorization', `Bearer ${token}`);
      let body: BodyInit;
      if (activeId === 'brief') {
        let currentBrief: unknown;
        try { currentBrief = JSON.parse(brief); } catch { throw new Error('Current brief must be valid JSON.'); }
        headers.set('Content-Type', 'application/json');
        body = JSON.stringify({ message: prompt, current_brief: currentBrief });
      } else {
        const form = new FormData();
        if (activeId === 'image2') { form.append('prompt', prompt); if (file) form.append('reference_image', file); }
        if (activeId === 'model') { if (!file) throw new Error('Select an input image.'); form.append('image', file); }
        if (activeId === 'multicolor') { if (!file && !reuseUrl.trim()) throw new Error('Select a GLB model or provide a Meshy result URL.'); if (file) form.append('model', file); form.append('max_colors', String(maxColors)); if (reuseUrl.trim()) form.append('meshy_result_url', reuseUrl.trim()); }
        if (activeId === 'calibrate') { if (!file) throw new Error('Select a model 3MF.'); form.append('file', file); }
        if (activeId === 'analyze') { if (!file) throw new Error('Select a GLB model.'); form.append('model', file); }
        body = form;
      }
      const started = performance.now();
      const response = await fetch(`/api/v1/creator/modules${active.path}`, { method: 'POST', headers, body });
      const responseHeaders = Object.fromEntries([...response.headers].filter(([key]) => key.startsWith('content-') || key.startsWith('x-bca-')));
      const elapsedMs = Math.round(performance.now() - started);
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || `Request failed (${response.status})`);
      }
      if ((response.headers.get('content-type') || '').includes('application/json')) {
        const payload = await response.json() as Record<string, unknown>;
        const prompts = payload.prompts as Record<string, unknown> | null;
        if (activeId === 'brief' && typeof prompts?.image2_prompt === 'string') setPrompt(prompts.image2_prompt);
        setResult({ status: response.status, elapsedMs, headers: responseHeaders, json: payload });
      } else {
        const artifact = { url: URL.createObjectURL(await response.blob()), type: artifactType(activeId), name: filenameFromDisposition(response.headers.get('content-disposition'), `creator-${activeId}.${artifactType(activeId)}`) };
        setResult({ status: response.status, elapsedMs, headers: responseHeaders, artifact });
      }
    } catch (err) { setError(err instanceof Error ? err.message : 'Module request failed'); }
    finally { setBusy(false); }
  }

  return <main className="creator-console">
    <header className="creator-console-heading"><div><h1>Creator API test bench</h1><p>Each request invokes exactly one public capability. The console never creates or advances a Creator workflow.</p></div><button className="small-action" disabled={busy} onClick={() => selectModule(activeId)}><RefreshCw size={15} />Clear result</button></header>
    <nav className="creator-module-nav" aria-label="Creator API modules">{modules.map((item) => <button key={item.id} className={item.id === activeId ? 'is-active' : ''} aria-pressed={item.id === activeId} onClick={() => selectModule(item.id)}>{item.title}</button>)}</nav>
    <section className="creator-console-workspace">
      <form className="creator-console-request" onSubmit={(event) => { event.preventDefault(); void run(); }}>
        <header><div><h2>{active.title}</h2><p>{active.description}</p></div><code>POST /api/v1/creator/modules{active.path}</code></header>
        {(activeId === 'brief' || activeId === 'image2') && <label>Prompt<textarea value={prompt} rows={4} onChange={(event) => setPrompt(event.target.value)} /></label>}
        {activeId === 'brief' && <label>Current brief JSON<textarea value={brief} rows={8} onChange={(event) => setBrief(event.target.value)} /></label>}
        {active.fileLabel && <label className="creator-console-file"><span>{active.fileLabel}</span><input type="file" accept={active.accept} onChange={(event) => setFile(event.target.files?.[0] || null)} /><output>{file ? `${file.name} · ${(file.size / (1024 * 1024)).toFixed(2)} MiB` : 'No file selected'}</output></label>}
        {activeId === 'multicolor' && <><label>Maximum colors <output>{maxColors}</output><input type="range" min="1" max="8" value={maxColors} onChange={(event) => setMaxColors(Number(event.target.value))} /></label><label>Existing Meshy 3MF result URL <input value={reuseUrl} placeholder="Optional: retry download without a new Meshy task" onChange={(event) => setReuseUrl(event.target.value)} /></label></>}
        <button className="primary-button" disabled={busy} type="submit">{busy ? <Loader2 className="spin" size={16} /> : <Play size={16} />}Invoke module</button>
      </form>
      <section className="creator-console-result" aria-live="polite">
        <header><div><h2>Response</h2><p>Raw response metadata, JSON data, and returned artifact preview.</p></div>{result && <span>{result.status} · {result.elapsedMs} ms</span>}</header>
        {error && <p className="creator-error" role="alert">{error}</p>}
        {!result && !error && <div className="creator-console-empty"><FileJson size={22} /><p>Invoke a module to inspect its response.</p></div>}
        {result && <>
          <pre>{JSON.stringify({ headers: result.headers, body: result.json }, null, 2)}</pre>
          {result.artifact && <a className="creator-console-download" href={result.artifact.url} download={result.artifact.name}>Download {result.artifact.name}</a>}
          {result.artifact?.type === 'image' && <img className="creator-console-image" src={result.artifact.url} alt="Returned style image" />}
          {result.artifact?.type !== 'image' && result.artifact && <div className="creator-console-model"><ModelViewer url={result.artifact.url} fileType={result.artifact.type} showControls={false} /></div>}
        </>}
      </section>
    </section>
    <footer className="creator-console-footer"><ImageIcon size={16} /> Image2 output is normalized to 1:1. <Palette size={16} /> Calibration uses active filament inventory. <Box size={16} /> GLB and 3MF replies remain downloadable HTTP artifacts.</footer>
  </main>;
}
