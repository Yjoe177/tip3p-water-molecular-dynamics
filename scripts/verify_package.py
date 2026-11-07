"""Check the frozen public package and supplied report/presentation files.

This is a byte-integrity check. It does not rerun molecular dynamics or analyses.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evidence"
MANIFEST = PACKAGE / "FINAL_PACKAGE_MANIFEST_SHA256.csv"
ARTIFACTS = {
    "report/MD_Research_Experiment_Report.pdf": "5cd982fe633d980977ce91143fb295cb007410d44d681da8531c36bfa3efa8ba",
    "presentation/MD_Research_Experiment_Presentation.pdf": "120cbdf2edd0b054323d2e3d979bd4008e8dd9833cf4eade975c859853f3599c",
    "presentation/MD_Research_Experiment_Presentation.pptx": "adb3a8bd3ee6ae3b8ea31528704d917ab445e228e8c07e72e9fa8ec7ad60ed38",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify() -> None:
    with MANIFEST.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["relative_path", "bytes", "sha256"]:
            raise ValueError("Unexpected manifest columns")
        rows = list(reader)

    listed = set()
    for row in rows:
        relative = PurePosixPath(row["relative_path"])
        if relative.is_absolute() or ".." in relative.parts or str(relative) in listed:
            raise ValueError(f"Unsafe or repeated manifest path: {relative}")
        listed.add(str(relative))
        path = PACKAGE.joinpath(*relative.parts)
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing or linked package file: {relative}")
        if path.stat().st_size != int(row["bytes"]):
            raise ValueError(f"Size mismatch: {relative}")
        if sha256_file(path).lower() != row["sha256"].lower():
            raise ValueError(f"SHA-256 mismatch: {relative}")

    actual = {
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*")
        if path.is_file() and path != MANIFEST
    }
    if listed != actual or len(rows) != 451:
        raise ValueError(f"Package inventory mismatch: listed={len(listed)}, actual={len(actual)}")

    for relative, expected in ARTIFACTS.items():
        path = ROOT.joinpath(*PurePosixPath(relative).parts)
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f"Published artifact mismatch: {relative}")

    print(f"Verified {len(rows)} package files and {len(ARTIFACTS)} report/presentation artifacts.")


if __name__ == "__main__":
    verify()
