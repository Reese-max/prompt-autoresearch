# -*- coding: utf-8 -*-
"""研究驗證階段執行器：以可恢復檢查點取代單一長逾時。"""
import json
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone


STAGES = (
    "candidate_evaluation",
    "evidence_validation",
    "ranking",
    "report_delivery",
)

# ponytail: 固定四階段 deadline，先提供可稽核上限；若實測瓶頸穩定再拆更細。
DEFAULT_STAGE_DEADLINES = {
    "candidate_evaluation": 600.0,
    "evidence_validation": 60.0,
    "ranking": 30.0,
    "report_delivery": 30.0,
}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _json_safe(value):
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=repr))
    except (TypeError, ValueError):
        return repr(value)


class StageTimeout(TimeoutError):
    """階段 callback 明確表示已逾時。"""


class StageContext:
    def __init__(self, executor, stage, deadline_monotonic):
        self._executor = executor
        self.stage = stage
        self.deadline_monotonic = deadline_monotonic
        self.last_available_output = None

    @property
    def remaining_seconds(self):
        return max(0.0, self.deadline_monotonic - self._executor.clock())

    def heartbeat(self, progress, output=None):
        """持久化一筆進度；長 callback 可在自然檢查點呼叫。"""
        if output is not None:
            self.last_available_output = _json_safe(output)
        event = {"at": self._executor.now(), "progress": str(progress)}
        if output is not None:
            event["output"] = self.last_available_output
        self._executor.state["stages"][self.stage]["heartbeats"].append(event)
        self._executor.persist()

    def checkpoint(self, output, progress="checkpoint"):
        self.heartbeat(progress, output)

    def check_deadline(self):
        if self.remaining_seconds <= 0:
            raise StageTimeout(f"{self.stage} deadline exceeded")


class StagedValidationExecutor:
    """依序執行四階段，並在每個可觀察邊界保存狀態。"""

    def __init__(self, state_path="output/research_validation_state.json", deadlines=None,
                 clock=None, now=None):
        self.state_path = state_path
        self.deadlines = dict(DEFAULT_STAGE_DEADLINES)
        if deadlines:
            for stage, seconds in deadlines.items():
                if stage not in STAGES:
                    raise ValueError(f"unknown validation stage: {stage}")
                seconds = float(seconds)
                if seconds <= 0:
                    raise ValueError(f"deadline must be positive: {stage}")
                self.deadlines[stage] = seconds
        self.clock = clock or time.monotonic
        self.now = now or utc_now
        self.state = {}

    def persist(self):
        """原子寫入 checkpoint，避免中斷時留下半個 JSON。"""
        parent = os.path.dirname(os.path.abspath(self.state_path))
        os.makedirs(parent, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=".research-validation-", suffix=".tmp", dir=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(self.state, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp_path, self.state_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def _new_stage(self, name, started_at, deadline):
        return {
            "status": "running",
            "started_at": started_at,
            "ended_at": None,
            "deadline": deadline,
            "heartbeats": [],
            "last_available_output": None,
        }

    def run(self, callbacks):
        self.state = {
            "schema_version": 1,
            "run_id": uuid.uuid4().hex,
            "status": "running",
            "started_at": self.now(),
            "ended_at": None,
            "stage_deadlines_seconds": dict(self.deadlines),
            "timed_out_stage": None,
            "timed_out_stages": [],
            "last_available_output": None,
            "stages": {},
        }
        self.persist()

        for name in STAGES:
            started_mono = self.clock()
            started_at = self.now()
            deadline_seconds = self.deadlines[name]
            deadline = datetime.fromtimestamp(
                time.time() + deadline_seconds, timezone.utc,
            ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            stage = self._new_stage(name, started_at, deadline)
            self.state["stages"][name] = stage
            context = StageContext(self, name, started_mono + deadline_seconds)
            context.heartbeat("started")
            callback = callbacks.get(name) if isinstance(callbacks, dict) else None

            if callback is None:
                stage["status"] = "skipped"
                stage["ended_at"] = self.now()
                context.heartbeat("skipped")
                continue

            result = None
            error = None
            try:
                result = callback(context)
                context.check_deadline()
                stage["status"] = "completed"
            except (StageTimeout, TimeoutError) as exc:
                error = f"{type(exc).__name__}: {exc}"
                stage["status"] = "timeout"
                self.state["timed_out_stages"].append(name)
                if self.state["timed_out_stage"] is None:
                    self.state["timed_out_stage"] = name
            except Exception as exc:  # 一階段失敗不抹掉其他階段的證據
                error = f"{type(exc).__name__}: {exc}"
                stage["status"] = "failed"

            if result is not None:
                context.last_available_output = _json_safe(result)
            if context.last_available_output is not None:
                stage["last_available_output"] = context.last_available_output
                self.state["last_available_output"] = {
                    "stage": name,
                    "output": context.last_available_output,
                }
            if error:
                stage["error"] = error
            stage["ended_at"] = self.now()
            context.heartbeat(stage["status"])

        self.state["ended_at"] = self.now()
        if self.state["timed_out_stages"]:
            self.state["status"] = "timed_out"
        elif any(stage["status"] == "failed" for stage in self.state["stages"].values()):
            self.state["status"] = "failed"
        else:
            self.state["status"] = "completed"
        self.persist()
        return self.state


def run_staged_validation(callbacks, state_path="output/research_validation_state.json", deadlines=None):
    """便利入口，回傳已持久化的完整狀態。"""
    return StagedValidationExecutor(state_path=state_path, deadlines=deadlines).run(callbacks)
