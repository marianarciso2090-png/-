import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Evidence } from "../api";

function EvidenceMarkdown({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        table: ({ children }) => (
          <>
            <p className="evidence-table-hint">
              宽表可左右滑动查看 · — 表示数据源未提供
            </p>
            <div
              className="evidence-table-scroll"
              role="region"
              aria-label="证据数据表"
              tabIndex={0}
            >
              <table>{children}</table>
            </div>
          </>
        ),
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noreferrer">
            {children}
          </a>
        ),
      }}
    >
      {text}
    </ReactMarkdown>
  );
}

export function EvidenceContent({ item }: { item: Evidence }) {
  const content = item.readable;
  const [body, ...parameters] = (
    content?.markdown || "该资料尚未完成阅读格式整理，请刷新页面后重试。"
  ).split("\n\n#### 数据口径\n\n");
  return (
    <div className="evidence-body">
      <div className="evidence-context">
        <span>查询范围</span>
        <p>
          {typeof item.request_params.query === "string"
            ? item.request_params.query
            : "根据已采集财务资料计算相关指标"}
        </p>
      </div>
      {content?.failed && (
        <p className="evidence-warning" role="status">
          该项资料未采集成功，不能作为研究结论的依据。
        </p>
      )}
      {content?.notices.map((notice, index) => (
        <p className="evidence-warning" key={index}>
          {notice}
        </p>
      ))}
      <div className="readable-evidence">
        <EvidenceMarkdown text={body} />
        {parameters.length > 0 && (
          <details className="evidence-parameters">
            <summary>查看数据口径与单位</summary>
            <EvidenceMarkdown text={parameters.join("\n\n")} />
          </details>
        )}
      </div>
      <details className="evidence-audit">
        <summary>查看核验详情</summary>
        <dl>
          <dt>证据编号</dt>
          <dd>{item.id}</dd>
          <dt>快照校验值</dt>
          <dd>{item.response_sha256}</dd>
        </dl>
        <details>
          <summary>原始接口摘要</summary>
          <pre>{item.excerpt}</pre>
        </details>
      </details>
    </div>
  );
}
