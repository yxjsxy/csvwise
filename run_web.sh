#!/bin/bash
# csvwise Web UI 启动脚本

cd "$(dirname "$0")"
source venv/bin/activate

echo "🧠 启动 csvwise Web UI..."
echo "📍 http://localhost:8501"

streamlit run app.py --server.port 8501 --server.headless true
