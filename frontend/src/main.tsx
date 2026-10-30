import { FormEvent, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import ReactMarkdown from "react-markdown";
import { ApiError, api, type Research, type ResearchDetail } from "./api";
import "./styles.css";

const processing = new Set(["queued", "collecting", "analysing", "reviewing"]);

function formatDate(value: string | null): string {
  return value ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}

function statusLabel(status: Research["status"]): string {
  return { queued: "排队中", collecting: "采集 iFinD 数据", analysing: "撰写分析", reviewing: "审阅中", completed: "已完成", failed: "失败" }[status];
}

function Login({ onSuccess }: { onSuccess: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.login(username, password);
      onSuccess();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return <main className="login-shell"><form className="login-card" onSubmit={submit}>
    <p className="eyebrow">PRIVATE RESEARCH</p><h1>A 股个股研究智能体</h1>
    <p>登录后创建可追溯的 iFinD 研究报告。</p>
    <label>管理员用户名<input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required /></label>
    <label>密码<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
    {error && <p className="error" role="alert">{error}</p>}
    <button disabled={busy}>{busy ? "登录中…" : "登录"}</button>
  </form></main>;
}

function ResearchForm({ onCreated }: { onCreated: (run: Research) => void }) {
  const [symbol, setSymbol] = useState("");
  const [asOf, setAsOf] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const run = await api.createResearch(symbol, asOf);
      setSymbol(""); setAsOf(""); onCreated(run);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法创建研究任务");
    } finally { setBusy(false); }
  }
  return <form className="research-form" onSubmit={submit}>
    <label>股票代码或简称<input placeholder="例如：600519 或 贵州茅台" value={symbol} onChange={(event) => setSymbol(event.target.value)} required /></label>
    <label>截至日期（可选）<input type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} /></label>
    <button disabled={busy}>{busy ? "创建中…" : "生成研究报告"}</button>
    {error && <p className="error" role="alert">{error}</p>}
  </form>;
}

function EvidenceList({ evidence }: { evidence: ResearchDetail["evidence"] }) {
  return <details className="evidence"><summary>证据快照（{evidence.length}）</summary>
    {evidence.map((item) => <article key={item.id} className="evidence-item">
      <code>证据:{item.id}</code><p><b>iFinD {item.source_server}/{item.tool_name}</b> · {formatDate(item.captured_at)}</p>
      <p className="muted">请求：{JSON.stringify(item.request_params)}</p><p>{item.excerpt}</p>
    </article>)}
  </details>;
}

function Report({ run }: { run: ResearchDetail }) {
  if (run.status === "failed") return <section className="report empty"><h2>任务失败</h2><p>{run.error_message || "请检查服务配置后重试。"}</p></section>;
  if (processing.has(run.status)) return <section className="report empty"><div className="spinner" /><h2>{statusLabel(run.status)}</h2><p>正在按受控流程采集并审阅数据；完成后本页会自动刷新。</p></section>;
  return <section className="report"><div className="report-toolbar"><span className="pill completed">已完成</span><a className="secondary-button" href={api.markdownUrl(run.id)}>下载 Markdown</a></div>
    {run.report_markdown ? <ReactMarkdown>{run.report_markdown}</ReactMarkdown> : <p>报告内容尚不可用。</p>}
    <EvidenceList evidence={run.evidence} />
  </section>;
}

function Dashboard({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [runs, setRuns] = useState<Research[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ResearchDetail | null>(null);
  const [search, setSearch] = useState("");
  const [filterDate, setFilterDate] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    try { setRuns(await api.listResearches(search, filterDate)); setError(""); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "无法加载历史报告"); }
  }
  useEffect(() => { void refresh(); }, []);
  useEffect(() => { if (!selectedId) return; void api.getResearch(selectedId).then(setDetail).catch((caught) => setError(caught instanceof Error ? caught.message : "无法加载报告")); }, [selectedId]);
  const currentRun = useMemo(() => runs.find((item) => item.id === selectedId), [runs, selectedId]);
  useEffect(() => {
    if (!currentRun || !processing.has(currentRun.status)) return;
    const interval = window.setInterval(() => { void refresh(); void api.getResearch(currentRun.id).then(setDetail).catch(() => undefined); }, 2500);
    return () => window.clearInterval(interval);
  }, [currentRun?.id, currentRun?.status]);

  async function create(run: Research) { setRuns((existing) => [run, ...existing]); setSelectedId(run.id); setDetail(null); }
  async function logout() { await api.logout(); onLogout(); }
  return <main className="app-shell"><header><div><p className="eyebrow">A-SHARE RESEARCH</p><h1>个股研究智能体</h1></div><div className="header-actions"><span>{username}</span><button className="text-button" onClick={() => void logout()}>退出</button></div></header>
    <p className="disclaimer">仅供研究参考，不构成投资建议。报告不包含买入、持有或卖出指令。</p>
    <ResearchForm onCreated={create} />
    {error && <p className="error" role="alert">{error}</p>}
    <div className="workspace"><aside><div className="list-header"><h2>报告历史</h2><button className="text-button" onClick={() => void refresh()}>刷新</button></div>
      <div className="filters"><input aria-label="筛选股票" placeholder="按代码或简称筛选" value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void refresh(); }} />
      <input aria-label="按截至日期筛选" type="date" value={filterDate} onChange={(event) => setFilterDate(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void refresh(); }} /></div>
      <div className="run-list">{runs.map((run) => <button key={run.id} className={`run ${run.id === selectedId ? "selected" : ""}`} onClick={() => setSelectedId(run.id)}>
        <span><b>{run.resolved_name || run.symbol}</b><small>{run.as_of_date || "最新"}</small></span><span className={`pill ${run.status}`}>{statusLabel(run.status)}</span>
      </button>)}{runs.length === 0 && <p className="muted">尚无报告。</p>}</div>
    </aside><div className="content">{detail ? <Report run={detail} /> : <section className="empty"><h2>开始一项研究</h2><p>输入 A 股代码或简称。系统将采集 iFinD 证据、生成研究报告并保存其版本。</p></section>}</div></div>
  </main>;
}

function App() {
  const [username, setUsername] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { void api.me().then(({ username: value }) => setUsername(value)).catch((error: unknown) => { if (!(error instanceof ApiError) || error.status !== 401) console.error(error); }).finally(() => setLoading(false)); }, []);
  if (loading) return <main className="loading">正在加载…</main>;
  return username ? <Dashboard username={username} onLogout={() => setUsername(null)} /> : <Login onSuccess={() => void api.me().then(({ username: value }) => setUsername(value))} />;
}

createRoot(document.getElementById("root")!).render(<App />);
