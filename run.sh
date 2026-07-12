#!/bin/bash
echo "=========================================================="
echo "   Prompt AutoResearch v2 本機伺服器與 CORS 代理啟動中..."
echo "=========================================================="
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"
python3 run_app.py
