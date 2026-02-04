#!/usr/bin/env python3
"""Basic tests for csvwise (no LLM required)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import csvwise


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


if __name__ == "__main__":
    tests = [
        test_load_csv,
        test_infer_column_types,
        test_compute_basic_stats,
        test_csv_to_markdown_table,
        test_truncate,
        test_build_schema_prompt,
        test_gbk_csv,
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
