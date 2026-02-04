# DEVELOPMENT.md - csvwise 开发文档

## 项目架构

### 设计原则
1. **单文件核心** — `src/csvwise.py` 包含所有逻辑，零第三方依赖（仅 Python 标准库）
2. **LLM-as-Analyst** — 本地 gemini CLI 作为分析引擎，数据不离开本机
3. **渐进式功能** — `info` 纯 Python 无需 LLM；`ask/report/clean` 需要 LLM；`plot/query` 需要 pandas
4. **中英双语** — 自动检测中文 CSV（GBK/GB2312），输出默认中文

### 核心流程
```
CSV 文件 → load_csv() → 类型推断 → 统计计算 → 构建 prompt → gemini CLI → 格式化输出
                ↓
         编码检测 (utf-8/gbk/gb2312/latin-1)
         分隔符检测 (csv.Sniffer)
```

### 数据处理管线
1. **load_csv()** — 自动编码检测 + 分隔符嗅探
2. **infer_column_types()** — 采样 50 行，推断 numeric/date/text/empty
3. **compute_basic_stats()** — 数值列的 min/max/mean/median/sum
4. **build_schema_prompt()** — 生成结构化数据描述给 LLM
5. **llm_query()** — 调用 gemini CLI，支持超时和错误处理

### LLM Prompt 设计
- 每个命令有专门的 prompt 模板
- 包含：数据 schema + 基础统计 + 数据样本（前 200 行）
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

## 文件说明

| 文件 | 说明 |
|------|------|
| `src/csvwise.py` | 核心代码，所有功能 |
| `examples/sales_demo.csv` | 中文销售数据示例 |
| `examples/stocks_demo.csv` | 美股数据示例 |
| `tests/test_csvwise.py` | 单元测试（不需要 LLM） |
| `setup.py` | pip 安装配置 |

## 开发环境

```bash
# 运行测试
python3 tests/test_csvwise.py

# 直接运行
python3 src/csvwise.py info examples/sales_demo.csv
python3 src/csvwise.py ask examples/sales_demo.csv "问题"

# 安装到 PATH
pip install -e .
csvwise info data.csv
```

## 已知限制
1. gemini CLI 有速率限制，连续调用可能超时
2. 大文件（>10000 行）只采样前 200 行发送给 LLM
3. `plot` 和 `query` 命令需要额外安装 pandas/matplotlib
4. 暂不支持 Excel (.xlsx) 格式

## 路线图

### v0.2 (计划)
- [ ] 支持 Excel 和 JSON 输入
- [ ] 可配置 LLM 后端（claude, gpt-4, 本地模型）
- [ ] 交互式 REPL 模式
- [ ] 缓存常用查询

### v0.3 (计划)
- [ ] Web UI（Streamlit 或 Gradio）
- [ ] 数据库连接（SQLite, PostgreSQL）
- [ ] 自动图表推荐
- [ ] 导出 Jupyter Notebook

### v1.0 (目标)
- [ ] 团队协作功能
- [ ] API 服务
- [ ] 付费订阅系统
- [ ] 插件系统

## 变现策略

| 阶段 | 时间 | 目标 |
|------|------|------|
| MVP | 现在 | CLI 工具，开源引流 |
| v0.3 | 2周后 | Web UI，Product Hunt 发布 |
| v1.0 | 1个月 | SaaS，$9.99/月 Pro |
| 增长 | 3个月 | 团队版，$29.99/月 |

---

*Created: 2026-02-04*
