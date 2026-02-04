# DEVELOPMENT.md - csvwise 开发文档

## 项目架构

### 设计原则
1. **单文件核心** — `src/csvwise.py` 包含所有逻辑，零第三方依赖（仅 Python 标准库）
2. **LLM-as-Analyst** — 本地 gemini CLI 作为分析引擎，数据不离开本机
3. **渐进式功能** — `info/diagnose` 不需要 LLM（本地分析）；`ask/report/clean` 需要 LLM；`plot/query` 需要 pandas
4. **中英双语** — 自动检测中文 CSV（GBK/GB2312），输出默认中文
5. **DataContext 模式** — 懒加载数据上下文，消除命令间的代码重复

### 核心流程
```
CSV 文件 → load_csv() → DataContext
                           ├── col_types (懒加载) → infer_column_types / infer_advanced_types
                           ├── stats (懒加载) → compute_basic_stats (含 std/q1/q3/iqr)
                           ├── outliers (懒加载) → detect_outliers (IQR 方法)
                           ├── quality (懒加载) → compute_data_quality_score (0-100)
                           ├── viz_suggestions (懒加载) → suggest_visualizations
                           └── schema_prompt (懒加载) → build_schema_prompt → gemini CLI
```

### 数据处理管线
1. **load_csv()** — 自动编码检测 + 分隔符嗅探 + 空行过滤
2. **infer_column_types()** — 采样 50 行，推断 12 种类型 (numeric/date/text/empty/email/url/phone/percentage/currency/boolean/ip)
3. **infer_advanced_types()** — 扩展推断：基数分析 + 唯一值统计
4. **compute_basic_stats()** — 数值列的 min/max/mean/median/sum/std_dev/q1/q3/iqr
5. **detect_outliers()** — IQR 方法异常值检测
6. **compute_data_quality_score()** — 完整性/一致性/有效性三维评分
7. **suggest_visualizations()** — 基于数据特征推荐图表类型
8. **build_schema_prompt()** — 生成结构化数据描述给 LLM
9. **llm_query()** — 调用 gemini CLI，支持超时、重试和错误处理

### LLM Prompt 设计
- 每个命令有专门的 prompt 模板
- 包含：数据 schema + 基础统计 + 异常值 + 质量评分 + 数据样本（前 200 行）
- 角色设定：「你是一个专业的数据分析师」
- 输出要求：中文、具体数据、markdown 格式

## 技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.9+ | Karl 技术栈，生态丰富 |
| CLI 框架 | argparse (标准库) | 零依赖，够用 |
| LLM | gemini CLI | 免费，本地调用，无需 API key 管理 |
| 编码检测 | 多编码尝试 | 兼容中文 CSV (GBK/GB2312) |
| 可视化 | matplotlib (可选) | 标准选择，LLM 生成代码 |
| 日志 | logging (标准库) | 文件日志 + 可选 stderr 输出 |
| 统计 | math (标准库) | 标准差、四分位数等 |

## 文件说明

| 文件 | 说明 |
|------|------|
| `src/csvwise.py` | 核心代码，所有功能 (~650 行) |
| `examples/sales_demo.csv` | 中文销售数据示例 (20行) |
| `examples/stocks_demo.csv` | 美股数据示例 (25行) |
| `tests/test_csvwise.py` | 单元测试 (20个, 不需要 LLM) |
| `setup.py` | pip 安装配置 |
| `PR_REPORT_20260204.md` | v0.2.0 PR 报告 |

## 开发环境

```bash
# 运行测试 (20 tests, 无需 LLM)
python3 tests/test_csvwise.py

# 直接运行
python3 src/csvwise.py info examples/sales_demo.csv
python3 src/csvwise.py diagnose examples/sales_demo.csv
python3 src/csvwise.py ask examples/sales_demo.csv "问题"

# verbose 模式
python3 src/csvwise.py --verbose info examples/sales_demo.csv

# 安装到 PATH
pip install -e .
csvwise info data.csv
```

## 版本历史

### v0.2.0 (2026-02-04)
- ✅ DataContext 类消除代码重复
- ✅ 12 种列类型检测（新增 email/URL/phone/currency/boolean/IP 等）
- ✅ 数据质量评分 (0-100, 三维: 完整性/一致性/有效性)
- ✅ IQR 异常值检测
- ✅ 智能可视化推荐（6种图表类型）
- ✅ 新增 `diagnose` 命令
- ✅ logging 日志系统 + `--verbose` 参数
- ✅ LLM 调用重试机制
- ✅ 性能修复 (O(n²) → O(n))
- ✅ 测试从 7 个增加到 20 个
- ✅ 增强的统计信息（std_dev, Q1, Q3, IQR）

### v0.1.0 (2026-02-03)
- ✅ MVP: info, ask, report, clean, plot, query, compare, history
- ✅ 自动编码检测 (UTF-8/GBK/GB2312)
- ✅ gemini CLI 集成

## 已知限制
1. gemini CLI 有速率限制，连续调用可能超时
2. 大文件（>10000 行）只采样前 200 行发送给 LLM
3. `plot` 和 `query` 命令需要额外安装 pandas/matplotlib
4. 暂不支持 Excel (.xlsx) 格式
5. `cmd_query` 执行 LLM 生成的代码存在安全风险

## 路线图

### v0.3 (计划)
- [ ] 支持 Excel 和 JSON 输入
- [ ] 可配置 LLM 后端（claude, gpt-4, 本地模型）
- [ ] 交互式 REPL 模式
- [ ] 缓存常用查询
- [ ] 代码执行沙箱

### v0.4 (计划)
- [ ] Web UI（Streamlit 或 Gradio）
- [ ] 数据库连接（SQLite, PostgreSQL）
- [ ] 自动图表推荐 + 一键生成
- [ ] 导出 Jupyter Notebook

### v1.0 (目标)
- [ ] 团队协作功能
- [ ] API 服务
- [ ] 付费订阅系统
- [ ] 插件系统

## 变现策略

| 阶段 | 时间 | 目标 |
|------|------|------|
| MVP | ✅ 完成 | CLI 工具，开源引流 |
| v0.3 | 2周后 | Web UI，Product Hunt 发布 |
| v1.0 | 1个月 | SaaS，$9.99/月 Pro |
| 增长 | 3个月 | 团队版，$29.99/月 |

---

*Created: 2026-02-03 | Updated: 2026-02-04*
