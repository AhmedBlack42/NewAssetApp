from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


COLAB_RAR_MIN_BYTES = 4_000_000_000


def find_rar_writer() -> str | None:
    for name in ("rar", "winrar"):
        found = shutil.which(name)
        if found:
            return found
    candidates = (
        Path(os.environ.get("ProgramFiles", "")) / "WinRAR" / "WinRAR.exe",
        Path(os.environ.get("ProgramFiles", "")) / "WinRAR" / "Rar.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "WinRAR" / "WinRAR.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "WinRAR" / "Rar.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def package_uncompressed_size(package_dir: Path) -> int:
    package_dir = Path(package_dir)
    return sum(path.stat().st_size for path in package_dir.rglob("*") if path.is_file())


def inspect_colab_rar_readiness(package_dir: Path) -> dict:
    package_dir = Path(package_dir)
    uncompressed = package_uncompressed_size(package_dir) if package_dir.is_dir() else 0
    writer = find_rar_writer()
    size_ready = uncompressed >= COLAB_RAR_MIN_BYTES
    ready_to_attempt = writer is not None and size_ready
    return {
        "status": "ready_to_attempt" if ready_to_attempt else "blocked",
        "minimum_rar_bytes": COLAB_RAR_MIN_BYTES,
        "uncompressed_package_bytes": uncompressed,
        "remaining_bytes_for_minimum": max(0, COLAB_RAR_MIN_BYTES - uncompressed),
        "rar_writer": writer,
        "rar_available": writer is not None,
        "minimum_satisfied_by_uncompressed_size": size_ready,
        "archive_size_verified": False,
    }


def create_colab_rar(package_dir: Path, output_archive: Path) -> dict:
    package_dir = Path(package_dir).resolve()
    output_archive = Path(output_archive).resolve()
    readiness = inspect_colab_rar_readiness(package_dir)
    if not readiness["rar_available"]:
        return {
            "status": "blocked",
            "reason": "No legitimate RAR writer is available. Use the existing WinRAR/RAR executable; no ZIP fallback will be generated.",
            **readiness,
            "archive": None,
        }
    if package_uncompressed_size(package_dir) < COLAB_RAR_MIN_BYTES:
        return {
            "status": "blocked",
            "reason": "The eligible package is below the exact 4,000,000,000-byte RAR minimum.",
            "remaining_bytes": max(0, COLAB_RAR_MIN_BYTES - package_uncompressed_size(package_dir)),
            **readiness,
            "archive": None,
        }
    output_archive.parent.mkdir(parents=True, exist_ok=True)
    writer = readiness["rar_writer"]
    command = [writer, "a", "-ep1", "-r", "-m5", str(output_archive),
               str(package_dir) + os.sep + "*"]
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, timeout=3600)
    if completed.returncode != 0 or not output_archive.is_file():
        return {"status": "failed", "reason": completed.stdout.strip(),
                "archive": str(output_archive), "returncode": completed.returncode}
    archive_size = output_archive.stat().st_size
    if archive_size < COLAB_RAR_MIN_BYTES:
        return {
            "status": "blocked",
            "reason": "The actual RAR archive is below the exact 4,000,000,000-byte minimum.",
            "remaining_bytes": COLAB_RAR_MIN_BYTES - archive_size,
            "archive": str(output_archive),
            "archive_size": archive_size,
        }
    test = subprocess.run([writer, "t", str(output_archive)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, timeout=3600)
    if test.returncode != 0:
        return {"status": "failed", "reason": test.stdout.strip(),
                "archive": str(output_archive), "archive_size": archive_size,
                "integrity_test": "failed"}
    return {
        "status": "ready",
        "archive": str(output_archive),
        "archive_size": archive_size,
        "integrity_test": "passed",
        "rar_writer": writer,
    }
