"""Deterministic calculations over explicitly structured iFinD financial rows.

The provider can return prose snippets as well as tables. This module intentionally
does nothing with prose: a derived number is created only when two or more numeric
values occur in a structured record, so the system never turns ambiguous Chinese
text or units into a false precision calculation.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

PERIOD_KEYS = ("period", "report_date", "date", "year", "报告期", "报告日期", "年份")
ALIASES = {
    "revenue": ("revenue", "营业收入"),
    "net_profit": ("net_profit", "归母净利润", "净利润"),
    "operating_cash_flow": ("operating_cash_flow", "经营活动现金流净额"),
    "total_assets": ("total_assets", "总资产"),
    "total_liabilities": ("total_liabilities", "总负债"),
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    # Strings with Chinese units, commas or percentages are not safe to combine
    # without an explicit provider unit field, and are therefore ignored.
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _records(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _records(child)
    elif isinstance(value, list):
        for child in value:
            yield from _records(child)


def _period(row: dict[str, Any]) -> str | None:
    for key in PERIOD_KEYS:
        value = row.get(key)
        if isinstance(value, (str, int)):
            return str(value)
    return None


def _field(row: dict[str, Any], field: str) -> float | None:
    for alias in ALIASES[field]:
        if alias in row:
            return _number(row[alias])
    return None


def calculate_financial_indicators(payloads: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Return source-addressable derived metrics from structured provider records.

    Each output includes its source evidence ID(s). Callers store this output as a
    separate evidence snapshot, preserving both calculation inputs and provenance.
    """
    series: list[tuple[str, str, dict[str, float]]] = []
    for evidence_id, payload in payloads:
        for row in _records(payload):
            period = _period(row)
            if not period:
                continue
            values = {field: number for field in ALIASES if (number := _field(row, field)) is not None}
            if values:
                series.append((period, evidence_id, values))

    calculated: list[dict[str, Any]] = []
    for field, metric_name in (("revenue", "营业收入同比"), ("net_profit", "归母净利润同比")):
        points = sorted((item for item in series if field in item[2]), key=lambda item: item[0])
        if len(points) >= 2:
            previous, current = points[-2], points[-1]
            baseline = previous[2][field]
            if baseline != 0:
                calculated.append(
                    {
                        "metric": metric_name,
                        "period": current[0],
                        "value_percent": round((current[2][field] / baseline - 1) * 100, 4),
                        "source_evidence_ids": [previous[1], current[1]],
                    }
                )

    for period, evidence_id, values in series:
        if values.get("revenue") not in (None, 0) and "net_profit" in values:
            calculated.append(
                {
                    "metric": "净利率",
                    "period": period,
                    "value_percent": round(values["net_profit"] / values["revenue"] * 100, 4),
                    "source_evidence_ids": [evidence_id],
                }
            )
        if values.get("net_profit") not in (None, 0) and "operating_cash_flow" in values:
            calculated.append(
                {
                    "metric": "经营现金流/归母净利润",
                    "period": period,
                    "value_percent": round(values["operating_cash_flow"] / values["net_profit"] * 100, 4),
                    "source_evidence_ids": [evidence_id],
                }
            )
        if values.get("total_assets") not in (None, 0) and "total_liabilities" in values:
            calculated.append(
                {
                    "metric": "资产负债率",
                    "period": period,
                    "value_percent": round(values["total_liabilities"] / values["total_assets"] * 100, 4),
                    "source_evidence_ids": [evidence_id],
                }
            )
    return calculated
