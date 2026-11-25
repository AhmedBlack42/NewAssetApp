from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "train_data" / "clothing_classifier"
REPORTS = ROOT / "reports"
SPLITS = ("train", "val", "test")
SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
SEED = 20261107


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def classes() -> list[str]:
    names = (DATA / "classes" / "classes.txt").read_text(encoding="utf-8").splitlines()
    registry = json.loads((DATA / "classes" / "registry.json").read_text(encoding="utf-8"))
    active = [row["class_name"] for row in registry["classes"] if row.get("active", True)]
    if names != active or len(names) != 12 or len(set(names)) != 12:
        raise ValueError("Dataset class file and active registry must match the exact ordered 12-class list.")
    map_path = ROOT / "data" / "models" / "clothing_classifier_12class_map.json"
    class_map = json.loads(map_path.read_text(encoding="utf-8"))
    if list(class_map) != names or list(class_map.values()) != list(range(12)):
        raise ValueError("Active model output map does not match the class file order.")
    return names


def scan() -> tuple[list[str], list[dict], list[dict], list[dict]]:
    names = classes()
    rows, unreadable, empty_legacy_dirs = [], [], []
    for split in SPLITS:
        split_root = DATA / split
        if not split_root.is_dir():
            raise FileNotFoundError(split_root)
        for directory in sorted(split_root.iterdir()):
            if not directory.is_dir():
                raise ValueError(f"Unexpected file in active split root: {directory}")
            if directory.name not in names:
                nested = list(directory.rglob("*"))
                if any(item.is_file() for item in nested):
                    raise ValueError(f"Unregistered class folder contains files: {directory}")
                empty_legacy_dirs.append({"split": split, "class_name": directory.name})
                continue
            for path in sorted(directory.rglob("*")):
                if path.is_dir():
                    continue
                if path.suffix.lower() not in SUPPORTED:
                    unreadable.append({"path": path.relative_to(ROOT).as_posix(), "reason": "unsupported_extension"})
                    continue
                row = {"path": path, "relative_path": path.relative_to(DATA).as_posix(),
                       "split": split, "class_name": directory.name,
                       "sha256": sha256(path), "size_bytes": path.stat().st_size}
                try:
                    with Image.open(path) as image:
                        image.verify()
                    with Image.open(path) as image:
                        image.load()
                        row["width"], row["height"], row["format"] = image.width, image.height, image.format
                except Exception as error:
                    unreadable.append({"path": row["relative_path"], "reason": f"decode_error:{error}"})
                rows.append(row)
    return names, rows, unreadable, empty_legacy_dirs


def duplicate_groups(rows: list[dict]) -> list[list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["sha256"]].append(row)
    return [group for group in grouped.values() if len(group) > 1]


def plan_split(names: list[str], rows: list[dict]) -> list[dict]:
    result = []
    for class_name in names:
        members = [row for row in rows if row["class_name"] == class_name]
        if len(members) < 3:
            raise ValueError(f"Too few examples for a held-out test split: {class_name}")
        members.sort(key=lambda row: hashlib.sha256(
            f"{SEED}\0{class_name}\0{row['sha256']}".encode("utf-8")).hexdigest())
        n_val = max(1, math.floor(len(members) * 0.1 + 0.5))
        n_test = max(1, math.floor(len(members) * 0.1 + 0.5))
        if n_val + n_test >= len(members):
            raise ValueError(f"Insufficient training examples after split: {class_name}")
        assignments = (["test"] * n_test + ["val"] * n_val +
                       ["train"] * (len(members) - n_val - n_test))
        for row, assigned in zip(members, assignments):
            result.append({**row, "original_split": row["split"], "assigned_split": assigned})
    return result


def collision_safe_target(split: str, class_name: str, source: Path, digest: str, reserved: set[str]) -> Path:
    destination = DATA / split / class_name / source.name
    key = str(destination).casefold()
    if key in reserved:
        destination = destination.with_name(f"{source.stem}__{digest[:12]}{source.suffix.lower()}")
        key = str(destination).casefold()
        serial = 2
        while key in reserved:
            destination = destination.with_name(f"{source.stem}__{digest[:12]}_{serial}{source.suffix.lower()}")
            key = str(destination).casefold()
            serial += 1
    reserved.add(key)
    return destination


def apply() -> dict:
    names, rows, unreadable, empty_legacy_dirs = scan()
    if unreadable:
        raise ValueError(f"Dataset contains {len(unreadable)} unsupported or unreadable image(s); no files moved.")
    groups = duplicate_groups(rows)
    quarantine_root = DATA / "review" / "duplicate_quarantine"
    if (quarantine_root / "manifest.json").exists():
        raise FileExistsError("A duplicate quarantine manifest already exists; inspect it before a new cleanup run.")
    quarantined = []
    removed_paths: set[str] = set()
    planned_quarantine = []
    for group in groups:
        labels = {row["class_name"] for row in group}
        if len(labels) > 1:
            representatives = []
            chosen = []
        else:
            # Prefer the cleanest original filename when duplicate copies share a class.
            ordered = sorted(group, key=lambda row: ("(1)" in row["path"].name,
                                                     row["path"].name.casefold(), row["relative_path"]))
            representatives, chosen = ordered[:1], ordered[1:]
        representative = representatives[0] if representatives else None
        for row in chosen if representative else group:
            original = row["path"]
            target = quarantine_root / row["sha256"][:16] / row["split"] / row["class_name"] / original.name
            planned_quarantine.append({"source": original, "target": target,
                                       "record": {"source_relative_path": row["relative_path"],
                                                  "quarantine_relative_path": target.relative_to(ROOT).as_posix(),
                                                  "sha256": row["sha256"], "class_name": row["class_name"],
                                                  "original_split": row["split"],
                                                  "reason": "ambiguous_cross_class_exact_duplicate" if not representative else
                                                           "redundant_same_class_exact_duplicate",
                                                  "representative_relative_path": representative["relative_path"] if representative else None}})
    write_json(DATA / "manifests" / "phase5b_cleanup_journal.json", {
        "status": "cleanup_planned", "duplicate_quarantine": [x["record"] for x in planned_quarantine],
        "empty_legacy_class_dirs": empty_legacy_dirs, "no_files_deleted": True})
    for planned in planned_quarantine:
        original, target, record = planned["source"], planned["target"], planned["record"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(f"Quarantine target already exists: {target}")
        shutil.move(str(original), str(target))
        removed_paths.add(str(original))
        quarantined.append(record)
    for entry in empty_legacy_dirs:
        source = DATA / entry["split"] / entry["class_name"]
        target = DATA / "review" / "legacy_empty_class_dirs" / entry["split"] / entry["class_name"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(f"Legacy folder archive already exists: {target}")
        shutil.move(str(source), str(target))

    active_rows = [row for row in rows if str(row["path"]) not in removed_paths]
    assignments = plan_split(names, active_rows)
    reserved: set[str] = set()
    for row in assignments:
        row["target"] = collision_safe_target(row["assigned_split"], row["class_name"],
                                               row["path"], row["sha256"], reserved)
        row["target_relative_path"] = row["target"].relative_to(DATA).as_posix()
        row["source_relative_path"] = row["relative_path"]

    stage_root = DATA / "review" / "split_staging"
    if stage_root.exists() and any(stage_root.iterdir()):
        raise FileExistsError(f"Unfinished prior split staging data must be reviewed first: {stage_root}")
    journal_path = DATA / "manifests" / "phase5b_split_manifest.json"
    journal = {"schema_version": 1, "status": "planned", "seed": SEED,
               "algorithm": "per-class deterministic SHA256 ordering; rounded 10% validation and test; remainder train",
               "source_identity_grouping": "unavailable; exact duplicates are grouped by SHA-256; filename family heuristics are warning-only",
               "class_order": names, "records": [{key: value for key, value in row.items()
                                                     if key not in {"path", "target"}} for row in assignments],
               "duplicate_quarantine": quarantined,
               "legacy_empty_class_dirs_archived": empty_legacy_dirs,
               "unreadable_files": unreadable}
    write_json(journal_path, journal)
    journal["status"] = "moving_to_staging"
    write_json(journal_path, journal)
    for row in assignments:
        stage = stage_root / row["source_relative_path"]
        stage.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(row["path"]), str(stage))
        row["staged_path"] = stage
    journal["status"] = "placing_new_splits"
    write_json(journal_path, journal)
    for row in assignments:
        target = row["target"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(f"Unexpected target collision: {target}")
        shutil.move(str(row["staged_path"]), str(target))
    if stage_root.exists():
        for path in sorted(stage_root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        if not any(stage_root.iterdir()):
            stage_root.rmdir()

    final_names, final_rows, final_unreadable, final_empty = scan()
    final_dupes = duplicate_groups(final_rows)
    if final_unreadable or final_dupes or final_empty or final_names != names:
        journal["status"] = "post_move_validation_failed"
        write_json(journal_path, journal)
        raise ValueError("Post-split inventory validation failed; inspect the split manifest before proceeding.")
    counts = {split: Counter(row["class_name"] for row in final_rows if row["split"] == split) for split in SPLITS}
    split_counts = {split: dict(counts[split]) for split in SPLITS}
    journal.update({"status": "completed", "counts_by_split_and_class": split_counts,
                    "total_active_examples": len(final_rows), "exact_duplicate_groups_after_cleanup": len(final_dupes),
                    "unreadable_after_cleanup": len(final_unreadable)})
    write_json(journal_path, journal)
    quarantine_manifest = {"schema_version": 1, "files": quarantined,
                           "legacy_empty_class_dirs_archived": empty_legacy_dirs,
                           "no_files_deleted": True}
    write_json(quarantine_root / "manifest.json", quarantine_manifest)
    migration_path = DATA / "manifests" / "migration_manifest.json"
    old_migration = json.loads(migration_path.read_text(encoding="utf-8")) if migration_path.exists() else {}
    migration_backup = DATA / "manifests" / "migration_manifest.pre_phase5b.json"
    if migration_path.exists() and not migration_backup.exists():
        shutil.copy2(migration_path, migration_backup)
    write_json(migration_path, {"schema_version": 2, "status": "phase5b_stratified_split_complete",
                                "class_count": 12, "class_order": names,
                                "previous_migration_manifest": migration_backup.relative_to(ROOT).as_posix() if migration_backup.exists() else None,
                                "old_migration_record": old_migration,
                                "split_manifest": journal_path.relative_to(ROOT).as_posix(),
                                "duplicate_quarantine_manifest": (quarantine_root / "manifest.json").relative_to(ROOT).as_posix(),
                                "source_photographs_outside_active_dataset_modified": False,
                                "training_performed": False})
    cleanup_journal = {"status": "completed", "duplicate_quarantine": quarantined,
                       "empty_legacy_class_dirs": empty_legacy_dirs,
                       "active_split_counts": split_counts, "no_files_deleted": True}
    write_json(DATA / "manifests" / "phase5b_cleanup_journal.json", cleanup_journal)
    return journal


def audit() -> dict:
    names, rows, unreadable, empty_legacy_dirs = scan()
    counts = {split: dict(Counter(row["class_name"] for row in rows if row["split"] == split)) for split in SPLITS}
    dupes = duplicate_groups(rows)
    class_totals = Counter(row["class_name"] for row in rows)
    source_prefix: dict[str, set[str]] = defaultdict(set)
    prefix_paths: dict[str, list[str]] = defaultdict(list)
    import re
    for row in rows:
        match = re.match(r"^(\d{7,})(?:_|\b)", row["path"].name)
        if match:
            prefix_paths[match.group(1)].append(row["relative_path"])
            source_prefix[match.group(1)].add(row["split"])
    possible_families = [{"filename_prefix": key, "paths": paths, "splits": sorted(source_prefix[key])}
                         for key, paths in prefix_paths.items() if len(paths) > 1 and len(source_prefix[key]) > 1]
    manifest_path = DATA / "manifests" / "phase5b_split_manifest.json"
    manifest_errors = []
    if not manifest_path.is_file():
        manifest_errors.append("split_manifest_missing")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") != "completed":
            manifest_errors.append("split_manifest_not_completed")
        if manifest.get("class_order") != names:
            manifest_errors.append("split_manifest_class_order_mismatch")
        manifest_rows = manifest.get("records", [])
        if len(manifest_rows) != len(rows):
            manifest_errors.append("split_manifest_record_count_mismatch")
        destinations = [row.get("target_relative_path") for row in manifest_rows]
        if len(destinations) != len(set(destinations)):
            manifest_errors.append("split_manifest_duplicate_destination")
        for row in manifest_rows:
            destination = DATA / str(row.get("target_relative_path", ""))
            if (not destination.is_file() or sha256(destination) != row.get("sha256")
                    or row.get("assigned_split") != row.get("target_relative_path", "").split("/", 1)[0]
                    or row.get("class_name") not in names):
                manifest_errors.append(f"split_manifest_file_mismatch:{row.get('target_relative_path')}")
                if len(manifest_errors) > 20:
                    break
        if manifest.get("counts_by_split_and_class") != counts:
            manifest_errors.append("split_manifest_counts_mismatch")
    return {"class_order": names, "counts_by_split_and_class": counts,
            "split_totals": {split: sum(counts[split].values()) for split in SPLITS},
            "total_images": len(rows), "supported_extensions": dict(Counter(row["path"].suffix.lower() for row in rows)),
            "unreadable_files": unreadable, "exact_duplicate_groups": [[
                {"path": row["relative_path"], "class_name": row["class_name"], "split": row["split"],
                 "sha256": row["sha256"]} for row in group] for group in dupes],
            "cross_split_duplicate_groups": [group for group in [[
                {"path": row["relative_path"], "class_name": row["class_name"], "split": row["split"],
                 "sha256": row["sha256"]} for row in group] for group in dupes]
                if len({row["split"] for row in group}) > 1],
            "cross_class_duplicate_groups": [group for group in [[
                {"path": row["relative_path"], "class_name": row["class_name"], "split": row["split"],
                 "sha256": row["sha256"]} for row in group] for group in dupes]
                if len({row["class_name"] for row in group}) > 1],
            "empty_classes": [name for name in names if class_totals[name] == 0],
            "inactive_empty_class_dirs": empty_legacy_dirs,
            "class_min": min(class_totals.values()) if class_totals else 0,
            "class_max": max(class_totals.values()) if class_totals else 0,
            "possible_source_leakage_warning_only": possible_families,
            "source_identity_manifest_available": False,
            "registry_consistency": "passed" if names == [row["class_name"] for row in json.loads((DATA / "classes" / "registry.json").read_text(encoding="utf-8"))["classes"]] else "failed",
            "split_manifest_consistency": "passed" if not manifest_errors else "failed",
            "split_manifest_errors": manifest_errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("audit", "apply"))
    args = parser.parse_args()
    if args.action == "audit":
        result = audit()
        write_json(REPORTS / "PHASE5B_CLOTHING_DATASET_REAUDIT.json", result)
        print(json.dumps(result, indent=2))
        return 1 if result["unreadable_files"] else 0
    result = apply()
    write_json(REPORTS / "PHASE5B_CLOTHING_SPLIT_VALIDATION.json", result)
    print(json.dumps({key: result[key] for key in ("status", "seed", "class_order", "counts_by_split_and_class",
                                                  "total_active_examples", "exact_duplicate_groups_after_cleanup",
                                                  "unreadable_after_cleanup")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
