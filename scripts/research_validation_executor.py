# -*- coding: utf-8 -*-
"""研究驗證階段執行器：以可恢復檢查點取代單一長逾時。"""
import json
import hashlib
import os
import subprocess
import tempfile
import threading
import time
import uuid
from contextlib import nullcontext
from datetime import datetime, timezone

from scripts.git_reproducibility import ResearchWorkspace, ResearchWorkspaceError


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
DEFAULT_NO_PROGRESS_SECONDS = 300.0


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


class WedgeDetected(TimeoutError):
    """研究輪次在 deadline 前已連續無進度，禁止再交付。"""


class StageContext:
    def __init__(self, executor, stage, deadline_monotonic, started_monotonic):
        self._executor = executor
        self.stage = stage
        self.deadline_monotonic = deadline_monotonic
        self.started_monotonic = started_monotonic
        self.last_progress_monotonic = started_monotonic
        self.last_available_output = None

    @property
    def remaining_seconds(self):
        deadline = min(self.deadline_monotonic, self._executor.round_deadline_monotonic)
        return max(0.0, deadline - self._executor.clock())

    @property
    def research_workspace(self):
        return self._executor.state.get("research_workspace", {})

    def heartbeat(self, progress, output=None):
        """持久化一筆進度；長 callback 可在自然檢查點呼叫。"""
        if output is not None:
            self.last_available_output = _json_safe(output)
            self._executor.consume_recovery_output(self.stage, output)
        self.last_progress_monotonic = self._executor.clock()
        self._executor.record_heartbeat(
            self.stage, progress, self.last_available_output if output is not None else None,
        )

    def checkpoint(self, output, progress="checkpoint"):
        self.check_round_deadline()
        self.heartbeat(progress, output)

    def completed_candidate(self, candidate_id, evidence):
        """追加一筆不可變的完成候選證據。"""
        return self._executor.record_completed_candidate(
            self.stage, candidate_id, evidence,
        )

    mark_candidate_completed = completed_candidate

    def isolate_candidate(self, candidate_id, reason, rerun_command=None,
                          cancellation=None, attempt_id="", original_attempt_id=""):
        """只隔離指定候選，並留下可重跑工作。"""
        return self._executor.record_isolated_candidate(
            self.stage, candidate_id, reason, rerun_command,
            cancellation=cancellation,
            attempt_id=attempt_id,
            original_attempt_id=original_attempt_id,
        )

    isolate = isolate_candidate

    def add_rerun_command(self, command, candidate_id="", reason=""):
        return self._executor.add_rerun_command(
            command, self.stage, candidate_id, reason,
        )

    def add_remaining_work(self, candidate_id="", reason="", rerun_command=None,
                           cancellation=None, attempt_id="", original_attempt_id=""):
        return self._executor.add_remaining_work(
            self.stage, candidate_id, reason, rerun_command,
            cancellation=cancellation,
            attempt_id=attempt_id,
            original_attempt_id=original_attempt_id,
        )

    def check_deadline(self):
        self._executor.check_stage_health(self)
        if self.remaining_seconds <= 0:
            raise StageTimeout(f"{self.stage} deadline exceeded")

    def check_round_deadline(self):
        if self._executor.clock() >= self._executor.round_deadline_monotonic:
            raise WedgeDetected(f"{self.stage} round deadline exceeded")

    def ensure_delivery_allowed(self):
        """交付 callback 寫入任何結論前的最後一道不可交付守門。"""
        self.check_deadline()
        if self._executor.state.get("wedge"):
            raise WedgeDetected(f"{self.stage} delivery is not allowed")


class StagedValidationExecutor:
    """依序執行四階段，並在每個可觀察邊界保存狀態。"""

    def __init__(self, state_path="output/research_validation_state.json", deadlines=None,
                 clock=None, now=None, isolate_workspace=False,
                 repository_root=None, workspace_root=None, research_workspace=None,
                 round_deadline_seconds=None, no_progress_seconds=DEFAULT_NO_PROGRESS_SECONDS,
                 no_progress_threshold=None, monitor_interval_seconds=0.25):
        self.state_path = os.path.abspath(os.fspath(state_path))
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
        if no_progress_threshold is not None:
            no_progress_seconds = no_progress_threshold
        if no_progress_seconds is not None:
            no_progress_seconds = float(no_progress_seconds)
            if no_progress_seconds <= 0:
                raise ValueError("no_progress_seconds must be positive")
        if round_deadline_seconds is None:
            round_deadline_seconds = sum(self.deadlines.values())
        round_deadline_seconds = float(round_deadline_seconds)
        if round_deadline_seconds <= 0:
            raise ValueError("round_deadline_seconds must be positive")
        monitor_interval_seconds = float(monitor_interval_seconds)
        if monitor_interval_seconds <= 0:
            raise ValueError("monitor_interval_seconds must be positive")
        self.no_progress_seconds = no_progress_seconds
        self.round_deadline_seconds = round_deadline_seconds
        self.monitor_interval_seconds = monitor_interval_seconds
        self.round_deadline_monotonic = float("inf")
        self._state_lock = threading.RLock()
        self._watchdog_stop = None
        self._watchdog_thread = None
        if research_workspace is not None:
            isolate_workspace = research_workspace
        self.isolate_workspace = bool(isolate_workspace)
        self.repository_root = repository_root
        self.workspace_root = workspace_root
        self.workspace = None
        self.state = {}

    def persist(self):
        """原子寫入 checkpoint，避免中斷時留下半個 JSON。"""
        with self._state_lock:
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

    def record_heartbeat(self, stage, progress, output=None):
        event = {"at": self.now(), "progress": str(progress)}
        workspace = self.state.get("research_workspace", {})
        if workspace:
            event["workspace_id"] = workspace.get("workspace_id", "")
            event["baseline_commit"] = workspace.get("baseline_commit", "")
            event["baseline_snapshot_hash"] = workspace.get("baseline_snapshot_hash", "")
        if output is not None:
            event["output"] = _json_safe(output)
        with self._state_lock:
            self.state["stages"][stage]["heartbeats"].append(event)
            self.state["stages"][stage]["last_progress_at"] = event["at"]
            self.state["progress"] = {
                "stage": stage,
                "progress": str(progress),
                "at": event["at"],
            }
            self.persist()

    def _mark_wedge(self, stage, reason):
        with self._state_lock:
            if self.state.get("wedge"):
                return
            wedge = {
                "status": "wedge",
                "stage": stage,
                "reason": str(reason),
                "detected_at": self.now(),
                "code": "INCOMPLETE_EVIDENCE",
            }
            self.state["wedge"] = wedge
            self.state["round_status"] = "wedge"
            self.state["status"] = "wedge"
            self.state["decision"] = {
                "status": "unproven",
                "code": "INCOMPLETE_EVIDENCE",
                "reason": str(reason),
            }
            self.state["global_best_allowed"] = False
            self.state["deliverable_allowed"] = False
            self.state["remaining_work"].append({
                "stage": stage,
                "status": "remaining",
                "reason": str(reason),
            })
            self._recovery().update({
                "status": "wedge",
                "wedge": wedge,
                "remaining_work": self.state["remaining_work"],
            })
            stage_data = self.state.get("stages", {}).get(stage)
            if isinstance(stage_data, dict) and stage_data.get("status") == "running":
                stage_data["status"] = "wedge"
                stage_data["error"] = str(reason)
                stage_data["ended_at"] = self.now()
            self.persist()

    def check_stage_health(self, context):
        if self.state.get("wedge"):
            raise WedgeDetected(self.state["wedge"].get("reason", "research round wedged"))
        now = self.clock()
        if now >= self.round_deadline_monotonic:
            reason = f"{context.stage} round deadline exceeded"
            self._mark_wedge(context.stage, reason)
            raise WedgeDetected(reason)
        if (
            self.no_progress_seconds is not None
            and now - context.last_progress_monotonic >= self.no_progress_seconds
        ):
            reason = (
                f"{context.stage} no progress for "
                f"{now - context.last_progress_monotonic:.3f}s"
            )
            self._mark_wedge(context.stage, reason)
            raise WedgeDetected(reason)

    def _watch_stage(self, context, stop):
        while not stop.wait(self.monitor_interval_seconds):
            try:
                self.check_stage_health(context)
            except WedgeDetected:
                return

    def _start_watchdog(self, context):
        stop = threading.Event()
        thread = threading.Thread(
            target=self._watch_stage, args=(context, stop),
            name="research-validation-watchdog", daemon=True,
        )
        self._watchdog_stop = stop
        self._watchdog_thread = thread
        thread.start()

    def _stop_watchdog(self):
        if self._watchdog_stop is not None:
            self._watchdog_stop.set()
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=self.monitor_interval_seconds * 2)
        self._watchdog_stop = None
        self._watchdog_thread = None

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
        workspace = self.state.get("research_workspace", {})
        if workspace:
            item.update({
                "workspace_id": workspace.get("workspace_id", ""),
                "baseline_commit": workspace.get("baseline_commit", ""),
                "baseline_snapshot_hash": workspace.get("baseline_snapshot_hash", ""),
            })
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

    def record_isolated_candidate(self, stage, candidate_id, reason, rerun_command=None,
                                  cancellation=None, attempt_id="", original_attempt_id=""):
        candidate_id = _candidate_id(candidate_id)
        item = {
            "candidate_id": candidate_id,
            "stage": stage,
            "attempt": self.state.get("attempt_number", 1),
            "status": "isolated",
            "reason": str(reason),
        }
        if attempt_id:
            item["attempt_id"] = str(attempt_id)
        if original_attempt_id:
            item["original_attempt_id"] = str(original_attempt_id)
        if cancellation:
            item["cancellation"] = _json_safe(cancellation)
        isolated = self.state.setdefault("isolated_candidates", [])
        if not any(
            row.get("candidate_id") == candidate_id
            and row.get("stage") == stage
            and row.get("attempt") == item["attempt"]
            and (
                not item.get("attempt_id")
                or row.get("attempt_id") == item.get("attempt_id")
            )
            for row in isolated
            if isinstance(row, dict)
        ):
            isolated.append(item)
        self._recovery()["isolated_candidates"] = isolated
        if rerun_command:
            self.add_rerun_command(rerun_command, stage, candidate_id, str(reason))
        self.add_remaining_work(
            stage, candidate_id, str(reason), rerun_command,
            cancellation=cancellation,
            attempt_id=attempt_id,
            original_attempt_id=original_attempt_id,
        )
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

    def add_remaining_work(self, stage, candidate_id="", reason="", rerun_command=None,
                           cancellation=None, attempt_id="", original_attempt_id=""):
        item = {
            "stage": stage,
            "candidate_id": _candidate_id(candidate_id),
            "status": "remaining",
            "reason": str(reason),
        }
        if attempt_id:
            item["attempt_id"] = str(attempt_id)
        if original_attempt_id:
            item["original_attempt_id"] = str(original_attempt_id)
        if cancellation:
            item["cancellation"] = _json_safe(cancellation)
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
                    cancellation=item.get("cancellation"),
                    attempt_id=item.get("attempt_id", ""),
                    original_attempt_id=item.get("original_attempt_id", ""),
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
                    cancellation=item.get("cancellation"),
                    attempt_id=item.get("attempt_id", ""),
                    original_attempt_id=item.get("original_attempt_id", ""),
                )

    def _new_stage(self, name, started_at, deadline):
        return {
            "status": "running",
            "attempt": self.state.get("attempt_number", 1),
            "started_at": started_at,
            "ended_at": None,
            "deadline": deadline,
            "heartbeats": [],
            "last_progress_at": started_at,
            "last_available_output": None,
        }

    def _blocked_stage(self, name):
        started_at = self.now()
        stage = self._new_stage(name, started_at, started_at)
        stage.update({
            "status": "blocked",
            "ended_at": started_at,
            "error": "研究輪次 wedge，停止後續選優／交付",
            "heartbeats": [{"at": started_at, "progress": "blocked_by_wedge"}],
        })
        self.state["stages"][name] = stage

    def _blocked_workspace(self, reason, evidence=None):
        metadata = evidence if isinstance(evidence, dict) else {}
        if not metadata:
            metadata = {
                "schema_version": 1,
                "status": "blocked",
                "blocked": True,
                "workspace_id": self.state.get("run_id", ""),
                "repository": os.path.abspath(os.fspath(self.repository_root or os.getcwd())),
                "workspace": "",
                "baseline_commit": "",
                "baseline_snapshot_hash": "",
                "decision": {
                    "status": "unproven",
                    "code": "INCOMPLETE_EVIDENCE",
                    "reason": str(reason),
                },
                "rerun_commands": ["python scripts/preflight.py --require-git"],
            }
        metadata.setdefault("status", "blocked")
        metadata.setdefault("blocked", True)
        metadata.setdefault("decision", {
            "status": "unproven",
            "code": "INCOMPLETE_EVIDENCE",
            "reason": str(reason),
        })
        self.state["research_workspace"] = metadata
        self.state["global_best_allowed"] = False
        self.state["status"] = "blocked"
        self.state["ended_at"] = self.now()
        self.state["decision"] = metadata["decision"]
        self.state["rerun_commands"] = list(metadata.get("rerun_commands") or [])
        self.state["remaining_work"] = [{
            "stage": "workspace",
            "status": "remaining",
            "reason": str(reason),
            "rerun_commands": self.state["rerun_commands"],
        }]
        self._recovery().update({
            "status": "blocked",
            "rerun_commands": self.state["rerun_commands"],
            "remaining_work": self.state["remaining_work"],
        })
        self.persist()
        return self.state

    def _run_stages(self, callbacks):
        for name in STAGES:
            if self.state.get("wedge"):
                self._blocked_stage(name)
                self.persist()
                continue
            started_mono = self.clock()
            started_at = self.now()
            deadline_seconds = self.deadlines[name]
            deadline = datetime.fromtimestamp(
                time.time() + deadline_seconds, timezone.utc,
            ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            stage = self._new_stage(name, started_at, deadline)
            self.state["stages"][name] = stage
            context = StageContext(
                self, name, started_mono + deadline_seconds, started_mono,
            )
            context.heartbeat("started")
            callback = callbacks.get(name) if isinstance(callbacks, dict) else None

            if callback is None:
                stage["status"] = "skipped"
                stage["ended_at"] = self.now()
                context.heartbeat("skipped")
                continue

            result = None
            error = None
            self._start_watchdog(context)
            try:
                context.check_deadline()
                result = callback(context)
                context.check_deadline()
                stage["status"] = "completed"
            except WedgeDetected as exc:
                error = f"{type(exc).__name__}: {exc}"
                self._mark_wedge(name, error)
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
            self._stop_watchdog()
            if not stage.get("ended_at"):
                stage["ended_at"] = self.now()
            if self.state.get("wedge") and stage.get("status") == "running":
                stage["status"] = "wedge"
                stage["ended_at"] = self.now()
            context.heartbeat(stage["status"])
            if self.state.get("wedge"):
                # 後續階段仍保留 checkpoint，但絕不執行 callback。
                continue

        self.state["ended_at"] = self.now()
        if self.state.get("wedge"):
            self.state["status"] = "wedge"
        elif self.state["timed_out_stages"]:
            self.state["status"] = "timed_out"
        elif any(stage["status"] == "failed" for stage in self.state["stages"].values()):
            self.state["status"] = "failed"
        else:
            self.state["status"] = "completed"
        self.state["recovery"]["status"] = (
            "wedge" if self.state["status"] == "wedge" else (
                "recoverable" if self.state["status"] in {"timed_out", "failed"} else "complete"
            )
        )
        self.persist()
        return self.state

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
            "round_status": "running",
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
            "deliverable_allowed": True,
            "wedge": None,
            "decision": {"status": "running", "code": "PENDING"},
            "progress": {},
            "round_deadline_seconds": self.round_deadline_seconds,
            "no_progress_seconds": self.no_progress_seconds,
            "research_workspace": {
                "status": "pending" if self.isolate_workspace else "not_requested",
                "required": self.isolate_workspace,
            },
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
        round_started_mono = self.clock()
        self.round_deadline_monotonic = round_started_mono + self.round_deadline_seconds
        self.state["round_deadline"] = datetime.fromtimestamp(
            time.time() + self.round_deadline_seconds, timezone.utc,
        ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        if self.isolate_workspace:
            try:
                self.workspace = ResearchWorkspace(
                    repository=self.repository_root,
                    workspace_root=self.workspace_root,
                    run_id=self.state["run_id"],
                ).create()
            except ResearchWorkspaceError as exc:
                return self._blocked_workspace(str(exc), exc.evidence)
            except Exception as exc:
                return self._blocked_workspace(
                    f"無法建立隔離研究工作區：{type(exc).__name__}: {exc}"
                )
            self.state["research_workspace"] = self.workspace.metadata

        self.persist()

        workspace_context = self.workspace.activate() if self.workspace else nullcontext()
        with workspace_context:
            return self._run_stages(callbacks)


def run_staged_validation(callbacks, state_path="output/research_validation_state.json", deadlines=None,
                          isolate_workspace=False, repository_root=None, workspace_root=None,
                          round_deadline_seconds=None, no_progress_seconds=DEFAULT_NO_PROGRESS_SECONDS,
                          no_progress_threshold=None, monitor_interval_seconds=0.25):
    """便利入口，回傳已持久化的完整狀態。"""
    return StagedValidationExecutor(
        state_path=state_path,
        deadlines=deadlines,
        isolate_workspace=isolate_workspace,
        repository_root=repository_root,
        workspace_root=workspace_root,
        round_deadline_seconds=round_deadline_seconds,
        no_progress_seconds=no_progress_seconds,
        no_progress_threshold=no_progress_threshold,
        monitor_interval_seconds=monitor_interval_seconds,
    ).run(callbacks)
