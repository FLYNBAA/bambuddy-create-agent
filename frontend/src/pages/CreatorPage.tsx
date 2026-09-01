import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Check, Download, Expand, Image as ImageIcon, Loader2, Plus, Send,
  Sparkles, Trash2, WandSparkles, X,
} from 'lucide-react';
import { getAuthToken } from '../api/client';
import { ModelViewer } from '../components/ModelViewer';

type Stage = { status: string; message?: string | null; error?: string | null };
type PrintAnalysis = {
  status: string;
  report?: { status?: string; [key: string]: unknown } | null;
  score?: number | null;
  insights?: string[] | null;
  error?: string | null;
};
type CreatorSession = {
  session_id: string;
  status: string;
  brief: { subject?: string; style?: string; product_type?: string; details?: string };
  image_prompt: string | null;
  generated_images: string[];
  selected_image_index: number | null;
  model_download_url: string | null;
  calibrated_print_file_download_url: string | null;
  image_generation?: Stage;
  model_generation?: Stage;
  print_analysis: PrintAnalysis;
  color_calibration: Stage;
  events: Array<{ stage: string; status: string; message: string }>;
  error: string | null;
};
type Preview = { url: string; fileType: 'glb' | '3mf'; title: string };
type TaskDetails = { title: string; customer_name: string; phone: string; address: string; notes: string };

const API = '/api/v1/creator';
const emptyTaskDetails: TaskDetails = { title: '', customer_name: '', phone: '', address: '', notes: '' };

async function creatorRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = getAuthToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init?.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${API}${path}`, { ...init, headers });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || `Creator request failed (${response.status})`);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

async function downloadCreatorArtifact(path: string, filename: string) {
  const headers = new Headers();
  const token = getAuthToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(path, { headers });
  if (!response.ok) throw new Error(`Artifact download failed (${response.status})`);
  const objectUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}

function statusLabel(status?: string) {
  return (status || 'not_started').replaceAll('_', ' ');
}

function stageTone(status?: string) {
  if (status === 'failed' || status === 'error') return 'failed';
  if (status === 'queued' || status === 'running' || status === 'generating') return 'running';
  if (status === 'succeeded' || status === 'completed') return 'completed';
  return 'pending';
}

function StageState({ status }: { status?: string }) {
  const tone = stageTone(status);
  return <span className={`creator-stage-state is-${tone}`}><span aria-hidden="true" />{statusLabel(status)}</span>;
}

function PreviewDialog({ preview, onClose }: { preview: Preview; onClose: () => void }) {
  const dialogRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
        .filter((element) => !element.hasAttribute('disabled'));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      previouslyFocused?.focus();
    };
  }, [onClose]);

  return <div className="creator-preview-backdrop" role="presentation" onMouseDown={onClose}>
    <section ref={dialogRef} className="creator-preview-dialog" role="dialog" aria-modal="true" aria-labelledby="creator-preview-title" onMouseDown={(event) => event.stopPropagation()}>
      <header><h2 id="creator-preview-title">{preview.title}</h2><button className="icon-button" onClick={onClose} aria-label="关闭预览" autoFocus><X size={18} /></button></header>
      <div className="creator-preview-large"><ModelViewer url={preview.url} fileType={preview.fileType} /></div>
    </section>
  </div>;
}

export function CreatorPage() {
  const [sessions, setSessions] = useState<CreatorSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [reference, setReference] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [imagePreviews, setImagePreviews] = useState<Record<string, string>>({});
  const [selectedCandidate, setSelectedCandidate] = useState<number | null>(null);
  const [calibrationMode, setCalibrationMode] = useState<'white' | 'multicolor'>('white');
  const [maxColors, setMaxColors] = useState(4);
  const [taskDetails, setTaskDetails] = useState<TaskDetails>(emptyTaskDetails);
  const [expandedPreview, setExpandedPreview] = useState<Preview | null>(null);
  const [typedPrompt, setTypedPrompt] = useState('');

  const active = useMemo(() => sessions.find((item) => item.session_id === activeId) || null, [sessions, activeId]);
  const imageRoutesKey = active?.generated_images.join('\u0000') ?? '';
  const hasCreativeResult = Boolean(active?.image_prompt || active?.brief.subject || active?.brief.details);
  const hasImages = Boolean(active?.generated_images.length);
  const hasModel = Boolean(active?.model_download_url);
  const hasCalibration = Boolean(active?.calibrated_print_file_download_url);

  const replaceSession = useCallback((updated: CreatorSession) => {
    setSessions((current) => current.map((item) => item.session_id === updated.session_id ? updated : item));
  }, []);
  const refresh = useCallback(async () => {
    try {
      const data = await creatorRequest<CreatorSession[]>('/sessions');
      setSessions(data);
      setActiveId((current) => current || data[0]?.session_id || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load creator sessions');
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!active) return;
    const statuses = [active.image_generation?.status, active.model_generation?.status, active.color_calibration.status, active.print_analysis.status];
    if (!statuses.some((status) => stageTone(status) === 'running')) return;
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(timer);
  }, [active, refresh]);
  useEffect(() => {
    setSelectedCandidate(active?.selected_image_index ?? null);
  }, [active?.selected_image_index]);
  useEffect(() => {
    setTaskDetails(emptyTaskDetails);
    setNotice(null);
  }, [activeId]);
  useEffect(() => {
    const prompt = active?.image_prompt || '';
    setTypedPrompt('');
    if (!prompt) return;
    let cursor = 0;
    const timer = window.setInterval(() => {
      cursor += Math.max(1, Math.ceil(prompt.length / 64));
      setTypedPrompt(prompt.slice(0, cursor));
      if (cursor >= prompt.length) window.clearInterval(timer);
    }, 20);
    return () => window.clearInterval(timer);
  }, [active?.image_prompt]);
  useEffect(() => {
    const routes = imageRoutesKey ? imageRoutesKey.split('\u0000') : [];
    if (!routes.length) { setImagePreviews({}); return; }
    const headers = new Headers();
    const token = getAuthToken();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const controller = new AbortController();
    const objectUrls: string[] = [];
    let disposed = false;
    void Promise.allSettled(routes.map(async (route) => {
      const response = await fetch(route, { headers, signal: controller.signal });
      if (!response.ok) throw new Error(`Style image preview failed (${response.status})`);
      const objectUrl = URL.createObjectURL(await response.blob());
      if (disposed) { URL.revokeObjectURL(objectUrl); return null; }
      objectUrls.push(objectUrl);
      return [route, objectUrl] as const;
    })).then((results) => {
      if (disposed) return;
      setImagePreviews(Object.fromEntries(results.flatMap((result) => result.status === 'fulfilled' && result.value ? [result.value] : [])));
    });
    return () => { disposed = true; controller.abort(); objectUrls.forEach(URL.revokeObjectURL); };
  }, [imageRoutesKey]);

  async function createSession() {
    setBusy(true); setError(null); setNotice(null);
    try {
      const created = await creatorRequest<CreatorSession>('/sessions', { method: 'POST' });
      setSessions((current) => [created, ...current]); setActiveId(created.session_id);
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to create creator session'); }
    finally { setBusy(false); }
  }
  async function removeSession(sessionId: string) {
    if (!window.confirm('永久删除此创作会话及其所有产物？')) return;
    setBusy(true); setError(null);
    try {
      await creatorRequest<void>(`/sessions/${sessionId}`, { method: 'DELETE' });
      setSessions((current) => {
        const remaining = current.filter((item) => item.session_id !== sessionId);
        if (activeId === sessionId) setActiveId(remaining[0]?.session_id ?? null);
        return remaining;
      });
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to delete creator session'); }
    finally { setBusy(false); }
  }
  async function prepare() {
    if (!activeId || (!message.trim() && !reference)) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      const form = new FormData();
      form.append('message', message.trim());
      if (reference) form.append('reference_image', reference);
      replaceSession(await creatorRequest<CreatorSession>(`/sessions/${activeId}/prepare`, { method: 'POST', body: form }));
      setMessage(''); setReference(null);
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to prepare creative direction'); }
    finally { setBusy(false); }
  }
  async function action(path: string, body?: object) {
    if (!activeId) return;
    setBusy(true); setError(null); setNotice(null);
    try { replaceSession(await creatorRequest<CreatorSession>(`/sessions/${activeId}${path}`, { method: 'POST', body: body ? JSON.stringify(body) : undefined })); }
    catch (err) { setError(err instanceof Error ? err.message : 'Creator action failed'); }
    finally { setBusy(false); }
  }
  async function createTask() {
    if (!activeId) return;
    const customer_name = taskDetails.customer_name.trim();
    const phone = taskDetails.phone.trim();
    const address = taskDetails.address.trim();
    if (!customer_name || !phone || !address) { setError('请填写客户姓名、联系电话和地址。'); return; }
    setBusy(true); setError(null); setNotice(null);
    try {
      await creatorRequest(`/sessions/${activeId}/task`, { method: 'POST', body: JSON.stringify({ title: taskDetails.title.trim() || undefined, customer_name, phone, address, notes: taskDetails.notes.trim() || undefined }) });
      setNotice('任务已创建，可在任务清单中继续处理。');
      setTaskDetails(emptyTaskDetails);
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to create task'); }
    finally { setBusy(false); }
  }
  async function download(path: string, filename: string) {
    setBusy(true); setError(null);
    try { await downloadCreatorArtifact(path, filename); }
    catch (err) { setError(err instanceof Error ? err.message : 'Artifact download failed'); }
    finally { setBusy(false); }
  }

  return <div className="creator-shell">
    <aside className="creator-sessions panel">
      <div className="creator-panel-heading"><div><h1>创作会话</h1><p>每个作品独立保存。</p></div><button className="icon-button" disabled={busy} onClick={() => void createSession()} aria-label="新建会话"><Plus size={18} /></button></div>
      <div className="creator-session-list">
        {sessions.map((session) => <div className={`creator-session-row ${session.session_id === activeId ? 'is-active' : ''}`} key={session.session_id}>
          <button className="creator-session-select" onClick={() => setActiveId(session.session_id)}><span>{session.brief.subject || '未命名创作'}</span><small>{statusLabel(session.status)}</small></button>
          <button className="creator-session-delete" disabled={busy} onClick={() => void removeSession(session.session_id)} aria-label={`删除创作会话 ${session.brief.subject || '未命名创作'}`}><Trash2 size={16} /></button>
        </div>)}
        {!sessions.length && <div className="creator-empty">新建一个会话，开始准备作品。</div>}
      </div>
    </aside>

    <main className="creator-workflow panel">
      <header className="creator-workflow-heading"><div><h2>3D 打印创作</h2><p>从灵感到已校准的打印文件。</p></div>{active && <StageState status={active.status} />}</header>
      {!active ? <div className="creator-empty creator-start-empty"><WandSparkles size={24} /><p>选择或新建会话以开始创作。</p></div> : <div className="creator-canvas">
        <article className="creator-card creator-card-start">
          <div className="creator-card-header"><div><h3>创意呈现</h3><p>填写文字创意，可选一张参考图，由 DeepSeek 补全创作方向。</p></div><StageState status={hasCreativeResult ? 'completed' : 'not_started'} /></div>
          <textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder="例如：做一只适合桌面打印的英短猫 Q 版摆件" rows={4} aria-label="创意描述" />
          <div className="creator-input-row"><label className="creator-upload"><ImageIcon size={17} /><span>{reference ? reference.name : '添加参考图'}</span><input type="file" accept="image/*" onChange={(event) => setReference(event.target.files?.[0] || null)} /></label><button className="primary-button" disabled={busy || (!message.trim() && !reference)} onClick={() => void prepare()}>{busy ? <Loader2 className="spin" size={16} /> : <Send size={16} />}准备创意</button></div>
          {hasCreativeResult && <div className="creator-creative-result"><Sparkles size={17} /><div><strong>创意方向</strong><p>{typedPrompt || active.image_prompt || active.brief.subject}</p></div></div>}
        </article>

        {hasCreativeResult && <><div className="creator-connector" /><article className="creator-card">
          <div className="creator-card-header"><div><h3>风格图生成</h3><p>由 Image2 生成可用于建模的风格参考，并选择一个版本。</p></div><StageState status={active.image_generation?.status || (hasImages ? 'succeeded' : 'not_started')} /></div>
          <div className="creator-card-actions"><button className="small-action" disabled={busy || stageTone(active.image_generation?.status) === 'running'} onClick={() => void action('/images/generate')}>{hasImages ? '重新生成风格图' : '生成风格图'}</button></div>
          {hasImages && <div className="creator-image-grid" role="radiogroup" aria-label="选择用于建模的风格图">{active.generated_images.map((url, index) => <button className={`creator-image ${selectedCandidate === index ? 'is-selected' : ''}`} key={url} role="radio" aria-checked={selectedCandidate === index} onClick={() => setSelectedCandidate(index)}><img src={imagePreviews[url]} alt={`风格图 ${index + 1}`} />{selectedCandidate === index && <span><Check size={14} /></span>}</button>)}</div>}
        </article></>}

        {hasImages && <><div className="creator-connector" /><article className="creator-card">
          <div className="creator-card-header"><div><h3>3D 概念图生成</h3><p>根据所选风格图，由混元生成可预览的 GLB 概念模型。</p></div><StageState status={active.model_generation?.status || (hasModel ? 'succeeded' : 'not_started')} /></div>
          <div className="creator-card-actions"><button className="small-action" disabled={busy || selectedCandidate == null || stageTone(active.model_generation?.status) === 'running'} onClick={() => void action('/model/generate', { image_index: selectedCandidate })}>{hasModel ? '重做 3D 概念图' : '生成 3D 概念图'}</button></div>
          {hasModel && <div className="creator-artifact-preview"><div className="creator-preview-small"><ModelViewer url={active.model_download_url!} fileType="glb" /></div><div><strong>GLB 模型</strong><p>旋转查看模型，或打开大图预览。</p><button className="creator-download" onClick={() => void download(active.model_download_url!, 'model.glb')}><Download size={15} />下载 GLB</button><button className="creator-download" onClick={() => setExpandedPreview({ url: active.model_download_url!, fileType: 'glb', title: 'GLB 模型预览' })}><Expand size={15} />展开预览</button></div></div>}
        </article></>}

        {hasModel && <><div className="creator-connector" /><article className="creator-card">
          <div className="creator-card-header"><div><h3>打印校准</h3><p>Meshy 生成 3MF 后完成颜色匹配；白模最终统一替换为白色。</p></div><StageState status={active.color_calibration.status || (hasCalibration ? 'succeeded' : 'not_started')} /></div>
          <div className="creator-mode-nav" role="group" aria-label="打印校准模式"><button className={calibrationMode === 'white' ? 'is-active' : ''} aria-pressed={calibrationMode === 'white'} onClick={() => setCalibrationMode('white')}>白模</button><button className={calibrationMode === 'multicolor' ? 'is-active' : ''} aria-pressed={calibrationMode === 'multicolor'} onClick={() => setCalibrationMode('multicolor')}>多色</button></div>
          {calibrationMode === 'multicolor' && <label className="creator-color-range">最大颜色数 <output>{maxColors}</output><input type="range" min="1" max="8" value={maxColors} onChange={(event) => setMaxColors(Number(event.target.value))} aria-valuemin={1} aria-valuemax={8} aria-valuenow={maxColors} /></label>}
          <div className="creator-card-actions"><button className="small-action" disabled={busy || stageTone(active.color_calibration.status) === 'running'} onClick={() => void action('/print/calibrate', { mode: calibrationMode, max_colors: calibrationMode === 'white' ? 1 : maxColors })}>{hasCalibration ? '重新校准' : '开始校准'}</button></div>
          {active.color_calibration.error && <p className="creator-error" role="alert">{active.color_calibration.error}</p>}
          {hasCalibration && <div className="creator-artifact-preview"><div className="creator-preview-small"><ModelViewer url={active.calibrated_print_file_download_url!} fileType="3mf" /></div><div><strong>最终 3MF</strong><p>此文件已完成最终校准，可用于创建任务。</p><button className="creator-download" onClick={() => void download(active.calibrated_print_file_download_url!, 'print-calibrated.3mf')}><Download size={15} />下载 3MF</button><button className="creator-download" onClick={() => setExpandedPreview({ url: active.calibrated_print_file_download_url!, fileType: '3mf', title: '最终 3MF 预览' })}><Expand size={15} />展开预览</button></div></div>}
        </article></>}

        {hasCalibration && <><div className="creator-connector" /><article className="creator-card">
          <div className="creator-card-header"><div><h3>打印分析</h3><p>Meshy 与 DeepSeek 在最终校准后给出评分和见解，不提供建议。</p></div><StageState status={active.print_analysis.status} /></div>
          <div className="creator-card-actions"><button className="small-action" disabled={busy || stageTone(active.print_analysis.status) === 'running'} onClick={() => void action('/print/analyze')}>{active.print_analysis.status === 'succeeded' ? '重新分析' : '开始分析'}</button></div>
          {active.print_analysis.error && <p className="creator-error" role="alert">{active.print_analysis.error}</p>}
          {active.print_analysis.status === 'succeeded' && <div className="creator-analysis"><div><strong>评分</strong><output>{active.print_analysis.score ?? '—'}</output></div><div><strong>洞察</strong>{active.print_analysis.insights?.length ? <ul>{active.print_analysis.insights.map((insight) => <li key={insight}>{insight}</li>)}</ul> : <p>暂无额外洞察。</p>}</div></div>}
        </article></>}

        {active.print_analysis.status === 'succeeded' && <><div className="creator-connector" /><article className="creator-card">
          <div className="creator-card-header"><div><h3>推送订单</h3><p>填写订单信息并将最终校准文件推送到 root 任务清单。</p></div><StageState status="ready" /></div>
          <div className="creator-order-grid"><label>任务标题（可选）<input value={taskDetails.title} maxLength={120} onChange={(event) => setTaskDetails((current) => ({ ...current, title: event.target.value }))} placeholder="留空可自动生成" /></label><label>客户姓名<input required value={taskDetails.customer_name} maxLength={120} onChange={(event) => setTaskDetails((current) => ({ ...current, customer_name: event.target.value }))} /></label><label>联系电话<input required value={taskDetails.phone} maxLength={40} onChange={(event) => setTaskDetails((current) => ({ ...current, phone: event.target.value }))} /></label><label>地址<input required value={taskDetails.address} maxLength={500} onChange={(event) => setTaskDetails((current) => ({ ...current, address: event.target.value }))} /></label><label className="creator-order-notes">订单备注（可选）<textarea value={taskDetails.notes} maxLength={2000} onChange={(event) => setTaskDetails((current) => ({ ...current, notes: event.target.value }))} rows={3} /></label></div>
          <div className="creator-card-actions"><button className="primary-button" disabled={busy} onClick={() => void createTask()}>{busy ? <Loader2 className="spin" size={16} /> : <Check size={16} />}推送订单</button></div>
        </article></>}
      </div>}
      {error && <div className="creator-error" role="alert">{error}</div>}
      {notice && <div className="creator-notice" role="status">{notice}</div>}
    </main>
    {expandedPreview && <PreviewDialog preview={expandedPreview} onClose={() => setExpandedPreview(null)} />}
  </div>;
}
