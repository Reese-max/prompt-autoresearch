# -*- coding: utf-8 -*-
"""
api/feedback.py — 回饋資料分析模組

處理來自 Voice Actress (Shenlun) 的評分回饋，並提供分析結果給優化引擎。

功能：
1. 讀取 feedback.jsonl 中的回饋資料
2. 計算各提示詞版本的平均分數
3. 分析各題型的表現差異
4. 提供優化建議
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.io import load_json, read_jsonl
from lib.config import get

# --- 常數 ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEEDBACK_PATH = os.path.join(PROJECT_ROOT, "feedback.jsonl")
BASELINE_META_PATH = os.path.join(PROJECT_ROOT, "prompts", "baseline.meta.json")


def load_feedback(limit=1000):
    """讀取回饋資料。"""
    return read_jsonl(FEEDBACK_PATH, limit=limit)


def analyze_feedback_by_hash(feedback_data=None):
    """按提示詞 hash 分析回饋資料。"""
    if feedback_data is None:
        feedback_data = load_feedback()

    by_hash = defaultdict(lambda: {
        "count": 0,
        "total_score": 0,
        "scores": defaultdict(float),
        "question_types": defaultdict(lambda: {"count": 0, "total": 0}),
    })

    for item in feedback_data:
        prompt_hash = item.get("prompt_hash", "unknown")
        total_score = item.get("total_score", 0)
        scores = item.get("scores", {})
        question_type = item.get("question_type", "unknown")

        entry = by_hash[prompt_hash]
        entry["count"] += 1
        entry["total_score"] += total_score

        for dim, score in scores.items():
            entry["scores"][dim] += score

        entry["question_types"][question_type]["count"] += 1
        entry["question_types"][question_type]["total"] += total_score

    # 計算平均值
    results = {}
    for prompt_hash, data in by_hash.items():
        if data["count"] == 0:
            continue

        avg_scores = {
            dim: round(total / data["count"], 2)
            for dim, total in data["scores"].items()
        }

        avg_by_type = {}
        for qtype, tdata in data["question_types"].items():
            if tdata["count"] > 0:
                avg_by_type[qtype] = round(tdata["total"] / tdata["count"], 2)

        results[prompt_hash] = {
            "count": data["count"],
            "avg_total": round(data["total_score"] / data["count"], 2),
            "avg_scores": avg_scores,
            "avg_by_type": avg_by_type,
        }

    return results


def get_recent_feedback_trend(days=7):
    """取得最近 N 天的回饋趨勢。"""
    feedback_data = load_feedback()
    cutoff = datetime.now() - timedelta(days=days)

    recent = []
    for item in feedback_data:
        try:
            ts = datetime.fromisoformat(item.get("timestamp", ""))
            if ts >= cutoff:
                recent.append(item)
        except (ValueError, TypeError):
            continue

    return analyze_feedback_by_hash(recent)


def get_weak_areas():
    """分析弱點區域（低分維度和題型）。"""
    analysis = analyze_feedback_by_hash()

    weak_dimensions = []
    weak_types = []

    for prompt_hash, data in analysis.items():
        # 找低分維度
        for dim, avg in data["avg_scores"].items():
            if avg < 15:  # 20分滿分，低於15分為弱點
                weak_dimensions.append({
                    "prompt_hash": prompt_hash[:12],
                    "dimension": dim,
                    "avg_score": avg,
                    "count": data["count"],
                })

        # 找低分題型
        for qtype, avg in data["avg_by_type"].items():
            if avg < 70:  # 100分滿分，低於70分為弱點
                weak_types.append({
                    "prompt_hash": prompt_hash[:12],
                    "question_type": qtype,
                    "avg_score": avg,
                    "count": data["count"],
                })

    return {
        "weak_dimensions": sorted(weak_dimensions, key=lambda x: x["avg_score"]),
        "weak_types": sorted(weak_types, key=lambda x: x["avg_score"]),
    }


def generate_optimization_hints():
    """根據回饋資料生成優化建議。"""
    weak_areas = get_weak_areas()
    baseline_meta = load_json(BASELINE_META_PATH)

    hints = []

    # 分析弱點維度
    dim_hints = {
        "issueHit": "加強題意命中：在提示詞中加入更明確的審題指引",
        "scholarlyRef": "加強學說引用：要求引用具體學者姓名和見解",
        "practicalRef": "加強實務見解：要求引用具體判決字號或實務見解",
        "structure": "加強結構完整性：要求更嚴格的段落結構",
        "riskControl": "加強風險控制：加入更明確的防編造指令",
    }

    for item in weak_areas["weak_dimensions"][:3]:  # 取前 3 個最弱維度
        hint = dim_hints.get(item["dimension"], "")
        if hint:
            hints.append({
                "type": "dimension",
                "target": item["dimension"],
                "hint": hint,
                "avg_score": item["avg_score"],
            })

    # 分析弱點題型
    for item in weak_areas["weak_types"][:3]:  # 取前 3 個最弱題型
        hints.append({
            "type": "question_type",
            "target": item["question_type"],
            "hint": f"加強{item['question_type']}：針對該題型做專項優化",
            "avg_score": item["avg_score"],
        })

    return hints


def get_feedback_summary():
    """取得回饋摘要。"""
    feedback_data = load_feedback()
    analysis = analyze_feedback_by_hash(feedback_data)
    weak_areas = get_weak_areas()
    hints = generate_optimization_hints()

    return {
        "total_feedback": len(feedback_data),
        "unique_prompts": len(analysis),
        "prompt_analysis": analysis,
        "weak_areas": weak_areas,
        "optimization_hints": hints,
        "baseline_score": load_json(BASELINE_META_PATH).get("dev_avg"),
    }


if __name__ == "__main__":
    # 命令行列印摘要
    summary = get_feedback_summary()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
