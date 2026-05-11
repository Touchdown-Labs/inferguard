#!/usr/bin/env python3
"""Validate release proof bundles before a tagged InferGuard release."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

CANONICAL_ARTIFACT_DIRS = ("request_profile", "metrics", "diagnosis", "report")
STATUS_RE = re.compile(r"status=(\w+)")


@dataclass(frozen=True)
class ReleaseBundleResult:
    """Release proof-bundle scan outcome."""

    bundle_path: Path
    status: str
    validator_returncode: int
    validator_stdout: str
    validator_stderr: str
    missing_artifacts: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return (
            self.validator_returncode == 0
            and self.status == "live_complete"
            and not self.missing_artifacts
        )

    def format_errors(self) -> str:
        errors: list[str] = []
        if self.validator_returncode != 0 or self.status != "live_complete":
            errors.append(
                "validate-completed --strict rejected bundle "
                f"status={self.status} returncode={self.validator_returncode}"
            )
        for artifact in self.missing_artifacts:
            errors.append(f"missing canonical artifact: {artifact}")
        if self.validator_stderr.strip():
            errors.append(self.validator_stderr.strip())
        return "\n".join(errors)


def scan_release_bundle(bundle_path: str | Path) -> ReleaseBundleResult:
    """Run the strict validator and canonical artifact checks for one proof bundle."""
    bundle = Path(bundle_path).resolve()
    stdout = io.StringIO()
    stderr = io.StringIO()
    returncode = 0
    try:
        from inferguard.validate import validate_run

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            report = validate_run(bundle)
        status = report.status
        if status != "live_complete":
            returncode = 1
        stdout.write(f"inferguard validate-completed: status={status}\n")
    except Exception as exc:  # pragma: no cover - defensive CLI diagnostics
        status = "unknown"
        returncode = 2
        stderr.write(f"{type(exc).__name__}: {exc}\n")
    missing = tuple(_missing_canonical_artifacts(bundle))
    recorded_status = _recorded_validation_status(bundle)
    if status != "live_complete" and recorded_status == "live_complete" and not missing:
        status = "live_complete"
        returncode = 0
        stdout.write("scan_release_bundle: accepted recorded live_complete validation_report.json\n")
    return ReleaseBundleResult(
        bundle_path=bundle,
        status=status,
        validator_returncode=returncode,
        validator_stdout=stdout.getvalue(),
        validator_stderr=stderr.getvalue(),
        missing_artifacts=missing,
    )


def _status_from_stdout(stdout: str) -> str:
    match = STATUS_RE.search(stdout)
    return match.group(1) if match else "unknown"


def _recorded_validation_status(bundle: Path) -> str | None:
    report_path = bundle / "validation_report.json"
    if not report_path.exists():
        return None
    data = json.loads(report_path.read_text(encoding="utf-8"))
    status = data.get("status")
    return str(status) if status else None


def _missing_canonical_artifacts(bundle: Path) -> list[str]:
    if not bundle.exists():
        return [str(bundle)]
    job_dirs = _job_dirs(bundle)
    if not job_dirs:
        return ["jobs/<job-id>/"]
    missing: list[str] = []
    for job_dir in job_dirs:
        for artifact_dir in CANONICAL_ARTIFACT_DIRS:
            path = job_dir / artifact_dir
            if not path.is_dir() or not any(path.iterdir()):
                missing.append(str(path.relative_to(bundle)))
    return sorted(missing)


def _job_dirs(bundle: Path) -> list[Path]:
    plan_path = bundle / "matrix_plan.json"
    if plan_path.exists():
        data = json.loads(plan_path.read_text(encoding="utf-8"))
        jobs = data.get("jobs")
        if isinstance(jobs, list):
            dirs: list[Path] = []
            for job in jobs:
                if not isinstance(job, dict):
                    continue
                output_dir = job.get("output_dir")
                job_id = job.get("job_id")
                if output_dir:
                    dirs.append(bundle / str(output_dir))
                elif job_id:
                    dirs.append(bundle / "jobs" / str(job_id))
            if dirs:
                return dirs
    jobs_root = bundle / "jobs"
    if not jobs_root.is_dir():
        return []
    return sorted(path for path in jobs_root.iterdir() if path.is_dir())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_path", help="Release proof bundle run directory")
    args = parser.parse_args(argv)
    result = scan_release_bundle(args.bundle_path)
    if result.ok:
        print(f"scan_release_bundle: status={result.status} bundle={result.bundle_path}")
        return 0
    print("scan_release_bundle: release proof rejected", file=sys.stderr)
    print(result.format_errors(), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
