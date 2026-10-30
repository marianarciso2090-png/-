"""Lossless presentation of saved provider facts, without model-generated claims."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

LABELS = {
    "title": "标题", "content": "正文", "text": "内容", "summary": "摘要",
    "url": "原文链接", "source": "来源", "publish_time": "发布时间",
    "date": "日期", "year": "年份", "period": "报告期", "metric": "指标",
    "value": "数值", "value_percent": "数值（%）", "formula": "计算公式",
    "revenue": "营业收入", "net_profit": "净利润", "operating_cash_flow": "经营现金流",
    "total_assets": "资产总额", "total_liabilities": "负债总额",
}
HIDDEN = {"authorization", "api_key", "token", "ifind_mcp_api_key", "deepseek_api_key", "source_evidence_ids"}


def _cell(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, dict):
        value = "；".join(f"{LABELS.get(str(k), str(k))}：{_cell(v)}" for k, v in value.items() if str(k).lower() not in HIDDEN)
    elif isinstance(value, list):
        value = "、".join(_cell(item) for item in value)
    return str(value).replace("|", "\\|").replace("\r", "").replace("\n", " ")


def _table(records: list[dict]) -> str:
    columns = list(dict.fromkeys(str(key) for record in records for key in record if str(key).lower() not in HIDDEN))
    if not columns:
        return ""
    if len(records) == 1:
        return "| 指标 | 数据 |\n| --- | --- |\n" + "\n".join(f"| {_cell(LABELS.get(key, key))} | {_cell(records[0].get(key))} |" for key in columns)
    return "\n".join([
        "| " + " | ".join(_cell(LABELS.get(key, key)) for key in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
        *("| " + " | ".join(_cell(record.get(key)) for key in columns) + " |" for record in records),
    ])


def _readable_tables(text: str) -> str:
    # Repeated security IDs become a caption, so actual metrics appear first.
    def cells(line: str) -> list[str]:
        line = line.strip()
        if line.startswith("|"): line = line[1:]
        if line.endswith("|") and not line.endswith("\\|"): line = line[:-1]
        return [part.strip() for part in re.split(r"(?<!\\)\|", line)]
    lines = text.replace("\r\n", "\n").splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        if i + 2 < len(lines) and lines[i].strip().startswith("|"):
            header, separator = cells(lines[i]), cells(lines[i + 1])
            if len(header) == len(separator) and all(re.fullmatch(r":?-{3,}:?", part) for part in separator):
                end = i + 2
                rows = []
                while end < len(lines) and lines[end].strip().startswith("|") and len(cells(lines[end])) == len(header):
                    rows.append(cells(lines[end])); end += 1
                if not rows:
                    out.append(lines[i]); i += 1; continue
                fixed = [n for n, name in enumerate(header) if name in {"证券代码", "证券简称", "股票代码", "股票简称"} and rows[0][n] and all(row[n] == rows[0][n] for row in rows)] if len(rows) > 1 else []
                if fixed:
                    out.extend(["**" + " · ".join(rows[0][n] for n in fixed) + "**", ""])
                keep = [n for n in range(len(header)) if n not in fixed]
                visible_header = [header[n] for n in keep]
                visible_rows = []
                changed = bool(fixed)
                for row in rows:
                    visible = []
                    for n in keep:
                        value = row[n] or "—"
                        if header[n] in {"日期", "报告期", "报告日期", "截至日期", "截止日期"} and re.fullmatch(r"\d{8}", value):
                            try: value = datetime.strptime(value, "%Y%m%d").strftime("%Y-%m-%d")
                            except ValueError: pass
                        changed = changed or value != row[n]
                        visible.append(value)
                    visible_rows.append(visible)
                if len(rows) == 1 and len(header) > 4:
                    out.extend(["| 指标 | 数据 |", "| --- | --- |", *(f"| {key} | {value} |" for key, value in zip(visible_header, visible_rows[0]))])
                elif changed and keep:
                    out.extend(["| " + " | ".join(visible_header) + " |", "| " + " | ".join("---" for _ in keep) + " |", *("| " + " | ".join(row) + " |" for row in visible_rows)])
                else:
                    out.extend(lines[i:end])
                i = end
                continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def readable_evidence(payload: Any) -> dict:
    notices: list[str] = []
    failed = False

    def extract(value: Any, depth: int = 0) -> str:
        nonlocal failed
        if depth > 14:
            notices.append("资料嵌套过深，部分内容未展开。")
            return ""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith(("{", "[", '"')):
                try:
                    return extract(json.loads(stripped), depth + 1)
                except (ValueError, TypeError):
                    if stripped.startswith(("{", "[")) and '"' in stripped:
                        notices.append("保存的接口资料不完整，部分内容无法解析。")
                        return ""
            return value
        if isinstance(value, list):
            if value and all(isinstance(item, dict) for item in value) and not any("type" in item for item in value):
                return _table(value)
            return "\n\n".join(filter(None, (extract(item, depth + 1) for item in value)))
        if not isinstance(value, dict):
            return _cell(value)
        if "collection_error" in value:
            failed = True
            return str(value["collection_error"])
        if value.get("isError") is True or value.get("error"):
            failed = True
            notices.append("该资料采集未成功，请勿将其作为分析依据。")
        if "result" in value:
            return extract(value["result"], depth + 1)
        if "structuredContent" in value:
            return extract(value["structuredContent"], depth + 1)
        if "content" in value and isinstance(value["content"], list):
            return extract(value["content"], depth + 1)
        if "answer" in value:
            result = extract(value["answer"], depth + 1)
            if params := value.get("indicators_params"):
                result += "\n\n#### 数据口径\n\n" + _table([params])
            return result
        if "data" in value:
            return extract(value["data"], depth + 1)
        if value.get("type") == "text" and "text" in value:
            return extract(value["text"], depth + 1)
        for name in ("rows", "records", "metrics"):
            if isinstance(value.get(name), list):
                return extract(value[name], depth + 1)
        return _table([value])

    markdown = _readable_tables(extract(payload)).strip()
    if "\ufffd" in markdown:
        notices.append("数据源快照含无法识别的字符，原文可能存在编码损坏。")
    if "[已截断" in markdown:
        notices.append("这份快照含截断内容，不能视为完整原文。")
    if len(markdown) > 100_000:
        markdown = markdown[:100_000]
        notices.append("资料较长，此处展示前 100,000 字符。")
    return {"markdown": markdown or "数据源未返回可展示的正文。", "notices": list(dict.fromkeys(notices)), "failed": failed}
