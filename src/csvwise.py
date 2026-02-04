#!/usr/bin/env python3
"""
csvwise - AI-Powered CSV Data Analyst CLI
Ask questions about your CSV data in natural language.

Enhanced v0.2.0 — Added smart diagnostics, outlier detection,
data quality scoring, visualization recommendations, and more.
"""

import argparse
import csv
import io
import json
import logging
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VERSION = "0.2.0"
MAX_PREVIEW_ROWS = 20          # rows sent to LLM for schema understanding
MAX_ANALYSIS_ROWS = 200        # rows sent for deep analysis
MAX_CELL_LEN = 200             # truncate long cell values
STATE_DIR = Path.home() / ".csvwise"
HISTORY_FILE = STATE_DIR / "history.json"
LOG_FILE = STATE_DIR / "csvwise.log"

LLM_TIMEOUT = 90               # default LLM timeout seconds
LLM_MAX_RETRIES = 2            # max retry attempts for LLM calls
LLM_RETRY_DELAY = 3            # seconds between retries

# Advanced type detection patterns
PATTERNS = {
    "email": re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$"),
    "url": re.compile(r"^https?://\S+$"),
    "phone": re.compile(r"^[\+]?[\d\s\-\(\)]{7,15}$"),
    "percentage": re.compile(r"^-?\d+\.?\d*\s*%$"),
    "currency_cny": re.compile(r"^¥[\d,]+\.?\d*$"),
    "currency_usd": re.compile(r"^\$[\d,]+\.?\d*$"),
    "boolean": re.compile(r"^(true|false|yes|no|是|否|1|0)$", re.IGNORECASE),
    "ip_address": re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"),
}

DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
    "%Y年%m月%d日", "%m-%d-%Y",
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(verbose: bool = False):
    """Configure logging to file and optionally to stderr."""
    ensure_state_dir()
    handlers = [logging.FileHandler(LOG_FILE, encoding="utf-8")]
    if verbose:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )

logger = logging.getLogger("csvwise")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_state_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_csv(path: str):
    """Load CSV and return (headers, rows, delimiter) with robust validation."""
    p = Path(path)
    if not p.exists():
        print(f"❌ 文件不存在: {path}")
        sys.exit(1)
    if not p.is_file():
        print(f"❌ 不是文件: {path}")
        sys.exit(1)
    if p.stat().st_size == 0:
        print(f"❌ 文件为空: {path}")
        sys.exit(1)
    if p.suffix.lower() not in (".csv", ".tsv", ".txt"):
        print(f"⚠️  文件类型 {p.suffix} 可能不是 CSV，尝试加载中...")

    logger.info("Loading CSV: %s (%.1f KB)", path, p.stat().st_size / 1024)

    # Detect encoding
    encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"]
    raw = p.read_bytes()
    text = None
    used_encoding = None
    for enc in encodings:
        try:
            text = raw.decode(enc)
            used_encoding = enc
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:
        print("❌ 无法解码文件，请检查编码")
        sys.exit(1)

    logger.info("Detected encoding: %s", used_encoding)

    # Detect delimiter
    sniffer = csv.Sniffer()
    try:
        dialect = sniffer.sniff(text[:4096])
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = "," if "," in text[:1024] else "\t"

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)

    # Filter out completely empty rows
    rows = [r for r in rows if any(cell.strip() for cell in r)]

    if len(rows) < 2:
        print("❌ CSV 文件至少需要表头 + 1行数据")
        sys.exit(1)

    headers = rows[0]
    data = rows[1:]
    logger.info("Loaded %d rows, %d columns, delimiter=%r", len(data), len(headers), delimiter)
    return headers, data, delimiter


def truncate(s, maxlen=MAX_CELL_LEN):
    """Truncate string to maxlen, adding '...' if needed."""
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
    """Infer column types by sampling data. Returns dict of header→type."""
    types = {}
    sample_size = min(len(data), 50)

    for col_idx, h in enumerate(headers):
        nums = 0
        dates = 0
        empties = 0
        pattern_counts = {k: 0 for k in PATTERNS}
        total = sample_size

        for row in data[:sample_size]:
            if col_idx >= len(row) or not row[col_idx].strip():
                empties += 1
                continue
            val = row[col_idx].strip()

            # Try number
            try:
                float(val.replace(",", "").replace("%", "").replace("¥", "").replace("$", ""))
                nums += 1
                continue
            except ValueError:
                pass

            # Try date
            is_date = False
            for fmt in DATE_FORMATS:
                try:
                    datetime.strptime(val, fmt)
                    dates += 1
                    is_date = True
                    break
                except ValueError:
                    continue

            if is_date:
                continue

            # Try advanced patterns
            for pname, pat in PATTERNS.items():
                if pat.match(val):
                    pattern_counts[pname] += 1
                    break

        non_empty = total - empties
        if non_empty == 0:
            types[h] = "empty"
        elif nums / max(non_empty, 1) > 0.7:
            types[h] = "numeric"
        elif dates / max(non_empty, 1) > 0.5:
            types[h] = "date"
        else:
            # Check advanced patterns
            best_pattern = max(pattern_counts, key=pattern_counts.get)
            if pattern_counts[best_pattern] / max(non_empty, 1) > 0.5:
                types[h] = best_pattern
            else:
                types[h] = "text"

    return types


def infer_advanced_types(headers, data):
    """Extended type inference with cardinality and uniqueness info."""
    types = infer_column_types(headers, data)
    details = {}

    for col_idx, h in enumerate(headers):
        values = [row[col_idx].strip() for row in data if col_idx < len(row) and row[col_idx].strip()]
        unique_count = len(set(values))
        total = len(values)

        detail = {
            "type": types[h],
            "total": len(data),
            "non_empty": total,
            "empty": len(data) - total,
            "empty_pct": round((len(data) - total) / max(len(data), 1) * 100, 1),
            "unique": unique_count,
            "cardinality": "high" if unique_count > total * 0.8 else ("medium" if unique_count > total * 0.2 else "low"),
        }

        # For categorical (low cardinality text), list unique values
        if detail["cardinality"] == "low" and types[h] == "text" and unique_count <= 20:
            from collections import Counter
            counter = Counter(values)
            detail["value_counts"] = dict(counter.most_common(10))

        details[h] = detail

    return types, details


def compute_basic_stats(headers, data, col_types):
    """Compute basic statistics for numeric columns."""
    stats = {}
    for col_idx, h in enumerate(headers):
        if col_types.get(h) != "numeric":
            continue
        values = []
        for row in data:
            if col_idx < len(row) and row[col_idx].strip():
                try:
                    values.append(float(row[col_idx].strip().replace(",", "").replace("%", "").replace("¥", "").replace("$", "")))
                except ValueError:
                    pass
        if not values:
            continue
        values.sort()
        n = len(values)
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / max(n - 1, 1)
        std_dev = math.sqrt(variance)
        q1 = values[n // 4] if n >= 4 else values[0]
        q3 = values[(3 * n) // 4] if n >= 4 else values[-1]
        iqr = q3 - q1

        stats[h] = {
            "count": n,
            "min": round(values[0], 4),
            "max": round(values[-1], 4),
            "mean": round(mean, 4),
            "median": round(values[n // 2], 4),
            "sum": round(sum(values), 4),
            "std_dev": round(std_dev, 4),
            "q1": round(q1, 4),
            "q3": round(q3, 4),
            "iqr": round(iqr, 4),
        }
    return stats


def detect_outliers(headers, data, col_types, stats=None):
    """Detect outliers using IQR method. Returns dict of header→outlier_info."""
    if stats is None:
        stats = compute_basic_stats(headers, data, col_types)

    outliers = {}
    for col_idx, h in enumerate(headers):
        if h not in stats or stats[h]["iqr"] == 0:
            continue

        s = stats[h]
        q1, q3, iqr = s["q1"], s["q3"], s["iqr"]
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        outlier_values = []
        outlier_rows = []
        for row_idx, row in enumerate(data):
            if col_idx < len(row) and row[col_idx].strip():
                try:
                    v = float(row[col_idx].strip().replace(",", "").replace("%", "").replace("¥", "").replace("$", ""))
                    if v < lower_bound or v > upper_bound:
                        outlier_values.append(v)
                        outlier_rows.append(row_idx + 2)  # +2 for header + 1-indexed
                except ValueError:
                    pass

        if outlier_values:
            outliers[h] = {
                "count": len(outlier_values),
                "percentage": round(len(outlier_values) / s["count"] * 100, 1),
                "lower_bound": round(lower_bound, 4),
                "upper_bound": round(upper_bound, 4),
                "values": outlier_values[:10],  # first 10
                "rows": outlier_rows[:10],
            }

    return outliers


def compute_data_quality_score(headers, data, col_types, type_details=None):
    """Compute an overall data quality score (0-100)."""
    if type_details is None:
        _, type_details = infer_advanced_types(headers, data)

    scores = {
        "completeness": 100,
        "consistency": 100,
        "validity": 100,
    }

    # Completeness: penalize empty values
    total_cells = len(headers) * len(data)
    empty_cells = sum(d["empty"] for d in type_details.values())
    if total_cells > 0:
        scores["completeness"] = round((1 - empty_cells / total_cells) * 100, 1)

    # Consistency: check if columns have consistent types
    inconsistent = 0
    for col_idx, h in enumerate(headers):
        if col_types.get(h) == "numeric":
            non_numeric = 0
            total = 0
            for row in data:
                if col_idx < len(row) and row[col_idx].strip():
                    total += 1
                    try:
                        float(row[col_idx].strip().replace(",", "").replace("%", "").replace("¥", "").replace("$", ""))
                    except ValueError:
                        non_numeric += 1
            if total > 0 and non_numeric / total > 0.1:
                inconsistent += 1
    if headers:
        scores["consistency"] = round((1 - inconsistent / len(headers)) * 100, 1)

    # Validity: check row length consistency
    expected_cols = len(headers)
    bad_rows = sum(1 for row in data if len(row) != expected_cols)
    if data:
        scores["validity"] = round((1 - bad_rows / len(data)) * 100, 1)

    overall = round(sum(scores.values()) / len(scores), 1)
    return {**scores, "overall": overall}


def suggest_visualizations(headers, col_types, stats, data):
    """Suggest appropriate chart types based on data characteristics."""
    suggestions = []

    numeric_cols = [h for h in headers if col_types.get(h) == "numeric"]
    date_cols = [h for h in headers if col_types.get(h) == "date"]
    text_cols = [h for h in headers if col_types.get(h) == "text"]

    # Time series
    if date_cols and numeric_cols:
        suggestions.append({
            "type": "折线图 (Line Chart)",
            "x": date_cols[0],
            "y": numeric_cols[0],
            "reason": "有时间维度和数值列，适合展示趋势",
            "priority": "high",
        })

    # Distribution
    for col in numeric_cols[:2]:
        suggestions.append({
            "type": "直方图 (Histogram)",
            "column": col,
            "reason": f"展示 {col} 的分布特征",
            "priority": "medium",
        })

    # Category comparison
    if text_cols and numeric_cols:
        unique_count = len(set(row[headers.index(text_cols[0])]
                              for row in data[:100]
                              if headers.index(text_cols[0]) < len(row)))
        if unique_count <= 15:
            suggestions.append({
                "type": "柱状图 (Bar Chart)",
                "x": text_cols[0],
                "y": numeric_cols[0],
                "reason": f"按 {text_cols[0]} 分组比较 {numeric_cols[0]}",
                "priority": "high",
            })

        if unique_count <= 8 and len(numeric_cols) >= 1:
            suggestions.append({
                "type": "饼图 (Pie Chart)",
                "column": text_cols[0],
                "value": numeric_cols[0],
                "reason": f"展示 {text_cols[0]} 各类别在 {numeric_cols[0]} 中的占比",
                "priority": "medium",
            })

    # Scatter plot for correlation
    if len(numeric_cols) >= 2:
        suggestions.append({
            "type": "散点图 (Scatter Plot)",
            "x": numeric_cols[0],
            "y": numeric_cols[1],
            "reason": f"探索 {numeric_cols[0]} 与 {numeric_cols[1]} 的相关性",
            "priority": "medium",
        })

    # Box plot for outlier visualization
    if numeric_cols:
        suggestions.append({
            "type": "箱线图 (Box Plot)",
            "columns": numeric_cols[:5],
            "reason": "直观展示数值分布和异常值",
            "priority": "low",
        })

    # Heatmap for multi-category
    if len(text_cols) >= 2 and numeric_cols:
        suggestions.append({
            "type": "热力图 (Heatmap)",
            "row": text_cols[0],
            "col": text_cols[1],
            "value": numeric_cols[0],
            "reason": f"展示 {text_cols[0]} × {text_cols[1]} 的 {numeric_cols[0]} 分布",
            "priority": "low",
        })

    return suggestions


def build_schema_prompt(headers, data, col_types):
    """Build a schema description for the LLM."""
    lines = ["## 数据集概要", f"- 总行数: {len(data)}", f"- 列数: {len(headers)}", ""]
    lines.append("## 列信息")
    for col_idx, h in enumerate(headers):
        t = col_types.get(h, "unknown")
        # Get sample unique values
        vals = set()
        for row in data[:100]:
            if col_idx < len(row) and row[col_idx].strip():
                vals.add(truncate(row[col_idx], 50))
            if len(vals) >= 5:
                break
        sample = ", ".join(list(vals)[:5])
        lines.append(f"- **{h}** (类型: {t}) — 示例值: {sample}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DataContext — eliminates repeated loading boilerplate
# ---------------------------------------------------------------------------

class DataContext:
    """Holds loaded CSV data with lazy-computed analytics."""

    def __init__(self, path: str):
        self.path = path
        self.headers, self.data, self.delimiter = load_csv(path)
        self._col_types = None
        self._type_details = None
        self._stats = None
        self._outliers = None
        self._quality = None
        self._viz_suggestions = None
        self._schema_prompt = None

    @property
    def col_types(self):
        if self._col_types is None:
            self._col_types = infer_column_types(self.headers, self.data)
        return self._col_types

    @property
    def type_details(self):
        if self._type_details is None:
            self._col_types, self._type_details = infer_advanced_types(self.headers, self.data)
        return self._type_details

    @property
    def stats(self):
        if self._stats is None:
            self._stats = compute_basic_stats(self.headers, self.data, self.col_types)
        return self._stats

    @property
    def outliers(self):
        if self._outliers is None:
            self._outliers = detect_outliers(self.headers, self.data, self.col_types, self.stats)
        return self._outliers

    @property
    def quality(self):
        if self._quality is None:
            self._quality = compute_data_quality_score(
                self.headers, self.data, self.col_types, self.type_details
            )
        return self._quality

    @property
    def viz_suggestions(self):
        if self._viz_suggestions is None:
            self._viz_suggestions = suggest_visualizations(
                self.headers, self.col_types, self.stats, self.data
            )
        return self._viz_suggestions

    @property
    def schema_prompt(self):
        if self._schema_prompt is None:
            self._schema_prompt = build_schema_prompt(
                self.headers, self.data, self.col_types
            )
        return self._schema_prompt

    def stats_text(self):
        """Format stats as text section for prompts."""
        if not self.stats:
            return ""
        lines = ["## 基础统计"]
        for h, s in self.stats.items():
            lines.append(
                f"- {h}: count={s['count']}, min={s['min']}, max={s['max']}, "
                f"mean={s['mean']}, median={s['median']}, sum={s['sum']}, "
                f"std_dev={s['std_dev']}"
            )
        return "\n".join(lines)

    def sample_table(self, max_rows=None):
        """Get markdown table of sample data."""
        n = max_rows or min(MAX_ANALYSIS_ROWS, len(self.data))
        return csv_to_markdown_table(self.headers, self.data, max_rows=n)

    def outliers_text(self):
        """Format outlier info as text section."""
        if not self.outliers:
            return ""
        lines = ["## 异常值检测 (IQR方法)"]
        for h, o in self.outliers.items():
            lines.append(
                f"- **{h}**: {o['count']}个异常值 ({o['percentage']}%), "
                f"范围 [{o['lower_bound']}, {o['upper_bound']}], "
                f"异常值样例: {o['values'][:5]}"
            )
        return "\n".join(lines)

    def quality_text(self):
        """Format quality score as text."""
        q = self.quality
        lines = [
            "## 数据质量评分",
            f"- 总分: {q['overall']}/100",
            f"- 完整性: {q['completeness']}/100",
            f"- 一致性: {q['consistency']}/100",
            f"- 有效性: {q['validity']}/100",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM Integration
# ---------------------------------------------------------------------------

def llm_query(prompt: str, timeout: int = LLM_TIMEOUT, retries: int = LLM_MAX_RETRIES) -> str:
    """Call gemini CLI for LLM inference with retry logic."""
    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            logger.info("LLM query attempt %d/%d (prompt length: %d chars)", attempt, retries, len(prompt))
            result = subprocess.run(
                ["gemini", prompt],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0 and result.stdout.strip():
                logger.info("LLM query succeeded (response length: %d chars)", len(result.stdout))
                return result.stdout.strip()

            # Fallback: try with stdin
            result2 = subprocess.run(
                ["gemini"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result2.returncode == 0 and result2.stdout.strip():
                logger.info("LLM query succeeded via stdin (response length: %d chars)", len(result2.stdout))
                return result2.stdout.strip()

            last_error = result.stderr[:200] or result2.stderr[:200] or "empty response"
            logger.warning("LLM attempt %d failed: %s", attempt, last_error)

        except FileNotFoundError:
            return "❌ 未找到 gemini CLI。请安装: npm i -g @anthropic-ai/gemini-cli"
        except subprocess.TimeoutExpired:
            last_error = "timeout"
            logger.warning("LLM attempt %d timed out after %ds", attempt, timeout)

        if attempt < retries:
            delay = LLM_RETRY_DELAY * attempt
            logger.info("Retrying in %ds...", delay)
            time.sleep(delay)

    return f"❌ LLM 调用失败 (重试{retries}次): {last_error}"


def save_history(action: str, file: str, query: str, result_preview: str):
    """Save query history."""
    ensure_state_dir()
    history = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            logger.warning("Failed to load history, starting fresh")
            history = []
    history.append({
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "file": str(file),
        "query": query,
        "result_preview": result_preview[:200],
    })
    # Keep last 100 entries
    history = history[-100:]
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_info(args):
    """Show dataset information with enhanced diagnostics."""
    ctx = DataContext(args.file)

    print(f"\n📊 数据集: {args.file}")
    print(f"   行数: {len(ctx.data):,}  |  列数: {len(ctx.headers)}  |  分隔符: {repr(ctx.delimiter)}")

    # Quality score
    q = ctx.quality
    quality_emoji = "🟢" if q["overall"] >= 80 else ("🟡" if q["overall"] >= 60 else "🔴")
    print(f"   数据质量: {quality_emoji} {q['overall']}/100 (完整性:{q['completeness']} 一致性:{q['consistency']} 有效性:{q['validity']})")
    print()

    # Column info with advanced types
    print("📋 列信息:")
    details = ctx.type_details
    for h in ctx.headers:
        t = ctx.col_types.get(h, "unknown")
        d = details.get(h, {})
        emoji = {
            "numeric": "🔢", "date": "📅", "text": "📝", "empty": "⬜",
            "email": "📧", "url": "🔗", "phone": "📱", "percentage": "💯",
            "currency_cny": "💰", "currency_usd": "💵", "boolean": "✅",
            "ip_address": "🌐",
        }.get(t, "❓")

        line = f"   {emoji} {h} ({t})"

        # Add cardinality info
        if d:
            empty_str = f"  空值:{d['empty']}({d['empty_pct']}%)" if d["empty"] > 0 else ""
            line += f"  [{d['cardinality']}基数, {d['unique']}种]{empty_str}"

        # Add stats for numeric
        if h in ctx.stats:
            s = ctx.stats[h]
            line += f"  — min={s['min']}, max={s['max']}, mean={s['mean']}, std={s['std_dev']}"

        print(line)

    # Outlier summary
    if ctx.outliers:
        print(f"\n⚠️  异常值检测:")
        for h, o in ctx.outliers.items():
            print(f"   📍 {h}: {o['count']}个异常值 ({o['percentage']}%) — 正常范围 [{o['lower_bound']}, {o['upper_bound']}]")

    # Preview
    print(f"\n📃 前 {min(5, len(ctx.data))} 行预览:")
    print(csv_to_markdown_table(ctx.headers, ctx.data, max_rows=5))

    # Visualization suggestions
    if ctx.viz_suggestions:
        print(f"\n💡 推荐可视化:")
        for i, s in enumerate(ctx.viz_suggestions[:3], 1):
            print(f"   {i}. {s['type']} — {s['reason']}")

    print()


def cmd_ask(args):
    """Ask a natural language question about the data."""
    ctx = DataContext(args.file)

    sample_rows = min(MAX_ANALYSIS_ROWS, len(ctx.data))
    table = ctx.sample_table(sample_rows)

    prompt = f"""你是一个专业的数据分析师。请根据以下 CSV 数据回答用户的问题。

{ctx.schema_prompt}

{ctx.stats_text()}

{ctx.outliers_text()}

## 数据样本 (前 {sample_rows} 行，共 {len(ctx.data)} 行)
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
    """Generate a comprehensive analysis report with AI-enhanced insights."""
    ctx = DataContext(args.file)

    sample_rows = min(MAX_ANALYSIS_ROWS, len(ctx.data))
    table = ctx.sample_table(sample_rows)

    # Build enhanced prompt with all analytics
    prompt = f"""你是一个资深数据分析师。请对以下 CSV 数据生成一份全面的分析报告。

{ctx.schema_prompt}

{ctx.stats_text()}

{ctx.outliers_text()}

{ctx.quality_text()}

## 数据样本 (前 {sample_rows} 行，共 {len(ctx.data)} 行)
{table}

## 报告要求
请生成以下章节的详细报告（中文）：

### 1. 📊 数据概览
- 数据集大小、完整性、质量评估
- 数据质量得分解读

### 2. 📈 关键发现
- 最重要的 3-5 个发现
- 用具体数据支撑

### 3. 📉 趋势与模式
- 数据中的趋势（如有时间维度）
- 分布特征
- 异常值分析（参考上方异常值检测结果）

### 4. 🔗 关联分析
- 列之间的关系
- 有意义的分组对比

### 5. 🧹 数据清洗建议
- 基于质量评分的改进建议
- 缺失值处理策略
- 异常值处理建议

### 6. 📊 可视化建议
- 推荐的图表类型及理由
- 具体的可视化方案

### 7. 💡 建议与洞察
- 基于数据的可行建议
- 需要进一步调查的方向

### 8. ⚠️ 数据局限性
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
        report_content += f"_csvwise v{VERSION} — AI-Powered CSV Data Analyst_\n\n"

        # Add local analytics section
        report_content += "---\n\n## 📊 自动化分析摘要\n\n"
        report_content += f"| 指标 | 值 |\n|------|------|\n"
        report_content += f"| 总行数 | {len(ctx.data):,} |\n"
        report_content += f"| 总列数 | {len(ctx.headers)} |\n"
        q = ctx.quality
        report_content += f"| 数据质量分 | {q['overall']}/100 |\n"
        report_content += f"| 完整性 | {q['completeness']}/100 |\n"
        report_content += f"| 一致性 | {q['consistency']}/100 |\n"
        report_content += f"| 有效性 | {q['validity']}/100 |\n\n"

        if ctx.outliers:
            report_content += "### 异常值检测\n\n"
            for h, o in ctx.outliers.items():
                report_content += f"- **{h}**: {o['count']}个 ({o['percentage']}%)\n"
            report_content += "\n"

        report_content += "---\n\n## AI 深度分析\n\n"
        report_content += result
        out_path.write_text(report_content, encoding="utf-8")
        print(f"\n✅ 报告已保存: {out_path}")

    save_history("report", args.file, "full_report", result)


def cmd_clean(args):
    """AI-suggested data cleaning recommendations with quality scoring."""
    ctx = DataContext(args.file)

    # Quality analysis
    quality_lines = ["## 数据质量详细检查"]
    details = ctx.type_details
    for h, d in details.items():
        flags = []
        if d["empty_pct"] > 5:
            flags.append(f"⚠️ 空值 {d['empty']}个 ({d['empty_pct']}%)")
        if d["cardinality"] == "low" and d["type"] == "text" and d.get("value_counts"):
            top = list(d["value_counts"].items())[:3]
            flags.append(f"📊 主要值: {', '.join(f'{k}({v})' for k,v in top)}")
        flag_str = " | ".join(flags) if flags else "✅"
        quality_lines.append(f"- {h} [{d['type']}]: {flag_str}")

    quality_text = "\n".join(quality_lines)
    table = ctx.sample_table(20)

    prompt = f"""你是一个数据清洗专家。请分析以下数据集的质量问题并给出清洗建议。

{ctx.schema_prompt}

{quality_text}

{ctx.quality_text()}

{ctx.outliers_text()}

## 数据样本
{table}

## 请输出
1. 🔍 **发现的问题** — 空值、异常值、格式不一致、编码问题等
2. 🛠️ **清洗建议** — 具体的处理方案（填充策略、删除策略、格式标准化等）
3. 📊 **清洗后预期效果** — 数据质量提升预估（目标分数）
4. 🐍 **Python 代码片段** — 可直接运行的 pandas 清洗代码

用中文回答。"""

    print(f"\n🧹 数据质量分析: {args.file}")
    q = ctx.quality
    quality_emoji = "🟢" if q["overall"] >= 80 else ("🟡" if q["overall"] >= 60 else "🔴")
    print(f"   当前质量分: {quality_emoji} {q['overall']}/100")
    print("─" * 60)
    result = llm_query(prompt, timeout=90)
    print(result)
    print("─" * 60)

    save_history("clean", args.file, "clean_analysis", result)


def cmd_diagnose(args):
    """Full AI-powered data diagnosis — combines outlier detection, quality scoring, and smart suggestions."""
    ctx = DataContext(args.file)

    print(f"\n🔬 数据诊断: {args.file}")
    print("═" * 60)

    # 1. Data Quality Score
    q = ctx.quality
    quality_emoji = "🟢" if q["overall"] >= 80 else ("🟡" if q["overall"] >= 60 else "🔴")
    print(f"\n📊 数据质量评分: {quality_emoji} {q['overall']}/100")
    print(f"   完整性: {q['completeness']}  |  一致性: {q['consistency']}  |  有效性: {q['validity']}")

    # 2. Column Diagnostics
    print(f"\n📋 列诊断:")
    details = ctx.type_details
    for h in ctx.headers:
        d = details.get(h, {})
        t = ctx.col_types.get(h, "?")
        status = "🟢" if d.get("empty_pct", 0) < 5 else ("🟡" if d.get("empty_pct", 0) < 20 else "🔴")
        print(f"   {status} {h}: type={t}, unique={d.get('unique','?')}, empty={d.get('empty_pct',0)}%", end="")
        if h in ctx.stats:
            s = ctx.stats[h]
            print(f", range=[{s['min']}, {s['max']}], σ={s['std_dev']}", end="")
        print()

    # 3. Outlier Report
    if ctx.outliers:
        print(f"\n⚠️  异常值检测 (IQR方法):")
        for h, o in ctx.outliers.items():
            print(f"   📍 {h}: {o['count']}个异常值 ({o['percentage']}%)")
            print(f"      正常范围: [{o['lower_bound']}, {o['upper_bound']}]")
            print(f"      异常值样例: {o['values'][:5]}")
    else:
        print(f"\n✅ 未检测到显著异常值")

    # 4. Visualization Recommendations
    if ctx.viz_suggestions:
        print(f"\n📊 可视化建议:")
        for i, s in enumerate(ctx.viz_suggestions[:5], 1):
            priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s.get("priority", ""), "⚪")
            print(f"   {i}. {priority_emoji} {s['type']} — {s['reason']}")

    # 5. AI Deep Diagnosis
    sample_rows = min(50, len(ctx.data))
    table = ctx.sample_table(sample_rows)

    prompt = f"""你是一个数据科学家。请对以下数据集进行深度诊断，给出专业建议。

{ctx.schema_prompt}

{ctx.stats_text()}

{ctx.outliers_text()}

{ctx.quality_text()}

## 数据样本 (前 {sample_rows} 行)
{table}

## 请给出简洁的诊断意见
1. **数据健康度** — 一句话总结
2. **最关键的3个问题** — 如有
3. **快速改进建议** — 立即可行的 2-3 个步骤
4. **深入分析方向** — 值得探索的 2-3 个方向

简洁为主，每点 1-2 句话。中文回答。"""

    print(f"\n🤖 AI 诊断意见:")
    print("─" * 60)
    result = llm_query(prompt, timeout=60)
    print(result)
    print("═" * 60)

    save_history("diagnose", args.file, "diagnose", result)


def cmd_plot(args):
    """Generate a Python matplotlib plotting script."""
    ctx = DataContext(args.file)

    # Include visualization suggestions in prompt
    viz_text = ""
    if ctx.viz_suggestions:
        viz_text = "## 推荐的可视化类型\n"
        for s in ctx.viz_suggestions[:3]:
            viz_text += f"- {s['type']}: {s['reason']}\n"

    prompt = f"""你是一个数据可视化专家。请根据用户的描述生成 Python matplotlib 绑图代码。

{ctx.schema_prompt}

{viz_text}

## 用户要求
{args.description}

## 代码要求
1. 使用 pandas + matplotlib
2. 中文标题和标签（使用 plt.rcParams 设置中文字体）
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

    if not code.strip():
        print("❌ LLM 未生成有效代码")
        return

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
    ctx = DataContext(args.file)

    prompt = f"""你是一个 Python pandas 专家。请根据用户的查询需求生成 pandas 代码。

{ctx.schema_prompt}

## 用户查询
{args.sql}

## 代码要求
1. 读取 CSV: pd.read_csv("{os.path.abspath(args.file)}")
2. 执行查询
3. 打印结果（用 to_string() 或 to_markdown() 格式化）
4. 如果结果是数值，直接打印
5. 只输出可执行的 Python 代码
6. 不要使用 tabulate（可能未安装）

只输出代码，用 ```python ``` 包裹。"""

    result = llm_query(prompt, timeout=60)

    code = result
    if "```python" in result:
        code = result.split("```python")[1].split("```")[0].strip()
    elif "```" in result:
        code = result.split("```")[1].split("```")[0].strip()

    if not code.strip():
        print("❌ LLM 未生成有效代码")
        return

    print(f"\n🔍 执行查询: {args.sql}")
    print("─" * 60)

    # Execute the code in a temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
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
        try:
            os.unlink(tmp)
        except OSError:
            pass

    print("─" * 60)
    save_history("query", args.file, args.sql, code[:200])


def cmd_compare(args):
    """Compare two CSV files."""
    ctx1 = DataContext(args.file1)
    ctx2 = DataContext(args.file2)

    table1 = ctx1.sample_table(10)
    table2 = ctx2.sample_table(10)

    prompt = f"""你是一个数据分析师。请比较以下两个数据集并给出详细分析。

## 数据集 1: {args.file1}
{ctx1.schema_prompt}
{ctx1.stats_text()}
{table1}

## 数据集 2: {args.file2}
{ctx2.schema_prompt}
{ctx2.stats_text()}
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

    try:
        history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        print("❌ 历史记录文件损坏")
        return

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
        emoji = {
            "ask": "❓", "report": "📝", "clean": "🧹", "plot": "📊",
            "query": "🔍", "compare": "🔄", "diagnose": "🔬",
        }.get(action, "📌")
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
  csvwise info data.csv                          # 查看数据概览 + 质量评分
  csvwise ask data.csv "平均销售额是多少?"          # 提问
  csvwise report data.csv -o report.md            # 生成分析报告
  csvwise clean data.csv                          # 数据清洗建议
  csvwise diagnose data.csv                       # AI 深度诊断
  csvwise plot data.csv "按月份的销售趋势"          # 生成图表
  csvwise query data.csv "销售额 > 10000 的记录"    # SQL 式查询
  csvwise compare a.csv b.csv                     # 对比两个数据集
  csvwise history                                 # 查看历史
        """,
    )
    parser.add_argument("--version", action="version", version=f"csvwise {VERSION}")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示详细日志")

    sub = parser.add_subparsers(dest="command", help="可用命令")

    # info
    p_info = sub.add_parser("info", help="查看数据集概览 + 质量评分")
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

    # diagnose (NEW)
    p_diagnose = sub.add_parser("diagnose", help="AI 深度数据诊断")
    p_diagnose.add_argument("file", help="CSV 文件路径")

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

    # Setup logging
    setup_logging(verbose=getattr(args, "verbose", False))

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "info": cmd_info,
        "ask": cmd_ask,
        "report": cmd_report,
        "clean": cmd_clean,
        "diagnose": cmd_diagnose,
        "plot": cmd_plot,
        "query": cmd_query,
        "compare": cmd_compare,
        "history": cmd_history,
    }

    try:
        commands[args.command](args)
    except KeyboardInterrupt:
        print("\n\n⏹  已取消")
        sys.exit(130)
    except Exception as e:
        logger.exception("Unhandled error in command '%s'", args.command)
        print(f"\n❌ 发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
