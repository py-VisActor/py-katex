"""Standard-library evidence logging. Active manifests update atomically; closed runs are immutable."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import threading
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
RUN_SCHEMA = "py-mermaid-run/v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def file_identity(path: Path) -> dict:
    checksum = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            checksum.update(chunk)
            size += len(chunk)
    return {"sha256": checksum.hexdigest(), "bytes": size}


def write_json(path: Path, value: dict, *, exclusive: bool = False) -> None:
    if exclusive:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        return
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for attempt in range(6):
            try:
                temporary.replace(path)
                break
            except PermissionError as error:
                # Windows readers/antivirus can briefly deny replacement of
                # an open manifest. Keep the old complete file until one
                # atomic swap succeeds; persistent failures still propagate.
                if getattr(error, 'winerror', None) not in {5, 32, 33} or attempt == 5:
                    raise
                time.sleep(.01 * 2**attempt)
    finally:
        temporary.unlink(missing_ok=True)


def safe_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value):
        raise ValueError("IDs must use 1–96 ASCII letters, digits, _, . or -")
    return value


def source_identity(root: Path = ROOT) -> dict:
    """Exclude caches, egg-info and outputs from product source identities."""
    paths = [p for p in (root / "src/py_katex").rglob("*")
             if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    paths += [root / name for name in ("pyproject.toml", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md",
                                       "references/licenses/katex-LICENSE") if (root / name).is_file()]
    files = {p.relative_to(root).as_posix(): file_identity(p)["sha256"] for p in sorted(paths)}
    return {"sourceTreeSha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
            "files": files}


def environment_identity(root: Path = ROOT) -> dict:
    packages = {}
    for name in ("py-skia-canvas", "py-visactor-elk", "Pillow"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    result = {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
              "packages": packages, "displayTimezone": "Asia/Shanghai", "gitHead": None}
    try:
        result["gitHead"] = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                                   stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return result


class Run:
    def __init__(self, scope: str, kind: str, *, runs_dir: Path | None = None, root: Path = ROOT):
        self.root = root.resolve()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.id = f"{safe_id(scope)}-{safe_id(kind)}-{stamp}-{uuid.uuid4().hex[:8]}"
        parent = (runs_dir or root / "test-runs").resolve()
        parent.mkdir(parents=True, exist_ok=True)
        self.path = parent / self.id
        self.path.mkdir(exist_ok=False)
        for name in ("commands", "artifacts", "report"):
            (self.path / name).mkdir()
        self.started = time.monotonic()
        self.closed = False
        self._event_lock = threading.Lock()
        self.data = {"schema": RUN_SCHEMA, "runId": self.id, "scope": scope, "kind": kind,
                     "status": "RUNNING", "startedAtUtc": utc_now(), "finishedAtUtc": None,
                     "environment": environment_identity(self.root), "source": source_identity(self.root),
                     "commands": [], "inputs": {}, "artifacts": {}, "functionalStatus": "NOT_EVALUATED"}
        self.data["tooling"] = {path.name: file_identity(path) for path in
                                 (Path(__file__), ROOT / "tools/workflow.py") if path.is_file()}
        try:
            status = subprocess.check_output(["git", "-C", str(self.root), "status", "--short"], stderr=subprocess.DEVNULL)
            (self.path / "git-status.txt").write_bytes(status)
        except (OSError, subprocess.SubprocessError):
            pass
        self.event("run_started", scope=scope, kind=kind)
        self.save()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is not None:
            (self.path / "error.txt").write_text("".join(traceback.format_exception(exc_type, exc, tb)), encoding="utf-8")
        self.close("INTERRUPTED" if isinstance(exc, KeyboardInterrupt) else "ERROR" if exc is not None else None)
        return False

    def event(self, event_name: str, **fields) -> None:
        if self.closed:
            raise RuntimeError("Cannot append to a closed run")
        row = {"schema": "py-mermaid-event/v1", "atUtc": utc_now(), "runId": self.id, "event": event_name, **fields}
        with self._event_lock:
            with (self.path / "events.ndjson").open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    def save(self) -> None:
        write_json(self.path / "run.json", self.data)

    def input(self, path: Path) -> None:
        if self.closed:
            raise RuntimeError("Run already closed")
        target = path.resolve(strict=True)
        self.data["inputs"][str(target)] = file_identity(target)
        self.save()

    def command(self, name: str, argv: list[str], *, cwd: Path | None = None,
                env: dict[str, str] | None = None, timeout: float | None = None) -> dict:
        if self.closed:
            raise RuntimeError("Run already closed")
        safe_id(name)
        if not argv or not all(isinstance(v, str) and v for v in argv):
            raise ValueError("A nonempty argv string array is required; shell command strings are not accepted")
        if timeout is not None and timeout <= 0:
            raise ValueError("Timeout must be positive")
        command_dir = self.path / "commands" / f"{len(self.data['commands']) + 1:03d}-{name}"
        command_dir.mkdir()
        workdir = (cwd or self.root).resolve(strict=True)
        result = {"name": name, "argv": argv, "cwd": str(workdir), "startedAtUtc": utc_now(),
                  "timeoutSeconds": timeout, "finishedAtUtc": None, "exitCode": None, "status": "RUNNING",
                  "stdout": (command_dir / "stdout.log").relative_to(self.path).as_posix(),
                  "stderr": (command_dir / "stderr.log").relative_to(self.path).as_posix()}
        result["toolFiles"] = {}
        for arg in argv:
            candidate = (workdir / arg).resolve()
            if candidate.suffix in (".py", ".cjs", ".mjs") and candidate.is_file():
                result["toolFiles"][str(candidate)] = file_identity(candidate)
        self.data["commands"].append(result)
        write_json(command_dir / "command.json", result, exclusive=True)
        self.event("command_started", name=name, argv=argv)
        self.save()
        started = time.monotonic()
        child_env = os.environ.copy()
        child_env.update({"PYTHONIOENCODING": "utf-8", **(env or {})})
        with (command_dir / "stdout.log").open("wb") as stdout, (command_dir / "stderr.log").open("wb") as stderr:
            try:
                completed = subprocess.run(argv, cwd=workdir, env=child_env, stdout=stdout, stderr=stderr,
                                           timeout=timeout, shell=False)
                result.update(exitCode=completed.returncode, status="SUCCESS" if completed.returncode == 0 else "FAILED")
            except subprocess.TimeoutExpired:
                result.update(exitCode=124, status="TIMEOUT")
            except KeyboardInterrupt:
                result.update(exitCode=130, status="INTERRUPTED")
                raise
            except OSError as exc:
                result.update(exitCode=127, status="ERROR", error=str(exc))
                stderr.write((str(exc) + "\n").encode("utf-8"))
            finally:
                result.update(finishedAtUtc=utc_now(), durationSeconds=round(time.monotonic() - started, 6))
                stdout.flush()
                stderr.flush()
                result["stdoutSha256"] = file_identity(command_dir / "stdout.log")["sha256"]
                result["stderrSha256"] = file_identity(command_dir / "stderr.log")["sha256"]
                write_json(command_dir / "result.json", result, exclusive=True)
                self.event("command_finished", name=name, status=result["status"], exitCode=result["exitCode"])
                self.save()
        return result

    def close(self, status: str | None = None) -> None:
        if self.closed:
            return
        failures = [c for c in self.data["commands"] if c["exitCode"] != 0]
        self.data.update(status=status or ("FAILED" if failures else "SUCCESS"), finishedAtUtc=utc_now(),
                         durationSeconds=round(time.monotonic() - self.started, 6))
        self.event("run_finished", status=self.data["status"])
        self.data["sourceUnchanged"] = source_identity(self.root) == self.data["source"]
        for path in sorted(self.path.rglob("*")):
            if path.is_symlink():
                continue
            if path.is_file() and path != self.path / "run.json":
                self.data["artifacts"][path.relative_to(self.path).as_posix()] = file_identity(path)
        self.save()
        self.closed = True


def verify_run(path: Path) -> dict:
    root = path.resolve(strict=True)
    manifest = json.loads((root / "run.json").read_text(encoding="utf-8"))
    errors = []
    if manifest.get("schema") != RUN_SCHEMA:
        errors.append("Unsupported run schema")
    if manifest.get("status") == "RUNNING" or not manifest.get("finishedAtUtc"):
        errors.append("Run has not finalized")
    for relative, expected in manifest.get("artifacts", {}).items():
        original = root / relative
        target = original.resolve()
        if not target.is_relative_to(root) or not target.is_file() or original.is_symlink():
            errors.append(f"Missing or invalid artifact: {relative}")
        elif file_identity(target) != expected:
            errors.append(f"Artifact fingerprint mismatch: {relative}")
    if not manifest.get("artifacts"):
        errors.append("Run has no recorded artifacts")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p != root / "run.json"}
    for extra in sorted(actual - set(manifest.get("artifacts", {}))):
        errors.append(f"Unrecorded artifact added after finalization: {extra}")
    for name, expected in manifest.get("publishedArtifacts", {}).items():
        target = Path(name)
        if not target.is_file() or file_identity(target) != expected:
            errors.append(f"Published artifact missing or changed: {name}")
    return {"schema": "py-mermaid-run-integrity/v1", "runId": manifest.get("runId"),
            "integrityStatus": "FAIL" if errors else "PASS", "executionStatus": manifest.get("status"),
            "functionalStatus": manifest.get("functionalStatus", "NOT_EVALUATED"), "errors": errors}
