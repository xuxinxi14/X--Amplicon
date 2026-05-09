"""Background job manager for Web UI-triggered CLI commands."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import threading
from typing import Any, Sequence
from uuid import uuid4

from webui.backend.config import get_jobs_dir
from webui.backend.models.common import CommandSpec, utc_now_iso
from webui.backend.models.job import JobEvent, JobRecord
from webui.backend.services.json_store import read_json, write_json

ACTIVE_JOB_STATUSES = {"queued", "checking", "running"}


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return
        except Exception:
            pass
    process.terminate()


class JobManager:
    """Minimal local subprocess manager for long-running X-Amplicon jobs."""

    def __init__(self) -> None:
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._lock = threading.Lock()

    def _job_path(self, job_id: str) -> Path:
        return get_jobs_dir() / f"{job_id}.json"

    def _log_path(self, job_id: str) -> Path:
        return get_jobs_dir() / f"{job_id}.log"

    def _event_path(self, job_id: str) -> Path:
        return get_jobs_dir() / f"{job_id}.events.jsonl"

    def _delete_job_files(self, job_id: str) -> None:
        for path in (self._job_path(job_id), self._log_path(job_id), self._event_path(job_id)):
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    def _save(self, record: JobRecord) -> None:
        write_json(self._job_path(record.id), record.model_dump(mode="json"))

    def _load(self, job_id: str) -> JobRecord:
        raw = read_json(self._job_path(job_id), None)
        if not isinstance(raw, dict):
            raise KeyError(f"Job not found: {job_id}")
        return JobRecord(**raw)

    def _append_event(self, event: JobEvent) -> None:
        event_path = self._event_path(event.job_id)
        event_path.parent.mkdir(parents=True, exist_ok=True)
        with event_path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json())
            handle.write("\n")

    def emit_event(
        self,
        job_id: str,
        *,
        event_type: str = "status",
        stage: str = "job",
        status: str = "running",
        message: str = "",
        command: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Emit one structured job event."""

        self._append_event(
            JobEvent(
                job_id=job_id,
                type=event_type,
                stage=stage,
                status=status,
                message=message,
                command=command,
                details=details or {},
            )
        )

    def start_job(
        self,
        *,
        job_type: str,
        command: CommandSpec,
        project_id: str | None = None,
        initial_status: str = "queued",
    ) -> JobRecord:
        """Create and start a subprocess job."""

        job_id = f"{job_type}-{uuid4().hex[:10]}"
        record = JobRecord(
            id=job_id,
            project_id=project_id,
            job_type=job_type,
            status=initial_status,  # type: ignore[arg-type]
            command=command.args,
            display_command=command.display,
            cwd=command.cwd,
            log_path=str(self._log_path(job_id)),
            event_path=str(self._event_path(job_id)),
            message="Job queued.",
        )
        self._save(record)
        self.emit_event(
            job_id,
            status=initial_status,
            message="Job queued.",
            command=command.display,
            details={"job_type": job_type, "project_id": project_id},
        )

        thread = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        thread.start()
        return record

    def start_sequence_job(
        self,
        *,
        job_type: str,
        commands: Sequence[tuple[str, CommandSpec]],
        project_id: str | None = None,
        initial_status: str = "queued",
    ) -> JobRecord:
        """Create and start a job made of multiple subprocess steps."""

        if not commands:
            raise ValueError("commands cannot be empty.")

        job_id = f"{job_type}-{uuid4().hex[:10]}"
        display_command = "\n".join(
            f"[{index}/{len(commands)}] {stage}: {command.display}"
            for index, (stage, command) in enumerate(commands, start=1)
        )
        first_command = commands[0][1]
        record = JobRecord(
            id=job_id,
            project_id=project_id,
            job_type=job_type,
            status=initial_status,  # type: ignore[arg-type]
            command=first_command.args,
            display_command=display_command,
            cwd=first_command.cwd,
            log_path=str(self._log_path(job_id)),
            event_path=str(self._event_path(job_id)),
            message="Job queued.",
        )
        self._save(record)
        self.emit_event(
            job_id,
            status=initial_status,
            message="Sequence job queued.",
            command=display_command,
            details={
                "job_type": job_type,
                "project_id": project_id,
                "steps": [stage for stage, _ in commands],
            },
        )

        thread = threading.Thread(target=self._run_sequence_job, args=(job_id, list(commands)), daemon=True)
        thread.start()
        return record

    def _run_job(self, job_id: str) -> None:
        record = self._load(job_id)
        record.status = "checking" if record.job_type == "preflight" else "running"
        record.started_at = utc_now_iso()
        record.message = "Job started."
        self._save(record)
        self.emit_event(
            job_id,
            status=record.status,
            message="Job started.",
            command=record.display_command,
            details={"cwd": record.cwd},
        )

        log_path = Path(record.log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8", errors="replace") as log_handle:
            log_handle.write(f"$ {record.display_command}\n\n")
            log_handle.flush()
            try:
                process = subprocess.Popen(
                    record.command,
                    cwd=record.cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except Exception as exc:
                record.status = "failed"
                record.error = str(exc)
                record.completed_at = utc_now_iso()
                record.message = "Job failed to start."
                self._save(record)
                log_handle.write(f"Failed to start job: {exc}\n")
                self.emit_event(job_id, status="failed", message=str(exc))
                return

            record.pid = process.pid
            self._save(record)
            with self._lock:
                self._processes[job_id] = process

            try:
                assert process.stdout is not None
                with process.stdout:
                    for line in process.stdout:
                        log_handle.write(line)
                        log_handle.flush()
                return_code = process.wait()
            finally:
                with self._lock:
                    self._processes.pop(job_id, None)

            latest = self._load(job_id)
            if latest.status == "cancelled":
                latest.return_code = return_code
                latest.completed_at = utc_now_iso()
                latest.message = "Job cancelled."
                self._save(latest)
                self.emit_event(job_id, status="cancelled", message="Job cancelled.")
                return

            latest.return_code = return_code
            latest.completed_at = utc_now_iso()
            if return_code == 0:
                latest.status = "completed"
                latest.message = "Job completed successfully."
                event_status = "completed"
            else:
                latest.status = "failed"
                latest.error = f"Process exited with code {return_code}."
                latest.message = latest.error
                event_status = "failed"
            self._save(latest)
            self.emit_event(job_id, status=event_status, message=latest.message, details={"return_code": return_code})

    def _run_sequence_job(self, job_id: str, commands: list[tuple[str, CommandSpec]]) -> None:
        record = self._load(job_id)
        record.status = "running"
        record.started_at = utc_now_iso()
        record.message = "Sequence job started."
        self._save(record)
        self.emit_event(
            job_id,
            status="running",
            message="Sequence job started.",
            command=record.display_command,
            details={"cwd": record.cwd, "steps": [stage for stage, _ in commands]},
        )

        log_path = Path(record.log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8", errors="replace") as log_handle:
            log_handle.write("$ X-Amplicon Web UI sequence job\n")
            log_handle.write(f"{record.display_command}\n\n")
            log_handle.flush()

            for index, (stage, command) in enumerate(commands, start=1):
                latest = self._load(job_id)
                if latest.status == "cancelled":
                    latest.completed_at = utc_now_iso()
                    latest.message = "Job cancelled."
                    self._save(latest)
                    self.emit_event(job_id, stage=stage, status="cancelled", message="Job cancelled.")
                    return

                latest.command = command.args
                latest.cwd = command.cwd
                latest.pid = None
                latest.message = f"Running step {index}/{len(commands)}: {stage}."
                self._save(latest)
                self.emit_event(
                    job_id,
                    stage=stage,
                    status="running",
                    message=latest.message,
                    command=command.display,
                    details={"step": index, "total_steps": len(commands), "cwd": command.cwd},
                )

                log_handle.write(f"\n[step {index}/{len(commands)}] {stage}\n")
                log_handle.write(f"$ {command.display}\n\n")
                log_handle.flush()

                try:
                    process = subprocess.Popen(
                        command.args,
                        cwd=command.cwd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                except Exception as exc:
                    failed = self._load(job_id)
                    failed.status = "failed"
                    failed.error = str(exc)
                    failed.completed_at = utc_now_iso()
                    failed.message = f"Step failed to start: {stage}."
                    self._save(failed)
                    log_handle.write(f"Failed to start step {stage}: {exc}\n")
                    self.emit_event(job_id, stage=stage, status="failed", message=str(exc))
                    return

                latest = self._load(job_id)
                latest.pid = process.pid
                latest.cwd = command.cwd
                self._save(latest)
                with self._lock:
                    self._processes[job_id] = process

                try:
                    assert process.stdout is not None
                    with process.stdout:
                        for line in process.stdout:
                            log_handle.write(line)
                            log_handle.flush()
                    return_code = process.wait()
                finally:
                    with self._lock:
                        self._processes.pop(job_id, None)

                latest = self._load(job_id)
                if latest.status == "cancelled":
                    latest.return_code = return_code
                    latest.completed_at = utc_now_iso()
                    latest.message = "Job cancelled."
                    latest.pid = None
                    self._save(latest)
                    self.emit_event(job_id, stage=stage, status="cancelled", message="Job cancelled.")
                    return

                if return_code != 0:
                    latest.status = "failed"
                    latest.return_code = return_code
                    latest.error = f"Step {stage} exited with code {return_code}."
                    latest.completed_at = utc_now_iso()
                    latest.message = latest.error
                    latest.pid = None
                    self._save(latest)
                    self.emit_event(
                        job_id,
                        stage=stage,
                        status="failed",
                        message=latest.message,
                        details={"return_code": return_code, "step": index},
                    )
                    return

                latest.return_code = return_code
                latest.message = f"Step completed: {stage}."
                latest.pid = None
                self._save(latest)
                self.emit_event(
                    job_id,
                    stage=stage,
                    status="completed",
                    message=latest.message,
                    details={"return_code": return_code, "step": index},
                )

            completed = self._load(job_id)
            completed.status = "completed"
            completed.return_code = 0
            completed.completed_at = utc_now_iso()
            completed.message = "All steps completed successfully."
            completed.pid = None
            self._save(completed)
            self.emit_event(
                job_id,
                status="completed",
                message=completed.message,
                details={"steps": [stage for stage, _ in commands]},
            )

    def get_job(self, job_id: str) -> JobRecord:
        """Return one job record."""

        return self._load(job_id)

    def list_jobs(self, *, limit: int | None = None) -> list[JobRecord]:
        """Return persisted jobs sorted from newest to oldest."""

        records: list[JobRecord] = []
        for path in get_jobs_dir().glob("*.json"):
            raw = read_json(path, None)
            if not isinstance(raw, dict):
                continue
            try:
                records.append(JobRecord(**raw))
            except Exception:
                continue
        records.sort(key=lambda item: item.created_at, reverse=True)
        if limit is not None and limit > 0:
            return records[:limit]
        return records

    def active_jobs(self, *, project_id: str | None = None) -> list[JobRecord]:
        """Return persisted jobs that should block history deletion."""

        return [
            job
            for job in self.list_jobs()
            if job.status in ACTIVE_JOB_STATUSES and (project_id is None or job.project_id == project_id)
        ]

    def delete_jobs_for_project(self, project_id: str) -> int:
        """Delete finished job records for one project."""

        if self.active_jobs(project_id=project_id):
            raise ValueError("Cannot clear history while jobs are running. Cancel or wait for active jobs first.")
        jobs = [job for job in self.list_jobs() if job.project_id == project_id]
        for job in jobs:
            self._delete_job_files(job.id)
        return len(jobs)

    def clear_job_history(self) -> int:
        """Delete all finished job records."""

        if self.active_jobs():
            raise ValueError("Cannot clear history while jobs are running. Cancel or wait for active jobs first.")
        jobs = self.list_jobs()
        for path in get_jobs_dir().glob("*"):
            if path.suffix == ".log" or path.suffix == ".json" or path.name.endswith(".events.jsonl"):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
        return len(jobs)

    def get_logs(self, job_id: str, *, tail_lines: int | None = None) -> dict[str, Any]:
        """Return job logs, optionally tailed."""

        record = self._load(job_id)
        log_path = Path(record.log_path)
        if not log_path.is_file():
            return {"job_id": job_id, "log_path": str(log_path), "text": ""}
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if tail_lines is not None and tail_lines > 0:
            lines = lines[-tail_lines:]
        return {"job_id": job_id, "log_path": str(log_path), "text": "\n".join(lines)}

    def cancel_job(self, job_id: str) -> JobRecord:
        """Cancel a running job."""

        record = self._load(job_id)
        with self._lock:
            process = self._processes.get(job_id)
        if process is None or process.poll() is not None:
            if record.status not in ("completed", "failed", "cancelled"):
                record.status = "cancelled"
                record.completed_at = utc_now_iso()
                record.message = "Job cancelled before process start."
                self._save(record)
            return record

        record.status = "cancelled"
        record.message = "Cancellation requested."
        self._save(record)
        self.emit_event(job_id, status="cancelled", message="Cancellation requested.")
        _terminate_process_tree(process)
        return record


manager = JobManager()
