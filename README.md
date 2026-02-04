# 🧠 csvwise - AI-Powered CSV Data Analyst

> 用自然语言分析你的 CSV 数据，无需写代码

csvwise 是一个命令行工具，让你用自然语言与 CSV 数据对话。它结合了 AI 大语言模型的理解能力和传统数据分析方法，帮助你快速获取数据洞察。

## ✨ 功能

| 命令 | 说明 | 示例 |
|------|------|------|
| `info` | 数据集概览 | `csvwise info data.csv` |
| `ask` | 自然语言提问 | `csvwise ask data.csv "哪个产品最畅销?"` |
| `report` | 生成完整分析报告 | `csvwise report data.csv -o report.md` |
| `clean` | 数据清洗建议 | `csvwise clean data.csv` |
| `plot` | 生成可视化图表 | `csvwise plot data.csv "月度趋势"` |
| `query` | SQL 式查询 | `csvwise query data.csv "销售额>10000"` |
| `compare` | 对比两个数据集 | `csvwise compare a.csv b.csv` |
| `history` | 查看查询历史 | `csvwise history` |

## 🚀 快速开始

```bash
# 克隆项目
git clone https://github.com/yxjsxy/csvwise.git
cd csvwise

# 安装
pip install -e .

# 或直接运行
python src/csvwise.py info examples/sales_demo.csv
```

## 📖 使用示例

### 查看数据概览
```bash
csvwise info examples/sales_demo.csv
```
输出数据集大小、列类型、基础统计、预览等。

### 提问
```bash
csvwise ask examples/sales_demo.csv "哪个地区的销售额最高？"
csvwise ask examples/stocks_demo.csv "NVDA这周的涨幅是多少？"
```

### 生成报告
```bash
csvwise report examples/sales_demo.csv -o analysis.md
```

### 数据清洗
```bash
csvwise clean messy_data.csv
```

### 可视化
```bash
csvwise plot examples/sales_demo.csv "各类别的销售额占比饼图" --run
```

## 🔧 前置要求

- Python 3.9+
- [gemini CLI](https://github.com/google-gemini/gemini-cli) (用于 AI 分析)
- 可选: `pip install matplotlib pandas tabulate` (用于图表和查询)

## 📁 项目结构

```
csvwise/
├── src/
│   └── csvwise.py       # 核心代码 (单文件，零依赖)
├── examples/
│   ├── sales_demo.csv   # 销售数据示例
│   └── stocks_demo.csv  # 股票数据示例
├── tests/
│   └── test_csvwise.py  # 测试
├── setup.py             # 安装配置
├── README.md
├── DEVELOPMENT.md
└── LICENSE
```

## 💡 设计理念

1. **零依赖核心**: 核心代码只用 Python 标准库，LLM 调用通过 gemini CLI
2. **中文优先**: 输出默认中文，适合中文数据分析场景
3. **渐进式复杂度**: `info` 不需要 LLM，`ask/report` 需要 LLM，`plot/query` 需要 pandas
4. **本地优先**: 数据不上传，通过本地 LLM CLI 处理

## 💰 变现路径

| 版本 | 价格 | 功能 |
|------|------|------|
| 免费版 | $0 | info, ask (5次/天), history |
| Pro | $9.99/月 | 无限 ask, report, clean, compare |
| Team | $29.99/月 | 共享历史, 团队报告, API 访问 |

## 📜 License

MIT
