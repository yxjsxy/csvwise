#!/usr/bin/env python3
"""Tests for csvwise v0.2.0 (no LLM required)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import csvwise


# ---------------------------------------------------------------------------
# Original tests (preserved)
# ---------------------------------------------------------------------------

def test_load_csv():
    """Test CSV loading with various formats."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("name,age,city\nAlice,30,NYC\nBob,25,LA\n")
        f.flush()
        headers, data, delim = csvwise.load_csv(f.name)
        assert headers == ["name", "age", "city"]
        assert len(data) == 2
        assert delim == ","
    os.unlink(f.name)


def test_infer_column_types():
    headers = ["name", "score", "date"]
    data = [
        ["Alice", "95.5", "2026-01-01"],
        ["Bob", "88.0", "2026-01-02"],
        ["Charlie", "72.3", "2026-01-03"],
    ]
    types = csvwise.infer_column_types(headers, data)
    assert types["name"] == "text"
    assert types["score"] == "numeric"
    assert types["date"] == "date"


def test_compute_basic_stats():
    headers = ["item", "price"]
    data = [
        ["A", "10"],
        ["B", "20"],
        ["C", "30"],
        ["D", "40"],
        ["E", "50"],
    ]
    types = {"item": "text", "price": "numeric"}
    stats = csvwise.compute_basic_stats(headers, data, types)
    assert "price" in stats
    assert stats["price"]["min"] == 10
    assert stats["price"]["max"] == 50
    assert stats["price"]["mean"] == 30
    assert stats["price"]["sum"] == 150


def test_csv_to_markdown_table():
    headers = ["a", "b"]
    data = [["1", "2"], ["3", "4"]]
    md = csvwise.csv_to_markdown_table(headers, data)
    assert "| a | b |" in md
    assert "| 1 | 2 |" in md
    assert "| --- | --- |" in md


def test_truncate():
    assert csvwise.truncate("short") == "short"
    long = "x" * 300
    assert csvwise.truncate(long).endswith("...")
    assert len(csvwise.truncate(long)) == 203  # 200 + "..."


def test_build_schema_prompt():
    headers = ["name", "value"]
    data = [["test", "100"], ["demo", "200"]]
    types = {"name": "text", "value": "numeric"}
    prompt = csvwise.build_schema_prompt(headers, data, types)
    assert "name" in prompt
    assert "numeric" in prompt


def test_gbk_csv():
    """Test GBK encoded CSV."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        content = "姓名,年龄,城市\n张三,25,北京\n李四,30,上海\n"
        f.write(content.encode("gbk"))
        f.flush()
        headers, data, delim = csvwise.load_csv(f.name)
        assert headers[0] == "姓名"
        assert data[0][0] == "张三"
    os.unlink(f.name)


# ---------------------------------------------------------------------------
# New tests for v0.2.0 features
# ---------------------------------------------------------------------------

def test_compute_basic_stats_extended():
    """Test that stats now include std_dev, q1, q3, iqr."""
    headers = ["item", "price"]
    data = [
        ["A", "10"], ["B", "20"], ["C", "30"], ["D", "40"], ["E", "50"],
    ]
    types = {"item": "text", "price": "numeric"}
    stats = csvwise.compute_basic_stats(headers, data, types)
    assert "std_dev" in stats["price"]
    assert "q1" in stats["price"]
    assert "q3" in stats["price"]
    assert "iqr" in stats["price"]
    assert stats["price"]["std_dev"] > 0


def test_detect_outliers():
    """Test IQR outlier detection."""
    headers = ["name", "value"]
    data = [
        ["A", "10"], ["B", "12"], ["C", "11"], ["D", "13"],
        ["E", "10"], ["F", "12"], ["G", "11"], ["H", "100"],  # 100 is outlier
    ]
    types = {"name": "text", "value": "numeric"}
    stats = csvwise.compute_basic_stats(headers, data, types)
    outliers = csvwise.detect_outliers(headers, data, types, stats)
    assert "value" in outliers
    assert outliers["value"]["count"] >= 1
    assert 100 in outliers["value"]["values"]


def test_detect_outliers_no_outliers():
    """Test that normal data has no outliers."""
    headers = ["x"]
    data = [["10"], ["11"], ["12"], ["13"], ["14"], ["15"]]
    types = {"x": "numeric"}
    stats = csvwise.compute_basic_stats(headers, data, types)
    outliers = csvwise.detect_outliers(headers, data, types, stats)
    assert len(outliers) == 0


def test_data_quality_score():
    """Test quality score computation."""
    headers = ["name", "value"]
    data = [["Alice", "100"], ["Bob", "200"], ["", "300"]]
    types = {"name": "text", "value": "numeric"}
    _, details = csvwise.infer_advanced_types(headers, data)
    score = csvwise.compute_data_quality_score(headers, data, types, details)
    assert "overall" in score
    assert "completeness" in score
    assert "consistency" in score
    assert "validity" in score
    assert 0 <= score["overall"] <= 100
    # One empty name out of 6 cells = some loss
    assert score["completeness"] < 100


def test_data_quality_score_perfect():
    """Test perfect quality data."""
    headers = ["a", "b"]
    data = [["x", "1"], ["y", "2"], ["z", "3"]]
    types = {"a": "text", "b": "numeric"}
    _, details = csvwise.infer_advanced_types(headers, data)
    score = csvwise.compute_data_quality_score(headers, data, types, details)
    assert score["completeness"] == 100
    assert score["validity"] == 100


def test_suggest_visualizations():
    """Test visualization suggestions."""
    headers = ["date", "product", "sales"]
    types = {"date": "date", "product": "text", "sales": "numeric"}
    stats = {"sales": {"count": 10, "min": 1, "max": 100, "mean": 50, "median": 50, "sum": 500, "std_dev": 30, "q1": 25, "q3": 75, "iqr": 50}}
    data = [
        ["2026-01-01", "A", "100"],
        ["2026-01-02", "B", "200"],
        ["2026-01-03", "A", "150"],
    ]
    suggestions = csvwise.suggest_visualizations(headers, types, stats, data)
    assert len(suggestions) > 0
    types_found = [s["type"] for s in suggestions]
    # Should suggest line chart for date + numeric
    assert any("折线图" in t for t in types_found)


def test_infer_advanced_types():
    """Test advanced type inference with cardinality."""
    headers = ["name", "score", "active"]
    data = [
        ["Alice", "95", "yes"],
        ["Bob", "88", "no"],
        ["Charlie", "72", "yes"],
        ["Diana", "91", "no"],
    ]
    types, details = csvwise.infer_advanced_types(headers, data)
    assert types["name"] == "text"
    assert types["score"] == "numeric"
    assert "cardinality" in details["name"]
    assert "unique" in details["name"]
    assert details["name"]["empty"] == 0


def test_infer_advanced_types_with_empties():
    """Test advanced types with missing data."""
    headers = ["name", "email"]
    data = [
        ["Alice", "alice@test.com"],
        ["Bob", ""],
        ["Charlie", "charlie@test.com"],
    ]
    types, details = csvwise.infer_advanced_types(headers, data)
    assert details["email"]["empty"] == 1
    assert details["email"]["empty_pct"] > 0


def test_data_context():
    """Test DataContext lazy loading."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("name,score\nAlice,95\nBob,88\nCharlie,72\n")
        f.flush()
        ctx = csvwise.DataContext(f.name)
        assert len(ctx.headers) == 2
        assert len(ctx.data) == 3
        assert ctx.col_types["score"] == "numeric"
        assert "score" in ctx.stats
        assert ctx.quality["overall"] > 0
        assert isinstance(ctx.viz_suggestions, list)
        assert "score" in ctx.schema_prompt
        assert "统计" in ctx.stats_text()
    os.unlink(f.name)


def test_data_context_outliers():
    """Test DataContext outlier detection."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("item,value\n")
        for i in range(20):
            f.write(f"item{i},{10 + i}\n")
        f.write("outlier,9999\n")  # outlier
        f.flush()
        ctx = csvwise.DataContext(f.name)
        assert "value" in ctx.outliers
        assert ctx.outliers["value"]["count"] >= 1
    os.unlink(f.name)


def test_load_csv_empty_rows():
    """Test that empty rows are filtered out."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("name,age\nAlice,30\n\n\nBob,25\n\n")
        f.flush()
        headers, data, delim = csvwise.load_csv(f.name)
        assert len(data) == 2
    os.unlink(f.name)


def test_truncate_edge_cases():
    """Test truncate with edge cases."""
    assert csvwise.truncate("") == ""
    assert csvwise.truncate("  spaces  ") == "spaces"
    exact = "x" * 200
    assert csvwise.truncate(exact) == exact  # exactly 200, no truncation
    over = "x" * 201
    assert csvwise.truncate(over) == "x" * 200 + "..."


def test_csv_to_markdown_table_padded():
    """Test markdown table with uneven rows."""
    headers = ["a", "b", "c"]
    data = [["1", "2"], ["3", "4", "5", "6"]]  # short and long rows
    md = csvwise.csv_to_markdown_table(headers, data)
    assert "| a | b | c |" in md
    lines = md.split("\n")
    # Each data line should have exactly 3 columns
    for line in lines[2:]:  # skip header and separator
        assert line.count("|") == 4  # 3 cols = 4 pipe chars


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        # Original tests
        test_load_csv,
        test_infer_column_types,
        test_compute_basic_stats,
        test_csv_to_markdown_table,
        test_truncate,
        test_build_schema_prompt,
        test_gbk_csv,
        # New v0.2.0 tests
        test_compute_basic_stats_extended,
        test_detect_outliers,
        test_detect_outliers_no_outliers,
        test_data_quality_score,
        test_data_quality_score_perfect,
        test_suggest_visualizations,
        test_infer_advanced_types,
        test_infer_advanced_types_with_empties,
        test_data_context,
        test_data_context_outliers,
        test_load_csv_empty_rows,
        test_truncate_edge_cases,
        test_csv_to_markdown_table_padded,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {t.__name__}: {e}")
            failed += 1
    print(f"\n{'✅' if failed == 0 else '❌'} {passed}/{passed + failed} tests passed")
    sys.exit(0 if failed == 0 else 1)
