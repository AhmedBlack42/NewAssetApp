from __future__ import annotations

import json
import hashlib
import math
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA_VERSION = 4
TRAINING_BUNDLE_MAX_BYTES = 5_000_000_000
SHARED_CNN_TASKS = {"body_images_classification", "fullbody_state_classification",
                    "portrait_classification", "arousal_classification", "corruption_classification"}


class StudioStore:
    def __init__(self, path: Path | str,
                 training_bundle_max_bytes: int = TRAINING_BUNDLE_MAX_BYTES):
        self.path = Path(path).resolve()
        if int(training_bundle_max_bytes) != TRAINING_BUNDLE_MAX_BYTES:
            raise ValueError("Training segments are capped at exactly 5,000,000,000 bytes.")
        self.training_bundle_max_bytes = TRAINING_BUNDLE_MAX_BYTES

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
              CREATE TABLE IF NOT EXISTS studio_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS bundles(
                id INTEGER PRIMARY KEY, bundle_id TEXT NOT NULL, schema_version INTEGER NOT NULL,
                bundle_sha256 TEXT NOT NULL UNIQUE, source_path TEXT NOT NULL,
                manifest_json TEXT NOT NULL, imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
              CREATE TABLE IF NOT EXISTS registries(
                id INTEGER PRIMARY KEY, bundle_id INTEGER NOT NULL REFERENCES bundles(id) ON DELETE CASCADE,
                registry_id TEXT NOT NULL, version TEXT NOT NULL, sha256 TEXT NOT NULL,
                relative_path TEXT NOT NULL, payload_json TEXT NOT NULL,
                UNIQUE(bundle_id,registry_id,version));
              CREATE TABLE IF NOT EXISTS records(
                id INTEGER PRIMARY KEY, bundle_id INTEGER NOT NULL REFERENCES bundles(id) ON DELETE CASCADE,
                external_id TEXT NOT NULL, task TEXT NOT NULL, model_id TEXT, registry_id TEXT,
                registry_version TEXT, class_label TEXT, target_class_id INTEGER,
                status TEXT NOT NULL CHECK(status IN ('accepted','warning','quarantined','rejected')),
                reason TEXT, source_image_id TEXT, source_sha256 TEXT, source_width INTEGER,
                source_height INTEGER, media_path TEXT, original_json TEXT NOT NULL,
                annotation_json TEXT NOT NULL, human_confirmed INTEGER NOT NULL DEFAULT 0,
                training_eligible INTEGER NOT NULL DEFAULT 0, rejected_reason TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(bundle_id,external_id));
              CREATE INDEX IF NOT EXISTS idx_records_task_status ON records(task,status);
              CREATE INDEX IF NOT EXISTS idx_records_source ON records(source_sha256);
              CREATE TABLE IF NOT EXISTS annotation_events(
                id INTEGER PRIMARY KEY, record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
                event_type TEXT NOT NULL, before_json TEXT, after_json TEXT NOT NULL,
                note TEXT, occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
              CREATE TABLE IF NOT EXISTS training_bundles(
                id INTEGER PRIMARY KEY, bundle_key TEXT NOT NULL UNIQUE, task TEXT NOT NULL,
                model_id TEXT, registry_id TEXT NOT NULL, registry_version TEXT NOT NULL,
                bundle_number INTEGER NOT NULL, capacity INTEGER NOT NULL,
                record_count INTEGER NOT NULL DEFAULT 0,
                state TEXT NOT NULL CHECK(state IN ('open','full')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(task,model_id,registry_id,registry_version,bundle_number));
              CREATE TABLE IF NOT EXISTS training_bundle_records(
                training_bundle_id INTEGER NOT NULL REFERENCES training_bundles(id),
                record_id INTEGER NOT NULL UNIQUE REFERENCES records(id),
                assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(training_bundle_id,record_id));
              CREATE TABLE IF NOT EXISTS datasets(
                id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, task TEXT NOT NULL,
                registry_id TEXT NOT NULL, registry_version TEXT NOT NULL,
                training_bundle_id INTEGER REFERENCES training_bundles(id), model_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
              CREATE TABLE IF NOT EXISTS dataset_versions(
                id INTEGER PRIMARY KEY, dataset_id INTEGER NOT NULL REFERENCES datasets(id),
                version_number INTEGER NOT NULL, seed INTEGER NOT NULL,
                ratios_json TEXT NOT NULL, snapshot_json TEXT NOT NULL,
                finalized INTEGER NOT NULL DEFAULT 0, finalized_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(dataset_id,version_number));
              CREATE TABLE IF NOT EXISTS dataset_version_records(
                version_id INTEGER NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
                record_id INTEGER NOT NULL REFERENCES records(id), split TEXT,
                included INTEGER NOT NULL DEFAULT 1, exclusion_reason TEXT,
                annotation_snapshot_json TEXT NOT NULL,
                PRIMARY KEY(version_id,record_id));
              CREATE TABLE IF NOT EXISTS training_runs(
                id INTEGER PRIMARY KEY, run_key TEXT NOT NULL UNIQUE,
                version_id INTEGER NOT NULL REFERENCES dataset_versions(id),
                model_id TEXT NOT NULL, checkpoint_path TEXT, device TEXT NOT NULL CHECK(device='cpu'),
                params_json TEXT NOT NULL, output_dir TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL, log_path TEXT NOT NULL, metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at TEXT);
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(datasets)")}
            if "training_bundle_id" not in columns:
                db.execute("ALTER TABLE datasets ADD COLUMN training_bundle_id INTEGER REFERENCES training_bundles(id)")
            if "model_id" not in columns:
                db.execute("ALTER TABLE datasets ADD COLUMN model_id TEXT")
            db.execute(
                """UPDATE datasets SET model_id=(
                     SELECT tb.model_id FROM training_bundles tb
                     WHERE tb.id=datasets.training_bundle_id)
                   WHERE model_id IS NULL AND training_bundle_id IS NOT NULL"""
            )
            record_columns = {row["name"] for row in db.execute("PRAGMA table_info(records)")}
            if "source_project_id" not in record_columns:
                db.execute("ALTER TABLE records ADD COLUMN source_project_id TEXT")
            bundle_columns = {row["name"] for row in db.execute("PRAGMA table_info(training_bundles)")}
            if "size_bytes" not in bundle_columns:
                db.execute("ALTER TABLE training_bundles ADD COLUMN size_bytes INTEGER NOT NULL DEFAULT 0")
            if "max_bytes" not in bundle_columns:
                db.execute("ALTER TABLE training_bundles ADD COLUMN max_bytes INTEGER NOT NULL DEFAULT 5000000000")
            membership_columns = {row["name"] for row in db.execute("PRAGMA table_info(training_bundle_records)")}
            if "record_bytes" not in membership_columns:
                db.execute("ALTER TABLE training_bundle_records ADD COLUMN record_bytes INTEGER NOT NULL DEFAULT 0")
            if "training_identity" not in membership_columns:
                db.execute("ALTER TABLE training_bundle_records ADD COLUMN training_identity TEXT")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_training_bundle_identity "
                       "ON training_bundle_records(training_bundle_id,training_identity) "
                       "WHERE training_identity IS NOT NULL")
            db.execute("""CREATE TABLE IF NOT EXISTS training_identity_conflicts(
                          training_identity TEXT PRIMARY KEY,
                          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            # Backfill old segment size estimates from immutable record and media payloads.
            for membership in db.execute("""SELECT tbr.training_bundle_id,tbr.record_id,r.media_path,
                                                  r.annotation_json,r.original_json
                                           FROM training_bundle_records tbr JOIN records r ON r.id=tbr.record_id
                                           WHERE tbr.record_bytes=0""").fetchall():
                media_bytes = Path(membership["media_path"]).stat().st_size if membership["media_path"] and Path(membership["media_path"]).is_file() else 0
                record_bytes = media_bytes + len(membership["annotation_json"].encode("utf-8")) + len(membership["original_json"].encode("utf-8"))
                db.execute("UPDATE training_bundle_records SET record_bytes=? WHERE training_bundle_id=? AND record_id=?",
                           (record_bytes, membership["training_bundle_id"], membership["record_id"]))
                db.execute("UPDATE training_bundles SET size_bytes=size_bytes+? WHERE id=?",
                           (record_bytes, membership["training_bundle_id"]))
            db.execute("INSERT OR REPLACE INTO studio_meta(key,value) VALUES('schema_version',?)",
                       (str(SCHEMA_VERSION),))

    def list_records(self, *, task: str | None = None, status: str | None = None) -> list[dict]:
        clauses, args = [], []
        if task and task != "all":
            clauses.append("task=?"); args.append(task)
        if status and status != "all":
            clauses.append("status=?"); args.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect() as db:
            scoped_where = where.replace("task=", "r.task=").replace("status=", "r.status=")
            rows = db.execute("SELECT r.*,tb.id training_bundle_id,tb.bundle_key training_bundle_key,"
                              "tb.record_count training_bundle_record_count,tb.capacity training_bundle_capacity,"
                              "tb.size_bytes training_bundle_size_bytes,tb.max_bytes training_bundle_max_bytes "
                              "FROM records r LEFT JOIN training_bundle_records tbr ON tbr.record_id=r.id "
                              "LEFT JOIN training_bundles tb ON tb.id=tbr.training_bundle_id" + scoped_where +
                              " ORDER BY r.task,r.external_id", args).fetchall()
        return [self._decode_record(row) for row in rows]

    def get_record(self, record_id: int) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT r.*,tb.id training_bundle_id,tb.bundle_key training_bundle_key,"
                             "tb.record_count training_bundle_record_count,tb.capacity training_bundle_capacity,"
                             "tb.size_bytes training_bundle_size_bytes,tb.max_bytes training_bundle_max_bytes "
                             "FROM records r LEFT JOIN training_bundle_records tbr ON tbr.record_id=r.id "
                             "LEFT JOIN training_bundles tb ON tb.id=tbr.training_bundle_id WHERE r.id=?",
                             (int(record_id),)).fetchone()
        return self._decode_record(row) if row else None

    @staticmethod
    def _decode_record(row) -> dict:
        value = dict(row)
        value["original"] = json.loads(value.pop("original_json"))
        value["annotation"] = json.loads(value.pop("annotation_json"))
        return value

    def save_annotation(self, record_id: int, annotation: dict, *, confirm: bool | None = None,
                        reject_reason: str | None = None, note: str = "") -> None:
        with self.connect() as db:
            row = db.execute("SELECT annotation_json,status FROM records WHERE id=?", (record_id,)).fetchone()
            if not row:
                raise ValueError("Record no longer exists.")
            before = json.loads(row["annotation_json"])
            status = row["status"]
            if reject_reason is not None:
                status = "rejected"
            elif confirm is True:
                status = "accepted"
            elif status == "accepted":
                status = "warning"
            db.execute("""UPDATE records SET annotation_json=?,status=?,reason=?,rejected_reason=?,
                         human_confirmed=?,training_eligible=?,task=COALESCE(?,task),
                         model_id=COALESCE(?,model_id),registry_id=COALESCE(?,registry_id),
                         registry_version=COALESCE(?,registry_version),class_label=COALESCE(?,class_label),
                         target_class_id=COALESCE(?,target_class_id),updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                       (json.dumps(annotation, sort_keys=True), status,
                        reject_reason or ("Human review required" if status == "warning" else None),
                        reject_reason, int(confirm is True), int(confirm is True and not reject_reason),
                        annotation.get("task"), annotation.get("model_id"), annotation.get("registry_id"),
                        annotation.get("registry_version"), annotation.get("class_label"),
                        annotation.get("target_class_id"), record_id))
            db.execute("""INSERT INTO annotation_events(record_id,event_type,before_json,after_json,note)
                         VALUES(?,?,?,?,?)""",
                       (record_id, "rejected" if reject_reason else "confirmed" if confirm else "edited",
                        json.dumps(before, sort_keys=True), json.dumps(annotation, sort_keys=True), note))
            current = db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
            self._assign_training_bundle(db, current)

    @staticmethod
    def _assign_training_bundle(db: sqlite3.Connection, record,
                                max_bytes: int = TRAINING_BUNDLE_MAX_BYTES) -> int | None:
        """Enroll complete task records in a shared, byte-capped task segment."""
        existing = db.execute("SELECT tb.*,tbr.record_bytes AS existing_record_bytes FROM training_bundle_records tbr JOIN training_bundles tb "
                              "ON tb.id=tbr.training_bundle_id WHERE tbr.record_id=?",
                              (int(record["id"]),)).fetchone()

        def remove_existing_membership() -> None:
            if not existing:
                return
            db.execute("DELETE FROM training_bundle_records WHERE record_id=?",
                       (int(record["id"]),))
            new_size = max(0, int(existing["size_bytes"])
                           - int(existing["existing_record_bytes"] or 0))
            db.execute(
                """UPDATE training_bundles SET record_count=MAX(0,record_count-1),
                   size_bytes=?,state=? WHERE id=?""",
                (new_size, "open" if new_size < int(existing["max_bytes"]) else "full",
                 int(existing["id"])),
            )

        if not record["human_confirmed"] or not record["training_eligible"] or record["status"] != "accepted":
            remove_existing_membership()
            return None
        task = str(record["task"])
        bundle_task = "shared_cnn" if task in SHARED_CNN_TASKS else task
        label = str(record["class_label"] or "").strip()
        registry_id = str(record["registry_id"] or "").strip()
        registry_version = str(record["registry_version"] or "").strip()
        model_id = str(record["model_id"] or "")
        try:
            annotation = json.loads(record["annotation_json"])
            empty_yolo = (task in {"yolo_detection", "yolo_detector"}
                          and annotation.get("empty_image") is True
                          and label == "__empty__"
                          and annotation.get("target_class_id") is None)
            box = ([] if empty_yolo else
                   [float(value) for value in annotation.get("bbox_xyxy", [])])
        except (ValueError, TypeError, json.JSONDecodeError):
            remove_existing_membership()
            return None
        width, height = int(record["source_width"] or 0), int(record["source_height"] or 0)
        if (not label or not registry_id or not registry_version or not record["source_sha256"]
                or (not empty_yolo and len(box) != 4)
                or not all(math.isfinite(value) for value in box)
                or (not empty_yolo and not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height))
                or width <= 0 or height <= 0):
            remove_existing_membership()
            return None
        registry_row = db.execute("SELECT payload_json FROM registries WHERE registry_id=? AND version=? "
                                  "ORDER BY id DESC LIMIT 1", (registry_id, registry_version)).fetchone()
        if not registry_row:
            remove_existing_membership()
            return None
        registry = json.loads(registry_row["payload_json"])
        labels = annotation.get("labels") or {}
        output_group = (labels.get("structured") or {}).get("output_group")
        if task in {"yolo_detection", "yolo_detector"}:
            cls = (None if empty_yolo else next((item for item in registry.get("classes", []) if item.get("name") == label), None))
            expected_id = cls.get("id") if cls else None
        elif task in {"body_images_classification", "fullbody_state_classification", "asset_classification",
                      "portrait_classification", "arousal_classification", "corruption_classification"}:
            group = registry.get("output_groups", {}).get(output_group or "", {})
            cls = next((item for item in group.get("classes", []) if item.get("class_name") == label), None)
            expected_id = cls.get("class_id") if cls else None
        elif task in {"broad_clothing_classification", "corruption_state_classification"}:
            cls = next((item for item in registry.get("classes", []) if item.get("class_name") == label
                        and item.get("active", True)), None)
            expected_id = cls.get("class_id") if cls else None
        elif task == "detailed_clothing_classification":
            cls = next((item for item in registry.get("entries", [])
                        if item.get("serialized_value") == label and item.get("selectable")
                        and not item.get("requires_review")), None)
            expected_id = cls.get("class_id") if cls else None
        else:
            remove_existing_membership()
            return None
        target_id = annotation.get("target_class_id")
        if target_id is None:
            target_id = record["target_class_id"]
        body_images_multi_label = (
            task == "body_images_classification"
            and label in {"body_images_multi_label", "body_images_none", "body_images_pending"}
            and isinstance(annotation.get("body_images_target_mask"), dict)
        )
        if body_images_multi_label:
            cls = {"class_name": label}
            expected_id = None
        if ((cls is None and not empty_yolo)
                or (empty_yolo and (task not in {"yolo_detection", "yolo_detector"}
                    or annotation.get("labels", {}).get("structured", {}).get("no_objects") is not True))
                or (expected_id is not None and
                    (target_id is None or int(target_id) != int(expected_id)))):
            remove_existing_membership()
            return None
        if task in {"yolo_detection", "yolo_detector"}:
            opposite = db.execute("""SELECT r.id FROM training_bundle_records tbr
                                   JOIN records r ON r.id=tbr.record_id
                                   WHERE r.source_sha256=? AND r.task IN ('yolo_detection','yolo_detector')
                                   AND COALESCE(json_extract(r.annotation_json,'$.empty_image'),0)<>?
                                   LIMIT 1""", (record["source_sha256"], int(empty_yolo))).fetchone()
            if opposite:
                remove_existing_membership()
                return None
        structured = labels.get("structured") or {}
        task_head = (annotation.get("task_head") or annotation.get("head")
                     or structured.get("output_group"))
        identity_value = {"task": task, "task_head": task_head, "model_id": model_id,
                          "registry_id": registry_id, "registry_version": registry_version,
                          "source_sha256": record["source_sha256"], "bbox_xyxy": box,
                          "empty_image": empty_yolo}
        identity = hashlib.sha256(json.dumps(identity_value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        target_mask = (annotation.get("body_images_target_mask")
                       or structured.get("body_images_target_mask")
                       or annotation.get("target_mask"))
        target_identity = {"class_label": label, "target_class_id": target_id,
                           "target_mask": target_mask}
        prior_conflict = db.execute(
            "SELECT 1 FROM training_identity_conflicts WHERE training_identity=?",
            (identity,),
        ).fetchone()
        if prior_conflict:
            remove_existing_membership()
            db.execute(
                """UPDATE records SET status='warning',
                   reason='conflicting_task_annotation_identity',training_eligible=0,
                   updated_at=CURRENT_TIMESTAMP WHERE id=?""", (int(record["id"]),)
            )
            return None
        matches = db.execute(
            """SELECT r.id,r.class_label,r.target_class_id,r.annotation_json,
                      tbr.training_bundle_id
               FROM training_bundle_records tbr
               JOIN records r ON r.id=tbr.record_id
               WHERE tbr.training_identity=? AND tbr.record_id<>?""",
            (identity, int(record["id"])),
        ).fetchall()
        if matches:
            exact_duplicate = False
            conflict = False
            for match in matches:
                prior = json.loads(match["annotation_json"] or "{}")
                prior_labels = prior.get("labels") or {}
                prior_structured = prior_labels.get("structured") or {}
                prior_target_mask = (prior.get("body_images_target_mask")
                                     or prior_structured.get("body_images_target_mask")
                                     or prior.get("target_mask"))
                prior_target = {"class_label": match["class_label"],
                                "target_class_id": (prior.get("target_class_id")
                                                    if prior.get("target_class_id") is not None
                                                    else match["target_class_id"]),
                                "target_mask": prior_target_mask}
                if prior_target == target_identity:
                    exact_duplicate = True
                else:
                    conflict = True
            if conflict:
                db.execute(
                    "INSERT OR IGNORE INTO training_identity_conflicts(training_identity) VALUES(?)",
                    (identity,),
                )
                affected_ids = {int(match["id"]) for match in matches}
                affected_ids.add(int(record["id"]))
                for record_id in affected_ids:
                    membership = db.execute(
                        """SELECT tbr.training_bundle_id,tbr.record_bytes,tb.max_bytes,
                                  tb.size_bytes
                           FROM training_bundle_records tbr
                           JOIN training_bundles tb ON tb.id=tbr.training_bundle_id
                           WHERE tbr.record_id=?""", (record_id,)
                    ).fetchone()
                    if membership:
                        db.execute("DELETE FROM training_bundle_records WHERE record_id=?",
                                   (record_id,))
                        new_size = max(0, int(membership["size_bytes"])
                                       - int(membership["record_bytes"] or 0))
                        db.execute(
                            """UPDATE training_bundles SET record_count=MAX(0,record_count-1),
                               size_bytes=?,state=? WHERE id=?""",
                            (new_size, "open" if new_size < int(membership["max_bytes"]) else "full",
                             int(membership["training_bundle_id"])),
                        )
                    db.execute(
                        """UPDATE records SET status='warning',
                           reason='conflicting_task_annotation_identity',training_eligible=0,
                           updated_at=CURRENT_TIMESTAMP WHERE id=?""", (record_id,)
                    )
                return None
            if exact_duplicate:
                remove_existing_membership()
                db.execute(
                    """UPDATE records SET status='warning',reason='duplicate_task_content_identity',
                       training_eligible=0,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (int(record["id"]),),
                )
                return int(matches[0]["training_bundle_id"])

        media_path = Path(record["media_path"]) if record["media_path"] else None
        if not media_path or not media_path.is_file():
            remove_existing_membership()
            return None
        media_bytes = media_path.stat().st_size
        record_bytes = media_bytes + len(record["annotation_json"].encode("utf-8")) + len(record["original_json"].encode("utf-8"))
        if record_bytes > max_bytes:
            raise ValueError(f"Complete training record is {record_bytes} bytes, over the 5,000,000,000-byte segment cap.")
        if existing and (existing["task"], existing["model_id"] or "", existing["registry_id"],
                         existing["registry_version"]) == (bundle_task, model_id, registry_id, registry_version):
            old_record_bytes = int(existing["existing_record_bytes"] or 0)
            updated_size = int(existing["size_bytes"]) - old_record_bytes + record_bytes
            if updated_size <= int(existing["max_bytes"]):
                db.execute(
                    """UPDATE training_bundle_records SET record_bytes=?,training_identity=?
                       WHERE training_bundle_id=? AND record_id=?""",
                    (record_bytes, identity, int(existing["id"]), int(record["id"])),
                )
                db.execute(
                    "UPDATE training_bundles SET size_bytes=?,state=? WHERE id=?",
                    (updated_size,
                     "full" if updated_size >= int(existing["max_bytes"]) else "open",
                     int(existing["id"])),
                )
                return int(existing["id"])
        if existing:
            db.execute("DELETE FROM training_bundle_records WHERE record_id=?", (int(record["id"]),))
            db.execute("UPDATE training_bundles SET record_count=MAX(0,record_count-1),"
                       "size_bytes=MAX(0,size_bytes-?),"
                       "state=CASE WHEN size_bytes-? < max_bytes THEN 'open' ELSE 'full' END WHERE id=?",
                       (int(existing["existing_record_bytes"] or 0), int(existing["existing_record_bytes"] or 0), int(existing["id"])))
        pool_key = (bundle_task, model_id or None, registry_id, registry_version)
        bundle = db.execute("""SELECT * FROM training_bundles WHERE task=? AND model_id IS ?
                            AND registry_id=? AND registry_version=? AND max_bytes=?
                            AND size_bytes<=max_bytes-?
                            ORDER BY bundle_number DESC LIMIT 1""",
                            (*pool_key, int(max_bytes), record_bytes)).fetchone()
        if not bundle:
            number = int(db.execute("""SELECT COALESCE(MAX(bundle_number),0)+1 FROM training_bundles
                                   WHERE task=? AND model_id IS ? AND registry_id=? AND registry_version=?""",
                                    pool_key).fetchone()[0])
            series_key = hashlib.sha256(json.dumps(
                [model_id, registry_id, registry_version],
                separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")).hexdigest()
            key = f"{bundle_task}:{series_key}:batch{number:04d}"
            cursor = db.execute("""INSERT INTO training_bundles(bundle_key,task,model_id,registry_id,
                                 registry_version,bundle_number,capacity,record_count,state,max_bytes)
                                 VALUES(?,?,?,?,?,?,0,0,'open',?)""",
                                (key, bundle_task, model_id or None, registry_id, registry_version,
                                 number, int(max_bytes)))
            bundle_id, count = int(cursor.lastrowid), 0
        else:
            bundle_id, count = int(bundle["id"]), int(bundle["record_count"])
        db.execute("""INSERT INTO training_bundle_records(training_bundle_id,record_id,record_bytes,training_identity)
                     VALUES(?,?,?,?)""", (bundle_id, int(record["id"]), record_bytes, identity))
        count += 1
        size = int(db.execute("SELECT size_bytes FROM training_bundles WHERE id=?", (bundle_id,)).fetchone()[0]) + record_bytes
        db.execute("UPDATE training_bundles SET record_count=?,size_bytes=?,state=? WHERE id=?",
                   (count, size, "full" if size >= max_bytes else "open", bundle_id))
        return bundle_id

    def list_training_bundles(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM training_bundles ORDER BY task,registry_id,bundle_number").fetchall()
        return [dict(row) for row in rows]

    def annotation_history(self, record_id: int) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM annotation_events WHERE record_id=? ORDER BY id DESC",
                              (int(record_id),)).fetchall()
        return [dict(row) for row in rows]

    def list_datasets(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM datasets ORDER BY name")]

    def list_versions(self, dataset_id: int | None = None) -> list[dict]:
        with self.connect() as db:
            if dataset_id is None:
                rows = db.execute("SELECT * FROM dataset_versions ORDER BY id DESC").fetchall()
            else:
                rows = db.execute("SELECT * FROM dataset_versions WHERE dataset_id=? ORDER BY version_number DESC",
                                  (int(dataset_id),)).fetchall()
        return [dict(row) for row in rows]

    def version_rows(self, version_id: int) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("""SELECT dvr.*,r.task,r.class_label,r.target_class_id,r.media_path,
                                      r.source_sha256,r.source_width,r.source_height,r.original_json,r.annotation_json,
                                      r.status,r.reason,r.human_confirmed,r.training_eligible
                               FROM dataset_version_records dvr JOIN records r ON r.id=dvr.record_id
                               WHERE dvr.version_id=? ORDER BY dvr.record_id""", (int(version_id),)).fetchall()
        values = []
        for row in rows:
            value = dict(row)
            value["annotation_snapshot"] = json.loads(value.pop("annotation_snapshot_json"))
            value["annotation"] = json.loads(value.pop("annotation_json"))
            values.append(value)
        return values

