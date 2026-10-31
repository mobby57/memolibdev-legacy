#!/usr/bin/env python3
"""memolib_safe_apply.py - Applique un diff via D5.9 (rollback auto).

Usage :
    python memolib_safe_apply.py <diff-file> --file <rel-path> [--root <git-root>]

Arguments :
    diff-file        fichier .diff (format git diff)
    --file           chemin relatif du fichier cible dans le repo
    --root           racine du repo git (defaut: CWD)
    --dry-run        pre_apply + git apply --check seulement (aucune ecriture)
    --skip-pre-hooks ne pas executer .memolib/hooks/pre_task_*.py
    --skip-post-hooks ne pas executer .memolib/hooks/post_task_*.py

Exit codes :
    0 APPLIED
    1 ROLLED_BACK
    2 BLOCKED
    3 erreur technique
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from d59_controlled_apply import (
    ApplyCertificate, pre_apply, sha256_file,
)
from project_target import _compute_fingerprint


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def _normalize_diff(raw: str) -> str:
    d = raw.replace("\r\n", "\n")
    if d and not d.endswith("\n"):
        d += "\n"
    return d


def _compute_target(root: Path) -> tuple[str, str, str]:
    head = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current") or "HEAD"
    fp = _compute_fingerprint(str(root.resolve()), head, branch)
    return head, branch, fp


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Applique un diff via D5.9 avec rollback automatique.",
    )
    ap.add_argument("diff_file", help="fichier .diff (format git diff)")
    ap.add_argument("--file", required=True,
                    help="chemin relatif du fichier cible dans le repo")
    ap.add_argument("--root", default=".",
                    help="racine du repo git (defaut: CWD)")
    ap.add_argument("--dry-run", action="store_true",
                    help="pre_apply + git apply --check, aucune ecriture")
    ap.add_argument("--authorization", default=None,
                    help="JSON authorization file (required for real apply)")
    ap.add_argument("--skip-pre-hooks", action="store_true")
    ap.add_argument("--skip-post-hooks", action="store_true")
    args = ap.parse_args()

    diff_path = Path(args.diff_file)
    root = Path(args.root).resolve()
    rel = Path(args.file).as_posix()

    try:
        if not diff_path.is_file():
            print(f"ECHEC: diff introuvable: {diff_path}", file=sys.stderr)
            return 3
        if not (root / ".git").is_dir():
            print(f"ECHEC: {root} n'est pas un repo git", file=sys.stderr)
            return 3

        diff = _normalize_diff(diff_path.read_text(encoding="utf-8"))

        if args.authorization:
            import json, hashlib
            auth_path = Path(args.authorization)
            if not auth_path.is_file():
                print(f"ECHEC: authorization introuvable: {auth_path}", file=sys.stderr)
                return 3
            try:
                auth = json.loads(auth_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                print(f"ECHEC: authorization JSON invalide: {e}", file=sys.stderr)
                return 3
            proposal_id = auth.get("proposal_id", "")
            expected_sha = auth.get("expected_diff_sha256", "")
            if not proposal_id or not proposal_id.startswith("P-"):
                print("ECHEC: proposal_id manquant ou invalide", file=sys.stderr)
                return 2
            if not expected_sha:
                print("ECHEC: expected_diff_sha256 manquant", file=sys.stderr)
                return 2
            actual_sha = hashlib.sha256(diff.encode("utf-8")).hexdigest()
            if actual_sha != expected_sha:
                print("ECHEC: diff SHA mismatch", file=sys.stderr)
                return 2
            print(f"  authorization OK: {proposal_id}")

        head, branch, fp = _compute_target(root)
        target_file = root / rel
        if not target_file.is_file():
            print(f"ECHEC: fichier cible introuvable: {target_file}", file=sys.stderr)
            return 3
        evidence = sha256_file(target_file)

        cert = ApplyCertificate(
            path=rel,
            status="AUTHORIZED",
            evidence_sha256=evidence,
            target_git_root=str(root),
            target_head=head,
            target_fingerprint=fp,
        )

        print(f"=== memolib safe-apply ===")
        print(f"diff    : {diff_path} ({len(diff)} octets)")
        print(f"file    : {rel}")
        print(f"root    : {root}")
        print(f"branch  : {branch}")
        print(f"head    : {head[:12]}")
        print(f"fingerprint : {fp}")

        print("\n[1/3] pre_apply gates...")
        ok, reason = pre_apply(
            root, cert, diff,
            target_head=head, target_fingerprint=fp,
        )
        if not ok:
            print(f"  BLOCKED: {reason}")
            print(f"\nRESULT: BLOCKED")
            return 2
        print(f"  OK: {reason}")

        if args.dry_run:
            print("\nRESULT: DRY-RUN OK (aucune ecriture)")
            return 0

        if not args.authorization:
            print("\nRESULT: BLOCKED (use --authorization <json> for real apply)")
            return 2

        from d59_controlled_apply import run_controlled_apply

        def _verify(_repo_root):
            try:
                content = target_file.read_text(encoding="utf-8", errors="ignore")
                if "<<<<<<<" in content or ">>>>>>>" in content:
                    return False, "conflict markers detected"
                return True, "no conflict markers"
            except Exception as e:
                return False, f"verify error: {e}"

        print("\n[2/2] run_controlled_apply...")
        result = run_controlled_apply(
            root, cert, diff,
            target_head=head,
            target_fingerprint=fp,
            verify=_verify,
        )
        print(f"  status: {result.status}")
        print(f"  reason: {result.reason}")
        print(f"\nRESULT: {result.status}")
        if result.status == "APPLIED":
            return 0
        if result.status == "ROLLED_BACK":
            return 1
        return 2

    except Exception as e:
        print(f"ECHEC technique: {type(e).__name__}: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
