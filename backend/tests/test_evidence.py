import json

from app.services.evidence import readable_evidence


def test_mcp_answer_is_extracted_without_json_envelope():
    answer = "|证券代码|证券简称|评级|\n|---|---|---|\n|603986.SH|兆易创新|AAA|"
    payload = {"id": 9, "jsonrpc": "2.0", "result": {"content": [{"type": "text", "data": {"code": 1, "msg": "success", "data": {"answer": answer}}}]}}
    result = readable_evidence(payload)
    assert result["markdown"] == answer
    assert "jsonrpc" not in result["markdown"]
    assert not result["failed"]


def test_legacy_json_embedded_in_mcp_text_is_also_readable():
    payload = {"result": {"content": [{"type": "text", "text": json.dumps({"data": {"answer": "中文正文\n\n第二段"}})}]}}
    assert readable_evidence(payload)["markdown"] == "中文正文\n\n第二段"


def test_single_wide_record_becomes_indicator_table_without_changing_values():
    table = "|公司|收入|利润|ROE|现金流|\n|---|---|---|---|---|\n|兆易创新|1,234.50|0|12.30%|-8.2|"
    result = readable_evidence({"data": {"answer": table}})["markdown"]
    assert result.startswith("| 指标 | 数据 |")
    assert "| 收入 | 1,234.50 |" in result
    assert "| 利润 | 0 |" in result
    assert "| ROE | 12.30% |" in result
    assert "| 现金流 | -8.2 |" in result


def test_multi_period_table_is_not_transposed():
    table = "|年|收入|\n|---|---|\n|2024|100|\n|2025|120|"
    assert readable_evidence({"answer": table})["markdown"] == table


def test_repeated_identity_is_captioned_and_dates_and_missing_values_are_readable():
    table = "|证券代码|证券简称|日期|收入|\n|---|---|---|---|\n|603986.SH|兆易创新|20250930|0|\n|603986.SH|兆易创新|20260930||"
    markdown = readable_evidence({"answer": table})["markdown"]
    assert "**603986.SH · 兆易创新**" in markdown
    assert "| 日期 | 收入 |" in markdown
    assert "| 2025-09-30 | 0 |" in markdown
    assert "| 2026-09-30 | — |" in markdown


def test_structured_records_render_as_table_with_human_labels_and_zero_values():
    result = readable_evidence({"rows": [{"year": 2024, "revenue": 0}, {"year": 2025, "revenue": 120}]})
    assert "| 年份 | 营业收入 |" in result["markdown"]
    assert "| 2024 | 0 |" in result["markdown"]


def test_failures_and_broken_encoding_are_explicit_not_silently_repaired():
    assert readable_evidence({"collection_error": "请求被限流"})["failed"] is True
    result = readable_evidence({"answer": "不可识别\ufffd文字"})
    assert result["notices"]
    assert "\ufffd" in result["markdown"]


def test_incomplete_json_does_not_become_the_main_reading_content():
    result = readable_evidence({"result": {"content": [{"type": "text", "text": '{"data": "truncated'}]}})
    assert "数据源未返回可展示的正文" in result["markdown"]
    assert result["notices"]


def test_full_saved_content_is_used_beyond_old_excerpt_limit():
    text = "正常中文资料。" * 600 + "正文结尾标记"
    result = readable_evidence({"data": {"answer": text}})
    assert result["markdown"].endswith("正文结尾标记")
    assert len(result["markdown"]) > 3000


def test_indicators_keep_their_source_period_and_unit():
    result = readable_evidence({"answer": "原始资料", "indicators_params": {"营业收入": {"报告期": "2025-12-31", "单位": "万元"}}})
    assert "数据口径" in result["markdown"]
    assert "2025-12-31" in result["markdown"]
    assert "万元" in result["markdown"]
