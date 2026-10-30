import { type FormEvent, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import ReactMarkdown from "react-markdown";
import { ApiError, api, type Research, type ResearchDetail } from "./api";
import "./styles.css";

const active = new Set(["queued", "collecting", "analysing", "reviewing"]);
const labels = {
  queued: "等待开始",
  collecting: "采集数据",
  analysing: "生成分析",
  reviewing: "审阅报告",
  completed: "已完成",
  failed: "未完成",
};
const stages = ["queued", "collecting", "analysing", "reviewing", "completed"];
const stageNames = [
  "创建任务",
  "采集证据",
  "基本面分析",
  "报告审阅",
  "研究完成",
];
const toolNames: Record<string, string> = {
  get_stock_info: "公司资料",
  get_stock_financials: "财务数据",
  get_stock_performance: "行情与估值",
  get_stock_shareholders: "股东结构",
  get_risk_indicators: "风险指标",
  get_stock_events: "重大事件",
  get_esg_data: "ESG 评级",
  search_stocks: "可比公司",
  search_notice: "公司公告",
  search_news: "新闻资讯",
  financial_calculations: "财务指标计算",
};
type IconName =
  | "grid"
  | "file"
  | "plus"
  | "arrow"
  | "search"
  | "refresh"
  | "download"
  | "logout"
  | "check"
  | "layers"
  | "close";
function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, string> = {
    grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
    file: "M14 2H5v20h14V7z M14 2v6h5 M8 12h8 M8 16h6",
    plus: "M12 5v14 M5 12h14",
    arrow: "M4 12h16 M14 6l6 6-6 6",
    search: "M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
    refresh: "M20 7a9 9 0 1 0 1 9 M20 2v6h-6",
    download: "M12 3v12 M7 10l5 5 5-5 M4 16v5h16v-5",
    logout: "M9 4H4v16h5 M10 12h11 M16 7l5 5-5 5",
    check: "M5 12l4 4L19 6",
    layers: "M12 3L2 8l10 5 10-5z M2 12l10 5 10-5 M2 16l10 5 10-5",
    close: "M6 6l12 12 M18 6L6 18",
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
function date(value: string | null) {
  if (!value) return "—";
  // Backend timestamps without an offset are UTC.
  const parsed = new Date(
    /(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`,
  );
  return Number.isNaN(parsed.valueOf())
    ? "—"
    : new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Shanghai",
      }).format(parsed);
}
function today() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}
function Badge({ status }: { status: Research["status"] }) {
  return (
    <span className={`badge ${status}`}>
      <i />
      {labels[status]}
    </span>
  );
}
function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark">
        <Icon name="layers" size={23} />
      </span>
      <div>
        研序<span>RESEARCH STUDIO</span>
      </div>
    </div>
  );
}

function Login({ onSuccess }: { onSuccess: () => void }) {
  const [username, setUsername] = useState("admin");
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
    } catch (e) {
      setError(e instanceof Error ? e.message : "登录失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-shell">
      <section className="login-intro">
        <Brand />
        <div>
          <p className="eyebrow">A CLEARER VIEW OF VALUE</p>
          <h1>
            让每一份研究，
            <br />
            都有据可循。
          </h1>
          <p>
            从公司经营到财务质量，
            <br />
            把分散的信息，整理成清晰的判断。
          </p>
          <div className="intro-line">
            <span>01 数据</span>
            <b>—</b>
            <span>02 分析</span>
            <b>—</b>
            <span>03 证据</span>
          </div>
        </div>
        <small>专注 A 股 · 长期视角 · 可追溯研究</small>
      </section>
      <section className="login-area">
        <form className="login-card" onSubmit={submit}>
          <span className="eyebrow">YOUR RESEARCH SPACE</span>
          <h2>进入研究工作台</h2>
          <p className="subtle">登录你的专属空间，开始一次深入研究。</p>
          <label>
            用户名
            <input
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </label>
          <label>
            密码
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button className="primary" disabled={busy}>
            {busy ? "正在登录…" : "登录工作台"}
            <Icon name="arrow" />
          </button>
          <p className="login-foot">仅供研究参考，不构成投资建议</p>
        </form>
      </section>
    </main>
  );
}

function ResearchForm({
  onCreated,
  retryTarget,
}: {
  onCreated: (run: Research) => void;
  retryTarget: Research | null;
}) {
  const [symbol, setSymbol] = useState("");
  const [asOf, setAsOf] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!retryTarget) return;
    setSymbol(retryTarget.symbol);
    setAsOf(retryTarget.as_of_date || "");
    setError("");
    document.getElementById("symbol-input")?.focus();
    document
      .getElementById("new-research")
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [retryTarget]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!symbol.trim()) return;
    setBusy(true);
    setError("");
    try {
      onCreated(await api.createResearch(symbol.trim(), asOf));
      setSymbol("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "无法创建研究任务");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="new-research" id="new-research">
      <div className="section-heading">
        <span className="heading-icon">
          <Icon name="plus" />
        </span>
        <h2>开始新的研究</h2>
        <span className="section-note">从一家公司开始，理解价值的来源</span>
      </div>
      <form onSubmit={submit}>
        <label className="symbol-field">
          研究标的
          <div className="input-wrap">
            <Icon name="search" />
            <input
              id="symbol-input"
              placeholder="输入 A 股代码或公司简称"
              value={symbol}
              maxLength={32}
              onChange={(e) => setSymbol(e.target.value)}
              required
            />
          </div>
        </label>
        <label className="date-field">
          研究截至日 <span>可选</span>
          <input
            aria-label="研究截至日"
            type="date"
            value={asOf}
            max={today()}
            onChange={(e) => setAsOf(e.target.value)}
          />
          <small>留空使用最新可得数据</small>
        </label>
        <button className="primary" disabled={busy || !symbol.trim()}>
          {busy ? "正在创建…" : "开始研究"}
          <Icon name="arrow" />
        </button>
        {error && (
          <p className="error form-error" role="alert">
            {error}
          </p>
        )}
      </form>
      <div className="form-foot">
        <span className="live-dot" />
        iFinD 数据支持<span className="foot-divider">/</span>DeepSeek 深度分析
        <span className="auto-note">自动采集 · 生成分析 · 审阅存档</span>
      </div>
    </section>
  );
}

function Evidence({
  items,
  targetId,
}: {
  items: ResearchDetail["evidence"];
  targetId: string | null;
}) {
  const [query, setQuery] = useState("");
  useEffect(() => {
    if (!targetId) return;
    const element = document.getElementById(
      `evidence-${targetId}`,
    ) as HTMLDetailsElement | null;
    if (element) {
      element.open = true;
      element.scrollIntoView({ behavior: "smooth", block: "center" });
      element.querySelector("summary")?.focus();
    }
  }, [targetId]);
  const filtered = items.filter((item) =>
    `${toolNames[item.tool_name] || item.tool_name} ${item.id} ${item.excerpt}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <div className="evidence-view">
      <p className="subtle">每条证据保留采集时间与查询口径，便于交叉核验。</p>
      <div className="input-wrap evidence-search">
        <Icon name="search" />
        <input
          aria-label="搜索证据"
          placeholder="搜索来源、证据编号或内容"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      {filtered.map((item) => (
        <details
          className="evidence-item"
          id={`evidence-${item.id}`}
          key={item.id}
        >
          <summary>
            <span className="evidence-number">
              {String(items.indexOf(item) + 1).padStart(2, "0")}
            </span>
            <span>
              <b>{toolNames[item.tool_name] || item.tool_name}</b>
              <small>
                {item.source_server === "derived" ? "财务计算" : "同花顺 iFinD"}{" "}
                · {date(item.captured_at)}
              </small>
            </span>
            <span className="evidence-expand">展开 +</span>
          </summary>
          <div className="evidence-body">
            <code>证据编号：{item.id}</code>
            <p>
              查询口径：
              {String(
                item.request_params.query ||
                  JSON.stringify(item.request_params),
              )}
            </p>
            <pre>{item.excerpt}</pre>
            <small>SHA-256：{item.response_sha256}</small>
          </div>
        </details>
      ))}
      {!filtered.length && (
        <div className="small-empty">
          {items.length ? "没有匹配的证据" : "暂无证据快照"}
        </div>
      )}
    </div>
  );
}
function Report({
  run,
  onRetry,
}: {
  run: ResearchDetail;
  onRetry: () => void;
}) {
  const [tab, setTab] = useState<"report" | "evidence">("report");
  const [targetEvidence, setTargetEvidence] = useState<string | null>(null);
  const reportText = (run.report_markdown || "")
    .split("\n## 证据附录")[0]
    .replace(/\[证据:([^\]]+)\]/g, (original, id: string) => {
      const index = run.evidence.findIndex((item) => item.id === id);
      return index < 0
        ? original
        : `[证据 ${index + 1}](#evidence-${encodeURIComponent(id)})`;
    });
  const step = stages.indexOf(run.status);
  return (
    <section className="report-panel">
      <div className="report-top">
        <div>
          <p className="eyebrow">RESEARCH REPORT</p>
          <h2>
            {run.resolved_name || run.symbol}
            <span>基本面研究</span>
          </h2>
          <p className="report-meta">
            {run.as_of_date ? `截至 ${run.as_of_date}` : "最新可得数据"}{" "}
            <span>·</span> 创建于 {date(run.created_at)}
          </p>
        </div>
        <Badge status={run.status} />
      </div>
      {active.has(run.status) ? (
        <div className="progress-view" aria-live="polite">
          <div className="progress-orbit">
            <Icon name="layers" size={28} />
          </div>
          <h3>{labels[run.status]}</h3>
          <p className="subtle">研究正在进行，完成后会自动显示报告。</p>
          <ol className="step-list">
            {stageNames.map((name, i) => (
              <li
                key={name}
                className={i < step ? "done" : i === step ? "current" : ""}
              >
                <span>
                  {i < step ? <Icon name="check" size={13} /> : i + 1}
                </span>
                {name}
              </li>
            ))}
          </ol>
          <p className="progress-note">你可以查看其他研究，任务会继续运行。</p>
        </div>
      ) : run.status === "failed" ? (
        <div className="report-failure">
          <span className="failure-icon">!</span>
          <h3>这次研究未能完成</h3>
          <p>{run.error_message || "服务暂时不可用，请稍后重试。"}</p>
          <button className="secondary" onClick={onRetry}>
            <Icon name="refresh" />
            重新研究该标的
          </button>
        </div>
      ) : (
        <>
          <div className="report-nav">
            <div className="tabs" role="tablist" aria-label="研究内容">
              <button
                role="tab"
                aria-selected={tab === "report"}
                onClick={() => setTab("report")}
              >
                研究报告
              </button>
              <button
                role="tab"
                aria-selected={tab === "evidence"}
                onClick={() => {
                  setTargetEvidence(null);
                  setTab("evidence");
                }}
              >
                证据来源 <span>{run.evidence.length}</span>
              </button>
            </div>
            {run.report_markdown && (
              <a className="download" href={api.markdownUrl(run.id)}>
                <Icon name="download" size={16} />
                <span>导出报告</span>
              </a>
            )}
          </div>
          <div role="tabpanel">
            {tab === "report" ? (
              <article className="markdown">
                {run.report_markdown ? (
                  <ReactMarkdown
                    components={{
                      a: ({ href, children }) => (
                        <a
                          href={href}
                          onClick={(event) => {
                            if (!href?.startsWith("#evidence-")) return;
                            event.preventDefault();
                            const id = decodeURIComponent(
                              href.slice("#evidence-".length),
                            );
                            if (run.evidence.some((item) => item.id === id)) {
                              setTargetEvidence(id);
                              setTab("evidence");
                            }
                          }}
                        >
                          {children}
                        </a>
                      ),
                    }}
                  >
                    {reportText}
                  </ReactMarkdown>
                ) : (
                  <p className="subtle">报告内容暂不可用，请刷新后重试。</p>
                )}
              </article>
            ) : (
              <Evidence items={run.evidence} targetId={targetEvidence} />
            )}
          </div>
        </>
      )}
    </section>
  );
}
function EmptyReport() {
  return (
    <section className="report-panel report-welcome">
      <div className="welcome-visual">
        <div className="paper">
          <div className="paper-icon">
            <Icon name="file" size={24} />
          </div>
          <i />
          <i />
          <i />
          <div className="mini-bars">
            <b />
            <b />
            <b />
            <b />
            <b />
          </div>
        </div>
        <span className="paper-check">
          <Icon name="check" size={18} />
        </span>
      </div>
      <p className="eyebrow">BUILD YOUR CONVICTION</p>
      <h2>好的研究，从一个问题开始</h2>
      <p>
        输入一家你关注的公司，
        <br />
        让数据、分析和证据形成完整的研究脉络。
      </p>
      <div className="welcome-features">
        <span>
          <Icon name="layers" size={16} />
          多维基本面
        </span>
        <span>
          <Icon name="file" size={16} />
          证据可追溯
        </span>
        <span>
          <Icon name="download" size={16} />
          报告可导出
        </span>
      </div>
    </section>
  );
}

function Dashboard({
  username,
  onLogout,
}: {
  username: string;
  onLogout: () => void;
}) {
  const [runs, setRuns] = useState<Research[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ResearchDetail | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [error, setError] = useState("");
  const [listLoading, setListLoading] = useState(true);
  const [detailError, setDetailError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [logoutBusy, setLogoutBusy] = useState(false);
  const [retryTarget, setRetryTarget] = useState<Research | null>(null);
  const selectedRef = useRef(selectedId);
  selectedRef.current = selectedId;
  const inProgress = runs.some((run) => active.has(run.status));
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await api.listResearches();
        if (!cancelled) {
          setRuns(data);
          setError("");
        }
      } catch (e) {
        if (!cancelled) {
          if (e instanceof ApiError && e.status === 401) onLogout();
          else setError("研究记录加载失败，请检查网络后重试。");
        }
      } finally {
        if (!cancelled) setListLoading(false);
      }
    }
    void load();
    const interval = inProgress
      ? window.setInterval(() => void load(), 3000)
      : undefined;
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [refreshKey, inProgress]);
  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    let timer: number | undefined;
    setDetail(null);
    setDetailError("");
    async function load() {
      try {
        const data = await api.getResearch(selectedId!);
        if (cancelled || selectedRef.current !== data.id) return;
        setDetail(data);
        setDetailError("");
        setRuns((existing) =>
          existing.map((run) => (run.id === data.id ? data : run)),
        );
        if (active.has(data.status))
          timer = window.setTimeout(() => void load(), 2500);
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 401) {
          onLogout();
          return;
        }
        setDetailError("报告暂时无法加载，请重试。");
      }
    }
    void load();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [selectedId, refreshKey]);
  function created(run: Research) {
    setRuns((existing) => [run, ...existing]);
    setSelectedId(run.id);
  }
  async function logout() {
    setLogoutBusy(true);
    try {
      await api.logout();
      onLogout();
    } catch {
      setError("退出失败，请稍后重试。");
    } finally {
      setLogoutBusy(false);
    }
  }
  const filtered = runs.filter(
    (run) =>
      `${run.symbol} ${run.resolved_name || ""}`
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (filter === "all" ||
        (filter === "active" ? active.has(run.status) : run.status === filter)),
  );
  const completeCount = runs.filter((run) => run.status === "completed").length;
  const activeCount = runs.filter((run) => active.has(run.status)).length;
  return (
    <div className="app-layout">
      <aside className="sidebar">
        <Brand />
        <div className="nav-label">工作空间</div>
        <a className="nav-item current-nav" href="#workspace">
          <Icon name="grid" />
          研究工作台<span>01</span>
        </a>
        <a className="nav-item" href="#history">
          <Icon name="file" />
          研究记录<span>{runs.length}</span>
        </a>
        <button
          className="new-button"
          onClick={() => {
            document.getElementById("symbol-input")?.focus();
            document
              .getElementById("new-research")
              ?.scrollIntoView({ behavior: "smooth", block: "center" });
          }}
        >
          <Icon name="plus" />
          新建研究
        </button>
        <div className="sidebar-bottom">
          <div className="source-note">
            <span className="live-dot" />
            研究数据来源<b>同花顺 iFinD</b>
            <small>事实有来源，判断有依据。</small>
          </div>
          <div className="account">
            <span className="avatar">{username[0]?.toUpperCase()}</span>
            <div>
              <b>{username}</b>
              <small>个人研究空间</small>
            </div>
            <button
              className="icon-button"
              title="退出登录"
              aria-label="退出登录"
              disabled={logoutBusy}
              onClick={() => void logout()}
            >
              <Icon name="logout" size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-layout">
        <header className="topbar">
          <span>
            工作空间 <span className="slash">/</span> <b>研究工作台</b>
          </span>
          <span className="topbar-note">
            <span className="live-dot" />
            专注长期价值
          </span>
        </header>
        <main className="main-content" id="workspace">
          <div className="page-heading">
            <div>
              <p className="eyebrow">RESEARCH WORKSPACE</p>
              <h1>
                研究工作台<span>把信息变成洞察。</span>
              </h1>
              <p>聚焦公司基本面，构建有证据支撑的研究判断。</p>
            </div>
            <span className="workspace-tag">A 股研究</span>
          </div>
          <div className="stats">
            <div>
              <span>研究记录</span>
              <b>
                {String(runs.length).padStart(2, "0")}
                <small>份研究</small>
              </b>
              <Icon name="file" size={23} />
            </div>
            <div>
              <span>已完成报告</span>
              <b>
                {String(completeCount).padStart(2, "0")}
                <small>份已归档</small>
              </b>
              <Icon name="check" size={23} />
            </div>
            <div>
              <span>进行中的研究</span>
              <b>
                {String(activeCount).padStart(2, "0")}
                <small>{activeCount ? "自动更新中" : "准备好新的探索"}</small>
              </b>
              <Icon name="layers" size={23} />
            </div>
          </div>
          <ResearchForm onCreated={created} retryTarget={retryTarget} />
          {error && (
            <div className="error-banner" role="alert">
              {error}
              <button onClick={() => setRefreshKey((v) => v + 1)}>重试</button>
            </div>
          )}
          <div className="workspace">
            <section className="history-panel" id="history">
              <div className="history-heading">
                <h2>
                  研究记录<span>{runs.length}</span>
                </h2>
                <button
                  className="icon-button"
                  title="刷新记录"
                  aria-label="刷新记录"
                  onClick={() => setRefreshKey((v) => v + 1)}
                >
                  <Icon name="refresh" size={16} />
                </button>
              </div>
              <div className="history-search input-wrap">
                <Icon name="search" size={16} />
                <input
                  aria-label="搜索研究记录"
                  placeholder="搜索代码或公司"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                {search && (
                  <button
                    className="icon-button"
                    aria-label="清空搜索"
                    onClick={() => setSearch("")}
                  >
                    <Icon name="close" size={13} />
                  </button>
                )}
              </div>
              <div className="history-filters" aria-label="按状态筛选">
                {[
                  ["all", "全部"],
                  ["completed", "已完成"],
                  ["active", "进行中"],
                  ["failed", "未完成"],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    aria-pressed={filter === value}
                    className={filter === value ? "chosen" : ""}
                    onClick={() => setFilter(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="run-list">
                {filtered.map((run) => (
                  <button
                    className={`run ${run.id === selectedId ? "selected" : ""}`}
                    key={run.id}
                    onClick={() => setSelectedId(run.id)}
                    aria-pressed={run.id === selectedId}
                  >
                    <div className="run-title">
                      <b>{run.resolved_name || run.symbol}</b>
                      <Badge status={run.status} />
                    </div>
                    <p>{run.resolved_name ? run.symbol : "A 股基本面研究"}</p>
                    <div className="run-meta">
                      <span>{date(run.created_at)}</span>
                      <span>{run.as_of_date || "最新数据"}</span>
                    </div>
                  </button>
                ))}
                {!filtered.length && (
                  <div className="small-empty">
                    <Icon name="file" size={24} />
                    <p>
                      {listLoading
                        ? "正在加载研究记录…"
                        : search || filter !== "all"
                          ? "没有匹配的研究"
                          : "你的第一份研究，从这里开始"}
                    </p>
                    {(search || filter !== "all") && (
                      <button
                        className="text-button"
                        onClick={() => {
                          setSearch("");
                          setFilter("all");
                        }}
                      >
                        清除筛选
                      </button>
                    )}
                  </div>
                )}
              </div>
              <div className="history-foot">
                {runs.length >= 50
                  ? "显示最近 50 份研究"
                  : "每次研究独立保存，随时回看"}
              </div>
            </section>
            <div className="report-container">
              {detailError ? (
                <section className="report-panel small-empty" role="alert">
                  <p>{detailError}</p>
                  <button
                    className="secondary"
                    onClick={() => setRefreshKey((v) => v + 1)}
                  >
                    重新加载
                  </button>
                </section>
              ) : detail && detail.id === selectedId ? (
                <Report
                  key={detail.id}
                  run={detail}
                  onRetry={() => {
                    setRetryTarget({ ...detail });
                  }}
                />
              ) : selectedId ? (
                <section className="report-panel report-loading" role="status">
                  <div className="spinner" />
                  <p>正在打开研究报告…</p>
                </section>
              ) : (
                <EmptyReport />
              )}
            </div>
          </div>
          <footer className="page-footer">
            <span>研序 · 让研究更有条理</span>
            <span>仅供研究参考，不构成投资建议</span>
          </footer>
        </main>
      </div>
    </div>
  );
}

function App() {
  const [username, setUsername] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  async function checkSession() {
    setError("");
    setLoading(true);
    try {
      setUsername((await api.me()).username);
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401))
        setError("无法连接研究服务，请检查服务是否启动。");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void checkSession();
  }, []);
  if (loading)
    return (
      <main className="loading" role="status">
        <Brand />
        <div className="spinner" />
        <p>正在进入研究空间…</p>
      </main>
    );
  if (error)
    return (
      <main className="loading">
        <Brand />
        <p role="alert">{error}</p>
        <button className="secondary" onClick={() => void checkSession()}>
          重新连接
        </button>
      </main>
    );
  return username ? (
    <Dashboard username={username} onLogout={() => setUsername(null)} />
  ) : (
    <Login onSuccess={() => void checkSession()} />
  );
}
createRoot(document.getElementById("root")!).render(<App />);
