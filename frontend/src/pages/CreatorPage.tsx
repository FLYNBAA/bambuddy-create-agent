import { useCallback, useEffect, useMemo, useState } from 'react';
import { Bot, Check, Download, Image as ImageIcon, Loader2, Plus, Send, Sparkles, Trash2, WandSparkles } from 'lucide-react';
import { getAuthToken } from '../api/client';

type CreatorSession = {
  session_id: string;
  status: string;
  brief: { subject?: string; style?: string; product_type?: string; details?: string };
  questions: Array<{ field: string; prompt: string; options: string[] }>;
  image_prompt: string | null;
  generated_images: string[];
  selected_image_index: number | null;
  model_download_url: string | null;
  print_file_download_url: string | null;
  calibrated_print_file_download_url: string | null;
  print_analysis: { status: string; report?: { status: string } | null };
  model_repair: { status: string };
  print_file: { status: string };
  color_calibration: { status: string };
  events: Array<{ stage: string; status: string; message: string }>;
  error: string | null;
  geometry_print_file_download_url: string | null;
  geometry_status: string;
  conversation: Array<{ role: 'user' | 'assistant'; content: string }>;
};

const API = '/api/v1/creator';

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
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || `Artifact download failed (${response.status})`);
  }
  const objectUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}

function statusLabel(status: string) {
  return status.replaceAll('_', ' ');
}

export function CreatorPage() {
  const [sessions, setSessions] = useState<CreatorSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [reference, setReference] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [acknowledgeIssues, setAcknowledgeIssues] = useState(false);
  const [imagePreviews, setImagePreviews] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const active = useMemo(() => sessions.find((item) => item.session_id === activeId) || null, [sessions, activeId]);
  const requiresIssueAcknowledgment = Boolean(
    active?.print_analysis.report && active.print_analysis.report.status !== 'healthy',
  );
  const imageRoutesKey = active?.generated_images.join('\u0000') ?? '';
  const refresh = useCallback(async () => {
    try {
      const data = await creatorRequest<CreatorSession[]>('/sessions');
      setSessions(data);
      if (!activeId && data[0]) setActiveId(data[0].session_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load creator sessions');
    }
  }, [activeId]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const hasActiveWorkflow = active && (
      ['queued_image', 'generating_images', 'queued_3d', 'generating_3d'].includes(active.status)
      || ['queued', 'running'].includes(active.print_analysis.status)
      || ['queued', 'running'].includes(active.print_file.status)
      || ['queued', 'running'].includes(active.color_calibration.status)
      || active.geometry_status === 'running'
    );
    if (!hasActiveWorkflow) return;
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(timer);
  }, [active, refresh]);
  useEffect(() => {
    const onCreatorUpdate = (event: Event) => {
      const detail = (event as CustomEvent<{ session_id?: string }>).detail;
      if (detail?.session_id && detail.session_id === activeId) void refresh();
    };
    window.addEventListener('bca:creator-session', onCreatorUpdate);
    return () => window.removeEventListener('bca:creator-session', onCreatorUpdate);
  }, [activeId, refresh]);

  useEffect(() => { setAcknowledgeIssues(false); }, [activeId, active?.print_analysis.report?.status]);

  useEffect(() => {
    const routes = imageRoutesKey ? imageRoutesKey.split('\u0000') : [];
    if (!routes.length) {
      setImagePreviews({});
      return;
    }
    const headers = new Headers();
    const token = getAuthToken();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const controller = new AbortController();
    const objectUrls: string[] = [];
    let disposed = false;
    void Promise.allSettled(routes.map(async (route) => {
      const response = await fetch(route, { headers, signal: controller.signal });
      if (!response.ok) throw new Error(`Candidate image preview failed (${response.status})`);
      const objectUrl = URL.createObjectURL(await response.blob());
      if (disposed) {
        URL.revokeObjectURL(objectUrl);
        return null;
      }
      objectUrls.push(objectUrl);
      return [route, objectUrl] as const;
    })).then((results) => {
      if (disposed) return;
      const entries = results.flatMap((result) => result.status === 'fulfilled' && result.value ? [result.value] : []);
      if (entries.length) setImagePreviews(Object.fromEntries(entries));
      const rejection = results.find((result) => result.status === 'rejected');
      if (rejection && !controller.signal.aborted) {
        setError(rejection.reason instanceof Error ? rejection.reason.message : 'Candidate image preview failed');
      }
    });
    return () => {
      disposed = true;
      controller.abort();
      objectUrls.forEach((objectUrl) => URL.revokeObjectURL(objectUrl));
    };
  }, [imageRoutesKey]);

  async function createSession() {
    setError(null);
    const created = await creatorRequest<CreatorSession>('/sessions', { method: 'POST' });
    setSessions((current) => [created, ...current]);
    setActiveId(created.session_id);
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
    setBusy(true); setError(null);
    try {
      if (reference) {
        const form = new FormData();
        form.append('message', message);
        form.append('reference_image', reference);
        const updated = await creatorRequest<CreatorSession>(`/sessions/${activeId}/prepare`, { method: 'POST', body: form });
        setSessions((current) => current.map((item) => item.session_id === updated.session_id ? updated : item));
      } else {
        const chat = await creatorRequest<{ session: CreatorSession }>(`/sessions/${activeId}/chat`, { method: 'POST', body: JSON.stringify({ message }) });
        setSessions((current) => current.map((item) => item.session_id === chat.session.session_id ? chat.session : item));
      }
    } catch (err) { setError(err instanceof Error ? err.message : 'Creator request failed'); }
    finally { setBusy(false); }
  }

  async function download(path: string, filename: string) {
    setBusy(true); setError(null);
    try { await downloadCreatorArtifact(path, filename); }
    catch (err) { setError(err instanceof Error ? err.message : 'Artifact download failed'); }
    finally { setBusy(false); }
  }

  async function action(path: string, init?: RequestInit) {
    if (!activeId) return;
    setBusy(true); setError(null);
    try {
      const updated = await creatorRequest<CreatorSession>(`/sessions/${activeId}${path}`, { method: 'POST', ...init });
      setSessions((current) => current.map((item) => item.session_id === updated.session_id ? updated : item));
    } catch (err) { setError(err instanceof Error ? err.message : 'Creator action failed'); }
    finally { setBusy(false); }
  }

  async function generatePrintFile() {
    if (requiresIssueAcknowledgment && !acknowledgeIssues) {
      setError('请先确认已了解打印分析报告中的问题。');
      return;
    }
    await action('/print/generate', {
      method: 'POST',
      body: JSON.stringify({ max_colors: 8, acknowledge_issues: requiresIssueAcknowledgment }),
    });
  }

  async function pushTask(mode: 'multicolor' | 'geometry') {
    if (!activeId) return;
    setBusy(true); setError(null);
    try {
      await creatorRequest(`/sessions/${activeId}/task`, { method: 'POST', body: JSON.stringify({ mode }) });
      setError('已加入任务清单；请在任务清单中上传切片后的 .gcode.3mf。');
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to create task'); }
    finally { setBusy(false); }
  }

  return (
    <div className="creator-shell">
      <aside className="creator-sessions panel">
        <div className="creator-panel-heading"><div><span className="eyebrow">BCA WORKSPACE</span><h1>创作会话</h1></div><button className="icon-button" onClick={() => void createSession()} aria-label="新建会话"><Plus size={18} /></button></div>
        <div className="creator-session-list">
          {sessions.map((session) => <div className={`creator-session-row ${session.session_id === activeId ? 'is-active' : ''}`} key={session.session_id}><button className="creator-session-select" onClick={() => setActiveId(session.session_id)}><span>{session.brief.subject || '未命名创作'}</span><small>{statusLabel(session.status)}</small></button><button className="creator-session-delete" disabled={busy} onClick={() => void removeSession(session.session_id)} aria-label={`删除创作会话 ${session.brief.subject || '未命名创作'}`}><Trash2 size={15} /></button></div>)}
          {!sessions.length && <div className="creator-empty">还没有创作会话。新建一个开始。</div>}
        </div>
      </aside>

      <section className="creator-chat panel">
        <div className="creator-panel-heading"><div><span className="eyebrow">AGENT CONTROL</span><h2>和 Agent 对话</h2></div><Bot size={22} /></div>
        {active ? <>
          <div className="creator-chat-intro"><Sparkles size={17} /><span>告诉我你想制作什么；参考图可选。</span></div>
          {active.conversation.length > 0 && <div className="creator-transcript">{active.conversation.slice(-8).map((turn, index) => <p className={`creator-turn creator-turn-${turn.role}`} key={`${turn.role}-${index}`}><strong>{turn.role === 'user' ? '你' : 'Agent'}</strong>{turn.content}</p>)}</div>}
          <textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder="例如：做一只适合桌面打印的英短猫 Q 版摆件" rows={7} />
          <label className="creator-upload"><ImageIcon size={17} />{reference ? reference.name : '附加参考图'}<input type="file" accept="image/*" onChange={(event) => setReference(event.target.files?.[0] || null)} /></label>
          <button className="primary-button creator-send" disabled={busy || (!message.trim() && !reference)} onClick={() => void prepare()}>{busy ? <Loader2 className="spin" size={16} /> : <Send size={16} />}发送创意</button>
          {active.questions.length > 0 && <div className="creator-questions"><strong>还需要确认</strong>{active.questions.map((question) => <div key={question.field}><p>{question.prompt}</p><div className="creator-options">{question.options.map((option) => <button key={option} onClick={() => setMessage((current) => `${current}${current ? '，' : ''}${option}`)}>{option}</button>)}</div></div>)}</div>}
          {error && <div className="creator-error" role="alert">{error}</div>}
        </> : <div className="creator-empty">选择或新建一个会话。</div>}
      </section>

      <main className="creator-workflow panel">
        <div className="creator-panel-heading"><div><span className="eyebrow">WORKFLOW CANVAS</span><h2>3D 打印创作流程</h2></div>{active && <span className="creator-status"><span className="status-dot" />{statusLabel(active.status)}</span>}</div>
        {active && <div className="creator-restart-row"><span>不满意？</span>{(['brief', 'images', 'model', 'print'] as const).map((stage) => <button key={stage} className="small-action" onClick={() => void action('/restart', { method: 'POST', body: JSON.stringify({ stage }) })}>重做 {stage === 'brief' ? '创意' : stage === 'images' ? '效果图' : stage === 'model' ? '3D 模型' : '打印处理'}</button>)}</div>}
        {active && <div className="creator-canvas">
          <article className="creator-card creator-card-start"><div className="creator-card-icon"><WandSparkles size={20} /></div><div><span className="eyebrow">01 · BRIEF</span><h3>告诉我你的创意</h3><p>{active.brief.subject || active.brief.style || '等待输入主体、风格和作品类型'}</p></div></article>
          <div className="creator-connector" />
          <article className="creator-card"><div className="creator-card-header"><span className="eyebrow">02 · CONCEPTS</span>{active.status === 'awaiting_image_confirmation' && <button className="small-action" onClick={() => void action('/confirm-image')}>确认生成四张图</button>}</div><h3>打印友好的风格图</h3><p>{active.image_prompt || '补全创意后生成标准提示词'}</p>{active.generated_images.length > 0 && <><div className="creator-image-grid">{active.generated_images.map((url, index) => <button className={`creator-image ${active.selected_image_index === index ? 'is-selected' : ''}`} key={url} onClick={() => void action('/select-image', { method: 'POST', body: JSON.stringify({ image_index: index }) })}>{imagePreviews[url] ? <img src={imagePreviews[url]} alt={`候选效果图 ${index + 1}`} /> : <span className="creator-image-loading">加载预览中</span>}<span>{active.selected_image_index === index ? <Check size={16} /> : index + 1}</span></button>)}</div><div className="creator-image-downloads">{active.generated_images.map((url, index) => <button className="creator-download" key={url} onClick={() => void download(url, `candidate-${index + 1}.png`)}><Download size={15} />下载图 {index + 1}</button>)}</div></>}</article>
          <div className="creator-connector" />
          <article className="creator-card"><div className="creator-card-header"><span className="eyebrow">03 · MODEL</span>{active.status === 'awaiting_3d_confirmation' && <button className="small-action" onClick={() => void action('/confirm-3d')}>确认生成 GLB</button>}</div><h3>图生 3D 模型</h3><p>只使用选中的持久化效果图，完成后保存 GLB。</p>{active.model_download_url && <button className="creator-download" onClick={() => void download(active.model_download_url!, 'model.glb')}><Download size={15} />下载 GLB</button>}</article>
          <div className="creator-connector" />
          <article className="creator-card">
            <div className="creator-card-header">
              <span className="eyebrow">04 · COLOR</span>
              {active.print_file.status === 'not_started' && active.status === 'completed' && active.print_analysis.status !== 'succeeded' && <button className="small-action" onClick={() => void action('/print/analyze')}>开始打印分析</button>}
              {active.print_analysis.status === 'succeeded' && active.print_file.status === 'not_started' && <div className="creator-print-confirmation">
                {requiresIssueAcknowledgment && <label className="creator-issue-acknowledgment"><input type="checkbox" checked={acknowledgeIssues} onChange={(event) => setAcknowledgeIssues(event.target.checked)} />我已了解打印分析报告中的问题，并确认继续生成多色 3MF。</label>}
                <button className="small-action" disabled={busy || (requiresIssueAcknowledgment && !acknowledgeIssues)} onClick={() => void generatePrintFile()}>确认生成多色 3MF（最多 8 色）</button>
              </div>}
            </div>
            <h3>多色 3MF 与校准</h3>
            <p>Meshy 多色转换后，可选择几何模式白模，或使用耗材库进行多色校准。</p>
            {active.print_file_download_url && <button className="creator-download" onClick={() => void download(active.print_file_download_url!, 'print.3mf')}><Download size={15} />下载原始 3MF</button>}
            {active.print_file.status === 'succeeded' && !active.geometry_print_file_download_url && <button className="small-action" onClick={() => void action('/print/geometry')}>生成几何白模</button>}
            {active.geometry_print_file_download_url && <><button className="creator-download" onClick={() => void download(active.geometry_print_file_download_url!, 'print-geometry.3mf')}><Download size={15} />下载几何白模 3MF</button><button className="small-action" onClick={() => void pushTask('geometry')}>加入任务清单</button></>}
            {active.print_file.status === 'succeeded' && active.color_calibration.status === 'not_started' && <button className="small-action" onClick={() => void action('/print/calibrate')}>匹配耗材并校准</button>}
            {active.calibrated_print_file_download_url && <><button className="creator-download creator-download-final" onClick={() => void download(active.calibrated_print_file_download_url!, 'print-calibrated.3mf')}><Download size={15} />下载多色校准 3MF</button><button className="small-action" onClick={() => void pushTask('multicolor')}>加入任务清单</button></>}
          </article>
          <div className="creator-events"><h3>运行事件</h3>{active.events.slice(-8).reverse().map((event, index) => <div className="creator-event" key={`${event.stage}-${index}`}><span>{event.stage}</span><p>{event.message}</p></div>)}</div>
        </div>}
      </main>
    </div>
  );
}
