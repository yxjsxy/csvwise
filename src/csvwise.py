#!/usr/bin/env python3
"""
csvwise - AI-Powered CSV Data Analyst CLI
Ask questions about your CSV data in natural language.
"""

import argparse
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VERSION = "0.1.0"
MAX_PREVIEW_ROWS = 20          # rows sent to LLM for schema understanding
MAX_ANALYSIS_ROWS = 200        # rows sent for deep analysis
MAX_CELL_LEN = 200             # truncate long cell values
STATE_DIR = Path.home() / ".csvwise"
HISTORY_FILE = STATE_DIR / "history.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_state_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_csv(path: str):
    """Load CSV and return (headers, rows) with basic validation."""
    p = Path(path)
    if not p.exists():
        print(f"❌ 文件不存在: {path}")
        sys.exit(1)
    if p.suffix.lower() not in (".csv", ".tsv", ".txt"):
        print(f"⚠️  文件类型 {p.suffix} 可能不是 CSV，尝试加载中...")

    # Detect encoding
    encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"]
    raw = p.read_bytes()
    text = None
    for enc in encodings:
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:
        print("❌ 无法解码文件，请检查编码")
        sys.exit(1)

    # Detect delimiter
    sniffer = csv.Sniffer()
    try:
        dialect = sniffer.sniff(text[:4096])
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = "," if "," in text[:1024] else "\t"

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if len(rows) < 2:
        print("❌ CSV 文件至少需要表头 + 1行数据")
        sys.exit(1)

    headers = rows[0]
    data = rows[1:]
    return headers, data, delimiter


def truncate(s, maxlen=MAX_CELL_LEN):
    s = str(s).strip()
    return s[:maxlen] + "..." if len(s) > maxlen else s


def csv_to_markdown_table(headers, rows, max_rows=None):
    """Convert CSV rows to markdown table string."""
    if max_rows:
        rows = rows[:max_rows]
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        # Pad or truncate row to match header count
        padded = row + [""] * (len(headers) - len(row))
        padded = padded[:len(headers)]
        lines.append("| " + " | ".join(truncate(c) for c in padded) + " |")
    return "\n".join(lines)


def infer_column_types(headers, data):
    """Infer column types by sampling data."""
    types = {}
    for i, h in enumerate(headers):
        nums = 0
        dates = 0
        total = min(len(data), 50)
        for row in data[:50]:
            if i >= len(row) or not row[i].strip():
                continue
            val = row[i].strip()
            # Try number
            try:
                float(val.replace(",", "").replace("%", ""))
                nums += 1
                continue
            except ValueError:
                pass
            # Try date
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
                try:
                    datetime.strptime(val, fmt)
                    dates += 1
                    break
                except ValueError:
                    continue
        if total == 0:
            types[h] = "empty"
        elif nums / max(total, 1) > 0.7:
            types[h] = "numeric"
        elif dates / max(total, 1) > 0.5:
            types[h] = "date"
        else:
            types[h] = "text"
    return types


def build_schema_prompt(headers, data, col_types):
    """Build a schema description for the LLM."""
    lines = ["## 数据集概要", f"- 总行数: {len(data)}", f"- 列数: {len(headers)}", ""]
    lines.append("## 列信息")
    for h in headers:
        t = col_types.get(h, "unknown")
        # Get sample unique values
        idx = headers.index(h)
        vals = set()
        for row in data[:100]:
            if idx < len(row) and row[idx].strip():
                vals.add(truncate(row[idx], 50))
            if len(vals) >= 5:
                break
        sample = ", ".join(list(vals)[:5])
        lines.append(f"- **{h}** (类型: {t}) — 示例值: {sample}")
    return "\n".join(lines)


def compute_basic_stats(headers, data, col_types):
    """Compute basic statistics for numeric columns."""
    stats = {}
    for h in headers:
        if col_types.get(h) != "numeric":
            continue
        idx = headers.index(h)
        values = []
        for row in data:
            if idx < len(row) and row[idx].strip():
                try:
                    values.append(float(row[idx].strip().replace(",", "").replace("%", "")))
                except ValueError:
                    pass
        if not values:
            continue
        values.sort()
        n = len(values)
        stats[h] = {
            "count": n,
            "min": round(values[0], 4),
            "max": round(values[-1], 4),
            "mean": round(sum(values) / n, 4),
            "median": round(values[n // 2], 4),
            "sum": round(sum(values), 4),
        }
    return stats


def llm_query(prompt: str, timeout: int = 60) -> str:
    """Call gemini CLI for LLM inference."""
    try:
        result = subprocess.run(
            ["gemini", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            # Fallback: try with stdin
            result2 = subprocess.run(
                ["gemini"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result2.stdout.strip() if result2.returncode == 0 else f"❌ LLM 调用失败: {result.stderr[:200]}"
    except FileNotFoundError:
        return "❌ 未找到 gemini CLI。请安装: npm i -g @anthropic-ai/gemini-cli"
    except subprocess.TimeoutExpired:
        return "❌ LLM 调用超时"


def save_history(action: str, file: str, query: str, result_preview: str):
    """Save query history."""
    ensure_state_dir()
    history = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            history = []
    history.append({
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "file": file,
        "query": query,
        "result_preview": result_preview[:200],
    })
    # Keep last 100 entries
    history = history[-100:]
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_info(args):
    """Show dataset information."""
    headers, data, delim = load_csv(args.file)
    col_types = infer_column_types(headers, data)
    stats = compute_basic_stats(headers, data, col_types)

    print(f"\n📊 数据集: {args.file}")
    print(f"   行数: {len(data):,}  |  列数: {len(headers)}  |  分隔符: {repr(delim)}")
    print()

    # Column info
    print("📋 列信息:")
    for h in headers:
        t = col_types.get(h, "unknown")
        emoji = {"numeric": "🔢", "date": "📅", "text": "📝", "empty": "⬜"}.get(t, "❓")
        line = f"   {emoji} {h} ({t})"
        if h in stats:
            s = stats[h]
            line += f"  — min={s['min']}, max={s['max']}, mean={s['mean']}, median={s['median']}"
        print(line)

    # Preview
    print(f"\n📃 前 {min(5, len(data))} 行预览:")
    print(csv_to_markdown_table(headers, data, max_rows=5))
    print()


def cmd_ask(args):
    """Ask a natural language question about the data."""
    headers, data, delim = load_csv(args.file)
    col_types = infer_column_types(headers, data)
    stats = compute_basic_stats(headers, data, col_types)
    schema = build_schema_prompt(headers, data, col_types)

    # Build data sample
    sample_rows = min(MAX_ANALYSIS_ROWS, len(data))
    table = csv_to_markdown_table(headers, data, max_rows=sample_rows)

    # Stats section
    stats_text = ""
    if stats:
        stats_lines = ["## 基础统计"]
        for h, s in stats.items():
            stats_lines.append(f"- {h}: count={s['count']}, min={s['min']}, max={s['max']}, mean={s['mean']}, median={s['median']}, sum={s['sum']}")
        stats_text = "\n".join(stats_lines)

    prompt = f"""你是一个专业的数据分析师。请根据以下 CSV 数据回答用户的问题。

{schema}

{stats_text}

## 数据样本 (前 {sample_rows} 行，共 {len(data)} 行)
{table}

## 用户问题
{args.question}

## 回答要求
1. 用中文回答
2. 给出具体数据和计算过程
3. 如果需要，用 markdown 表格展示结果
4. 指出数据中的有趣发现
5. 如果数据不足以回答，说明原因并建议需要什么额外数据"""

    print(f"\n🤔 分析中: {args.question}")
    print("─" * 60)
    result = llm_query(prompt, timeout=90)
    print(result)
    print("─" * 60)

    save_history("ask", args.file, args.question, result)


def cmd_report(args):
    """Generate a comprehensive analysis report."""
    headers, data, delim = load_csv(args.file)
    col_types = infer_column_types(headers, data)
    stats = compute_basic_stats(headers, data, col_types)
    schema = build_schema_prompt(headers, data, col_types)

    sample_rows = min(MAX_ANALYSIS_ROWS, len(data))
    table = csv_to_markdown_table(headers, data, max_rows=sample_rows)

    stats_text = ""
    if stats:
        stats_lines = ["## 基础统计"]
        for h, s in stats.items():
            stats_lines.append(f"- {h}: count={s['count']}, min={s['min']}, max={s['max']}, mean={s['mean']}, median={s['median']}, sum={s['sum']}")
        stats_text = "\n".join(stats_lines)

    prompt = f"""你是一个资深数据分析师。请对以下 CSV 数据生成一份全面的分析报告。

{schema}

{stats_text}

## 数据样本 (前 {sample_rows} 行，共 {len(data)} 行)
{table}

## 报告要求
请生成以下章节的详细报告（中文）：

### 1. 📊 数据概览
- 数据集大小、完整性、质量评估

### 2. 📈 关键发现
- 最重要的 3-5 个发现
- 用具体数据支撑

### 3. 📉 趋势与模式
- 数据中的趋势（如有时间维度）
- 分布特征
- 异常值

### 4. 🔗 关联分析
- 列之间的关系
- 有意义的分组对比

### 5. 💡 建议与洞察
- 基于数据的可行建议
- 需要进一步调查的方向

### 6. ⚠️ 数据局限性
- 数据的不足之处
- 改进建议

用 markdown 格式输出，包含表格和列表。"""

    print(f"\n📝 生成分析报告: {args.file}")
    print("═" * 60)
    result = llm_query(prompt, timeout=120)
    print(result)
    print("═" * 60)

    # Save report
    if args.output:
        out_path = Path(args.output)
        report_content = f"# 数据分析报告: {args.file}\n\n"
        report_content += f"_生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n\n"
        report_content += result
        out_path.write_text(report_content, encoding="utf-8")
        print(f"\n✅ 报告已保存: {out_path}")

    save_history("report", args.file, "full_report", result)


def cmd_clean(args):
    """AI-suggested data cleaning recommendations."""
    headers, data, delim = load_csv(args.file)
    col_types = infer_column_types(headers, data)
    schema = build_schema_prompt(headers, data, col_types)

    # Analyze data quality
    quality = {}
    for i, h in enumerate(headers):
        empty = sum(1 for row in data if i >= len(row) or not row[i].strip())
        duplicates = len(data) - len(set(row[i] if i < len(row) else "" for row in data))
        quality[h] = {"empty_count": empty, "empty_pct": round(empty / len(data) * 100, 1), "approx_duplicates": duplicates}

    quality_text = "## 数据质量检查\n"
    for h, q in quality.items():
        flags = []
        if q["empty_pct"] > 5:
            flags.append(f"⚠️ 空值 {q['empty_count']}个 ({q['empty_pct']}%)")
        if q["approx_duplicates"] > len(data) * 0.3:
            flags.append(f"🔄 重复值较多")
        flag_str = " | ".join(flags) if flags else "✅"
        quality_text += f"- {h}: {flag_str}\n"

    table = csv_to_markdown_table(headers, data, max_rows=20)

    prompt = f"""你是一个数据清洗专家。请分析以下数据集的质量问题并给出清洗建议。

{schema}

{quality_text}

## 数据样本
{table}

## 请输出
1. 🔍 **发现的问题** — 空值、异常值、格式不一致、编码问题等
2. 🛠️ **清洗建议** — 具体的处理方案（填充策略、删除策略、格式标准化等）
3. 📊 **清洗后预期效果** — 数据质量提升预估
4. 🐍 **Python 代码片段** — 可直接运行的 pandas 清洗代码

用中文回答。"""

    print(f"\n🧹 数据质量分析: {args.file}")
    print("─" * 60)
    result = llm_query(prompt, timeout=90)
    print(result)
    print("─" * 60)

    save_history("clean", args.file, "clean_analysis", result)


def cmd_plot(args):
    """Generate a Python matplotlib plotting script."""
    headers, data, delim = load_csv(args.file)
    col_types = infer_column_types(headers, data)
    schema = build_schema_prompt(headers, data, col_types)

    prompt = f"""你是一个数据可视化专家。请根据用户的描述生成 Python matplotlib 绑图代码。

{schema}

## 用户要求
{args.description}

## 代码要求
1. 使用 pandas + matplotlib
2. 中文标题和标签
3. 美观的配色方案
4. 代码可直接运行
5. 读取文件路径: {os.path.abspath(args.file)}
6. 保存图片到同目录
7. 打印保存路径

只输出 Python 代码，不要解释。用 ```python ``` 包裹。"""

    print(f"\n📊 生成可视化代码...")
    print("─" * 60)
    result = llm_query(prompt, timeout=60)

    # Extract code block
    code = result
    if "```python" in result:
        code = result.split("```python")[1].split("```")[0].strip()
    elif "```" in result:
        code = result.split("```")[1].split("```")[0].strip()

    # Save script
    script_path = Path(args.file).parent / f"plot_{Path(args.file).stem}.py"
    script_path.write_text(code, encoding="utf-8")
    print(f"📝 绘图脚本已保存: {script_path}")

    if args.run:
        print("\n🚀 运行绘图脚本...")
        try:
            subprocess.run([sys.executable, str(script_path)], timeout=30, check=True)
            print("✅ 图表生成成功!")
        except subprocess.CalledProcessError as e:
            print(f"❌ 运行失败: {e}")
        except subprocess.TimeoutExpired:
            print("❌ 运行超时")
    else:
        print(f"💡 运行: python {script_path}")

    print("─" * 60)
    save_history("plot", args.file, args.description, code[:200])


def cmd_query(args):
    """Execute a SQL-like query on the CSV (via pandas)."""
    headers, data, delim = load_csv(args.file)
    col_types = infer_column_types(headers, data)
    schema = build_schema_prompt(headers, data, col_types)

    prompt = f"""你是一个 Python pandas 专家。请根据用户的查询需求生成 pandas 代码。

{schema}

## 用户查询
{args.sql}

## 代码要求
1. 读取 CSV: pd.read_csv("{os.path.abspath(args.file)}")
2. 执行查询
3. 打印结果（用 tabulate 或 to_markdown 格式化）
4. 如果结果是数值，直接打印
5. 只输出可执行的 Python 代码

只输出代码，用 ```python ``` 包裹。"""

    result = llm_query(prompt, timeout=60)

    code = result
    if "```python" in result:
        code = result.split("```python")[1].split("```")[0].strip()
    elif "```" in result:
        code = result.split("```")[1].split("```")[0].strip()

    print(f"\n🔍 执行查询: {args.sql}")
    print("─" * 60)

    # Execute the code
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp = f.name

    try:
        result = subprocess.run(
            [sys.executable, tmp],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(f"⚠️ {result.stderr[:300]}")
    except subprocess.TimeoutExpired:
        print("❌ 查询执行超时")
    finally:
        os.unlink(tmp)

    print("─" * 60)
    save_history("query", args.file, args.sql, code[:200])


def cmd_compare(args):
    """Compare two CSV files."""
    h1, d1, _ = load_csv(args.file1)
    h2, d2, _ = load_csv(args.file2)

    t1 = infer_column_types(h1, d1)
    t2 = infer_column_types(h2, d2)

    s1 = build_schema_prompt(h1, d1, t1)
    s2 = build_schema_prompt(h2, d2, t2)

    table1 = csv_to_markdown_table(h1, d1, max_rows=10)
    table2 = csv_to_markdown_table(h2, d2, max_rows=10)

    prompt = f"""你是一个数据分析师。请比较以下两个数据集并给出详细分析。

## 数据集 1: {args.file1}
{s1}
{table1}

## 数据集 2: {args.file2}
{s2}
{table2}

## 请分析
1. 🔍 **结构差异** — 列名、类型、数量对比
2. 📊 **数据差异** — 数值范围、分布、趋势对比
3. 🔗 **共同点** — 相同的列、可关联的字段
4. 💡 **洞察** — 两个数据集结合后可以得出什么结论
5. 🛠️ **合并建议** — 如何合并这两个数据集

用中文回答，用 markdown 格式。"""

    print(f"\n🔄 对比分析: {args.file1} vs {args.file2}")
    print("═" * 60)
    result = llm_query(prompt, timeout=90)
    print(result)
    print("═" * 60)

    save_history("compare", f"{args.file1} vs {args.file2}", "compare", result)


def cmd_history(args):
    """Show query history."""
    if not HISTORY_FILE.exists():
        print("📭 暂无历史记录")
        return

    history = json.loads(HISTORY_FILE.read_text())
    if args.clear:
        HISTORY_FILE.unlink()
        print("✅ 历史记录已清除")
        return

    print(f"\n📜 查询历史 (最近 {min(len(history), 20)} 条)")
    print("─" * 60)
    for entry in history[-20:]:
        ts = entry.get("timestamp", "?")[:19]
        action = entry.get("action", "?")
        file = Path(entry.get("file", "?")).name
        query = entry.get("query", "")[:50]
        emoji = {"ask": "❓", "report": "📝", "clean": "🧹", "plot": "📊", "query": "🔍", "compare": "🔄"}.get(action, "📌")
        print(f"  {emoji} [{ts}] {action} on {file}: {query}")
    print("─" * 60)


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="csvwise",
        description="🧠 csvwise - AI-Powered CSV Data Analyst",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  csvwise info data.csv                          # 查看数据概览
  csvwise ask data.csv "平均销售额是多少?"          # 提问
  csvwise report data.csv -o report.md            # 生成分析报告
  csvwise clean data.csv                          # 数据清洗建议
  csvwise plot data.csv "按月份的销售趋势"          # 生成图表
  csvwise query data.csv "销售额 > 10000 的记录"    # SQL 式查询
  csvwise compare a.csv b.csv                     # 对比两个数据集
  csvwise history                                 # 查看历史
        """,
    )
    parser.add_argument("--version", action="version", version=f"csvwise {VERSION}")

    sub = parser.add_subparsers(dest="command", help="可用命令")

    # info
    p_info = sub.add_parser("info", help="查看数据集概览")
    p_info.add_argument("file", help="CSV 文件路径")

    # ask
    p_ask = sub.add_parser("ask", help="用自然语言提问")
    p_ask.add_argument("file", help="CSV 文件路径")
    p_ask.add_argument("question", help="你的问题")

    # report
    p_report = sub.add_parser("report", help="生成全面分析报告")
    p_report.add_argument("file", help="CSV 文件路径")
    p_report.add_argument("-o", "--output", help="保存报告到文件")

    # clean
    p_clean = sub.add_parser("clean", help="数据清洗建议")
    p_clean.add_argument("file", help="CSV 文件路径")

    # plot
    p_plot = sub.add_parser("plot", help="生成可视化图表")
    p_plot.add_argument("file", help="CSV 文件路径")
    p_plot.add_argument("description", help="图表描述")
    p_plot.add_argument("--run", action="store_true", help="自动运行绘图脚本")

    # query
    p_query = sub.add_parser("query", help="SQL 式数据查询")
    p_query.add_argument("file", help="CSV 文件路径")
    p_query.add_argument("sql", help="查询描述")

    # compare
    p_compare = sub.add_parser("compare", help="对比两个数据集")
    p_compare.add_argument("file1", help="第一个 CSV 文件")
    p_compare.add_argument("file2", help="第二个 CSV 文件")

    # history
    p_history = sub.add_parser("history", help="查看查询历史")
    p_history.add_argument("--clear", action="store_true", help="清除历史记录")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "info": cmd_info,
        "ask": cmd_ask,
        "report": cmd_report,
        "clean": cmd_clean,
        "plot": cmd_plot,
        "query": cmd_query,
        "compare": cmd_compare,
        "history": cmd_history,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
