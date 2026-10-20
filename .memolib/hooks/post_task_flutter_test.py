#!/usr/bin/env python3
"""post_task_flutter_test.py - Rollback D5.9 si `flutter test` echoue.

A executer depuis <project>/.memolib/hooks/ pour activer.
Recoit JSON sur stdin : {"diff": str, "target": str}
Retourne JSON sur stdout : {"ok": bool, "reason": str}
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def _fail(reason: str) -> int:
    print(json.dumps({"ok": False, "reason": reason[:500]}))
    return 1


def _run_flutter(args: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    exe = shutil.which("flutter")
    if not exe:
        raise FileNotFoundError("flutter not in PATH")
    return subprocess.run(
        [exe, *args], cwd=str(cwd), capture_output=True, text=True,
        timeout=timeout, encoding="utf-8", errors="replace",
    )


def main() -> int:
    try:
        ctx = json.load(sys.stdin)
    except Exception as e:
        return _fail(f"invalid stdin JSON: {e}")

    target = ctx.get("target")
    if not target:
        return _fail("missing 'target' in context")

    project = Path(target)
    if not (project / "pubspec.yaml").is_file():
        return _fail(f"not a Flutter project: {project}")

    try:
        r = _run_flutter(
            ["test", "--reporter=compact"],
            cwd=project, timeout=300,
        )
    except subprocess.TimeoutExpired:
        return _fail("flutter test timeout > 300s")
    except FileNotFoundError as e:
        return _fail(str(e))
    except OSError as e:
        return _fail(f"{type(e).__name__}: {e}")

    if r.returncode != 0:
        out = (r.stdout or "") + (r.stderr or "")
        fails = [l.strip() for l in out.splitlines() if "FAILED" in l or "Some tests failed" in l][:5]
        detail = " | ".join(fails) if fails else f"exit {r.returncode}"
        return _fail(f"flutter test failed: {detail}")

    print(json.dumps({"ok": True, "reason": "flutter test OK"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())