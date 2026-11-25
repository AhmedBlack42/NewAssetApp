from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable, Iterable

from PIL import Image

from app.core.database import Database


SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def iter_image_paths(folder: Path | str, recursive: bool = True,
                     extensions: Iterable[str] = SUPPORTED_EXTENSIONS):
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Image folder does not exist: {root}")
    allowed = {ext.lower() if ext.startswith(".") else "." + ext.lower()
               for ext in extensions}
    iterator = root.rglob("*") if recursive else root.iterdir()
    for path in sorted(iterator):
        try:
            if path.is_file() and path.suffix.lower() in allowed:
                yield path
        except OSError:
            continue


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_folder(folder: Path | str, database: Database, *, recursive: bool = True,
                extensions: Iterable[str] = SUPPORTED_EXTENSIONS,
                force_full: bool = False,
                progress: Callable[[int, int, str], None] | None = None,
                cancelled: Callable[[], bool] | None = None) -> dict:
    paths = list(iter_image_paths(folder, recursive, extensions))
    errors: list[dict] = []
    indexed = duplicates = changed = unchanged = new_or_changed = 0
    total = len(paths)
    for number, path in enumerate(paths, start=1):
        if cancelled and cancelled():
            return {"status": "cancelled", "total": total, "indexed": indexed,
                    "duplicates": duplicates, "errors": errors}
        try:
            stat = path.stat()
            digest = _sha256(path)
            old = database.source_image_by_path(path)
            same_content = bool(old and old["content_sha256"] == digest)
            if same_content and not force_full:
                database.update_source_root(path, folder)
                unchanged += 1
                if progress:
                    progress(number, total, str(path))
                continue
            with Image.open(path) as image:
                width, height = image.size
                image.verify()
            record = {
                "path": str(path.resolve()), "sha256": digest,
                "width": int(width), "height": int(height),
                "file_size": int(stat.st_size), "modified_ns": int(stat.st_mtime_ns),
                "source_root": str(Path(folder).expanduser().resolve()),
            }
            _, duplicate_id = database.upsert_source_image(record)
            indexed += 1
            changed += int(old is not None and not same_content)
            unchanged += int(same_content)
            new_or_changed += int(not same_content)
            duplicates += int(duplicate_id is not None)
        except Exception as exc:
            errors.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})
        if progress:
            progress(number, total, str(path))
    return {"status": "completed", "total": total, "indexed": indexed,
            "new_or_changed": new_or_changed, "changed": changed, "unchanged": unchanged,
            "duplicates": duplicates, "errors": errors}
