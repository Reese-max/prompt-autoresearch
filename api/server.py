# -*- coding: utf-8 -*-
"""
api/server.py — Prompt AutoResearch API 伺服器

提供 RESTful API 端點，讓外部系統（如 Voice Actress Shenlun）取得優化後的提示詞。

用法：
    python api/server.py                  # 預設 port 5001
    python api/server.py --port 8080      # 指定 port
    python api/server.py --host 0.0.0.0   # 允許外部連線

端點：
    GET  /api/current-prompt      — 取得當前優化提示詞
    GET  /api/prompt-meta         — 取得提示詞 metadata
    GET  /api/champion/<type>     — 取得指定題型的 champion prompt
    GET  /api/route               — 取得路由配置
    POST /api/feedback            — 接收外部評分回饋
    GET  /api/feedback/summary    — 取得回饋摘要
    GET  /api/feedback/weak-areas — 分析弱點區域
    GET  /api/feedback/hints      — 取得優化建議
    GET  /api/health              — 健康檢查
"""
import argparse
import json
import os
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# 確保專案根目錄在 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.io import load_file, load_json, write_json, read_jsonl, append_jsonl
from lib.config import get

# 匯入回饋分析模組（延遲匯入避免循環）
_feedback_module = None

def _get_feedback_module():
    global _feedback_module
    if _feedback_module is None:
        try:
            from api.feedback import get_feedback_summary, get_weak_areas, generate_optimization_hints
            _feedback_module = {
                "summary": get_feedback_summary,
                "weak_areas": get_weak_areas,
                "hints": generate_optimization_hints,
            }
        except ImportError:
            _feedback_module = {}
    return _feedback_module

# --- 常數 ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_PATH = os.path.join(PROJECT_ROOT, "prompts", "current.md")
BASELINE_PATH = os.path.join(PROJECT_ROOT, "prompts", "baseline.md")
BASELINE_META_PATH = os.path.join(PROJECT_ROOT, "prompts", "baseline.meta.json")
CHAMPIONS_DIR = os.path.join(PROJECT_ROOT, "prompts", "champions")
ROUTE_PATH = os.path.join(PROJECT_ROOT, "prompts", "routes", "type_champions.json")
FEEDBACK_PATH = os.path.join(PROJECT_ROOT, "feedback.jsonl")


def cors_headers(handler):
    """設定 CORS headers。"""
    origin = handler.headers.get("Origin", "*")
    handler.send_header("Access-Control-Allow-Origin", origin)
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    handler.send_header("Access-Control-Max-Age", "86400")


def send_json(handler, status, data):
    """傳送 JSON 回應。"""
    body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    cors_headers(handler)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def send_error_json(handler, status, message):
    """傳送 JSON 錯誤回應。"""
    send_json(handler, status, {"error": message})


class PromptAPIHandler(BaseHTTPRequestHandler):
    """Prompt AutoResearch API 請求處理器。"""

    def log_message(self, format, *args):
        """自訂日誌格式。"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {args[0]}")

    def do_OPTIONS(self):
        """處理 CORS preflight 請求。"""
        self.send_response(200)
        cors_headers(self)
        self.end_headers()

    def do_GET(self):
        """處理 GET 請求。"""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        routes = {
            "/api/current-prompt": self._get_current_prompt,
            "/api/prompt-meta": self._get_prompt_meta,
            "/api/baseline": self._get_baseline,
            "/api/route": self._get_route,
            "/api/champions": self._list_champions,
            "/api/feedback/summary": self._get_feedback_summary,
            "/api/feedback/weak-areas": self._get_feedback_weak_areas,
            "/api/feedback/hints": self._get_feedback_hints,
            "/api/optimizer/status": self._get_optimizer_status,
            "/api/health": self._health_check,
        }

        # 動態路由：/api/champion/<type>
        if path.startswith("/api/champion/"):
            type_slug = path[len("/api/champion/"):]
            self._get_champion(type_slug)
            return

        handler = routes.get(path)
        if handler:
            handler()
        else:
            send_error_json(self, 404, f"未知端點: {path}")

    def do_POST(self):
        """處理 POST 請求。"""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/feedback":
            self._post_feedback()
        else:
            send_error_json(self, 404, f"未知端點: {path}")

    # --- 端點實作 ---

    def _get_current_prompt(self):
        """取得當前優化提示詞。"""
        prompt = load_file(PROMPT_PATH)
        if not prompt:
            send_error_json(self, 404, "提示詞檔案不存在")
            return

        prompt_hash = __import__("hashlib").sha256(prompt.encode("utf-8")).hexdigest()
        send_json(self, 200, {
            "prompt": prompt,
            "hash": prompt_hash,
            "length": len(prompt),
            "source": "current.md",
        })

    def _get_prompt_meta(self):
        """取得提示詞 metadata。"""
        meta = load_json(BASELINE_META_PATH)
        if not meta:
            send_error_json(self, 404, "metadata 檔案不存在")
            return

        send_json(self, 200, meta)

    def _get_baseline(self):
        """取得 baseline 提示詞。"""
        prompt = load_file(BASELINE_PATH)
        if not prompt:
            send_error_json(self, 404, "baseline 檔案不存在")
            return

        prompt_hash = __import__("hashlib").sha256(prompt.encode("utf-8")).hexdigest()
        send_json(self, 200, {
            "prompt": prompt,
            "hash": prompt_hash,
            "length": len(prompt),
            "source": "baseline.md",
        })

    def _get_route(self):
        """取得路由配置。"""
        route = load_json(ROUTE_PATH)
        if not route:
            send_error_json(self, 404, "路由配置不存在")
            return

        send_json(self, 200, route)

    def _list_champions(self):
        """列出所有 champion prompts。"""
        if not os.path.exists(CHAMPIONS_DIR):
            send_json(self, 200, {"champions": []})
            return

        champions = []
        for filename in sorted(os.listdir(CHAMPIONS_DIR)):
            if filename.endswith(".md"):
                type_slug = filename[:-3]
                filepath = os.path.join(CHAMPIONS_DIR, filename)
                prompt = load_file(filepath)
                meta_path = filepath.replace(".md", ".meta.json")
                meta = load_json(meta_path)
                champions.append({
                    "type_slug": type_slug,
                    "type_name": meta.get("type", type_slug),
                    "length": len(prompt),
                    "meta": meta,
                })

        send_json(self, 200, {"champions": champions})

    def _get_champion(self, type_slug):
        """取得指定題型的 champion prompt。"""
        filepath = os.path.join(CHAMPIONS_DIR, f"{type_slug}.md")
        if not os.path.exists(filepath):
            # 嘗試中文名稱查找
            meta_files = [f for f in os.listdir(CHAMPIONS_DIR) if f.endswith(".meta.json")]
            for meta_file in meta_files:
                meta = load_json(os.path.join(CHAMPIONS_DIR, meta_file))
                if meta.get("type") == type_slug or meta.get("type_slug") == type_slug:
                    filepath = os.path.join(CHAMPIONS_DIR, meta_file.replace(".meta.json", ".md"))
                    break

        if not os.path.exists(filepath):
            send_error_json(self, 404, f"找不到題型 '{type_slug}' 的 champion prompt")
            return

        prompt = load_file(filepath)
        meta_path = filepath.replace(".md", ".meta.json")
        meta = load_json(meta_path)
        prompt_hash = __import__("hashlib").sha256(prompt.encode("utf-8")).hexdigest()

        send_json(self, 200, {
            "prompt": prompt,
            "hash": prompt_hash,
            "length": len(prompt),
            "type_slug": type_slug,
            "meta": meta,
        })

    def _post_feedback(self):
        """接收外部評分回饋。"""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            send_error_json(self, 400, "請求內容為空")
            return

        try:
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            send_error_json(self, 400, f"JSON 解析失敗: {e}")
            return

        # 驗證必要欄位
        required = ["source", "prompt_hash", "scores"]
        missing = [f for f in required if f not in data]
        if missing:
            send_error_json(self, 400, f"缺少必要欄位: {', '.join(missing)}")
            return

        # 補充 metadata
        feedback = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source": data["source"],
            "prompt_hash": data["prompt_hash"],
            "scores": data["scores"],
            "total_score": data.get("total_score"),
            "question_id": data.get("question_id"),
            "question_type": data.get("question_type"),
            "session_id": data.get("session_id"),
            "metadata": data.get("metadata", {}),
        }

        # 寫入 feedback log
        append_jsonl(FEEDBACK_PATH, feedback)

        send_json(self, 200, {
            "status": "accepted",
            "feedback_id": feedback["timestamp"],
        })

    def _get_feedback_summary(self):
        """取得回饋摘要。"""
        fb = _get_feedback_module()
        if not fb.get("summary"):
            send_json(self, 200, {"message": "回饋分析模組不可用", "total_feedback": 0})
            return

        try:
            summary = fb["summary"]()
            send_json(self, 200, summary)
        except Exception as e:
            send_error_json(self, 500, f"分析失敗: {e}")

    def _get_feedback_weak_areas(self):
        """分析弱點區域。"""
        fb = _get_feedback_module()
        if not fb.get("weak_areas"):
            send_json(self, 200, {"weak_dimensions": [], "weak_types": []})
            return

        try:
            weak_areas = fb["weak_areas"]()
            send_json(self, 200, weak_areas)
        except Exception as e:
            send_error_json(self, 500, f"分析失敗: {e}")

    def _get_feedback_hints(self):
        """取得優化建議。"""
        fb = _get_feedback_module()
        if not fb.get("hints"):
            send_json(self, 200, {"hints": []})
            return

        try:
            hints = fb["hints"]()
            send_json(self, 200, {"hints": hints})
        except Exception as e:
            send_error_json(self, 500, f"分析失敗: {e}")

    def _get_optimizer_status(self):
        """取得優化器狀態。"""
        log_path = os.path.join(PROJECT_ROOT, "optimization_log.jsonl")
        feedback_path = os.path.join(PROJECT_ROOT, "feedback.jsonl")

        # 讀取最近的優化記錄
        recent_logs = read_jsonl(log_path, limit=10) if os.path.exists(log_path) else []
        feedback_count = len(read_jsonl(feedback_path)) if os.path.exists(feedback_path) else 0

        # 取得最後一次優化結果
        last_optimization = None
        for log in reversed(recent_logs):
            if log.get("event") == "optimization":
                last_optimization = log
                break

        send_json(self, 200, {
            "feedback_count": feedback_count,
            "recent_logs": recent_logs[-5:],  # 最近 5 筆記錄
            "last_optimization": last_optimization,
            "status": "active" if last_optimization else "idle",
        })

    def _health_check(self):
        """健康檢查。"""
        prompt = load_file(PROMPT_PATH)
        meta = load_json(BASELINE_META_PATH)
        send_json(self, 200, {
            "status": "healthy",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "prompt_available": bool(prompt),
            "meta_available": bool(meta),
            "prompt_length": len(prompt) if prompt else 0,
            "baseline_score": meta.get("dev_avg") if meta else None,
        })


def main():
    parser = argparse.ArgumentParser(description="Prompt AutoResearch API 伺服器")
    parser.add_argument("--host", default="127.0.0.1", help="綁定位址（預設 127.0.0.1）")
    parser.add_argument("--port", type=int, default=5001, help="連接埠（預設 5001）")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), PromptAPIHandler)
    print(f"{'='*60}")
    print(f"  Prompt AutoResearch API 伺服器")
    print(f"  位址: http://{args.host}:{args.port}")
    print(f"{'='*60}")
    print(f"  端點:")
    print(f"    GET  /api/current-prompt      — 取得當前優化提示詞")
    print(f"    GET  /api/prompt-meta         — 取得提示詞 metadata")
    print(f"    GET  /api/baseline            — 取得 baseline 提示詞")
    print(f"    GET  /api/route               — 取得路由配置")
    print(f"    GET  /api/champions           — 列出所有 champion")
    print(f"    GET  /api/champion/<type>     — 取得指定題型 champion")
    print(f"    POST /api/feedback            — 接收評分回饋")
    print(f"    GET  /api/feedback/summary    — 取得回饋摘要")
    print(f"    GET  /api/feedback/weak-areas — 分析弱點區域")
    print(f"    GET  /api/feedback/hints      — 取得優化建議")
    print(f"    GET  /api/health              — 健康檢查")
    print(f"{'='*60}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n伺服器已停止")
        server.server_close()


if __name__ == "__main__":
    main()
