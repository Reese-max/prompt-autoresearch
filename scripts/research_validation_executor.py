# -*- coding: utf-8 -*-
"""研究驗證階段執行器：以可恢復檢查點取代單一長逾時。"""
import json
import hashlib
import os
import subprocess
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


def _command_record(command, stage, candidate_id="", reason=""):
    """把重跑命令正規化成可直接解析的資料。"""
    if isinstance(command, dict):
        record = _json_safe(command)
    elif isinstance(command, (list, tuple)):
        record = {"argv": [str(item) for item in command]}
    else:
        record = {"command": str(command)}
    if not isinstance(record, dict):
        record = {"command": str(record)}
    argv = record.get("argv")
    if not record.get("command") and isinstance(argv, list) and argv:
        record["command"] = subprocess.list2cmdline([str(item) for item in argv])
    record.setdefault("stage", stage)
    if candidate_id:
        record.setdefault("candidate_id", candidate_id)
    if reason:
        record.setdefault("reason", reason)
    return record


def _candidate_id(value):
    if isinstance(value, dict):
        return str(
            value.get("candidate_id")
            or value.get("candidate_path")
            or value.get("id")
            or value.get("path")
            or ""
        )
    return str(value or "")


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
            self._executor.consume_recovery_output(self.stage, output)
        event = {"at": self._executor.now(), "progress": str(progress)}
        if output is not None:
            event["output"] = self.last_available_output
        self._executor.state["stages"][self.stage]["heartbeats"].append(event)
        self._executor.persist()

    def checkpoint(self, output, progress="checkpoint"):
        self.heartbeat(progress, output)

    def completed_candidate(self, candidate_id, evidence):
        """追加一筆不可變的完成候選證據。"""
        return self._executor.record_completed_candidate(
            self.stage, candidate_id, evidence,
        )

    mark_candidate_completed = completed_candidate

    def isolate_candidate(self, candidate_id, reason, rerun_command=None):
        """只隔離指定候選，並留下可重跑工作。"""
        return self._executor.record_isolated_candidate(
            self.stage, candidate_id, reason, rerun_command,
        )

    isolate = isolate_candidate

    def add_rerun_command(self, command, candidate_id="", reason=""):
        return self._executor.add_rerun_command(
            command, self.stage, candidate_id, reason,
        )

    def add_remaining_work(self, candidate_id="", reason="", rerun_command=None):
        return self._executor.add_remaining_work(
            self.stage, candidate_id, reason, rerun_command,
        )

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

    def _archive_previous_state(self, previous):
        if not isinstance(previous, dict) or not previous:
            return ""
        run_id = previous.get("run_id") or uuid.uuid4().hex
        archive_path = f"{self.state_path}.attempt-{run_id}.json"
        if os.path.exists(archive_path):
            archive_path = f"{self.state_path}.attempt-{run_id}-{uuid.uuid4().hex[:8]}.json"
        with open(archive_path, "x", encoding="utf-8", newline="\n") as handle:
            json.dump(previous, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        return archive_path

    @staticmethod
    def _attempt_snapshot(previous):
        return _json_safe({
            "run_id": previous.get("run_id", ""),
            "attempt_number": previous.get("attempt_number", 1),
            "status": previous.get("status", ""),
            "started_at": previous.get("started_at", ""),
            "ended_at": previous.get("ended_at", ""),
            "timed_out_stage": previous.get("timed_out_stage"),
            "timed_out_stages": previous.get("timed_out_stages", []),
            "stages": previous.get("stages", {}),
            "completed_candidates": previous.get("completed_candidates", []),
            "isolated_candidates": previous.get("isolated_candidates", []),
            "rerun_commands": previous.get("rerun_commands", []),
            "remaining_work": previous.get("remaining_work", []),
        })

    def _recovery(self):
        return self.state.setdefault("recovery", {
            "isolated_stages": [],
            "isolated_candidates": [],
            "completed_candidates": [],
            "rerun_commands": [],
            "remaining_work": [],
        })

    def record_completed_candidate(self, stage, candidate_id, evidence):
        candidate_id = _candidate_id(candidate_id)
        item = {
            "candidate_id": candidate_id,
            "stage": stage,
            "attempt": self.state.get("attempt_number", 1),
            "status": "completed",
            "immutable": True,
            "evidence": _json_safe(evidence),
        }
        item["evidence_sha256"] = hashlib.sha256(
            json.dumps(item["evidence"], ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        completed = self.state.setdefault("completed_candidates", [])
        if not any(
            row.get("candidate_id") == candidate_id
            and row.get("stage") == stage
            and row.get("attempt") == item["attempt"]
            for row in completed
            if isinstance(row, dict)
        ):
            completed.append(item)
            self._recovery()["completed_candidates"] = completed
            self.persist()
        return item

    def record_isolated_candidate(self, stage, candidate_id, reason, rerun_command=None):
        candidate_id = _candidate_id(candidate_id)
        item = {
            "candidate_id": candidate_id,
            "stage": stage,
            "attempt": self.state.get("attempt_number", 1),
            "status": "isolated",
            "reason": str(reason),
        }
        isolated = self.state.setdefault("isolated_candidates", [])
        if not any(
            row.get("candidate_id") == candidate_id
            and row.get("stage") == stage
            and row.get("attempt") == item["attempt"]
            for row in isolated
            if isinstance(row, dict)
        ):
            isolated.append(item)
        self._recovery()["isolated_candidates"] = isolated
        if rerun_command:
            self.add_rerun_command(rerun_command, stage, candidate_id, str(reason))
        self.add_remaining_work(stage, candidate_id, str(reason), rerun_command)
        self.state["global_best_allowed"] = False
        self.persist()
        return item

    def add_rerun_command(self, command, stage="", candidate_id="", reason=""):
        record = _command_record(command, stage, _candidate_id(candidate_id), reason)
        commands = self.state.setdefault("rerun_commands", [])
        if record not in commands:
            commands.append(record)
        self._recovery()["rerun_commands"] = commands
        self.persist()
        return record

    def add_remaining_work(self, stage, candidate_id="", reason="", rerun_command=None):
        item = {
            "stage": stage,
            "candidate_id": _candidate_id(candidate_id),
            "status": "remaining",
            "reason": str(reason),
        }
        if rerun_command:
            item["rerun_command"] = _command_record(
                rerun_command, stage, _candidate_id(candidate_id), str(reason),
            )
        work = self.state.setdefault("remaining_work", [])
        if item not in work:
            work.append(item)
        self._recovery()["remaining_work"] = work
        self.persist()
        return item

    def consume_recovery_output(self, stage, output):
        if not isinstance(output, dict):
            return
        recovery = output.get("recovery") if isinstance(output.get("recovery"), dict) else {}
        payload = {**output, **recovery}
        for item in payload.get("completed_candidates", []) or []:
            if isinstance(item, dict):
                candidate_id = _candidate_id(item)
                evidence = item.get("evidence", item.get("evaluation", item))
            else:
                candidate_id = _candidate_id(item)
                evidence = item
            if candidate_id:
                self.record_completed_candidate(stage, candidate_id, evidence)
        for item in payload.get("isolated_candidates", []) or []:
            if isinstance(item, dict):
                self.record_isolated_candidate(
                    stage,
                    _candidate_id(item),
                    item.get("reason", "candidate isolated"),
                    item.get("rerun_command"),
                )
        for command in payload.get("rerun_commands", []) or []:
            if isinstance(command, dict):
                self.add_rerun_command(
                    command,
                    command.get("stage", stage),
                    command.get("candidate_id", ""),
                    command.get("reason", ""),
                )
            else:
                self.add_rerun_command(command, stage)
        for item in payload.get("remaining_work", []) or []:
            if isinstance(item, dict):
                self.add_remaining_work(
                    item.get("stage", stage),
                    item.get("candidate_id", ""),
                    item.get("reason", "remaining work"),
                    item.get("rerun_command"),
                )

    def _new_stage(self, name, started_at, deadline):
        return {
            "status": "running",
            "attempt": self.state.get("attempt_number", 1),
            "started_at": started_at,
            "ended_at": None,
            "deadline": deadline,
            "heartbeats": [],
            "last_available_output": None,
        }

    def run(self, callbacks):
        previous = {}
        if os.path.isfile(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as handle:
                    previous = json.load(handle)
            except (OSError, json.JSONDecodeError):
                previous = {}
        archive_path = self._archive_previous_state(previous)
        previous_history = previous.get("attempt_history", []) if isinstance(previous, dict) else []
        history = list(previous_history) if isinstance(previous_history, list) else []
        if previous:
            history.append(self._attempt_snapshot(previous))
        self.state = {
            "schema_version": 1,
            "run_id": uuid.uuid4().hex,
            "attempt_number": len(history) + 1,
            "attempt_history": history,
            "previous_attempt_path": archive_path,
            "status": "running",
            "started_at": self.now(),
            "ended_at": None,
            "stage_deadlines_seconds": dict(self.deadlines),
            "timed_out_stage": None,
            "timed_out_stages": [],
            "isolated_stages": [],
            "isolated_candidates": [],
            "completed_candidates": [],
            "rerun_commands": [],
            "remaining_work": [],
            "global_best_allowed": True,
            "recovery": {
                "isolated_stages": [],
                "isolated_candidates": [],
                "completed_candidates": [],
                "rerun_commands": [],
                "remaining_work": [],
            },
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
                isolated_stage = {
                    "stage": name,
                    "status": "isolated",
                    "reason": error,
                    "attempt": self.state["attempt_number"],
                }
                self.state["isolated_stages"].append(isolated_stage)
                self._recovery()["isolated_stages"] = self.state["isolated_stages"]
                self.add_remaining_work(name, reason="stage timeout")
                self.state["global_best_allowed"] = False
            except Exception as exc:  # 一階段失敗不抹掉其他階段的證據
                error = f"{type(exc).__name__}: {exc}"
                stage["status"] = "failed"

            if result is not None:
                context.last_available_output = _json_safe(result)
                self.consume_recovery_output(name, result)
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
        self.state["recovery"]["status"] = (
            "recoverable" if self.state["status"] in {"timed_out", "failed"} else "complete"
        )
        self.persist()
        return self.state


def run_staged_validation(callbacks, state_path="output/research_validation_state.json", deadlines=None):
    """便利入口，回傳已持久化的完整狀態。"""
    return StagedValidationExecutor(state_path=state_path, deadlines=deadlines).run(callbacks)
