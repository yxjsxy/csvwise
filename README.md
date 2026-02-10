# 🧠 csvwise - AI-Powered Data Analyst

> 用自然语言分析 CSV、Excel 和数据库，无需写代码

csvwise 让你用自然语言与数据对话。支持 CSV、Excel 文件和数据库（SQLite/PostgreSQL），结合 AI 大语言模型的理解能力，帮助你快速获取数据洞察。

## ✨ 功能一览

### 📊 命令行工具

| 命令 | 说明 | 示例 |
|------|------|------|
| `info` | 数据集概览 | `csvwise info data.csv` |
| `ask` | 自然语言提问 | `csvwise ask data.csv "哪个产品最畅销?"` |
| `report` | 生成完整分析报告 | `csvwise report data.csv -o report.md` |
| `clean` | 数据清洗建议 | `csvwise clean data.csv` |
| `diagnose` | 数据质量诊断 | `csvwise diagnose data.csv` |
| `plot` | 生成可视化图表 | `csvwise plot data.csv "月度趋势"` |
| `query` | SQL 式查询 | `csvwise query data.csv "销售额>10000"` |
| `compare` | 对比两个数据集 | `csvwise compare a.csv b.csv` |
| `history` | 查看查询历史 | `csvwise history` |

### 🌐 Web UI (Streamlit)

![Web UI](assets/web-ui.png)

| 功能 | 说明 |
|------|------|
| 📁 文件上传 | 拖拽 CSV/TSV/Excel 文件 |
| 🗄️ 数据库连接 | SQLite / PostgreSQL |
| 📊 数据概览 | 行数、列数、类型、统计 |
| 💬 自然语言提问 | 对话式数据分析 |
| 📈 可视化 | 折线图、柱状图、散点图、饼图、直方图 |
| 🔍 数据质量 | 完整性、一致性、异常值检测 |

### 🗄️ 数据库支持

| 数据库 | 连接方式 |
|--------|----------|
| SQLite | `/path/to/database.sqlite` |
| PostgreSQL | `postgresql://user:pass@host:port/dbname` |

## 🚀 快速开始

### 安装

```bash
git clone https://github.com/yxjsxy/csvwise.git
cd csvwise
pip install -r requirements.txt
pip install -e .
```

### 命令行使用

```bash
# 查看数据概览
csvwise info data.csv

# 提问
csvwise ask data.csv "哪个地区销售额最高？"

# 生成报告
csvwise report data.csv -o analysis.md

# 可视化
csvwise plot data.csv "销售趋势折线图" --run
```

### 启动 Web UI

```bash
./run_web.sh
# 或
streamlit run app.py
```

访问 http://localhost:8501

## 📖 详细使用

### 数据概览

```bash
csvwise info examples/sales_demo.csv
```

输出：
- 📊 数据集大小（行数 × 列数）
- 📋 列类型检测（数值、分类、日期、文本）
- 📈 基础统计（均值、中位数、标准差）
- 👀 数据预览
- ⚠️ 数据质量评分

### 自然语言提问

```bash
csvwise ask data.csv "哪个产品的毛利率最高？"
csvwise ask stocks.csv "NVDA 这周涨了多少？"
csvwise ask orders.csv "上个月的订单趋势是什么？"
```

### 数据质量诊断

```bash
csvwise diagnose data.csv
```

输出：
- ✅ 数据质量评分 (0-100)
- 🔍 缺失值分析
- 📊 异常值检测
- 💡 清洗建议

### 数据库查询

```python
from src.db_connector import DatabaseConnector

# SQLite
with DatabaseConnector("/path/to/db.sqlite") as db:
    tables = db.list_tables()
    headers, rows = db.query_table("users", limit=100)
    
# PostgreSQL
with DatabaseConnector("postgresql://user:pass@localhost:5432/mydb") as db:
    headers, rows = db.execute_query("SELECT * FROM orders WHERE amount > 1000")
```

## 🔧 前置要求

- Python 3.9+
- [gemini CLI](https://github.com/google-gemini/gemini-cli) (用于 AI 分析)

### 可选依赖

```bash
pip install streamlit    # Web UI
pip install pandas       # 数据处理
pip install matplotlib   # 图表
pip install psycopg2-binary  # PostgreSQL
```

## 📁 项目结构

```
csvwise/
├── app.py               # Streamlit Web UI
├── run_web.sh           # Web UI 启动脚本
├── src/
│   ├── csvwise.py       # CLI 核心代码
│   └── db_connector.py  # 数据库连接器
├── examples/
│   ├── sales_demo.csv   # 销售数据示例
│   └── stocks_demo.csv  # 股票数据示例
├── tests/
│   └── test_csvwise.py
├── requirements.txt
├── setup.py
└── README.md
```

## 💡 设计理念

1. **多数据源**: CSV + SQLite + PostgreSQL 统一接口
2. **双模式**: 命令行 CLI + Web UI
3. **中文优先**: 输出默认中文，适合中文数据分析场景
4. **本地优先**: 数据不上传云端，通过本地 LLM CLI 处理
5. **渐进式复杂度**: 
   - `info` 不需要 LLM
   - `ask/report` 需要 LLM
   - `plot/query` 需要 pandas

## 🎯 使用场景

| 场景 | 推荐方式 |
|------|----------|
| 快速查看数据 | `csvwise info data.csv` |
| 回答具体问题 | `csvwise ask data.csv "问题"` |
| 生成周报/月报 | `csvwise report data.csv -o report.md` |
| 数据探索 | Web UI (http://localhost:8501) |
| 定期分析 | 集成到 cron/OpenClaw |

## 📜 License

MIT

---

Made with ❤️ by Karl & 牧牧 🐶
