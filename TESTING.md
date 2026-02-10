# csvwise 测试指南

## 🔧 环境准备

```bash
cd ~/Documents/vibe_coding/csvwise
pip install -e .
```

### 测试数据
```bash
ls examples/*.csv
```
**预期**: 包含 sales_demo.csv 等示例数据

---

## 🧪 功能测试

### 1. 数据概览 (info)
```bash
csvwise info examples/sales_demo.csv
```
**预期**: 输出包含:
- [ ] 行数/列数
- [ ] 列名和类型
- [ ] 基础统计 (均值/最大/最小)
- [ ] 数据预览

### 2. 自然语言提问 (ask)
```bash
csvwise ask examples/sales_demo.csv "哪个产品销售额最高?"
csvwise ask examples/sales_demo.csv "按月统计销售趋势"
csvwise ask examples/sales_demo.csv "有多少种产品类别?"
```
**预期**: AI 返回准确答案

### 3. 生成报告 (report)
```bash
csvwise report examples/sales_demo.csv -o test_report.md
cat test_report.md
```
**预期**: 生成完整的 Markdown 分析报告

### 4. 数据清洗 (clean)
```bash
csvwise clean examples/sales_demo.csv
```
**预期**: 输出:
- [ ] 缺失值统计
- [ ] 异常值检测
- [ ] 清洗建议

### 5. 可视化 (plot)
```bash
csvwise plot examples/sales_demo.csv "销售趋势" -o trend.png
open trend.png  # macOS
```
**预期**: 生成图表文件

### 6. SQL 查询 (query)
```bash
csvwise query examples/sales_demo.csv "amount > 1000"
csvwise query examples/sales_demo.csv "category == 'Electronics'"
```
**预期**: 返回筛选后的数据

### 7. 数据对比 (compare)
```bash
# 需要两个 CSV 文件
csvwise compare examples/sales_2024.csv examples/sales_2025.csv
```
**预期**: 输出差异分析

### 8. 查询历史 (history)
```bash
csvwise history
```
**预期**: 显示之前的查询记录

---

## 📊 数据类型测试

### 不同格式 CSV
| 格式 | 命令 | 预期结果 |
|------|------|----------|
| UTF-8 | `csvwise info utf8.csv` | 正常解析 |
| GBK | `csvwise info gbk.csv` | 自动检测编码 |
| 带 BOM | `csvwise info bom.csv` | 正常解析 |
| 逗号分隔 | `csvwise info comma.csv` | 正常解析 |
| 分号分隔 | `csvwise info semicolon.csv` | 自动检测分隔符 |

### 大文件测试
```bash
# 测试大文件性能
time csvwise info large_file.csv
```
**预期**: 100MB 文件 < 10 秒

---

## 🐛 错误处理

### 文件不存在
```bash
csvwise info nonexistent.csv
```
**预期**: 友好的错误提示

### 无效 CSV
```bash
echo "invalid data" > /tmp/invalid.csv
csvwise info /tmp/invalid.csv
```
**预期**: 显示解析错误

### 空文件
```bash
touch /tmp/empty.csv
csvwise info /tmp/empty.csv
```
**预期**: 显示"文件为空"提示

---

## 🔄 集成测试

### OpenClaw 集成
```bash
# 通过 OpenClaw 分析 CSV
openclaw run "分析 ~/data.csv 中的销售趋势"
```
**预期**: 调用 csvwise 并返回分析结果

---

## ✅ 发布 Checklist

- [ ] info 命令正常
- [ ] ask 命令 AI 回答准确
- [ ] report 生成完整
- [ ] plot 图表正确
- [ ] query 筛选准确
- [ ] 大文件性能可接受
- [ ] 错误处理友好
