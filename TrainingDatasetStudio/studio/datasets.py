from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from .importer import (
    _approved_yolo_registry,
    _registry_class,
    _valid_body_images_target_mask,
    sha256_file,
)
from .store import SHARED_CNN_TASKS, StudioStore


SPLITS = ("train", "validation", "test")
TASK_YOLO = {"yolo_detection", "yolo_detector"}


class DatasetError(ValueError):
    pass


class DatasetService:
    def __init__(self, store: StudioStore, output_dir: Path | str):
        self.store = store
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_dataset(self, name: str, task: str, registry_id: str,
                       registry_version: str, training_bundle_id: int | None = None,
                       model_id: str | None = None) -> int:
        clean = " ".join(str(name).split())
        if not clean or not task or not registry_id or not registry_version:
            raise DatasetError("Dataset name, task and registry identity are required.")
        with self.store.connect() as db:
            if training_bundle_id is not None:
                bundle = db.execute("SELECT task,model_id,registry_id,registry_version FROM training_bundles WHERE id=?",
                                    (int(training_bundle_id),)).fetchone()
                expected_bundle_task = "shared_cnn" if task in SHARED_CNN_TASKS else task
                if not bundle or (bundle["task"], bundle["registry_id"], bundle["registry_version"]) != (
                        expected_bundle_task, registry_id, registry_version):
                    raise DatasetError("Choose a confirmed training bundle with this exact task and registry.")
                if model_id is not None and str(model_id) != str(bundle["model_id"] or ""):
                    raise DatasetError("The selected model identity does not match this training segment.")
                model_id = str(bundle["model_id"] or "")
            elif model_id is None:
                models = db.execute(
                    """SELECT DISTINCT model_id FROM records
                       WHERE task=? AND registry_id=? AND registry_version=? AND model_id IS NOT NULL
                       AND status='accepted' AND human_confirmed=1 AND training_eligible=1""",
                    (task, registry_id, registry_version),
                ).fetchall()
                if len(models) != 1:
                    raise DatasetError("Select one model-specific training segment to create this dataset.")
                model_id = str(models[0]["model_id"])
            cursor = db.execute(
                """INSERT INTO datasets(name,task,registry_id,registry_version,training_bundle_id,model_id)
                   VALUES(?,?,?,?,?,?)""",
                (clean, task, registry_id, registry_version, training_bundle_id, model_id),
            )
            return int(cursor.lastrowid)

    def readiness_report(self, dataset_id: int | None = None,
                         task: str | None = None,
                         model_id: str | None = None) -> dict:
        """Return a read-only, source-grouped CNN readiness report."""
        thresholds = {"insufficient": 50, "exploratory": 100,
                      "recommended": 300, "strong": 500}
        single_heads = {
            "fullbody": ("fullbody", ("clothed", "topless", "bottomless", "bra", "panty")),
            "portrait": ("portrait", ("portrait", "tportrait")),
            "arousal": ("arousal", ("aroused", "edging")),
            "corruption": ("corruption", ("conservative", "slut", "whore", "u_whore")),
        }
        with self.store.connect() as db:
            clauses = []
            args = []
            if dataset_id is not None:
                dataset = db.execute(
                    "SELECT * FROM datasets WHERE id=?", (int(dataset_id),)
                ).fetchone()
                if not dataset:
                    raise DatasetError("Dataset does not exist.")
                model_id = str(dataset["model_id"] or "")
                if dataset["task"] not in SHARED_CNN_TASKS:
                    clauses.append("r.task=?")
                    args.append(str(dataset["task"]))
                clauses.append("r.model_id=?")
                args.append(model_id)
                clauses.append("r.registry_id=?")
                args.append(str(dataset["registry_id"]))
                clauses.append("r.registry_version=?")
                args.append(str(dataset["registry_version"]))
            elif task:
                clauses.append("r.task=?")
                args.append(str(task))
            if model_id and dataset_id is None:
                clauses.append("r.model_id=?")
                args.append(str(model_id))
            where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
            rows = db.execute(
                """SELECT r.*,
                          (SELECT dvr.split FROM dataset_version_records dvr
                           JOIN dataset_versions dv ON dv.id=dvr.version_id
                           WHERE dvr.record_id=r.id
                           ORDER BY dv.id DESC LIMIT 1) AS split,
                          (SELECT dv.id FROM dataset_version_records dvr
                           JOIN dataset_versions dv ON dv.id=dvr.version_id
                           WHERE dvr.record_id=r.id
                           ORDER BY dv.id DESC LIMIT 1) AS version_id,
                          (SELECT dv.finalized FROM dataset_version_records dvr
                           JOIN dataset_versions dv ON dv.id=dvr.version_id
                           WHERE dvr.record_id=r.id
                           ORDER BY dv.id DESC LIMIT 1) AS finalized
                   FROM records r"""
                + where,
                args,
            ).fetchall()

        def status_for(source_count: int, split_counts: dict[str, int]) -> str:
            split_ready = (
                split_counts["train"] >= 70
                and split_counts["validation"] >= 15
                and split_counts["test"] >= 15
            )
            if source_count >= 100 and not split_ready:
                return "insufficient"
            if source_count >= thresholds["strong"]:
                return "strong"
            if source_count >= thresholds["recommended"]:
                return "recommended"
            if source_count >= 100:
                return "minimum_training_ready"
            if source_count >= thresholds["insufficient"]:
                return "exploratory_only"
            return "insufficient"

        def split_counts(source_rows: list[dict]) -> dict:
            return {
                split: len({
                    str(row["source_sha256"])
                    for row in source_rows
                    if row["split"] == split and row["source_sha256"]
                })
                for split in SPLITS
            }

        entries = []
        for head, (_, classes) in single_heads.items():
            for label in classes:
                eligible = []
                excluded_pending = 0
                excluded_stale = 0
                excluded_invalid = 0
                excluded_duplicate = 0
                for row in rows:
                    annotation = json.loads(row["annotation_json"] or "{}")
                    structured = (annotation.get("labels") or {}).get("structured") or {}
                    record_head = (annotation.get("task_head") or annotation.get("head")
                                   or structured.get("output_group") or "")
                    if record_head == "fullbody_state":
                        record_head = "fullbody"
                    if str(record_head) != head:
                        continue
                    target = annotation.get("target_label") or annotation.get("class_label")
                    if target != label:
                        continue
                    reason = str(row["reason"] or "").casefold()
                    if annotation.get("stale") or "stale" in reason:
                        excluded_stale += 1
                        continue
                    if reason in {"duplicate_task_content_identity",
                                  "conflicting_task_annotation_identity"}:
                        excluded_duplicate += 1
                        continue
                    if row["status"] in {"quarantined", "rejected"}:
                        excluded_invalid += 1
                        continue
                    if not row["human_confirmed"] or not row["training_eligible"]:
                        excluded_pending += 1
                        continue
                    if row["status"] != "accepted":
                        excluded_invalid += 1
                        continue
                    eligible.append(dict(row))
                source_groups = {
                    str(row["source_sha256"])
                    for row in eligible
                    if row["source_sha256"]
                }
                split_source_counts = split_counts(eligible)
                crop_hashes = {
                    hashlib.sha256(json.dumps(
                        [row["source_sha256"], row["task"],
                         json.loads(row["annotation_json"] or "{}").get("bbox_xyxy")],
                        separators=(",", ":"), sort_keys=True,
                    ).encode("utf-8")).hexdigest()
                    for row in eligible
                }
                entries.append({
                    "head": head,
                    "class": label,
                    "eligible_crop_records": len(eligible),
                    "unique_crop_hashes": len(crop_hashes),
                    "unique_source_groups": len(source_groups),
                    "train_source_groups": split_source_counts["train"],
                    "validation_source_groups": split_source_counts["validation"],
                    "test_source_groups": split_source_counts["test"],
                    "pending_unreviewed": excluded_pending,
                    "invalid_rejected": excluded_invalid,
                    "stale_excluded": excluded_stale,
                    "duplicates_excluded": excluded_duplicate
                    + max(0, len(eligible) - len(crop_hashes)),
                    "status": status_for(len(source_groups), split_source_counts),
                })

        body_entries = []
        for outcome, target_key in (("cum_positive", "cum"), ("cum_negative", "cum"),
                                    ("accessory_positive", "accessory"),
                                    ("accessory_negative", "accessory")):
            positive = outcome.endswith("positive")
            selected = []
            pending = stale = invalid = duplicates = 0
            for row in rows:
                annotation = json.loads(row["annotation_json"] or "{}")
                structured = (annotation.get("labels") or {}).get("structured") or {}
                record_head = (annotation.get("task_head") or annotation.get("head")
                               or structured.get("output_group") or "")
                if str(record_head) != "body_images":
                    continue
                target_mask = (annotation.get("target_mask")
                               or annotation.get("body_images_target_mask")
                               or structured.get("body_images_target_mask")
                               or {})
                state = target_mask.get(target_key) if isinstance(target_mask, dict) else None
                if not isinstance(state, dict) or set(("target", "evaluated")) - set(state):
                    pending += 1
                    continue
                if state["evaluated"] is not True:
                    pending += 1
                    continue
                if state["target"] not in {True, False}:
                    pending += 1
                    continue
                if state["target"] != positive:
                    continue
                reason = str(row["reason"] or "").casefold()
                if annotation.get("stale") or "stale" in reason:
                    stale += 1
                    continue
                if reason in {"duplicate_task_content_identity",
                              "conflicting_task_annotation_identity"}:
                    duplicates += 1
                    continue
                if row["status"] in {"quarantined", "rejected"}:
                    invalid += 1
                    continue
                if not row["human_confirmed"] or not row["training_eligible"]:
                    pending += 1
                    continue
                if row["status"] != "accepted":
                    invalid += 1
                    continue
                selected.append(dict(row))
            source_groups = {
                str(row["source_sha256"]) for row in selected if row["source_sha256"]
            }
            split_source_counts = split_counts(selected)
            crop_hashes = {
                hashlib.sha256(json.dumps(
                    [row["source_sha256"], row["task"],
                     json.loads(row["annotation_json"] or "{}").get("bbox_xyxy")],
                    separators=(",", ":"), sort_keys=True,
                ).encode("utf-8")).hexdigest()
                for row in selected
            }
            body_entries.append({
                "head": "body_images",
                "outcome": outcome,
                "eligible_crop_records": len(selected),
                "unique_source_groups": len(source_groups),
                "train_source_groups": split_source_counts["train"],
                "validation_source_groups": split_source_counts["validation"],
                "test_source_groups": split_source_counts["test"],
                "pending_unreviewed": pending,
                "invalid_rejected": invalid,
                "stale_excluded": stale,
                "eligible_crop_hashes": len(crop_hashes),
                "duplicates_excluded": duplicates + max(0, len(selected) - len(crop_hashes)),
                "status": status_for(len(source_groups), split_source_counts),
            })

        weakest = [entry["status"] for entry in entries + body_entries]
        rank = {"insufficient": 0, "exploratory_only": 1,
                "minimum_training_ready": 2, "recommended": 3, "strong": 4}
        model_status = min(weakest, key=lambda value: rank.get(value, 0)) if weakest else "insufficient"
        return {
            "thresholds": {
                "insufficient_below": 50,
                "exploratory": [50, 99],
                "minimum_training_ready": 100,
                "recommended": 300,
                "strong": 500,
                "minimum_split_groups": {"train": 70, "validation": 15, "test": 15},
            },
            "single_label": entries,
            "body_images": body_entries,
            "model_status": model_status,
            "dataset_id": dataset_id,
            "task": task,
            "model_id": model_id,
        }

    def version_readiness_report(self, version_id: int) -> dict:
        """Report exact-version eligibility, integrity and minimum group coverage."""
        with self.store.connect() as db:
            version = db.execute(
                """SELECT dv.finalized,dv.ratios_json,d.task,d.model_id,d.registry_id,
                          d.registry_version
                   FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id
                   WHERE dv.id=?""", (int(version_id),)
            ).fetchone()
        if not version:
            raise DatasetError("Dataset version does not exist.")
        rows = self.store.version_rows(version_id)
        included = [row for row in rows if row["included"]]
        eligible = [row for row in included
                    if row["status"] == "accepted" and row["human_confirmed"]
                    and row["training_eligible"]]
        split_group_sets = {split: set() for split in SPLITS}
        source_splits: dict[str, set[str]] = {}
        target_counts: dict[str, int] = {}
        body_target_counts = {
            target: {"positive": 0, "negative": 0, "pending": 0}
            for target in ("cum", "accessory")
        }
        invalid_media = []
        for row in eligible:
            source_hash = str(row["source_sha256"] or "")
            split = row["split"]
            if source_hash and split in split_group_sets:
                split_group_sets[split].add(source_hash)
                source_splits.setdefault(source_hash, set()).add(split)
            label = str(row["class_label"] or "")
            target_counts[label] = target_counts.get(label, 0) + 1
            if version["task"] == "body_images_classification":
                annotation = row["annotation_snapshot"]
                structured = (annotation.get("labels") or {}).get("structured") or {}
                mask = (annotation.get("body_images_target_mask")
                        or structured.get("body_images_target_mask") or {})
                for target in ("cum", "accessory"):
                    state = mask.get(target) if isinstance(mask, dict) else None
                    outcome = ("pending" if not isinstance(state, dict)
                               or state.get("evaluated") is not True else
                               "positive" if state.get("target") is True else "negative")
                    body_target_counts[target][outcome] += 1
            media_path = Path(row["media_path"]) if row["media_path"] else None
            original = row.get("original_json") or {}
            if isinstance(original, str):
                original = json.loads(original or "{}")
            media_info = original.get("media") or {}
            expected_hash = (str(media_info.get("sha256") or "").casefold()
                             if media_info.get("role") == "authoritative_detection_crop"
                             else source_hash.casefold())
            try:
                if (not media_path or not media_path.is_file()
                        or not expected_hash
                        or sha256_file(media_path).casefold() != expected_hash):
                    invalid_media.append(str(row["record_id"]))
                    continue
                with Image.open(media_path) as image:
                    image.verify()
            except (OSError, ValueError):
                invalid_media.append(str(row["record_id"]))
        split_groups = {split: len(groups) for split, groups in split_group_sets.items()}
        minimums = {"train": 70, "validation": 15, "test": 15}
        unique_groups = len(set().union(*split_group_sets.values()))
        leakage = sorted(source for source, splits in source_splits.items() if len(splits) > 1)
        finalized = bool(version["finalized"])
        blockers = []
        if not finalized:
            blockers.append("dataset_version_not_finalized")
        if unique_groups < 100:
            blockers.append(f"source_group_minimum_not_met:{unique_groups}/100")
        for split, minimum in minimums.items():
            if split_groups[split] < minimum:
                blockers.append(f"{split}_source_group_minimum_not_met:{split_groups[split]}/{minimum}")
        if leakage:
            blockers.append(f"source_group_split_leakage:{len(leakage)}")
        if invalid_media:
            blockers.append(f"missing_or_invalid_media:{len(invalid_media)}")
        return {
            "version_id": int(version_id),
            "task": version["task"],
            "model_id": version["model_id"],
            "registry_id": version["registry_id"],
            "registry_version": version["registry_version"],
            "state": "ready_for_training" if not blockers else "blocked_from_training",
            "imported_records": len(rows),
            "eligible_records": len(eligible),
            "ineligible_records": sum(
                row["status"] == "accepted"
                and (not row["human_confirmed"] or not row["training_eligible"])
                for row in rows
            ),
            "quarantined_records": sum(
                row["status"] in {"quarantined", "rejected", "warning"} for row in rows
            ),
            "assigned_to_split": sum(row["split"] in SPLITS for row in included),
            "source_groups": unique_groups,
            "split_source_groups": split_groups,
            "minimum_split_source_groups": minimums,
            "target_distribution": target_counts,
            "body_images_target_distribution": (
                body_target_counts if version["task"] == "body_images_classification" else None
            ),
            "duplicate_records": sum(
                row["reason"] == "duplicate_task_content_identity" for row in rows
            ),
            "invalid_media_record_ids": invalid_media,
            "split_leakage_source_hashes": leakage,
            "validated": finalized,
            "finalized": finalized,
            "ready_for_training": not blockers,
            "blocked_from_training": bool(blockers),
            "blockers": blockers,
            "split_ratios": json.loads(version["ratios_json"]),
        }

    def create_version(self, dataset_id: int, *, seed: int = 42,
                       ratios: dict[str, float] | None = None,
                       include_record_ids: set[int] | None = None,
                       exclusions: dict[int, str] | None = None,
                       split_overrides: dict[int, str] | None = None) -> int:
        ratios = ratios or {"train": .7, "validation": .15, "test": .15}
        self._validate_ratios(ratios)
        exclusions = {int(key): str(value).strip() for key, value in (exclusions or {}).items()}
        if any(not reason for reason in exclusions.values()):
            raise DatasetError("Every explicit exclusion needs a reason.")
        with self.store.connect() as db:
            dataset = db.execute("SELECT * FROM datasets WHERE id=?", (int(dataset_id),)).fetchone()
            if not dataset:
                raise DatasetError("Dataset does not exist.")
            latest = db.execute("SELECT COALESCE(MAX(version_number),0) FROM dataset_versions WHERE dataset_id=?",
                                (int(dataset_id),)).fetchone()[0]
            if not dataset["model_id"]:
                raise DatasetError("This dataset has no model identity; recreate it from a model-specific segment.")
            records = db.execute(
                """SELECT * FROM records WHERE task=? AND model_id=? AND registry_id=?
                   AND registry_version=? ORDER BY id""",
                (dataset["task"], dataset["model_id"], dataset["registry_id"],
                 dataset["registry_version"]),
            ).fetchall()
            if include_record_ids is None:
                included = {int(row["id"]) for row in records
                            if row["status"] == "accepted" and row["human_confirmed"]
                            and row["training_eligible"]}
            else:
                included = {int(value) for value in include_record_ids}
            id_map = {int(row["id"]): row for row in records}
            if not included.issubset(id_map):
                raise DatasetError("Selected records do not all belong to this dataset task and registry.")
            for record_id in included:
                row = id_map[record_id]
                if row["status"] != "accepted" or not row["human_confirmed"] or not row["training_eligible"]:
                    raise DatasetError(f"Record {record_id} is not human-confirmed and training eligible.")
                if not row["media_path"] or not row["source_sha256"]:
                    raise DatasetError(f"Record {record_id} has no verified source media.")
            all_sources = {record_id: row["source_sha256"] for record_id, row in id_map.items()}
            split_map = self._assign_splits(all_sources, seed, ratios)
            for record_id, split in (split_overrides or {}).items():
                if int(record_id) not in included or split not in SPLITS:
                    raise DatasetError("Split overrides must target included records and a valid split.")
                split_map[int(record_id)] = split
            self._assert_source_grouping(included, all_sources, split_map)
            snapshot = {"task": dataset["task"], "registry_id": dataset["registry_id"],
                        "registry_version": dataset["registry_version"], "seed": int(seed),
                        "ratios": ratios, "source_grouped": True,
                        "training_bundle_id": dataset["training_bundle_id"],
                        "model_id": dataset["model_id"]}
            cur = db.execute("""INSERT INTO dataset_versions(dataset_id,version_number,seed,ratios_json,
                               snapshot_json,finalized) VALUES(?,?,?,?,?,0)""",
                             (int(dataset_id), int(latest) + 1, int(seed),
                              json.dumps(ratios, sort_keys=True), json.dumps(snapshot, sort_keys=True)))
            version_id = int(cur.lastrowid)
            for record_id, row in id_map.items():
                is_included = record_id in included
                annotation = json.loads(row["annotation_json"])
                reason = None if is_included else exclusions.get(record_id, "Not selected for this dataset version.")
                db.execute("""INSERT INTO dataset_version_records(version_id,record_id,split,included,
                             exclusion_reason,annotation_snapshot_json) VALUES(?,?,?,?,?,?)""",
                           (version_id, record_id, split_map.get(record_id) if is_included else None,
                            int(is_included), reason, json.dumps(annotation, ensure_ascii=False, sort_keys=True)))
            return version_id

    @staticmethod
    def _validate_ratios(ratios: dict[str, float]) -> None:
        if set(ratios) != set(SPLITS):
            raise DatasetError("Train, validation and test ratios are required.")
        values = [float(ratios[key]) for key in SPLITS]
        if any(value < 0 or value > 1 for value in values) or abs(sum(values) - 1.0) > 1e-8:
            raise DatasetError("Split ratios must be between zero and one and sum to 1.0.")

    @staticmethod
    def _assign_splits(source_by_record: dict[int, str], seed: int,
                       ratios: dict[str, float]) -> dict[int, str]:
        sources = sorted(set(str(value) for value in source_by_record.values()),
                         key=lambda source: hashlib.sha256(f"{int(seed)}:{source}".encode()).hexdigest())
        active = [split for split in SPLITS if float(ratios[split]) > 0]
        counts = {split: 0 for split in SPLITS}
        n = len(sources)
        if n:
            total = sum(float(ratios[split]) for split in active)
            expected = {split: n * float(ratios[split]) / total for split in active}
            counts.update({split: int(expected[split]) for split in active})
            remainder = n - sum(counts.values())
            for split in sorted(active, key=lambda key: (expected[key] - counts[key], -SPLITS.index(key)),
                                reverse=True)[:remainder]:
                counts[split] += 1
            if n >= len(active):
                for split in active:
                    if counts[split] == 0:
                        donor = max((key for key in active if counts[key] > 1),
                                    key=lambda key: (counts[key] - expected[key], counts[key]))
                        counts[donor] -= 1; counts[split] += 1
            elif n >= 2 and "train" in active and "validation" in active:
                counts = {split: 0 for split in SPLITS}
                counts["train"] = 1; counts["validation"] = 1
            elif "train" in active:
                counts = {split: 0 for split in SPLITS}; counts["train"] = n
        by_source: dict[str, str] = {}
        cursor = 0
        for split in SPLITS:
            for source in sources[cursor:cursor + counts[split]]:
                by_source[source] = split
            cursor += counts[split]
        return {record_id: by_source[str(source)] for record_id, source in source_by_record.items()}

    @staticmethod
    def _assert_source_grouping(included: set[int], sources: dict[int, str], splits: dict[int, str]) -> None:
        owners: dict[str, str] = {}
        for record_id in included:
            source = str(sources[record_id])
            split = splits[record_id]
            if source in owners and owners[source] != split:
                raise DatasetError(f"Source image {source} would leak across dataset splits.")
            owners[source] = split

    def set_record_inclusion(self, version_id: int, record_id: int, included: bool,
                             exclusion_reason: str | None = None) -> None:
        if not included and not str(exclusion_reason or "").strip():
            raise DatasetError("Provide an explicit reason for excluding this record.")
        with self.store.connect() as db:
            version = db.execute("SELECT finalized FROM dataset_versions WHERE id=?", (int(version_id),)).fetchone()
            if not version or version["finalized"]:
                raise DatasetError("Finalized dataset versions are immutable.")
            row = db.execute("SELECT source_sha256 FROM records WHERE id=?", (int(record_id),)).fetchone()
            if not row:
                raise DatasetError("Record does not exist.")
            split = "train" if included else None
            db.execute("""UPDATE dataset_version_records SET included=?,split=?,exclusion_reason=?
                         WHERE version_id=? AND record_id=?""",
                       (int(included), split, None if included else exclusion_reason.strip(),
                        int(version_id), int(record_id)))

    def set_split(self, version_id: int, record_id: int, split: str) -> None:
        if split not in SPLITS:
            raise DatasetError("Choose train, validation or test.")
        with self.store.connect() as db:
            version = db.execute("SELECT finalized FROM dataset_versions WHERE id=?", (int(version_id),)).fetchone()
            if not version or version["finalized"]:
                raise DatasetError("Finalized dataset versions are immutable.")
            db.execute("UPDATE dataset_version_records SET split=? WHERE version_id=? AND record_id=? AND included=1",
                       (split, int(version_id), int(record_id)))
            rows = db.execute("""SELECT dvr.record_id,r.source_sha256,dvr.split FROM dataset_version_records dvr
                             JOIN records r ON r.id=dvr.record_id WHERE dvr.version_id=? AND dvr.included=1""",
                              (int(version_id),)).fetchall()
            sources: dict[str, set[str]] = {}
            for row in rows:
                sources.setdefault(row["source_sha256"], set()).add(row["split"])
            conflict = next((source for source, groups in sources.items() if len(groups) > 1), None)
            if conflict:
                raise DatasetError(f"Source image {conflict} must stay in one split.")

    def finalize(self, version_id: int) -> dict:
        with self.store.connect() as db:
            version = db.execute("""SELECT dv.*,d.task,d.registry_id,d.registry_version,d.training_bundle_id
                                FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id WHERE dv.id=?""",
                                 (int(version_id),)).fetchone()
            if not version:
                raise DatasetError("Dataset version does not exist.")
            if version["finalized"]:
                return {"version_id": int(version_id), "finalized": True, "already_finalized": True}
            rows = db.execute("""SELECT dvr.*,r.source_sha256,r.media_path,r.original_json,r.annotation_json,r.status,
                                      r.human_confirmed,r.training_eligible,r.task,r.target_class_id,
                                      r.source_width,r.source_height,r.class_label
                               FROM dataset_version_records dvr JOIN records r ON r.id=dvr.record_id
                               WHERE dvr.version_id=? ORDER BY r.id""", (int(version_id),)).fetchall()
            registry_row = db.execute("SELECT payload_json FROM registries WHERE registry_id=? AND version=?",
                                      (version["registry_id"], version["registry_version"])).fetchone()
            if not registry_row:
                raise DatasetError("The exact model registry for this dataset version is missing.")
            registry_data = json.loads(registry_row["payload_json"])
            if version["task"] in TASK_YOLO:
                if (version["registry_id"] != "newassetapp_yolo_detector_v1"
                        or registry_data != _approved_yolo_registry()):
                    raise DatasetError(
                        "The dataset registry does not match the approved Studio YOLO registry."
                    )
            selected = [row for row in rows if row["included"]]
            if not selected:
                raise DatasetError("A dataset version needs at least one included record.")
            split_sources: dict[str, set[str]] = {}
            for row in selected:
                if row["split"] not in SPLITS:
                    raise DatasetError(f"Included record {row['record_id']} has no valid split.")
                if row["status"] != "accepted" or not row["human_confirmed"] or not row["training_eligible"]:
                    raise DatasetError(f"Included record {row['record_id']} is not currently accepted.")
                if not row["source_sha256"] or not row["media_path"]:
                    raise DatasetError(f"Included record {row['record_id']} lacks verified media.")
                original = json.loads(row["original_json"] or "{}")
                source = original.get("source") or {}
                media = original.get("media") or {}
                source_digest = str(source.get("sha256") or "").casefold()
                if source_digest and source_digest != str(row["source_sha256"]).casefold():
                    raise DatasetError(f"Included record {row['record_id']} source provenance changed.")
                media_path = Path(row["media_path"])
                if not media_path.is_file():
                    raise DatasetError(f"Included record {row['record_id']} media file is missing.")
                actual_media_digest = sha256_file(media_path).casefold()
                if media.get("role") == "authoritative_detection_crop":
                    if str(media.get("source_sha256") or "").casefold() != str(row["source_sha256"]).casefold():
                        raise DatasetError(f"Included crop {row['record_id']} is not linked to its source image.")
                    expected_media_digest = str(media.get("sha256") or "").casefold()
                else:
                    expected_media_digest = str(row["source_sha256"]).casefold()
                    declared_media_digest = str(media.get("sha256") or "").casefold()
                    if declared_media_digest and declared_media_digest != expected_media_digest:
                        raise DatasetError(f"Included record {row['record_id']} media provenance changed.")
                if not expected_media_digest or actual_media_digest != expected_media_digest:
                    raise DatasetError(f"Included record {row['record_id']} media hash verification failed.")
                annotation = json.loads(row["annotation_snapshot_json"])
                box = annotation.get("bbox_xyxy")
                width, height = int(row["source_width"] or 0), int(row["source_height"] or 0)
                empty_yolo = (version["task"] in TASK_YOLO and annotation.get("empty_image") is True
                              and annotation.get("class_label") == "__empty__"
                              and annotation.get("labels", {}).get("structured", {}).get("no_objects") is True
                              and box is None and annotation.get("target_class_id") is None)
                try:
                    box = [] if empty_yolo else [float(value) for value in box]
                except (TypeError, ValueError):
                    box = []
                if (not empty_yolo and (len(box) != 4 or not all(math.isfinite(value) for value in box)
                        or not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height))):
                    raise DatasetError(f"Included record {row['record_id']} has an invalid or out-of-bounds box.")
                label = str(annotation.get("class_label") or row["class_label"] or "")
                structured = (annotation.get("labels") or {}).get("structured", {})
                body_mask = (annotation.get("body_images_target_mask")
                             or structured.get("body_images_target_mask"))
                body_mask_label = (version["task"] == "body_images_classification"
                                   and label in {"body_images_multi_label", "body_images_none",
                                                 "body_images_pending"})
                if version["task"] == "body_images_classification":
                    if not _valid_body_images_target_mask(body_mask, require_evaluated=True):
                        raise DatasetError(
                            f"Included Body Images record {row['record_id']} lacks a valid evaluated target mask."
                        )
                cls = (None if empty_yolo or body_mask_label else
                       _registry_class(registry_data, version["task"],
                                      structured.get("output_group"), label))
                if cls is None and not empty_yolo and not body_mask_label:
                    raise DatasetError(f"Included class {label!r} on record {row['record_id']} is absent from its task registry.")
                registry_class_id = (
                    (cls.get("id") if version["task"] in TASK_YOLO else cls.get("class_id"))
                    if cls else None
                )
                target_class_id = annotation.get("target_class_id", row["target_class_id"])
                if not empty_yolo and registry_class_id is not None:
                    if target_class_id is None or int(registry_class_id) != int(target_class_id):
                        raise DatasetError(f"Included record {row['record_id']} class name and registry ID do not match.")
                split_sources.setdefault(str(row["source_sha256"]), set()).add(str(row["split"]))
            if any(len(value) != 1 for value in split_sources.values()):
                raise DatasetError("Source image leakage detected across splits.")
            metadata = json.loads(version["snapshot_json"])
            metadata["finalized_at"] = datetime.now(timezone.utc).isoformat()
            metadata["record_count"] = len(selected)
            metadata["split_counts"] = {split: sum(row["split"] == split for row in selected) for split in SPLITS}
            db.execute("""UPDATE dataset_versions SET finalized=1,finalized_at=CURRENT_TIMESTAMP,
                         snapshot_json=? WHERE id=?""",
                       (json.dumps(metadata, ensure_ascii=False, sort_keys=True), int(version_id)))
            return {"version_id": int(version_id), "finalized": True,
                    "record_count": len(selected), "split_counts": metadata["split_counts"]}

    def export_colab(self, version_id: int, destination: Path | str) -> dict:
        destination = Path(destination).resolve()
        if destination.exists():
            raise DatasetError("Output directory already exists; package export never overwrites a prior package.")
        with self.store.connect() as db:
            version = db.execute("""SELECT dv.*,d.task,d.registry_id,d.registry_version,d.name dataset_name,
                                         d.training_bundle_id,d.model_id
                                  FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id
                                  WHERE dv.id=?""", (int(version_id),)).fetchone()
            if not version or not version["finalized"]:
                raise DatasetError("Finalize a dataset version before packaging it.")
            rows = self.store.version_rows(version_id)
            registry = db.execute("""SELECT payload_json,sha256 FROM registries
                                  WHERE registry_id=? AND version=? ORDER BY id DESC LIMIT 1""",
                                  (version["registry_id"], version["registry_version"])).fetchone()
            training_bundle = (db.execute("SELECT bundle_key,size_bytes,max_bytes,record_count FROM training_bundles WHERE id=?",
                                          (version["training_bundle_id"],)).fetchone()
                              if version["training_bundle_id"] is not None else None)
        if not registry:
            raise DatasetError("The dataset's exact model registry was not imported.")
        registry_data = json.loads(registry["payload_json"])
        staging = Path(tempfile.mkdtemp(prefix=".colab_package_", dir=destination.parent))
        try:
            data_root = staging / "dataset"
            files: dict[str, dict] = {}
            records_meta = []
            for row in rows:
                if not row["included"]:
                    continue
                split = row["split"]
                if split not in SPLITS:
                    raise DatasetError(f"Record {row['record_id']} has no split assignment.")
                source = Path(row["media_path"])
                original = json.loads(row["original_json"] or "{}")
                media_info = original.get("media") or {}
                media_role = str(media_info.get("role") or "")
                media_hash = str(media_info.get("sha256") or "").casefold()
                if (media_role == "authoritative_detection_crop"
                        and str(media_info.get("source_sha256") or "").casefold()
                        != str(row["source_sha256"] or "").casefold()):
                    raise DatasetError(f"Source provenance changed for Studio record {row['record_id']}.")
                expected_hash = media_hash if media_role == "authoritative_detection_crop" else str(row["source_sha256"] or "").casefold()
                if not source.is_file() or sha256_file(source).casefold() != expected_hash:
                    raise DatasetError(f"Source media hash changed for Studio record {row['record_id']}.")
                annotation = row["annotation_snapshot"]
                empty_yolo = (version["task"] in TASK_YOLO and annotation.get("empty_image") is True
                              and annotation.get("class_label") == "__empty__"
                              and annotation.get("labels", {}).get("structured", {}).get("no_objects") is True
                              and annotation.get("bbox_xyxy") is None
                              and annotation.get("target_class_id") is None)
                box = [] if empty_yolo else [float(value) for value in annotation["bbox_xyxy"]]
                safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(annotation.get("class_label") or row["class_label"] or "unknown"))
                unique = (f"{row['source_sha256'][:24]}" if version["task"] in TASK_YOLO
                          else f"{row['source_sha256'][:16]}_{row['record_id']}")
                if version["task"] in TASK_YOLO:
                    image_relative = Path("images") / split / (unique + source.suffix.lower())
                    label_relative = Path("labels") / split / (unique + ".txt")
                    image_target = data_root / image_relative
                    label_target = data_root / label_relative
                    image_target.parent.mkdir(parents=True, exist_ok=True)
                    label_target.parent.mkdir(parents=True, exist_ok=True)
                    if not image_target.exists():
                        shutil.copy2(source, image_target)
                    label_target.touch(exist_ok=True)
                    width, height = int(row["source_width"]), int(row["source_height"])
                    if not empty_yolo:
                        x1, y1, x2, y2 = box
                        class_id = annotation.get("target_class_id", row["target_class_id"])
                    else:
                        class_id = None
                    if (not empty_yolo and class_id is None) or width <= 0 or height <= 0:
                        raise DatasetError("YOLO package record lacks class ID or source dimensions.")
                    if not empty_yolo:
                        yolo_line = f"{int(class_id)} {(x1+x2)/(2*width):.8f} {(y1+y2)/(2*height):.8f} {(x2-x1)/width:.8f} {(y2-y1)/height:.8f}\n"
                        with label_target.open("a", encoding="utf-8") as label_file:
                            label_file.write(yolo_line)
                    artifacts = [image_target, label_target]
                else:
                    image_relative = Path("images") / split / safe_label / (unique + ".jpg")
                    image_target = data_root / image_relative
                    image_target.parent.mkdir(parents=True, exist_ok=True)
                    with Image.open(source) as image:
                        rgb = image.convert("RGB")
                        crop = (rgb.copy() if media_role == "authoritative_detection_crop"
                                else rgb.crop(tuple(int(round(v)) for v in box)))
                        crop.save(image_target, "JPEG", quality=95)
                        crop.close()
                        rgb.close()
                    artifacts = [image_target]
                for artifact in artifacts:
                    files[artifact.relative_to(staging).as_posix()] = {
                        "sha256": sha256_file(artifact), "bytes": artifact.stat().st_size}
                record_metadata = {
                    "record_id": row["record_id"], "source_sha256": row["source_sha256"],
                    "split": split, "class_label": annotation.get("class_label"),
                    "class_id": annotation.get("target_class_id"),
                    "bbox_xyxy": None if empty_yolo else box,
                    "empty_image": empty_yolo,
                }
                if version["task"] == "body_images_classification":
                    structured = (annotation.get("labels") or {}).get("structured") or {}
                    record_metadata["body_images_target_mask"] = (
                        annotation.get("body_images_target_mask")
                        or structured.get("body_images_target_mask")
                    )
                records_meta.append(record_metadata)
            registry_path = staging / "registry.json"
            registry_path.write_text(json.dumps(registry_data, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
            files["registry.json"] = {"sha256": sha256_file(registry_path), "bytes": registry_path.stat().st_size}
            if version["task"] in TASK_YOLO:
                names = {int(item["id"]): item["name"] for item in registry_data.get("classes", [])}
                yaml_text = "path: ./dataset\ntrain: images/train\nval: images/validation\ntest: images/test\nnames:\n"
                yaml_text += "".join(f"  {key}: {json.dumps(value)}\n" for key, value in sorted(names.items()))
                (staging / "dataset.yaml").write_text(yaml_text, encoding="utf-8")
                instructions = ("# Google Colab training\n\nUpload and extract this package in Colab. "
                                "Review dataset.yaml and registry.json, then run the model's documented "
                                "training command manually. This export never uploads or starts training.\n")
            else:
                instructions = ("# Google Colab training\n\nUpload and extract this package in Colab. "
                                "The dataset is arranged as images/{train,validation,test}/{class}/. "
                                "Load registry.json to preserve the exact task label identity. "
                                "This export never uploads or starts training.\n")
            (staging / "COLAB_README.md").write_text(instructions, encoding="utf-8")
            metadata = {"schema_version": 1, "package_type": "yolo" if version["task"] in TASK_YOLO else "cnn",
                        "dataset": version["dataset_name"], "dataset_version": int(version["version_number"]),
                        "dataset_version_id": int(version_id), "model_id": version["model_id"],
                        "task": version["task"], "registry_id": version["registry_id"],
                        "registry_version": version["registry_version"], "bundle_source": "TrainingDatasetStudio",
                        "registry_sha256": registry["sha256"],
                        "training_bundle": (dict(training_bundle) if training_bundle else None),
                        "created_at": datetime.now(timezone.utc).isoformat(), "records": records_meta,
                        "validation": {"passed": True,
                        "included_record_count": len(records_meta), "source_grouped_splits": True}}
            (staging / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                                                     encoding="utf-8")
            (staging / "run_training.py").write_text(
                "from pathlib import Path\n"
                "import argparse, json\n"
                "def main():\n"
                "    p=argparse.ArgumentParser(description='NewAssetApp Colab package entry point')\n"
                "    p.add_argument('--drive-root',default='/content/drive/MyDrive')\n"
                "    p.add_argument('--dry-run',action='store_true')\n"
                "    a=p.parse_args()\n"
                "    manifest=Path('package_manifest.json')\n"
                "    print(json.dumps({'drive_root':a.drive_root,'package_manifest':json.loads(manifest.read_text()) if manifest.exists() else None,'dry_run':a.dry_run},indent=2))\n"
                "    if not a.dry_run:\n"
                "        raise SystemExit('Select a model-specific real training entry point after validation; this package defaults to dry-run-safe inspection.')\n"
                "if __name__=='__main__': main()\n",
                encoding="utf-8")
            hash_manifest = {
                path.relative_to(staging).as_posix():
                {"sha256": sha256_file(path), "bytes": path.stat().st_size}
                for path in sorted(staging.rglob("*")) if path.is_file()
            }
            (staging / "hash_manifest.json").write_text(
                json.dumps({"schema_version": 1, "files": hash_manifest},
                           ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            package_files = {
                path.relative_to(staging).as_posix():
                {"sha256": sha256_file(path), "bytes": path.stat().st_size}
                for path in sorted(staging.rglob("*")) if path.is_file()
            }
            package_manifest = {
                "schema_version": 1,
                "package_type": metadata["package_type"],
                "dataset_version_id": int(version_id),
                "dataset_version": int(version["version_number"]),
                "model_id": version["model_id"],
                "task": version["task"],
                "registry_id": version["registry_id"],
                "registry_version": version["registry_version"],
                "registry_sha256": registry["sha256"],
                "rar_minimum_bytes": 4_000_000_000,
                "rar_status": "blocked_until_valid_rar_writer_and_4gb_archive",
                "training_entry": "run_training.py",
                "results_root": "training_results",
                "files": package_files,
            }
            (staging / "package_manifest.json").write_text(
                json.dumps(package_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(staging, destination)
            return {"path": str(destination), "records": len(records_meta),
                    "package_type": metadata["package_type"]}
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def export_shared_cnn_colab(self, version_ids: dict[str, int], destination: Path | str) -> dict:
        """Combine finalized task versions into one task-aware five-head package."""
        from .shared_training import (HEADS, MODEL_ID, PREPROCESSING, REGISTRY_ID,
                                     validate_shared_dataset)
        task_by_head = {"body_images": "body_images_classification",
                        "fullbody": "fullbody_state_classification",
                        "portrait": "portrait_classification", "arousal": "arousal_classification",
                        "corruption": "corruption_classification"}
        if set(version_ids) != set(HEADS):
            raise DatasetError("Select one finalized dataset version for each of the five shared CNN heads.")
        destination = Path(destination).resolve()
        if destination.exists():
            raise DatasetError("Output directory already exists; package export never overwrites a prior package.")
        versions, rows_by_head, registry_data = {}, {}, None
        with self.store.connect() as db:
            for head in HEADS:
                version_id = int(version_ids[head])
                version = db.execute("""SELECT dv.*,d.task,d.registry_id,d.registry_version,d.name dataset_name
                                    FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id WHERE dv.id=?""",
                                     (version_id,)).fetchone()
                if (not version or not version["finalized"] or version["task"] != task_by_head[head]
                        or version["registry_id"] != REGISTRY_ID):
                    raise DatasetError(f"The {head} version must be finalized for its exact shared-model task.")
                if versions and (version["registry_version"] != versions[HEADS[0]]["registry_version"]):
                    raise DatasetError("All five task versions must use the same shared registry version.")
                versions[head] = dict(version)
                rows_by_head[head] = [row for row in self.store.version_rows(version_id) if row["included"]]
                if not rows_by_head[head]:
                    raise DatasetError(f"The {head} version has no included training records.")
            registry = db.execute("SELECT payload_json,sha256 FROM registries WHERE registry_id=? AND version=? "
                                  "ORDER BY id DESC LIMIT 1",
                                  (REGISTRY_ID, versions[HEADS[0]]["registry_version"])).fetchone()
        if not registry:
            raise DatasetError("The exact shared CNN task registry was not imported.")
        registry_data = json.loads(registry["payload_json"])
        split_by_source: dict[str, str] = {}
        for head in HEADS:
            for row in rows_by_head[head]:
                split = row["split"]
                if split not in SPLITS or row["status"] != "accepted" or not row["human_confirmed"] or not row["training_eligible"]:
                    raise DatasetError(f"The {head} version contains an unaccepted or unassigned record.")
                source = row["source_sha256"]
                if source in split_by_source and split_by_source[source] != split:
                    raise DatasetError("A source photo would leak across shared CNN head splits.")
                split_by_source[source] = split
        staging = Path(tempfile.mkdtemp(prefix=".shared_cnn_package_", dir=destination.parent))
        try:
            mappings = {head: [{"class_id": int(item["class_id"]), "class_name": item["class_name"]}
                               for item in registry_data["output_groups"][head]["classes"]]
                        for head in HEADS}
            records, file_rows = [], {}
            for head in HEADS:
                for row in rows_by_head[head]:
                    source = Path(row["media_path"])
                    original = row.get("original_json") or {}
                    if isinstance(original, str):
                        original = json.loads(original or "{}")
                    media_info = original.get("media") or {}
                    media_role = str(media_info.get("role") or "")
                    media_hash = str(media_info.get("sha256") or "").casefold()
                    if (media_role == "authoritative_detection_crop"
                            and str(media_info.get("source_sha256") or "").casefold()
                            != str(row["source_sha256"] or "").casefold()):
                        raise DatasetError(f"Source provenance changed for Studio record {row['record_id']}.")
                    expected_hash = media_hash if media_role == "authoritative_detection_crop" else str(row["source_sha256"] or "").casefold()
                    if not source.is_file() or sha256_file(source).casefold() != expected_hash:
                        raise DatasetError(f"Source media changed for Studio record {row['record_id']}.")
                    annotation = row["annotation_snapshot"]
                    label = str(annotation.get("class_label") or row["class_label"] or "")
                    structured = (annotation.get("labels") or {}).get("structured") or {}
                    target = annotation.get("target_class_id", row["target_class_id"])
                    target_mask = (annotation.get("body_images_target_mask")
                                   or structured.get("body_images_target_mask"))
                    if head == "body_images" and isinstance(target_mask, dict):
                        for name in ("cum", "accessory"):
                            state = target_mask.get(name)
                            if (not isinstance(state, dict) or set(("target","evaluated")) - set(state)
                                    or state["evaluated"] not in {True, False}
                                    or (state["evaluated"] and state["target"] not in {True, False})
                                    or (not state["evaluated"] and state["target"] is not None)):
                                raise DatasetError("The Body Images target mask is malformed.")
                    else:
                        mapping = next((item for item in mappings[head] if item["class_name"] == label), None)
                        if not mapping or target is None or int(target) != mapping["class_id"]:
                            raise DatasetError(f"The {head} target does not match its authoritative class registry.")
                    box = annotation.get("bbox_xyxy")
                    if not isinstance(box, (list, tuple)) or len(box) != 4:
                        raise DatasetError(f"The {head} record has no valid current crop geometry.")
                    try:
                        with Image.open(source) as original:
                            values = [float(value) for value in box]
                            width = int(row["source_width"] or 0)
                            height = int(row["source_height"] or 0)
                            if not (0 <= values[0] < values[2] <= width
                                    and 0 <= values[1] < values[3] <= height):
                                raise DatasetError(f"The {head} crop lies outside its source image.")
                            rgb = original.convert("RGB")
                            crop = (rgb.copy() if media_role == "authoritative_detection_crop"
                                    else rgb.crop(tuple(round(value) for value in values)))
                            relative = Path("images") / row["split"] / head / f"{row['source_sha256'][:16]}_{row['record_id']}.jpg"
                            target_path = staging / relative
                            target_path.parent.mkdir(parents=True, exist_ok=True)
                            crop.save(target_path, "JPEG", quality=95)
                            crop.close()
                            rgb.close()
                    except DatasetError:
                        raise
                    except Exception as error:
                        raise DatasetError(f"Could not decode/crop the {head} source image.") from error
                    digest = sha256_file(target_path)
                    file_rows[relative.as_posix()] = {"sha256": digest, "bytes": target_path.stat().st_size}
                    records.append({"record_id": str(row["record_id"]), "task_head": head,
                                    "class_label": label,
                                    "target_class_id": (int(target) if target is not None else None),
                                    "source_sha256": row["source_sha256"], "split": row["split"],
                                    "image_path": relative.as_posix(), "sha256": digest,
                                    "human_confirmed": True, "training_eligible": True,
                                    "human_confirmed_labels": structured.get("human_confirmed_labels", []),
                                    **({"body_images_target_mask": target_mask}
                                       if head == "body_images" and isinstance(target_mask, dict) else {})})
            package = {"schema_version": 1, "model_id": MODEL_ID, "registry_id": REGISTRY_ID,
                       "registry_version": versions[HEADS[0]]["registry_version"], "heads": list(HEADS),
                       "class_mappings": mappings,
                       "dataset_provenance": {head: {"dataset": versions[head]["dataset_name"],
                           "version": int(versions[head]["version_number"]),
                           "dataset_version_id": int(versions[head]["id"])} for head in HEADS},
                       "input_size": [224, 224], "preprocessing": PREPROCESSING, "records": records}
            (staging / "shared_dataset.json").write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (staging / "registry.json").write_text(json.dumps(registry_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (staging / "dataset_files.json").write_text(json.dumps(file_rows, indent=2) + "\n", encoding="utf-8")
            trainer_dir = Path(__file__).resolve().parent
            shutil.copy2(trainer_dir / "shared_training.py", staging / "shared_training.py")
            shutil.copy2(trainer_dir / "shared_train.py", staging / "shared_train.py")
            (staging / "train_shared_cnn.py").write_text(
                "from pathlib import Path\nimport argparse\nfrom shared_train import run_shared_training\n"
                "p=argparse.ArgumentParser(); p.add_argument('--epochs',type=int,default=5); "
                "p.add_argument('--batch-size',type=int,default=8); p.add_argument('--learning-rate',type=float,default=.0003); "
                "a=p.parse_args(); run_shared_training(Path('.'),Path('training_output'),Path('cancel.request'), "
                "{'epochs':a.epochs,'batch_size':a.batch_size,'learning_rate':a.learning_rate},dry_run=False)\n",
                encoding="utf-8")
            validation = validate_shared_dataset(staging, registry_data)
            (staging / "COLAB_README.md").write_text(
                "# Shared five-head CNN training\n\n"
                "This package contains one shared ResNet-18 backbone with five task heads. "
                "It has not started training. In Colab, install PyTorch, torchvision and Pillow, "
                "then run `python train_shared_cnn.py --epochs 5`. The script writes a complete "
                "checkpoint under `training_output/shared_cnn.pth`; review its per-head metrics "
                "and provenance before preparing a NewAssetApp model artifact.\n",
                encoding="utf-8")
            package_manifest = {"schema_version": 1, "package_type": "shared_five_head_cnn",
                                "model_id": MODEL_ID, "registry_id": REGISTRY_ID,
                                "registry_version": package["registry_version"], "records": len(records),
                                "dataset_version_ids": {
                                    head: int(versions[head]["id"]) for head in HEADS},
                                "registry_sha256": registry["sha256"],
                                "validation": validation,
                                "files": {path.relative_to(staging).as_posix():
                                          {"sha256": sha256_file(path), "bytes": path.stat().st_size}
                                          for path in sorted(staging.rglob("*")) if path.is_file()}}
            (staging / "package_manifest.json").write_text(json.dumps(package_manifest, indent=2) + "\n", encoding="utf-8")
            os.replace(staging, destination)
            return {"path": str(destination), "records": len(records), "heads": list(HEADS),
                    "package_type": "shared_five_head_cnn", "validation": validation}
        finally:
            if staging.exists():
                shutil.rmtree(staging)

