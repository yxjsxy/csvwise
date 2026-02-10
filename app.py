#!/usr/bin/env python3
"""
csvwise Web UI - Streamlit Application
用自然语言分析 CSV 数据和数据库
"""

import io
import os
import sys
import tempfile
from pathlib import Path

import streamlit as st

# 添加 src 目录到 path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from csvwise import (
    Dataset, 
    load_csv, 
    llm_query, 
    csv_to_markdown_table,
    VERSION
)
from db_connector import DatabaseConnector, get_db_info

# ---------------------------------------------------------------------------
# Page Config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="csvwise - AI 数据分析",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------------------------
# Session State
# ---------------------------------------------------------------------------

if "dataset" not in st.session_state:
    st.session_state.dataset = None
if "headers" not in st.session_state:
    st.session_state.headers = None
if "data" not in st.session_state:
    st.session_state.data = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "db_connector" not in st.session_state:
    st.session_state.db_connector = None

# ---------------------------------------------------------------------------
# Sidebar - Data Source
# ---------------------------------------------------------------------------

st.sidebar.title("🧠 csvwise")
st.sidebar.caption(f"v{VERSION} - AI 数据分析助手")

st.sidebar.markdown("---")
st.sidebar.subheader("📂 数据源")

data_source = st.sidebar.radio(
    "选择数据源",
    ["📁 上传 CSV", "🗄️ 数据库连接"],
    label_visibility="collapsed"
)

if data_source == "📁 上传 CSV":
    uploaded_file = st.sidebar.file_uploader(
        "上传数据文件",
        type=["csv", "tsv", "txt", "xlsx", "xls"],
        help="支持 CSV、TSV、Excel 格式"
    )
    
    if uploaded_file:
        # 保存到临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        
        try:
            headers, data, _ = load_csv(tmp_path)
            st.session_state.headers = headers
            st.session_state.data = data
            st.session_state.dataset = Dataset(tmp_path)
            st.sidebar.success(f"✅ 已加载 {len(data)} 行数据")
        except Exception as e:
            st.sidebar.error(f"❌ 加载失败: {e}")
        finally:
            os.unlink(tmp_path)

elif data_source == "🗄️ 数据库连接":
    st.sidebar.markdown("**连接字符串**")
    
    db_type = st.sidebar.selectbox(
        "数据库类型",
        ["SQLite", "PostgreSQL"]
    )
    
    if db_type == "SQLite":
        db_path = st.sidebar.text_input(
            "数据库路径",
            placeholder="/path/to/database.sqlite"
        )
        conn_str = db_path
    else:
        st.sidebar.markdown("PostgreSQL 连接")
        pg_host = st.sidebar.text_input("主机", value="localhost")
        pg_port = st.sidebar.text_input("端口", value="5432")
        pg_user = st.sidebar.text_input("用户名")
        pg_pass = st.sidebar.text_input("密码", type="password")
        pg_db = st.sidebar.text_input("数据库名")
        conn_str = f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"
    
    if st.sidebar.button("🔗 连接"):
        if conn_str:
            try:
                db = DatabaseConnector(conn_str)
                db.connect()
                st.session_state.db_connector = db
                st.sidebar.success(f"✅ 已连接 ({db.db_type})")
            except Exception as e:
                st.sidebar.error(f"❌ 连接失败: {e}")
    
    # 如果已连接，显示表选择
    if st.session_state.db_connector:
        db = st.session_state.db_connector
        tables = db.list_tables()
        
        selected_table = st.sidebar.selectbox(
            "选择表",
            tables,
            help="选择要分析的表"
        )
        
        if selected_table and st.sidebar.button("📊 加载表"):
            try:
                headers, rows = db.query_table(selected_table, limit=5000)
                st.session_state.headers = headers
                st.session_state.data = list(rows)
                
                # 创建临时 CSV 用于 Dataset
                csv_content = db.table_to_csv_string(selected_table, limit=5000)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w") as tmp:
                    tmp.write(csv_content)
                    tmp_path = tmp.name
                
                st.session_state.dataset = Dataset(tmp_path)
                row_count = db.get_table_row_count(selected_table)
                st.sidebar.success(f"✅ 已加载 {selected_table} ({row_count} 行)")
                
                os.unlink(tmp_path)
            except Exception as e:
                st.sidebar.error(f"❌ 加载失败: {e}")

# ---------------------------------------------------------------------------
# Main Content
# ---------------------------------------------------------------------------

st.title("🧠 csvwise - AI 数据分析")

if st.session_state.dataset is None:
    st.info("👈 请先从左侧上传 CSV 文件或连接数据库")
    
    # 显示功能介绍
    st.markdown("""
    ### ✨ 功能
    
    - **📊 数据概览**: 自动分析数据结构、类型、统计信息
    - **💬 自然语言提问**: 用中文问问题，AI 帮你分析
    - **📈 智能可视化**: 自动推荐并生成图表
    - **🔍 异常检测**: 识别数据中的离群值
    - **📝 报告生成**: 一键生成完整分析报告
    
    ### 🗄️ 支持的数据源
    
    | 类型 | 格式 |
    |------|------|
    | 文件 | CSV, TSV, TXT |
    | 数据库 | SQLite, PostgreSQL |
    """)

else:
    dataset = st.session_state.dataset
    headers = st.session_state.headers
    data = st.session_state.data
    
    # Tabs
    tab_overview, tab_ask, tab_viz, tab_quality = st.tabs([
        "📊 数据概览", "💬 提问分析", "📈 可视化", "🔍 数据质量"
    ])
    
    # ---------------------------------------------------------------------------
    # Tab: 数据概览
    # ---------------------------------------------------------------------------
    with tab_overview:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("行数", f"{len(data):,}")
        with col2:
            st.metric("列数", len(headers))
        with col3:
            quality = dataset.quality
            st.metric("数据质量", f"{quality.get('score', 0):.0f}%")
        with col4:
            outliers = dataset.outliers
            outlier_count = sum(len(v) for v in outliers.values())
            st.metric("异常值", outlier_count)
        
        st.markdown("---")
        
        # 列信息
        st.subheader("📋 列信息")
        
        col_info = []
        col_types = dataset.col_types
        stats = dataset.stats
        
        for i, h in enumerate(headers):
            col_type = col_types.get(h, "unknown")
            col_stats = stats.get(h, {})
            
            info = {
                "列名": h,
                "类型": col_type,
                "非空": f"{col_stats.get('non_null_pct', 0):.0f}%"
            }
            
            if col_type == "numeric":
                info["均值"] = f"{col_stats.get('mean', 0):.2f}"
                info["最小"] = col_stats.get('min', '-')
                info["最大"] = col_stats.get('max', '-')
            elif col_type == "categorical":
                info["唯一值"] = col_stats.get('unique', '-')
            
            col_info.append(info)
        
        st.dataframe(col_info, use_container_width=True)
        
        # 数据预览
        st.subheader("👀 数据预览")
        preview_data = data[:100]
        
        import pandas as pd
        df = pd.DataFrame(preview_data, columns=headers)
        st.dataframe(df, use_container_width=True, height=400)
    
    # ---------------------------------------------------------------------------
    # Tab: 提问分析
    # ---------------------------------------------------------------------------
    with tab_ask:
        st.subheader("💬 用自然语言分析数据")
        
        # 显示聊天历史
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        
        # 用户输入
        user_question = st.chat_input("输入你的问题，例如：哪个产品销售额最高？")
        
        if user_question:
            # 添加用户消息
            st.session_state.chat_history.append({
                "role": "user",
                "content": user_question
            })
            
            with st.chat_message("user"):
                st.markdown(user_question)
            
            # AI 回答
            with st.chat_message("assistant"):
                with st.spinner("分析中..."):
                    try:
                        # 构建 prompt
                        schema = dataset.schema_prompt
                        sample = dataset.sample_table(10)
                        stats_text = dataset.stats_text
                        
                        prompt = f"""你是一个数据分析专家。基于以下数据集信息回答用户问题。

{schema}

数据样本:
{sample}

统计摘要:
{stats_text}

用户问题: {user_question}

请用简洁的中文回答，如果需要计算，展示计算过程。如果无法从数据中得出答案，请说明原因。"""

                        response = llm_query(prompt)
                        st.markdown(response)
                        
                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": response
                        })
                    except Exception as e:
                        st.error(f"分析失败: {e}")
        
        # 快捷问题
        st.markdown("---")
        st.caption("💡 快捷问题")
        
        quick_questions = [
            "这个数据集的主要特征是什么？",
            "有哪些异常值需要注意？",
            "给我一些数据洞察",
            "数据质量如何？有什么问题？"
        ]
        
        cols = st.columns(2)
        for i, q in enumerate(quick_questions):
            if cols[i % 2].button(q, key=f"quick_{i}"):
                st.session_state.chat_history.append({"role": "user", "content": q})
                st.rerun()
    
    # ---------------------------------------------------------------------------
    # Tab: 可视化
    # ---------------------------------------------------------------------------
    with tab_viz:
        st.subheader("📈 数据可视化")
        
        viz_suggestions = dataset.viz_suggestions
        
        if viz_suggestions:
            st.markdown("**🎯 推荐图表**")
            
            for i, viz in enumerate(viz_suggestions[:5]):
                with st.expander(f"{viz.get('title', '图表')} ({viz.get('type', 'chart')})"):
                    st.markdown(f"**描述**: {viz.get('description', '-')}")
                    st.markdown(f"**列**: {', '.join(viz.get('columns', []))}")
                    
                    if st.button("生成", key=f"viz_{i}"):
                        st.info("图表生成功能开发中...")
        
        st.markdown("---")
        st.markdown("**🖌️ 自定义图表**")
        
        chart_type = st.selectbox(
            "图表类型",
            ["折线图", "柱状图", "散点图", "饼图", "直方图"]
        )
        
        numeric_cols = [h for h in headers if dataset.col_types.get(h) == "numeric"]
        categorical_cols = [h for h in headers if dataset.col_types.get(h) == "categorical"]
        
        if chart_type in ["折线图", "柱状图", "散点图"]:
            col1, col2 = st.columns(2)
            with col1:
                x_col = st.selectbox("X 轴", headers)
            with col2:
                y_col = st.selectbox("Y 轴", numeric_cols if numeric_cols else headers)
        elif chart_type == "饼图":
            x_col = st.selectbox("分类列", categorical_cols if categorical_cols else headers)
            y_col = st.selectbox("数值列", numeric_cols if numeric_cols else headers)
        else:
            x_col = st.selectbox("列", numeric_cols if numeric_cols else headers)
            y_col = None
        
        if st.button("📊 生成图表"):
            import pandas as pd
            df = pd.DataFrame(data, columns=headers)
            
            try:
                if chart_type == "折线图":
                    st.line_chart(df.set_index(x_col)[y_col])
                elif chart_type == "柱状图":
                    st.bar_chart(df.set_index(x_col)[y_col])
                elif chart_type == "散点图":
                    st.scatter_chart(df, x=x_col, y=y_col)
                elif chart_type == "直方图":
                    import matplotlib.pyplot as plt
                    fig, ax = plt.subplots()
                    ax.hist(df[x_col].dropna(), bins=30)
                    ax.set_xlabel(x_col)
                    ax.set_ylabel("频率")
                    st.pyplot(fig)
                elif chart_type == "饼图":
                    import matplotlib.pyplot as plt
                    pie_data = df.groupby(x_col)[y_col].sum()
                    fig, ax = plt.subplots()
                    ax.pie(pie_data.values, labels=pie_data.index, autopct='%1.1f%%')
                    st.pyplot(fig)
            except Exception as e:
                st.error(f"图表生成失败: {e}")
    
    # ---------------------------------------------------------------------------
    # Tab: 数据质量
    # ---------------------------------------------------------------------------
    with tab_quality:
        st.subheader("🔍 数据质量分析")
        
        quality = dataset.quality
        
        # 总体评分
        score = quality.get("score", 0)
        
        if score >= 80:
            color = "🟢"
        elif score >= 60:
            color = "🟡"
        else:
            color = "🔴"
        
        st.markdown(f"### {color} 总体评分: {score:.0f}/100")
        
        # 详细分数
        st.markdown("**评分细项**")
        
        details = quality.get("details", {})
        cols = st.columns(4)
        
        metrics = [
            ("completeness", "完整性"),
            ("consistency", "一致性"),
            ("validity", "有效性"),
            ("uniqueness", "唯一性")
        ]
        
        for i, (key, label) in enumerate(metrics):
            val = details.get(key, 0)
            cols[i].metric(label, f"{val:.0f}%")
        
        # 问题列表
        st.markdown("---")
        st.markdown("**⚠️ 发现的问题**")
        
        issues = quality.get("issues", [])
        if issues:
            for issue in issues:
                st.warning(issue)
        else:
            st.success("没有发现明显的数据质量问题")
        
        # 异常值
        st.markdown("---")
        st.markdown("**📊 异常值检测**")
        
        outliers = dataset.outliers
        if outliers:
            for col, vals in outliers.items():
                if vals:
                    with st.expander(f"{col} - {len(vals)} 个异常值"):
                        st.write(vals[:20])
        else:
            st.info("未检测到异常值")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.sidebar.markdown("---")
st.sidebar.caption("Made with ❤️ by Karl & 牧牧")
st.sidebar.caption("[GitHub](https://github.com/yxjsxy/csvwise)")
