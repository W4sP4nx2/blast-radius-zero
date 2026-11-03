"use client";

import "./status.css";

import { ChangeEvent, FormEvent, useCallback, useEffect, useRef, useState } from "react";

type Pattern = "code" | "browser";
type IconName = "shield" | "arrow" | "code" | "globe" | "lock" | "cpu" | "clock" | "terminal" | "upload" | "file" | "play" | "check" | "close" | "chevron" | "external" | "copy" | "image" | "alert" | "refresh" | "layers";
type Preset = { id: string; name: string; description: string; pattern: Pattern; code?: string };
type Health = { status?: string; worker_ready?: boolean; browser_ready?: boolean; ai?: { enabled?: boolean; available?: boolean; reason?: string }; limits?: Record<string, unknown> };
type Artifact = { id: string; name: string; mime: string; url: string };
type PendingAction = { id: string; title: string; message: string; revision: string; target?: string; screenshot_url?: string; expires_at: number | string; expired?: boolean };
type Task = { id: string; status: string; pattern: Pattern; source: string; summary?: string; error?: string; result?: Record<string, unknown>; artifacts?: Artifact[]; pending_action?: PendingAction; usage?: Record<string, unknown>[]; policy?: Record<string, unknown> };
type TaskEvent = { id: string; type: string; data: unknown; at?: number | string };
type Notice = { message: string; reason?: string; retryAfter?: number; presets?: string[] };

const DEFAULT_CODE = `import csv, io, json\n\n# No network. No host secrets. A fresh sandbox every run.\nrows = list(csv.DictReader(io.StringIO(\n    "region,revenue\\nNorth,1250\\nSouth,980\\nNorth,1720\\n"\n)))\ntotals = {}\nfor row in rows:\n    region = row["region"]\n    totals[region] = totals.get(region, 0) + int(row["revenue"])\n\nprint(json.dumps({"revenue_by_region": totals}, indent=2))`;
const TERMINAL_STATUSES = new Set(["succeeded", "failed", "blocked", "timed_out", "oom_killed", "output_limit", "cancelled", "infrastructure_error", "awaiting_approval", "approval_pending", "prepared"]);

function Icon({ name, size = 18, className = "" }: { name: IconName; size?: number; className?: string }) {
  const paths: Record<IconName, React.ReactNode> = {
    shield: <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z" /><path d="m8.5 12 2.3 2.3 4.8-5" /></>,
    arrow: <><path d="M5 12h14m-5-5 5 5-5 5" /></>,
    code: <><path d="m8 7-5 5 5 5m8-10 5 5-5 5m-3-13-2 16" /></>,
    globe: <><circle cx="12" cy="12" r="9" /><ellipse cx="12" cy="12" rx="4" ry="9" /><path d="M3 12h18" /></>,
    lock: <><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3" /></>,
    cpu: <><rect x="6" y="6" width="12" height="12" rx="2" /><path d="M9 3v3m6-3v3M9 18v3m6-3v3M3 9h3m-3 6h3m12-6h3m-3 6h3" /><rect x="9" y="9" width="6" height="6" rx="1" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    terminal: <><path d="m5 6 5 5-5 5m8 1h6" /></>,
    upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5" /></>,
    file: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6Zm0 0v6h6M8 13h8m-8 4h5" /></>,
    play: <path d="m8 5 11 7-11 7V5Z" />,
    check: <path d="m5 12 4 4L19 6" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    chevron: <path d="m9 5 7 7-7 7" />,
    external: <><path d="M14 3h7v7m0-7L10 14M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5" /></>,
    copy: <><rect x="8" y="8" width="12" height="13" rx="2" /><path d="M15 8V3H3v12h5" /></>,
    image: <><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8" cy="8" r="1" /><path d="m21 15-6-6L3 21" /></>,
    alert: <><path d="m12 3 10 18H2L12 3Z" /><path d="M12 9v5m0 3h.01" /></>,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6 6a8 8 0 0 1 13 2M5 16a8 8 0 0 0 13 2" /></>,
    layers: <><path d="m12 3 10 5-10 5L2 8l10-5Zm-10 9 10 5 10-5M2 16l10 5 10-5" /></>,
  };
  return <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function eventText(data: unknown): string {
  if (typeof data === "string") return data;
  if (data && typeof data === "object") {
    const value = data as Record<string, unknown>;
    for (const key of ["text", "message", "output", "status", "reason"]) if (typeof value[key] === "string") return value[key] as string;
  }
  return JSON.stringify(data ?? "");
}

function humanStatus(status: string) { return status.replaceAll("_", " "); }

async function jsonResponse(response: Response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail ?? body;
    const message = typeof detail === "string" ? detail : detail.message || detail.reason || `Request failed (${response.status})`;
    const error = new Error(message) as Error & { info?: Notice };
    error.info = { message, reason: detail.reason, retryAfter: Number(detail.retry_after || response.headers.get("Retry-After")) || undefined, presets: detail.available_presets };
    throw error;
  }
  return body;
}

export default function Home() {
  const [pattern, setPattern] = useState<Pattern>("code");
  const [inputMode, setInputMode] = useState<"code" | "task">("code");
  const [code, setCode] = useState(DEFAULT_CODE);
  const [prompt, setPrompt] = useState("");
  const [csrf, setCsrf] = useState("");
  const [health, setHealth] = useState<Health | null>(null);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [upload, setUpload] = useState<{ upload_id: string; name: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [approving, setApproving] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [outputTab, setOutputTab] = useState<"terminal" | "artifacts">("terminal");
  const [copied, setCopied] = useState(false);
  const [connection, setConnection] = useState<"waiting" | "connected" | "reconnecting" | "finished">("waiting");
  const terminalRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const eventIds = useRef(new Set<string>());

  const running = Boolean(taskId && (!task || !TERMINAL_STATUSES.has(task.status)));
  const busy = submitting || running;
  const workerReady = health?.worker_ready === true;
  const browserReady = health?.browser_ready === true;
  const available = workerReady && (pattern === "code" || browserReady);
  const aiAvailable = health?.ai?.available === true;
  const canSubmit = Boolean(csrf && available && !busy && (inputMode === "code" && pattern === "code" ? code.trim() : prompt.trim()));
  const activePresets = presets.filter((preset) => preset.pattern === pattern);
  const screenshots = (task?.artifacts || []).filter((artifact) => artifact.mime.startsWith("image/"));
  const tokenUsage = (task?.usage || []).reduce((total, usage) => {
    const tokens = (usage.tokens || usage.usage || usage) as Record<string, unknown>;
    return total + (Number(tokens.total_tokens) || (Number(tokens.prompt_tokens) || 0) + (Number(tokens.completion_tokens) || 0));
  }, 0);
  const evidence = Array.isArray(task?.result?.evidence) ? task.result.evidence as {title?: string; url?: string; text?: string}[] : [];
  const receipt = task?.result?.receipt as {id?: string; title?: string; message?: string; effect?: string} | undefined;

  const refreshHealth = useCallback(async () => {
    try {
      const result = await fetch("/api/health", { cache: "no-store" }).then(jsonResponse);
      setHealth(result);
    } catch { setHealth(null); }
  }, []);

  useEffect(() => {
    let active = true;
    async function initialize() {
      try {
        const session = await fetch("/api/session", { cache: "no-store" }).then(jsonResponse);
        if (active) setCsrf(session.csrf_token);
      } catch { /* The status bar communicates control-plane availability. */ }
      try {
        const catalog = await fetch("/api/presets", { cache: "no-store" }).then(jsonResponse);
        if (active) setPresets(catalog.presets || []);
      } catch { /* Never fabricate an execution catalog. */ }
    }
    void initialize();
    void refreshHealth();
    const timer = setInterval(() => { void refreshHealth(); void initialize(); }, 30000);
    return () => { active = false; clearInterval(timer); };
  }, [refreshHealth]);

  useEffect(() => {
    if (!taskId) return;
    let active = true;
    let stream: EventSource | null = null;
    let poll: ReturnType<typeof setInterval> | null = null;
    let terminalSeen = false;
    const update = async () => {
      try {
        const snapshot: Task = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, { cache: "no-store" }).then(jsonResponse);
        if (!active) return;
        setTask(snapshot);
        if (TERMINAL_STATUSES.has(snapshot.status)) {
          terminalSeen = true;
        }
      } catch (error) {
        if (active) setNotice((error as Error & { info?: Notice }).info || { message: "The task connection was interrupted. Its deadline remains enforced." });
      }
    };
    stream = new EventSource(`/api/tasks/${encodeURIComponent(taskId)}/events`);
    stream.onopen = () => active && setConnection("connected");
    stream.onmessage = (message) => {
      if (!active) return;
      try {
        const item: TaskEvent = JSON.parse(message.data);
        const id = String(item.id || message.lastEventId);
        if (!eventIds.current.has(id)) {
          eventIds.current.add(id);
          setEvents((current) => [...current, { ...item, id }].slice(-500));
        }
        if (["status", "approval", "artifact", "summary", "usage"].includes(item.type)) void update();
      } catch { /* Ignore incomplete transport data; the status poll remains authoritative. */ }
    };
    stream.addEventListener("end", () => {
      stream?.close();
      if (poll) clearInterval(poll);
      if (active) { setConnection("finished"); void update(); }
    });
    stream.onerror = () => {
      if (terminalSeen) {
        stream?.close(); if (poll) clearInterval(poll);
        if (active) setConnection("finished");
      } else if (active) setConnection("reconnecting");
    };
    void update();
    poll = setInterval(() => void update(), 2500);
    return () => { active = false; stream?.close(); if (poll) clearInterval(poll); };
  }, [taskId]);

  useEffect(() => {
    if (terminalRef.current) terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
  }, [events, outputTab]);

  async function mutate(url: string, body: unknown) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify(body) }).then(jsonResponse);
  }

  async function execute(preset?: Preset) {
    setNotice(null); setSubmitting(true);
    try {
      const payload = preset ? { kind: "preset", preset_id: preset.id, upload_id: upload?.upload_id } : pattern === "code" && inputMode === "code" ? { kind: "code", code_payload: code, upload_id: upload?.upload_id } : { kind: "task", pattern, prompt, upload_id: upload?.upload_id };
      const result = await mutate("/api/execute", payload);
      setTask(null); setEvents([]); eventIds.current.clear(); setTaskId(result.task_id); setOutputTab("terminal"); setConnection("waiting");
    } catch (error) {
      setNotice((error as Error & { info?: Notice }).info || { message: (error as Error).message });
      void refreshHealth();
    } finally { setSubmitting(false); }
  }

  async function attachFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv") || file.size > 2 * 1024 * 1024) {
      setNotice({ message: "Choose a CSV file no larger than 2 MiB." }); return;
    }
    setUploading(true); setNotice(null);
    try {
      const form = new FormData(); form.append("file", file);
      const uploaded = await fetch("/api/uploads", { method: "POST", headers: { "X-CSRF-Token": csrf }, body: form }).then(jsonResponse);
      setUpload(uploaded);
    } catch (error) { setNotice((error as Error & { info?: Notice }).info || { message: (error as Error).message }); }
    finally { setUploading(false); }
  }

  async function approve() {
    if (!task?.pending_action) return;
    setApproving(true); setNotice(null);
    try {
      const result = await mutate(`/api/actions/${encodeURIComponent(task.pending_action.id)}/approve`, {});
      setTask(null); setEvents([]); eventIds.current.clear(); setTaskId(result.task_id); setOutputTab("terminal"); setConnection("waiting");
    } catch (error) { setNotice((error as Error & { info?: Notice }).info || { message: (error as Error).message }); }
    finally { setApproving(false); }
  }

  async function cancel() {
    if (!taskId) return;
    try { await mutate(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, {}); }
    catch (error) { setNotice({ message: (error as Error).message }); }
  }

  function selectPattern(value: Pattern) {
    setPattern(value); setNotice(null);
    if (value === "browser") setInputMode("task");
    else setInputMode("code");
  }

  async function copyLogs() {
    try { await navigator.clipboard.writeText(events.map((item) => `[${item.type}] ${eventText(item.data)}`).join("\n")); setCopied(true); setTimeout(() => setCopied(false), 2000); }
    catch { setNotice({ message: "Clipboard access is unavailable in this browser." }); }
  }

  function submit(event: FormEvent) { event.preventDefault(); if (canSubmit) void execute(); }

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="#" aria-label="Blast Radius Zero home"><span className="brand-mark"><Icon name="shield" size={24} /></span><span>BLAST RADIUS<span className="brand-zero"> ZERO</span><small>EXECUTION CONTROL</small></span></a>
        <nav aria-label="Main navigation"><a className="nav-active" href="#workspace">Workspace</a><a href="#containment">Containment</a><a href="https://lablab.ai/ai-hackathons/vultr-hackathon" target="_blank" rel="noopener noreferrer">The challenge <Icon name="external" size={12} /></a></nav>
        <div className="host-badge"><span className="vultr-symbol">V</span><span>BUILT ON <strong>Vultr</strong></span></div>
      </header>

      <main>
        <section className="intro" aria-labelledby="page-title">
          <div>
            <div className="eyebrow"><span className="tiny-square" /> CONTAINMENT-FIRST AGENTIC EXECUTION <span className="edition">/ 01</span></div>
            <h1 id="page-title">Real work.<br /><span>Visible boundaries.</span></h1>
            <p>Give your agents room to work. Keep their permissions small.<br className="desktop-break" /> Isolated execution, verifiable output, and a clean slate every run.</p>
          </div>
          <div className="architecture" aria-label="Execution architecture">
            <div className="architecture-top"><Icon name="layers" size={16} /><span>ONE CONTROL PLANE</span><span className="architecture-line" /><span>02 PATTERNS</span></div>
            <div className="architecture-flow"><span className="flow-input"><Icon name="terminal" size={18} /> Your task</span><span className="flow-connector">···<Icon name="arrow" size={14} /></span><span className="flow-sandbox"><Icon name="shield" size={22} /><span>Ephemeral<br /><strong>sandbox</strong></span></span><span className="flow-connector">···<Icon name="arrow" size={14} /></span><span className="flow-input"><Icon name="file" size={18} /> Real output</span></div>
            <div className="architecture-footer"><Icon name="lock" size={12} /><span>Fixed policies. Bounded resources. Explicit approval.</span></div>
          </div>
        </section>

        <section className="policy-strip" id="containment" aria-label="Sandbox policy profiles">
          <div><span className="policy-icon"><Icon name="lock" /></span><span><small>NETWORK POLICY</small><strong>{pattern === "code" ? "External access disabled" : "Allowlisted proxy egress"}</strong></span></div>
          <div><span className="policy-icon"><Icon name="cpu" /></span><span><small>RESOURCE CEILING</small><strong>{pattern === "code" ? "256 MiB · 0.5 CPU" : "512 MiB · 1 CPU"}</strong></span></div>
          <div><span className="policy-icon"><Icon name="clock" /></span><span><small>EXECUTION DEADLINE</small><strong>{pattern === "code" ? "10 seconds" : "30 seconds / stage"}</strong></span></div>
          <div><span className="policy-icon"><Icon name="layers" /></span><span><small>LIFECYCLE</small><strong>Fresh sandbox every run</strong></span></div>
        </section>

        <section className="workspace" id="workspace" aria-labelledby="workspace-title">
          <div className="section-heading"><div><span className="section-index">01 /</span><h2 id="workspace-title">Execution workspace</h2><span className="tag">PUBLIC PLAYGROUND</span></div><div className={`availability ${workerReady ? "ready" : "unavailable"}`}><span className="status-dot" />{health === null ? "Control plane offline" : workerReady ? "Worker connected" : "Worker unavailable"}<button className="icon-button" onClick={() => void refreshHealth()} aria-label="Refresh infrastructure status"><Icon name="refresh" size={13} /></button></div></div>
          <div className="ai-availability" role="status"><Icon name="layers" size={12} /><span>{aiAvailable ? "Live AI available · Vultr Inference" : "Live AI unavailable · Use presets"}</span>{health?.ai?.reason && <span className="ai-reason">{health.ai.reason}</span>}</div>

          <div className="workspace-grid">
            <section className="input-panel panel" aria-label="Task input">
              <div className="panel-tabs" role="tablist" aria-label="Execution pattern"><button id="tab-code" role="tab" aria-selected={pattern === "code"} className={pattern === "code" ? "active" : ""} onClick={() => selectPattern("code")}><Icon name="code" size={17} /> Python sandbox<span className="pattern-label">A</span></button><button id="tab-browser" role="tab" aria-selected={pattern === "browser"} className={pattern === "browser" ? "active" : ""} onClick={() => selectPattern("browser")}><Icon name="globe" size={17} /> Browser sandbox<span className="pattern-label">B</span></button></div>
              <form onSubmit={submit}>
                <div className="input-toolbar"><span className="editor-filename"><span className={`language-dot ${pattern}`} />{pattern === "code" && inputMode === "code" ? "main.py" : "task.prompt"}</span>{pattern === "code" ? <div className="mode-switch" aria-label="Input mode"><button type="button" className={inputMode === "code" ? "selected" : ""} onClick={() => setInputMode("code")}>Code</button><button type="button" className={inputMode === "task" ? "selected" : ""} onClick={() => setInputMode("task")}>Ask AI <span>✦</span></button></div> : <span className="text-label">STRUCTURED ACTIONS ONLY</span>}</div>
                {pattern === "code" && inputMode === "code" ? <div className="code-editor"><div className="line-numbers" aria-hidden="true">{Array.from({ length: Math.max(code.split("\n").length, 12) }, (_, index) => <span key={index}>{index + 1}</span>)}</div><textarea ref={editorRef} aria-label="Python source code" spellCheck={false} value={code} onChange={(event) => setCode(event.target.value)} maxLength={65536} onKeyDown={(event) => { if (event.key === "Tab") { event.preventDefault(); const start = event.currentTarget.selectionStart; const end = event.currentTarget.selectionEnd; setCode(code.slice(0, start) + "    " + code.slice(end)); requestAnimationFrame(() => editorRef.current?.setSelectionRange(start + 4, start + 4)); } }} /></div> : <div className="prompt-editor"><label htmlFor="task-prompt">{pattern === "browser" ? "What should the browser do?" : "What would you like to run?"}</label><textarea id="task-prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} maxLength={4000} placeholder={pattern === "browser" ? "Research the top three Hacker News stories and return screenshots with source links…" : "Analyze my sales CSV and summarize revenue by region…"} /><div className="prompt-note"><Icon name="shield" size={13} />{pattern === "browser" ? "Approved sites only. Form submission always requires your approval." : "AI writes the plan. The sandbox controls execution."}</div></div>}
                <div className="editor-footer"><span><Icon name="lock" size={12} />{pattern === "code" ? "Read-only filesystem" : "Private networks blocked"}</span><span>{pattern === "code" && inputMode === "code" ? `${new TextEncoder().encode(code).length.toLocaleString()} / 65,536 bytes` : `${prompt.length} / 4,000 characters`}</span></div>
                <div className="run-controls"><div className="attachment-row"><input ref={fileRef} type="file" accept=".csv,text/csv" className="visually-hidden" onChange={(event) => void attachFile(event)} /><button type="button" className="attach-button" disabled={!csrf || uploading || busy} onClick={() => fileRef.current?.click()}><Icon name={upload ? "file" : "upload"} size={15} />{uploading ? "Uploading…" : upload ? upload.name : "Attach CSV"}</button>{upload ? <button type="button" className="icon-button" aria-label="Remove attached CSV" onClick={() => setUpload(null)}><Icon name="close" size={14} /></button> : <span className="file-hint">OPTIONAL · UP TO 2 MiB</span>}</div><button type="submit" className="execute-button" disabled={!canSubmit}>{busy ? <span className="spinner" /> : <Icon name="play" size={16} />}{submitting ? "Dispatching…" : running ? "Sandbox running…" : "Execute securely"}{!busy && <Icon name="arrow" size={17} />}</button><p className="execution-note">{!available ? pattern === "browser" && workerReady ? "Browser execution is disabled until network preflight passes." : "Connect a healthy execution worker to launch tasks." : pattern === "code" && inputMode === "code" ? "Custom code uses no model calls. Limits apply to every execution." : aiAvailable ? "Live AI uses bounded model calls. Presets below use no inference." : "Live AI is unavailable. Choose a zero-token preset below."}</p></div>
              </form>
            </section>

            <section className="output-panel panel" aria-label="Task results">
              <div className="output-header"><div className="output-tabs" role="tablist" aria-label="Output view"><button role="tab" aria-selected={outputTab === "terminal"} className={outputTab === "terminal" ? "active" : ""} onClick={() => setOutputTab("terminal")}><Icon name="terminal" size={16} />Live terminal</button><button role="tab" aria-selected={outputTab === "artifacts"} className={outputTab === "artifacts" ? "active" : ""} onClick={() => setOutputTab("artifacts")}><Icon name="image" size={15} />Artifacts<span className="count">{task?.artifacts?.length || 0}</span></button></div><button className="icon-button" onClick={() => void copyLogs()} disabled={!events.length} aria-label={copied ? "Logs copied" : "Copy terminal logs"}><Icon name={copied ? "check" : "copy"} size={15} /></button></div>
              <div className="terminal-toolbar"><div className="window-dots"><i /><i /><i /></div><span>brz / {task ? task.id.slice(0, 12) : "awaiting-task"}</span><span className={`terminal-state ${task?.status || "idle"}`}>{task ? humanStatus(task.status) : "IDLE"}</span></div>
              {outputTab === "terminal" ? <div className="terminal-body" ref={terminalRef} aria-live="polite" aria-label="Live execution logs">{events.length ? events.map((item) => <div className={`terminal-entry event-${item.type}`} key={item.id}><span className="log-type">{item.type === "stdout" ? "OUT" : item.type === "stderr" ? "ERR" : item.type.toUpperCase().slice(0, 7)}</span><span>{eventText(item.data)}</span></div>) : <div className="terminal-empty"><div><span className="terminal-prompt">❯</span><span>Ready when you are.</span><span className="cursor" /></div><p>Launch a task to see actual execution logs.<br />Nothing runs outside the sandbox.</p><div className="terminal-divider" /><span className="terminal-empty-hint">stdout · stderr · lifecycle · policy events</span></div>}</div> : <div className="artifacts-body">{task?.artifacts?.length ? task.artifacts.map((artifact) => <div className="artifact" key={artifact.id}>{artifact.mime.startsWith("image/") && <a href={artifact.url} target="_blank" rel="noopener noreferrer"><img src={artifact.url} alt={artifact.name} /></a>}<a href={artifact.url} download={artifact.name}><Icon name={artifact.mime.startsWith("image/") ? "image" : "file"} size={16} /><span>{artifact.name}<small>{artifact.mime}</small></span><Icon name="external" size={14} /></a></div>) : <div className="artifacts-empty"><Icon name="image" size={32} /><strong>Evidence belongs here.</strong><p>Screenshots, generated files, and receipts<br />will appear after a task creates them.</p></div>}</div>}
              <div className="output-footer"><span><span className={`status-dot ${connection === "connected" ? "connected" : ""}`} />{connection === "connected" ? "Live stream connected" : connection === "reconnecting" ? "Reconnecting to stream…" : connection === "finished" ? "Execution stream complete" : "Waiting for execution"}</span>{running && <button onClick={() => void cancel()}>Cancel task <Icon name="close" size={12} /></button>}{task && !running && <span className="source-label">{task.source === "preset" ? "PRESET · NO AI" : task.source === "custom_code" || task.source === "code" ? "CUSTOM CODE" : "LIVE AI"}</span>}</div>
            </section>
          </div>

          {notice && <div className="notice" role="alert"><Icon name="alert" size={18} /><div><strong>{notice.message}</strong>{notice.retryAfter && <p>Try live AI again in {notice.retryAfter} seconds. Available presets still use the same sandbox controls.</p>}{notice.presets?.length ? <p>Choose an available preset below to run a real demo without model calls.</p> : null}</div><button className="icon-button" onClick={() => setNotice(null)} aria-label="Dismiss notification"><Icon name="close" size={15} /></button></div>}

          {task?.summary && <div className="result-summary"><div className="result-icon"><Icon name="file" size={18} /></div><div><span className="text-label">EXECUTION RESULT</span><p>{task.summary}</p></div>{tokenUsage > 0 && <span className="usage-pill">{tokenUsage.toLocaleString()} tokens reported</span>}</div>}
          {evidence.length > 0 && <section className="result-summary" aria-label="Source receipts"><div className="result-icon"><Icon name="globe" size={18} /></div><div><span className="text-label">SOURCE RECEIPTS</span>{typeof task?.result?.captured_at === "number" && <p>Captured {new Date(task.result.captured_at * 1000).toLocaleString()}</p>}{evidence.map((item, index) => <div key={index}><p><strong>{item.title}</strong></p>{item.url?.startsWith("https://") ? <a href={item.url} target="_blank" rel="noopener noreferrer">{item.url}</a> : <span>{item.url}</span>}<p>{item.text}</p></div>)}</div></section>}
          {receipt?.id && <section className="result-summary" aria-label="Trusted demo receipt"><div className="result-icon"><Icon name="check" size={18} /></div><div><span className="text-label">TRUSTED DEMO RECEIPT</span><p><strong>{receipt.title}</strong></p><p>{receipt.message}</p><code>{receipt.id}</code><p>One project-owned demo record. No email or purchase.</p></div></section>}
          {task?.error && <div className="task-error"><Icon name="alert" size={16} /><span>{task.error}</span></div>}

          {task?.pending_action && <section className="approval-panel" aria-labelledby="approval-title"><div className="approval-content"><span className="eyebrow"><Icon name="lock" size={14} /> YOUR APPROVAL REQUIRED</span><h3 id="approval-title">Review before anything is submitted.</h3><p>This action is limited to the project-owned demo form. The preparation browser has been destroyed.</p><dl>{task.pending_action.target && <div><dt>Destination</dt><dd>{task.pending_action.target}</dd></div>}<div><dt>Title</dt><dd>{task.pending_action.title}</dd></div><div><dt>Message</dt><dd>{task.pending_action.message}</dd></div><div><dt>Form revision</dt><dd className="mono">{task.pending_action.revision}</dd></div><div><dt>Approval expires</dt><dd>{new Date(typeof task.pending_action.expires_at === "number" && task.pending_action.expires_at < 1e12 ? task.pending_action.expires_at * 1000 : task.pending_action.expires_at).toLocaleString()}</dd></div></dl><button className="execute-button" onClick={() => void approve()} disabled={approving || busy}>{approving ? <span className="spinner" /> : <Icon name="check" size={17} />}Approve this exact submission<Icon name="arrow" size={17} /></button><small>A changed form needs a new approval. A permit can create only one receipt.</small></div>{task.pending_action.screenshot_url || screenshots[0]?.url ? <a className="approval-image" href={task.pending_action.screenshot_url || screenshots[0]?.url} target="_blank" rel="noopener noreferrer"><img src={task.pending_action.screenshot_url || screenshots[0]?.url} alt="Prepared demo form awaiting approval" /></a> : <div className="approval-image awaiting"><Icon name="image" size={30} /><span>No preparation screenshot was returned.</span></div>}</section>}
        </section>

        <section className="presets-section" aria-labelledby="presets-title"><div className="section-heading"><div><span className="section-index">02 /</span><h2 id="presets-title">Skip the prompt. See the proof.</h2></div><span className="zero-token-tag"><span>✦</span> ZERO MODEL CALLS</span></div><p className="section-description">Prebuilt plans. Real execution. The same boundaries as every other task.</p><div className="preset-grid">{activePresets.length ? activePresets.map((preset, index) => <button className="preset-card" key={preset.id} disabled={!csrf || !available || busy} onClick={() => void execute(preset)}><div className="preset-top"><span className="preset-icon"><Icon name={pattern === "browser" ? index === 0 ? "globe" : index === 1 ? "shield" : "file" : index === 0 ? "file" : index === 1 ? "lock" : "clock"} size={20} /></span><span className="preset-number">{String(index + 1).padStart(2, "0")}</span></div><h3>{preset.name}</h3><p>{preset.description}</p><span className="preset-launch">Run preset <Icon name="arrow" size={16} /></span></button>) : [1, 2, 3].map((item) => <div className="preset-card preset-loading" key={item}><span className="preset-icon"><Icon name={item === 1 ? "file" : item === 2 ? "shield" : "clock"} size={20} /></span><h3>Waiting for preset catalog</h3><p>Connect the control plane to load available sandbox demos.</p><span className="preset-launch">No simulated execution <Icon name="lock" size={14} /></span></div>)}</div></section>

        <section className="trust-note"><span className="trust-note-icon"><Icon name="shield" size={21} /></span><div><strong>Containment is a control, not a claim of invulnerability.</strong><p>Docker shares the host kernel. We publish enforced policies and measured results, and keep unverified controls clearly marked.</p></div><span className="trust-note-label">EVIDENCE OVER ASSUMPTIONS</span></section>
      </main>
      <footer className="site-footer"><span>BLAST RADIUS ZERO <span className="footer-divider">/</span> Built for Agent Rush</span><span><span className="tiny-square" /> Isolated by design. Observable by default.</span><a href="#workspace">Back to workspace <Icon name="arrow" size={13} /></a></footer>
    </div>
  );
}
