# -*- coding: utf-8 -*-
import http.server
import socketserver
import urllib.request
import urllib.error
import json
import os
import webbrowser
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

PORT = 8000
ALLOWED_PROXY_HOSTS = {
    "api.minimaxi.chat",
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
}

def read_text(path, default=""):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def read_jsonl(path, limit=None):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
                if limit and len(rows) >= limit:
                    break
    return rows

def read_tsv(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        lines = [line.rstrip("\n").split("\t") for line in f if line.strip()]
    if not lines:
        return []
    header = lines[0]
    return [dict(zip(header, row)) for row in lines[1:] if len(row) == len(header)]


def count_jsonl_rows(path):
    if not os.path.exists(path):
        return 0
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def file_state(root, relative_path):
    path = Path(root) / relative_path
    return {
        "path": relative_path.replace("\\", "/"),
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() and path.is_file() else 0,
    }


def read_json_file(path, default=None):
    if default is None:
        default = {}
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc)}


def to_project_path(root, path):
    path = Path(path)
    try:
        return path.resolve().relative_to(Path(root).resolve()).as_posix()
    except Exception:
        return str(path).replace("\\", "/")


def extract_score_diff(meta, split):
    comparison = meta.get(f"{split}_comparison") or {}
    if "score_diff" in comparison:
        return comparison.get("score_diff")
    if split == "dev":
        return meta.get("diff")
    return None


def build_champion_status(root):
    champions_dir = root / "prompts" / "champions"
    items = []
    if champions_dir.exists():
        for prompt_path in sorted(champions_dir.glob("*.md")):
            type_slug = prompt_path.stem
            meta_path = prompt_path.with_suffix(".meta.json")
            meta = read_json_file(meta_path)
            items.append({
                "type_slug": type_slug,
                "type": meta.get("type", type_slug),
                "path": to_project_path(root, prompt_path),
                "meta_path": to_project_path(root, meta_path),
                "exists": prompt_path.exists(),
                "bytes": prompt_path.stat().st_size,
                "decision": meta.get("decision") or ("ACTIVE_CHAMPION" if meta else "NO_META"),
                "updated_at": meta.get("updated_at") or meta.get("saved_at"),
                "candidate_path": (meta.get("candidate_path") or meta.get("candidate_source") or ""),
                "dev_run": meta.get("dev_run", ""),
                "holdout_run": meta.get("holdout_run", ""),
                "dev_score_diff": extract_score_diff(meta, "dev"),
                "holdout_score_diff": extract_score_diff(meta, "holdout"),
                "risk_rate": (meta.get("dev_comparison") or {}).get("risk_rate", meta.get("risk_rate")),
            })

    return {
        "path": "prompts/champions",
        "count": len(items),
        "items": items,
    }


def build_route_status(root):
    active_path = root / "prompts" / "routes" / "type_champions.json"
    type_decision_path = root / "prompts" / "routes" / "type_champions.decision.json"
    loop_decision_path = root / "prompts" / "routes" / "route_loop.decision.json"

    active = read_json_file(active_path)
    type_decision = read_json_file(type_decision_path)
    loop_decision = read_json_file(loop_decision_path)

    by_type = active.get("by_type") or {}
    best = loop_decision.get("best") or {}

    return {
        "active": {
            "path": "prompts/routes/type_champions.json",
            "exists": active_path.exists(),
            "name": active.get("name", ""),
            "default_prompt": active.get("default_prompt", ""),
            "by_type": by_type,
            "by_type_count": len(by_type),
        },
        "type_champion_decision": {
            "path": "prompts/routes/type_champions.decision.json",
            "exists": type_decision_path.exists(),
            "decision": type_decision.get("decision", "UNKNOWN"),
            "accepted": bool(type_decision.get("accepted", False)),
            "dev_diff": type_decision.get("dev_diff"),
            "holdout_diff": type_decision.get("holdout_diff"),
            "dev_run": type_decision.get("dev_run", ""),
            "holdout_run": type_decision.get("holdout_run", ""),
        },
        "loop_decision": {
            "path": "prompts/routes/route_loop.decision.json",
            "exists": loop_decision_path.exists(),
            "updated_at": loop_decision.get("updated_at", ""),
            "decision": loop_decision.get("decision", "UNKNOWN"),
            "candidate_count": loop_decision.get("candidate_count", 0),
            "accepted_count": loop_decision.get("accepted_count", 0),
            "best": {
                "route_path": (best.get("route_path") or "").replace("\\", "/"),
                "name": best.get("name", ""),
                "accepted": bool(best.get("accepted", False)),
                "dev_avg": best.get("dev_avg"),
                "holdout_avg": best.get("holdout_avg"),
                "dev_diff": best.get("dev_diff"),
                "holdout_diff": best.get("holdout_diff"),
                "dev_accept": bool(best.get("dev_accept", False)),
                "holdout_accept": bool(best.get("holdout_accept", False)),
            },
        },
    }


def build_architecture_snapshot(project_root=None):
    root = Path(project_root or Path(__file__).resolve().parent).resolve()
    dataset_groups = ["smoke", "dev", "holdout", "final"]
    champion_status = build_champion_status(root)
    route_status = build_route_status(root)

    return {
        "version": "v3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": {
            "name": "Prompt AutoResearch",
            "root": str(root),
            "purpose": "臺灣國考申論題提示詞的自動演化、評估與回歸守門。",
        },
        "frontend": {
            "entry": "index.html",
            "assets": ["app.js", "styles.css"],
            "tabs": [
                "workspace",
                "optimizer",
                "architecture",
                "questions",
                "rubrics",
                "arena",
                "settings",
            ],
        },
        "server": {
            "entry": "run_app.py",
            "routes": [
                "/",
                "/api/architecture",
                "/api/get-current-prompt",
                "/api/get-baseline-prompt",
                "/api/questions/<group>",
                "/api/latest-summary",
                "/api/latest-decision",
                "/api/experiment-report",
                "/api/evolution-log",
                "/api/results",
                "/api/baseline-meta",
                "/api/run-evolution",
                "/api/run-final",
                "/api/proxy",
            ],
            "proxy_allowlist": sorted(ALLOWED_PROXY_HOSTS),
        },
        "modules": [
            {
                "name": "Local UI Server",
                "path": "run_app.py",
                "role": "服務靜態前端、讀取本機資料、啟動評估/演化 subprocess、提供安全 CORS proxy。",
            },
            {
                "name": "Optimization Engine",
                "path": "run_opt.py / auto_evolve.py / route_loop.py / route_evolve.py",
                "role": "產生候選提示詞、跑 smoke/dev/holdout、執行 route-subset 與 champion 決策。",
            },
            {
                "name": "Evaluation Scripts",
                "path": "scripts/",
                "role": "固定題庫、評分、gatekeeper、compare_runs 與 leaderboard，不應因候選提示詞而改變。",
            },
            {
                "name": "Prompt Store",
                "path": "prompts/",
                "role": "保存 current、baseline、候選、champions 與 routing prompt。",
            },
            {
                "name": "Champion Store",
                "path": "prompts/champions/ + prompts/routes/",
                "role": "保存題型 champion prompt、active type route 與 route-loop promotion 決策狀態。",
            },
            {
                "name": "Historical Runs",
                "path": "runs/",
                "role": "保存每輪 details、summary、decision 與 route source，作為決策審計軌跡。",
            },
        ],
        "pipeline": [
            {
                "id": "gatekeeper",
                "name": "硬性規則閘門",
                "command": "python scripts/gatekeeper.py prompts/current.md",
                "evidence": "候選提示詞需通過長度、格式、風險與禁止事項。",
            },
            {
                "id": "smoke",
                "name": "Smoke 快速篩選",
                "command": "python scripts/evaluate.py prompts/current.md questions/smoke.jsonl --parallel 6",
                "evidence": "先用小題庫排除明顯退步或風險候選。",
            },
            {
                "id": "dev",
                "name": "Dev 正式評分",
                "command": "python scripts/evaluate.py prompts/current.md questions/dev.jsonl --parallel 24",
                "evidence": "以開發題庫驗證總分、題型平均與 F-code 改善。",
            },
            {
                "id": "holdout",
                "name": "Holdout 防過擬合",
                "command": "python scripts/evaluate.py prompts/current.md questions/holdout.jsonl --parallel 24",
                "evidence": "更新 baseline 前需確認盲測不退步。",
            },
        ],
        "datasets": {
            group: {
                "path": f"questions/{group}.jsonl",
                "count": count_jsonl_rows(root / "questions" / f"{group}.jsonl"),
            }
            for group in dataset_groups
        },
        "champions": champion_status,
        "route_status": route_status,
        "key_files": [
            file_state(root, "program.md"),
            file_state(root, "config.json"),
            file_state(root, "prompts/current.md"),
            file_state(root, "prompts/baseline.md"),
            file_state(root, "prompts/baseline.meta.json"),
            file_state(root, "prompts/routes/type_champions.json"),
            file_state(root, "prompts/routes/type_champions.decision.json"),
            file_state(root, "prompts/routes/route_loop.decision.json"),
            file_state(root, "results.tsv"),
            file_state(root, "runs/latest/summary.md"),
            file_state(root, "runs/latest/decision.md"),
        ],
        "write_boundaries": [
            "演化 agent 原則上只應改 prompts/current.md 或產生 prompts/candidates/*。",
            "questions/、rubrics/、scripts/、program.md、歷史 runs 與 results.tsv 是固定評估資產。",
            "本機 UI/API 變更需用測試證明，不可改 evaluator 換取分數。",
        ],
    }


def build_experiment_report_snapshot(limit=10):
    from scripts.experiment_report import build_report, list_runs

    safe_limit = max(1, min(50, int(limit or 10)))
    rows = list_runs()
    return {
        "path": "generated:experiment_report",
        "run_count": len(rows),
        "limit": safe_limit,
        "content": build_report(rows, safe_limit),
    }


class LocalProxyHandler(http.server.SimpleHTTPRequestHandler):
    def send_json(self, status, payload):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def send_text(self, status, text, content_type="text/plain; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))

    def do_GET(self):
        if self.path == "/favicon.ico":
            self.send_response(200)
            self.send_header("Content-Type", "image/x-icon")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b"")
            return
        elif self.path == "/api/get-current-prompt":
            try:
                with open("prompts/current.md", "r", encoding="utf-8") as f:
                    content = f.read()
                self.send_json(200, {"prompt": content})
            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return
        elif self.path == "/api/get-baseline-prompt":
            try:
                with open("prompts/baseline.md", "r", encoding="utf-8") as f:
                    content = f.read()
                self.send_json(200, {"prompt": content})
            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return
        elif self.path == "/api/architecture":
            self.send_json(200, build_architecture_snapshot())
            return
        elif self.path.startswith("/api/questions"):
            parsed = urlparse(self.path)
            if parsed.path == "/api/questions":
                group = parse_qs(parsed.query).get("group", ["smoke"])[0]
            else:
                group = unquote(parsed.path.rsplit("/", 1)[-1])
            if group not in {"smoke", "dev", "holdout", "final"}:
                self.send_json(400, {"error": "unknown question group"})
                return
            path = os.path.join("questions", f"{group}.jsonl")
            self.send_json(200, {"group": group, "count": len(read_jsonl(path)), "questions": read_jsonl(path)})
            return
        elif self.path == "/api/latest-summary":
            self.send_json(200, {"path": "runs/latest/summary.md", "content": read_text("runs/latest/summary.md")})
            return
        elif self.path == "/api/latest-decision":
            self.send_json(200, {"path": "runs/latest/decision.md", "content": read_text("runs/latest/decision.md")})
            return
        elif self.path.startswith("/api/experiment-report"):
            parsed = urlparse(self.path)
            try:
                limit = int(parse_qs(parsed.query).get("limit", ["10"])[0])
            except ValueError:
                limit = 10
            self.send_json(200, build_experiment_report_snapshot(limit))
            return
        elif self.path == "/api/evolution-log":
            self.send_json(200, {"path": "runs/evolution.log", "content": read_text("runs/evolution.log")})
            return
        elif self.path == "/api/results":
            self.send_json(200, {"path": "results.tsv", "rows": read_tsv("results.tsv")})
            return
        elif self.path == "/api/baseline-meta":
            meta_path = "prompts/baseline.meta.json"
            payload = {}
            if os.path.exists(meta_path):
                try:
                    payload = json.loads(read_text(meta_path))
                except Exception as e:
                    payload = {"error": str(e)}
            self.send_json(200, {"path": meta_path, "meta": payload})
            return
        else:
            super().do_GET()
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, x-api-key, anthropic-version, anthropic-dangerously-allow-browser')
        self.end_headers()

    def do_POST(self):
        if self.path == '/api/run-evolution':
            print("[CORS Proxy] 正在後台啟動自動化深度演化引擎...")
            try:
                content_length = int(self.headers.get('Content-Length', '0') or 0)
                body = self.rfile.read(content_length) if content_length else b"{}"
                req_json = json.loads(body.decode("utf-8") or "{}")
            except Exception:
                req_json = {}
            try:
                generations = max(1, min(20, int(req_json.get("generations", 1))))
            except Exception:
                generations = 1
            # 使用與當前伺服器相同的 Python 解譯器來啟動，確保跨平台相容性
            python_bin = sys.executable if sys.executable else "python3"
            
            # 建立 runs/ 目錄以存放日誌
            os.makedirs("runs", exist_ok=True)
            log_file = open("runs/evolution.log", "w", encoding="utf-8")
            
            cmd = [python_bin, "-u", "auto_evolve.py", str(generations)]
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=os.environ.copy()
            )
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "started",
                "pid": process.pid,
                "generations": generations,
                "command": " ".join(cmd),
                "message": f"{generations} 代自主演化任務已在後台啟動；詳細進度請見 runs/evolution.log"
            }).encode('utf-8'))
            return

        if self.path == "/api/run-final":
            try:
                content_length = int(self.headers.get('Content-Length', '0') or 0)
                body = self.rfile.read(content_length) if content_length else b"{}"
                req_json = json.loads(body.decode("utf-8") or "{}")
                parallel = max(1, min(48, int(req_json.get("parallel", 24))))
            except Exception:
                parallel = 24
            os.makedirs("runs", exist_ok=True)
            log_file = open("runs/final.log", "w", encoding="utf-8")
            python_bin = sys.executable if sys.executable else "python3"
            cmd = [python_bin, "-u", "scripts/evaluate.py", "prompts/current.md", "questions/final.jsonl", "--parallel", str(parallel)]
            process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, env=os.environ.copy())
            self.send_json(200, {
                "status": "started",
                "pid": process.pid,
                "parallel": parallel,
                "command": " ".join(cmd),
                "message": f"final 驗收已在後台啟動；詳細進度請見 runs/final.log"
            })
            return

        if self.path == '/api/proxy':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            req_json = json.loads(post_data.decode('utf-8'))
            
            target_url = req_json['url']
            parsed_target = urlparse(target_url)
            if parsed_target.scheme != "https" or parsed_target.hostname not in ALLOWED_PROXY_HOSTS:
                self.send_json(403, {
                    "error": "proxy target not allowed",
                    "allowed_hosts": sorted(ALLOWED_PROXY_HOSTS)
                })
                return
            headers = req_json['headers']
            body = req_json['body']
            
            print(f"[CORS Proxy] 正在將請求轉發至: {target_url}")
            
            # Perform server-side call to bypass browser CORS
            req = urllib.request.Request(
                target_url,
                data=json.dumps(body).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            
            try:
                with urllib.request.urlopen(req, timeout=120) as response:
                    res_status = response.status
                    res_body = response.read()
                    
                    self.send_response(res_status)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(res_body)
            except urllib.error.HTTPError as e:
                res_body = e.read()
                self.send_response(e.code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(res_body)
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

def main():
    # Change directory to script location
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Allow socket address reuse
    socketserver.ThreadingTCPServer.allow_reuse_address = True

    with socketserver.ThreadingTCPServer(("", PORT), LocalProxyHandler) as httpd:
        print(f"==========================================================")
        print(f"   Prompt AutoResearch v3 本機伺服器與 CORS 代理啟動成功！")
        print(f"   請在您的瀏覽器中開啟： http://localhost:{PORT}")
        print(f"==========================================================")
        
        if "--open" in sys.argv:
            try:
                webbrowser.open(f"http://localhost:{PORT}")
            except Exception:
                pass
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[系統] 伺服器已安全關閉。")
            sys.exit(0)


if __name__ == "__main__":
    main()
