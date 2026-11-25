from __future__ import annotations

import sqlite3
import json
import math
import hashlib
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


SCHEMA_VERSION = 25


def _source_integrity_reason(path: str | Path, expected_sha256: str) -> str | None:
    source = Path(path)
    if not source.is_file():
        return "source_image_missing"
    digest = hashlib.sha256()
    try:
        with source.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return "source_image_unreadable"
    if digest.hexdigest().casefold() != str(expected_sha256 or "").casefold():
        return "source_hash_mismatch"
    return None


def _normalize_body_images_decisions(payload: dict, legacy_target: str | None = None) -> dict:
    """Return a complete two-output Body Images decision and loss mask."""
    if any(key in payload for key in (
            "cum_target", "cum_evaluated", "accessory_target",
            "accessory_evaluated", "body_images_completed")):
        cum_target = payload.get("cum_target")
        accessory_target = payload.get("accessory_target")
        cum_evaluated = bool(payload.get("cum_evaluated"))
        accessory_evaluated = bool(payload.get("accessory_evaluated"))
        completed = bool(payload.get("body_images_completed"))
        if cum_evaluated and cum_target not in {0, 1, False, True}:
            raise ValueError("Cum target must be true or false when evaluated.")
        if accessory_evaluated and accessory_target not in {0, 1, False, True}:
            raise ValueError("Accessory target must be true or false when evaluated.")
        if not cum_evaluated and cum_target is not None:
            raise ValueError("An unevaluated Cum target must remain pending.")
        if not accessory_evaluated and accessory_target is not None:
            raise ValueError("An unevaluated Accessory target must remain pending.")
        if completed and not (cum_evaluated and accessory_evaluated):
            raise ValueError("Completed none or multi-label decisions require both binary targets.")
        return {
            "cum_target": bool(cum_target) if cum_evaluated else None,
            "cum_evaluated": cum_evaluated,
            "accessory_target": bool(accessory_target) if accessory_evaluated else None,
            "accessory_evaluated": accessory_evaluated,
            "completed": completed,
            "target_mask": {
                "cum": {"target": bool(cum_target) if cum_evaluated else None,
                        "evaluated": cum_evaluated},
                "accessory": {"target": bool(accessory_target) if accessory_evaluated else None,
                              "evaluated": accessory_evaluated},
            },
        }
    if legacy_target in {"bodypart_cum", "bodypart_acc"}:
        cum_positive = legacy_target == "bodypart_cum"
        accessory_positive = legacy_target == "bodypart_acc"
        return {
            "cum_target": True if cum_positive else None,
            "cum_evaluated": cum_positive,
            "accessory_target": True if accessory_positive else None,
            "accessory_evaluated": accessory_positive,
            "completed": False,
            "target_mask": {
                "cum": {"target": True if cum_positive else None,
                        "evaluated": cum_positive},
                "accessory": {"target": True if accessory_positive else None,
                              "evaluated": accessory_positive},
            },
        }
    return {
        "cum_target": None,
        "cum_evaluated": False,
        "accessory_target": None,
        "accessory_evaluated": False,
        "completed": False,
        "target_mask": {
            "cum": {"target": None, "evaluated": False},
            "accessory": {"target": None, "evaluated": False},
        },
    }


MIGRATIONS = {
    1: """
    CREATE TABLE source_images (
        id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE,
        content_sha256 TEXT NOT NULL, width INTEGER, height INTEGER,
        file_size INTEGER NOT NULL, modified_ns INTEGER NOT NULL,
        scan_status TEXT NOT NULL DEFAULT 'indexed',
        duplicate_of_id INTEGER REFERENCES source_images(id),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_source_hash ON source_images(content_sha256);
    CREATE TABLE yolo_detections (
        id INTEGER PRIMARY KEY,
        source_image_id INTEGER NOT NULL REFERENCES source_images(id) ON DELETE CASCADE,
        model_id TEXT, model_digest TEXT, class_id INTEGER, class_name TEXT NOT NULL,
        confidence REAL, x1 REAL NOT NULL, y1 REAL NOT NULL, x2 REAL NOT NULL,
        y2 REAL NOT NULL, coordinate_space TEXT NOT NULL DEFAULT 'source_pixels',
        status TEXT NOT NULL DEFAULT 'original', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_detection_source ON yolo_detections(source_image_id);
    CREATE TABLE cnn_predictions (
        id INTEGER PRIMARY KEY,
        detection_id INTEGER NOT NULL REFERENCES yolo_detections(id) ON DELETE CASCADE,
        model_id TEXT, model_digest TEXT, class_name TEXT, confidence REAL,
        probabilities_json TEXT, status TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE asset_proposals (
        id INTEGER PRIMARY KEY,
        source_image_id INTEGER NOT NULL REFERENCES source_images(id) ON DELETE CASCADE,
        detection_id INTEGER REFERENCES yolo_detections(id) ON DELETE SET NULL,
        prediction_id INTEGER REFERENCES cnn_predictions(id) ON DELETE SET NULL,
        asset_type TEXT,
        category TEXT NOT NULL CHECK(category IN ('fullbody','body_images','clothing','others')),
        confidence REAL, review_status TEXT NOT NULL DEFAULT 'pending',
        corrected_bbox_json TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_proposal_category ON asset_proposals(category, review_status);
    CREATE TABLE user_decisions (
        id INTEGER PRIMARY KEY,
        proposal_id INTEGER NOT NULL REFERENCES asset_proposals(id) ON DELETE CASCADE,
        decision TEXT NOT NULL CHECK(decision IN
          ('accepted','edited','reclassified','rejected','moved_to_others')),
        original_label TEXT, corrected_label TEXT, original_bbox_json TEXT,
        corrected_bbox_json TEXT, notes TEXT, human_confirmed INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE processing_jobs (
        id INTEGER PRIMARY KEY,
        proposal_id INTEGER REFERENCES asset_proposals(id) ON DELETE CASCADE,
        stage TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
        progress REAL NOT NULL DEFAULT 0, input_json TEXT, output_json TEXT,
        error_text TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE final_assets (
        id INTEGER PRIMARY KEY,
        proposal_id INTEGER NOT NULL REFERENCES asset_proposals(id) ON DELETE CASCADE,
        output_path TEXT NOT NULL UNIQUE, width INTEGER, height INTEGER, format TEXT,
        has_alpha INTEGER, processing_json TEXT,
        validation_status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE training_records (
        id INTEGER PRIMARY KEY,
        proposal_id INTEGER NOT NULL REFERENCES asset_proposals(id) ON DELETE CASCADE,
        task TEXT NOT NULL CHECK(task IN ('yolo','asset_cnn')),
        source_decision_id INTEGER REFERENCES user_decisions(id) ON DELETE SET NULL,
        export_version TEXT, include_in_export INTEGER NOT NULL DEFAULT 0,
        record_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE photoshoot_groups (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE photoshoot_memberships (
        group_id INTEGER NOT NULL REFERENCES photoshoot_groups(id) ON DELETE CASCADE,
        proposal_id INTEGER NOT NULL REFERENCES asset_proposals(id) ON DELETE CASCADE,
        added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(group_id, proposal_id)
    );
    """,
    2: """
    ALTER TABLE source_images ADD COLUMN source_root TEXT;
    ALTER TABLE source_images ADD COLUMN content_changed_at TEXT;
    CREATE TABLE correction_records (
        id INTEGER PRIMARY KEY,
        proposal_id INTEGER REFERENCES asset_proposals(id) ON DELETE SET NULL,
        source_image_id INTEGER NOT NULL REFERENCES source_images(id) ON DELETE CASCADE,
        source_path TEXT NOT NULL,
        source_sha256 TEXT NOT NULL,
        detection_id INTEGER REFERENCES yolo_detections(id) ON DELETE SET NULL,
        original_snapshot_json TEXT NOT NULL,
        corrected_payload_json TEXT NOT NULL,
        decision_type TEXT NOT NULL CHECK(decision_type IN
          ('confirmed_prediction','corrected','bbox_corrected','reclassified','rejected','manual_annotation','tag_added')),
        final_state TEXT NOT NULL,
        user_changed_prediction INTEGER NOT NULL,
        human_confirmed INTEGER NOT NULL DEFAULT 1,
        yolo_training_eligible INTEGER NOT NULL DEFAULT 0,
        cnn_training_eligible INTEGER NOT NULL DEFAULT 0,
        clothing_cnn_training_eligible INTEGER NOT NULL DEFAULT 0,
        model_version TEXT,
        taxonomy_version TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_correction_source ON correction_records(source_image_id, created_at);
    CREATE INDEX idx_correction_training ON correction_records(human_confirmed, yolo_training_eligible, cnn_training_eligible);
    CREATE TABLE dataset_split_assignments (
        dataset_family TEXT NOT NULL,
        source_sha256 TEXT NOT NULL,
        split TEXT NOT NULL CHECK(split IN ('train','val','test')),
        seed INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(dataset_family, source_sha256)
    );
    """,
    3: """
    ALTER TABLE asset_proposals ADD COLUMN fullbody_output_category TEXT
      CHECK(fullbody_output_category IS NULL OR fullbody_output_category IN
        ('fullbody','fullbody_topless','fullbody_bottomless'));
    CREATE TABLE source_image_versions (
      id INTEGER PRIMARY KEY,
      source_image_id INTEGER NOT NULL REFERENCES source_images(id) ON DELETE CASCADE,
      path TEXT NOT NULL, content_sha256 TEXT NOT NULL, width INTEGER, height INTEGER,
      file_size INTEGER NOT NULL, modified_ns INTEGER NOT NULL,
      superseded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(source_image_id, content_sha256)
    );
    """,
    4: """
    ALTER TABLE source_images ADD COLUMN inference_status TEXT NOT NULL DEFAULT 'pending';
    ALTER TABLE source_images ADD COLUMN inference_hash TEXT;
    """,
    5: """
    ALTER TABLE asset_proposals ADD COLUMN proposed_tags_json TEXT;
    CREATE TABLE tag_change_records (
      id INTEGER PRIMARY KEY,
      action TEXT NOT NULL CHECK(action IN ('add','edit','deprecate')),
      tag_id TEXT NOT NULL,
      source_image_id INTEGER REFERENCES source_images(id) ON DELETE SET NULL,
      source_path TEXT,
      source_sha256 TEXT,
      before_json TEXT,
      after_json TEXT NOT NULL,
      taxonomy_version TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    6: """
    ALTER TABLE correction_records ADD COLUMN unified_cnn_training_eligible INTEGER NOT NULL DEFAULT 0;
    CREATE INDEX idx_correction_unified_training ON correction_records(human_confirmed, unified_cnn_training_eligible);
    """,
    7: """
    ALTER TABLE correction_records ADD COLUMN broad_clothing_training_eligible INTEGER NOT NULL DEFAULT 0;
    CREATE INDEX idx_correction_broad_clothing_training ON correction_records(human_confirmed, broad_clothing_training_eligible);
    """,
    8: """
    CREATE TABLE classification_review_records (
      id INTEGER PRIMARY KEY,
      detection_id INTEGER NOT NULL REFERENCES yolo_detections(id) ON DELETE CASCADE,
      source_image_id INTEGER NOT NULL REFERENCES source_images(id) ON DELETE CASCADE,
      task TEXT NOT NULL CHECK(task IN ('fullbody_state','body_images','clothing_family')),
      prediction_snapshot_json TEXT,
      reviewed_label TEXT NOT NULL,
      event_type TEXT NOT NULL CHECK(event_type IN ('edited','confirmed','invalidated')),
      note TEXT,
      human_confirmed INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_classification_review_latest
      ON classification_review_records(detection_id, task, id DESC);
    """,
    9: """
    CREATE TABLE normal_crop_choices (
      proposal_id INTEGER PRIMARY KEY REFERENCES asset_proposals(id) ON DELETE CASCADE,
      source_image_id INTEGER NOT NULL REFERENCES source_images(id) ON DELETE CASCADE,
      category TEXT NOT NULL CHECK(category IN ('fullbody','body_images','clothing')),
      body_image_main_tag TEXT,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_normal_crop_choices_category ON normal_crop_choices(category);
    CREATE TABLE normal_crop_exports (
      id INTEGER PRIMARY KEY,
      proposal_id INTEGER NOT NULL REFERENCES asset_proposals(id) ON DELETE CASCADE,
      source_image_id INTEGER NOT NULL REFERENCES source_images(id) ON DELETE CASCADE,
      source_sha256 TEXT NOT NULL,
      output_path TEXT NOT NULL UNIQUE,
      category TEXT NOT NULL CHECK(category IN ('fullbody','body_images','clothing')),
      width INTEGER NOT NULL,
      height INTEGER NOT NULL,
      format TEXT NOT NULL DEFAULT 'webp',
      processing_json TEXT NOT NULL,
      exported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_normal_crop_exports_source ON normal_crop_exports(source_image_id, exported_at);
    """,
    10: """
    ALTER TABLE normal_crop_choices ADD COLUMN main_tag TEXT;
    ALTER TABLE normal_crop_choices ADD COLUMN fullbody_state TEXT;
    ALTER TABLE normal_crop_choices ADD COLUMN subtags_json TEXT NOT NULL DEFAULT '[]';
    ALTER TABLE normal_crop_choices ADD COLUMN location_value TEXT;
    ALTER TABLE normal_crop_choices ADD COLUMN taxonomy_version TEXT;
    ALTER TABLE normal_crop_exports ADD COLUMN export_manifest_json TEXT;
    CREATE TABLE structured_classifications (
      id INTEGER PRIMARY KEY,
      source_image_id INTEGER NOT NULL REFERENCES source_images(id) ON DELETE CASCADE,
      proposal_id INTEGER REFERENCES asset_proposals(id) ON DELETE SET NULL,
      detection_id INTEGER REFERENCES yolo_detections(id) ON DELETE SET NULL,
      task TEXT NOT NULL CHECK(task IN ('fullbody','body_images','clothing','others')),
      record_type TEXT NOT NULL CHECK(record_type IN ('detection_crop','manual_crop','source_image')),
      main_category TEXT,
      fullbody_state TEXT CHECK(fullbody_state IS NULL OR fullbody_state IN ('clothed','topless','bottomless')),
      clothing_family TEXT,
      subtags_json TEXT NOT NULL DEFAULT '[]',
      corruption_values_json TEXT NOT NULL DEFAULT '[]',
      location_value TEXT,
      location_suggestions_json TEXT NOT NULL DEFAULT '[]',
      validity_state TEXT NOT NULL DEFAULT 'unresolved'
        CHECK(validity_state IN ('valid','invalid','unresolved')),
      ai_suggestion_json TEXT,
      human_review_state TEXT NOT NULL DEFAULT 'candidate'
        CHECK(human_review_state IN ('candidate','edited_unconfirmed','confirmed','rejected')),
      human_confirmed INTEGER NOT NULL DEFAULT 0 CHECK(human_confirmed IN (0,1)),
      training_eligible INTEGER NOT NULL DEFAULT 0 CHECK(training_eligible IN (0,1)),
      exclusion_reason TEXT,
      registry_id TEXT NOT NULL,
      taxonomy_version TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE UNIQUE INDEX uq_structured_classification_proposal_task
      ON structured_classifications(proposal_id, task) WHERE proposal_id IS NOT NULL;
    CREATE UNIQUE INDEX uq_structured_classification_detection_task
      ON structured_classifications(detection_id, task)
      WHERE detection_id IS NOT NULL AND proposal_id IS NULL;
    CREATE INDEX idx_structured_classification_review
      ON structured_classifications(task, human_review_state, training_eligible);
    CREATE TABLE structured_classification_events (
      id INTEGER PRIMARY KEY,
      classification_id INTEGER NOT NULL REFERENCES structured_classifications(id) ON DELETE CASCADE,
      event_type TEXT NOT NULL CHECK(event_type IN ('created','edited','confirmed','rejected','eligibility_changed')),
      before_json TEXT,
      after_json TEXT NOT NULL,
      actor TEXT NOT NULL DEFAULT 'local_user',
      occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_structured_classification_events
      ON structured_classification_events(classification_id, id DESC);
    """,
    11: """
    ALTER TABLE normal_crop_choices ADD COLUMN clothing_broad_family TEXT;
    CREATE TABLE training_examples (
      id INTEGER PRIMARY KEY,
      source_image_id INTEGER NOT NULL REFERENCES source_images(id) ON DELETE CASCADE,
      proposal_id INTEGER NOT NULL REFERENCES asset_proposals(id) ON DELETE CASCADE,
      detection_id INTEGER REFERENCES yolo_detections(id) ON DELETE SET NULL,
      supersedes_id INTEGER REFERENCES training_examples(id) ON DELETE RESTRICT,
      source_sha256 TEXT NOT NULL,
      crop_bbox_json TEXT NOT NULL,
      task TEXT NOT NULL CHECK(task IN ('yolo_detector','unified_body_images_fullbody','clothing_broad','clothing_fine')),
      class_label TEXT NOT NULL,
      taxonomy_id TEXT NOT NULL,
      taxonomy_version TEXT NOT NULL,
      suggestion_provenance_json TEXT NOT NULL,
      workflow TEXT NOT NULL CHECK(workflow IN ('normal_processing','professional_review')),
      human_confirmed INTEGER NOT NULL CHECK(human_confirmed=1),
      training_eligible INTEGER NOT NULL CHECK(training_eligible=1),
      confirmed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_training_examples_latest
      ON training_examples(proposal_id, task, id DESC);
    CREATE INDEX idx_training_examples_source
      ON training_examples(source_sha256, task);
    CREATE TABLE normal_crop_export_attempts (
      id INTEGER PRIMARY KEY,
      proposal_id INTEGER NOT NULL REFERENCES asset_proposals(id) ON DELETE CASCADE,
      source_sha256 TEXT NOT NULL,
      status TEXT NOT NULL CHECK(status IN ('exported','failed')),
      output_path TEXT,
      message TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_normal_crop_export_attempts_latest
      ON normal_crop_export_attempts(proposal_id,source_sha256,id DESC);
    """,
    12: """
    ALTER TABLE normal_crop_choices ADD COLUMN clothing_cover_area TEXT;
    """,
    13: """
    DROP INDEX idx_correction_source;
    DROP INDEX idx_correction_training;
    DROP INDEX idx_correction_unified_training;
    DROP INDEX idx_correction_broad_clothing_training;
    ALTER TABLE correction_records RENAME TO correction_records_v12;
    CREATE TABLE correction_records (
      id INTEGER PRIMARY KEY,
      proposal_id INTEGER REFERENCES asset_proposals(id) ON DELETE SET NULL,
      source_image_id INTEGER NOT NULL REFERENCES source_images(id) ON DELETE CASCADE,
      source_path TEXT NOT NULL,
      source_sha256 TEXT NOT NULL,
      detection_id INTEGER REFERENCES yolo_detections(id) ON DELETE SET NULL,
      original_snapshot_json TEXT NOT NULL,
      corrected_payload_json TEXT NOT NULL,
      decision_type TEXT NOT NULL CHECK(decision_type IN
        ('confirmed_prediction','annotation_confirmation','classification_confirmation','corrected',
         'bbox_corrected','reclassified','rejected','manual_annotation','tag_added')),
      final_state TEXT NOT NULL,
      user_changed_prediction INTEGER NOT NULL,
      human_confirmed INTEGER NOT NULL DEFAULT 1,
      yolo_training_eligible INTEGER NOT NULL DEFAULT 0,
      cnn_training_eligible INTEGER NOT NULL DEFAULT 0,
      clothing_cnn_training_eligible INTEGER NOT NULL DEFAULT 0,
      model_version TEXT,
      taxonomy_version TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      unified_cnn_training_eligible INTEGER NOT NULL DEFAULT 0,
      broad_clothing_training_eligible INTEGER NOT NULL DEFAULT 0,
      corruption_training_eligible INTEGER NOT NULL DEFAULT 0
    );
    INSERT INTO correction_records
      (id,proposal_id,source_image_id,source_path,source_sha256,detection_id,
       original_snapshot_json,corrected_payload_json,decision_type,final_state,
       user_changed_prediction,human_confirmed,yolo_training_eligible,cnn_training_eligible,
       clothing_cnn_training_eligible,model_version,taxonomy_version,created_at,
       unified_cnn_training_eligible,broad_clothing_training_eligible,corruption_training_eligible)
    SELECT id,proposal_id,source_image_id,source_path,source_sha256,detection_id,
       original_snapshot_json,corrected_payload_json,decision_type,
       final_state,user_changed_prediction,human_confirmed,yolo_training_eligible,cnn_training_eligible,
       clothing_cnn_training_eligible,model_version,taxonomy_version,created_at,
       unified_cnn_training_eligible,broad_clothing_training_eligible,0
    FROM correction_records_v12;
    DROP TABLE correction_records_v12;
    CREATE INDEX idx_correction_source ON correction_records(source_image_id, created_at);
    CREATE INDEX idx_correction_training ON correction_records(human_confirmed, yolo_training_eligible, cnn_training_eligible);
    CREATE INDEX idx_correction_unified_training ON correction_records(human_confirmed, unified_cnn_training_eligible);
    CREATE INDEX idx_correction_broad_clothing_training ON correction_records(human_confirmed, broad_clothing_training_eligible);
    UPDATE asset_proposals
       SET category='others', asset_type='person',
           review_status=CASE WHEN review_status='unclassified_fullbody' THEN 'review_required'
                              ELSE review_status END,
           fullbody_output_category=NULL, updated_at=CURRENT_TIMESTAMP
     WHERE category='fullbody'
       AND detection_id IN (SELECT id FROM yolo_detections WHERE class_id=0 AND class_name='person')
       AND review_status IN ('unclassified_fullbody','review_required','pending')
       AND NOT EXISTS(SELECT 1 FROM correction_records cr WHERE cr.proposal_id=asset_proposals.id)
       AND NOT EXISTS(SELECT 1 FROM normal_crop_choices nc WHERE nc.proposal_id=asset_proposals.id);
    CREATE TABLE corruption_training_examples (
      id INTEGER PRIMARY KEY,
      source_image_id INTEGER NOT NULL REFERENCES source_images(id) ON DELETE CASCADE,
      proposal_id INTEGER NOT NULL REFERENCES asset_proposals(id) ON DELETE CASCADE,
      detection_id INTEGER REFERENCES yolo_detections(id) ON DELETE SET NULL,
      correction_record_id INTEGER NOT NULL REFERENCES correction_records(id) ON DELETE CASCADE,
      supersedes_id INTEGER REFERENCES corruption_training_examples(id) ON DELETE RESTRICT,
      source_sha256 TEXT NOT NULL,
      crop_bbox_json TEXT NOT NULL,
      task TEXT NOT NULL CHECK(task='corruption_state'),
      class_label TEXT NOT NULL CHECK(class_label IN ('slut','conservative','whore','u_whore')),
      model_id TEXT NOT NULL,
      taxonomy_id TEXT NOT NULL,
      taxonomy_version TEXT NOT NULL,
      suggestion_provenance_json TEXT NOT NULL,
      workflow TEXT NOT NULL CHECK(workflow='professional_review'),
      human_confirmed INTEGER NOT NULL CHECK(human_confirmed=1),
      training_eligible INTEGER NOT NULL CHECK(training_eligible=1),
      confirmed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_corruption_training_latest
      ON corruption_training_examples(proposal_id, id DESC);
    CREATE INDEX idx_corruption_training_source
      ON corruption_training_examples(source_sha256);
    """,
    14: """
    ALTER TABLE training_examples ADD COLUMN correction_record_id INTEGER
      REFERENCES correction_records(id) ON DELETE SET NULL;
    CREATE INDEX idx_training_examples_correction
      ON training_examples(correction_record_id);
    -- Keep historical decisions intact while preventing stale, unconfirmed flags
    -- from being mistaken for valid training eligibility.
    UPDATE correction_records
       SET yolo_training_eligible=0,
           cnn_training_eligible=0,
           clothing_cnn_training_eligible=0,
           unified_cnn_training_eligible=0,
           broad_clothing_training_eligible=0,
           corruption_training_eligible=0
     WHERE human_confirmed<>1 OR final_state='rejected';
    """,
    15: """
    -- Low-confidence portrait CNN suggestions still belong in Body Images; their
    -- review state remains review_required and no label is human-confirmed here.
    UPDATE asset_proposals
       SET category='body_images',
           asset_type=CASE
             WHEN prediction_id IN (SELECT id FROM cnn_predictions
                                    WHERE class_name='bodypart_portrait_clothed') THEN 'portrait'
             WHEN prediction_id IN (SELECT id FROM cnn_predictions
                                    WHERE class_name='bodypart_portrait_topless') THEN 'tportrait'
             ELSE asset_type END,
           review_status='review_required',
           updated_at=CURRENT_TIMESTAMP
     WHERE category='others'
       AND review_status IN ('pending','review_required')
       AND prediction_id IN (SELECT id FROM cnn_predictions
                             WHERE class_name IN ('bodypart_portrait_clothed',
                                                  'bodypart_portrait_topless'))
       AND NOT EXISTS(SELECT 1 FROM correction_records cr
                      WHERE cr.proposal_id=asset_proposals.id)
       AND NOT EXISTS(SELECT 1 FROM user_decisions ud
                      WHERE ud.proposal_id=asset_proposals.id)
       AND NOT EXISTS(SELECT 1 FROM normal_crop_choices nc
                      WHERE nc.proposal_id=asset_proposals.id)
       AND NOT EXISTS(SELECT 1 FROM structured_classifications sc
                      WHERE sc.proposal_id=asset_proposals.id)
       AND NOT EXISTS(SELECT 1 FROM classification_review_records rr
                      WHERE rr.detection_id=asset_proposals.detection_id);
    """,
    16: """
    -- A human-selected Normal Processing route is the proposal's displayed
    -- category too. Preserve professional-review decisions that already exist.
    UPDATE asset_proposals
       SET category=(SELECT nc.category FROM normal_crop_choices nc
                     WHERE nc.proposal_id=asset_proposals.id),
           asset_type=(SELECT COALESCE(nc.main_tag,nc.body_image_main_tag)
                       FROM normal_crop_choices nc WHERE nc.proposal_id=asset_proposals.id),
           fullbody_output_category=CASE
             WHEN (SELECT nc.category FROM normal_crop_choices nc
                   WHERE nc.proposal_id=asset_proposals.id)='fullbody'
              AND (SELECT nc.fullbody_state FROM normal_crop_choices nc
                   WHERE nc.proposal_id=asset_proposals.id)='topless' THEN 'fullbody_topless'
             WHEN (SELECT nc.category FROM normal_crop_choices nc
                   WHERE nc.proposal_id=asset_proposals.id)='fullbody'
              AND (SELECT nc.fullbody_state FROM normal_crop_choices nc
                   WHERE nc.proposal_id=asset_proposals.id)='bottomless' THEN 'fullbody_bottomless'
             WHEN (SELECT nc.category FROM normal_crop_choices nc
                   WHERE nc.proposal_id=asset_proposals.id)='fullbody' THEN 'fullbody'
             ELSE NULL END,
           updated_at=CURRENT_TIMESTAMP
     WHERE id IN (SELECT proposal_id FROM normal_crop_choices)
       AND category<>(SELECT nc.category FROM normal_crop_choices nc
                      WHERE nc.proposal_id=asset_proposals.id)
       AND NOT EXISTS(SELECT 1 FROM correction_records cr
                      WHERE cr.proposal_id=asset_proposals.id)
       AND NOT ((SELECT nc.category FROM normal_crop_choices nc
                 WHERE nc.proposal_id=asset_proposals.id)='fullbody'
                AND detection_id IN
                    (SELECT id FROM yolo_detections WHERE class_id=0 AND class_name='person'));
    """,
    17: """
    ALTER TABLE normal_crop_choices ADD COLUMN is_invalid INTEGER NOT NULL DEFAULT 0;
    CREATE TABLE normal_crop_invalidated_examples (
      proposal_id INTEGER NOT NULL REFERENCES asset_proposals(id) ON DELETE CASCADE,
      task TEXT NOT NULL,
      class_label TEXT NOT NULL,
      invalidated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(proposal_id, task, class_label)
    );
    UPDATE asset_proposals
       SET category='clothing', asset_type=NULL, updated_at=CURRENT_TIMESTAMP
     WHERE detection_id IN (SELECT id FROM yolo_detections WHERE class_id IN (8,9,10,11))
       AND NOT EXISTS(SELECT 1 FROM normal_crop_choices nc WHERE nc.proposal_id=asset_proposals.id)
       AND NOT EXISTS(SELECT 1 FROM correction_records cr WHERE cr.proposal_id=asset_proposals.id)
       AND NOT EXISTS(SELECT 1 FROM user_decisions ud WHERE ud.proposal_id=asset_proposals.id)
       AND NOT EXISTS(SELECT 1 FROM structured_classifications sc WHERE sc.proposal_id=asset_proposals.id);
    """,
    18: """
    -- Keep historical task values unchanged. New shared-backbone labels identify
    -- their output head separately, and exact human filename tags remain distinct.
    ALTER TABLE training_examples ADD COLUMN task_head TEXT;
    ALTER TABLE training_examples ADD COLUMN human_confirmed_labels_json TEXT NOT NULL DEFAULT '[]';
    CREATE INDEX idx_training_examples_head_source ON training_examples(task_head, source_sha256);
    ALTER TABLE normal_crop_choices ADD COLUMN body_images_cnn_target TEXT;
    ALTER TABLE normal_crop_choices ADD COLUMN fullbody_cnn_target TEXT;
    ALTER TABLE normal_crop_choices ADD COLUMN arousal_cnn_target TEXT;
    ALTER TABLE normal_crop_choices ADD COLUMN corruption_cnn_target TEXT;
    ALTER TABLE normal_crop_invalidated_examples ADD COLUMN task_head TEXT;
    """,
    19: """
    CREATE TABLE classification_task_reviews (
      id INTEGER PRIMARY KEY,
      proposal_id INTEGER NOT NULL REFERENCES asset_proposals(id) ON DELETE CASCADE,
      source_image_id INTEGER NOT NULL REFERENCES source_images(id) ON DELETE CASCADE,
      detection_id INTEGER NOT NULL REFERENCES yolo_detections(id) ON DELETE CASCADE,
      task_head TEXT NOT NULL CHECK(task_head IN
        ('body_images','fullbody','portrait','arousal','corruption','location','clothing_broad','clothing_fine')),
      target_label TEXT NOT NULL,
      suggestion_provenance_json TEXT NOT NULL DEFAULT '{}',
      source_sha256 TEXT NOT NULL,
      crop_bbox_json TEXT NOT NULL,
      bbox_revision INTEGER,
      registry_id TEXT NOT NULL,
      registry_version TEXT NOT NULL,
      workflow TEXT NOT NULL DEFAULT 'professional_review',
      confirmation_status TEXT NOT NULL CHECK(confirmation_status IN ('draft','confirmed','rejected','stale')),
      human_confirmed INTEGER NOT NULL DEFAULT 0 CHECK(human_confirmed IN (0,1)),
      training_eligible INTEGER NOT NULL DEFAULT 0 CHECK(training_eligible IN (0,1)),
      training_example_id INTEGER REFERENCES training_examples(id) ON DELETE SET NULL,
      supersedes_id INTEGER REFERENCES classification_task_reviews(id) ON DELETE SET NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_task_reviews_latest ON classification_task_reviews(detection_id,task_head,id DESC);
    CREATE TABLE training_example_suppressions (
      training_example_id INTEGER PRIMARY KEY REFERENCES training_examples(id) ON DELETE CASCADE,
      reason TEXT NOT NULL,
      task_review_id INTEGER REFERENCES classification_task_reviews(id) ON DELETE SET NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_task_review_source ON classification_task_reviews(source_sha256,task_head);
    """,
    20: """
    ALTER TABLE classification_task_reviews ADD COLUMN confirmed_at TEXT;
    ALTER TABLE classification_task_reviews ADD COLUMN staled_at TEXT;
    """,
    21: """
    CREATE TABLE yolo_bbox_reviews (
      id INTEGER PRIMARY KEY,
      detection_id INTEGER NOT NULL REFERENCES yolo_detections(id) ON DELETE CASCADE,
      proposal_id INTEGER REFERENCES asset_proposals(id) ON DELETE SET NULL,
      source_image_id INTEGER NOT NULL REFERENCES source_images(id) ON DELETE CASCADE,
      source_sha256 TEXT NOT NULL,
      original_bbox_xyxy TEXT NOT NULL,
      effective_bbox_xyxy TEXT NOT NULL,
      bbox_revision INTEGER,
      review_status TEXT NOT NULL CHECK(review_status IN ('approved','rejected','stale')),
      human_confirmed INTEGER NOT NULL CHECK(human_confirmed IN (0,1)),
      training_eligible INTEGER NOT NULL DEFAULT 0 CHECK(training_eligible IN (0,1)),
      training_example_id INTEGER REFERENCES training_examples(id) ON DELETE SET NULL,
      supersedes_id INTEGER REFERENCES yolo_bbox_reviews(id) ON DELETE SET NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      confirmed_at TEXT
    );
    CREATE INDEX idx_yolo_bbox_reviews_detection
      ON yolo_bbox_reviews(detection_id,id DESC);
    """,
    22: """
    CREATE TABLE IF NOT EXISTS training_examples (
      id INTEGER PRIMARY KEY
    );
    ALTER TABLE training_examples ADD COLUMN bbox_review_id INTEGER
      REFERENCES yolo_bbox_reviews(id) ON DELETE SET NULL;
    CREATE INDEX idx_training_examples_bbox_review
      ON training_examples(bbox_review_id);
    ALTER TABLE classification_task_reviews ADD COLUMN model_verified INTEGER NOT NULL DEFAULT 0
      CHECK(model_verified IN (0,1));
    ALTER TABLE classification_task_reviews ADD COLUMN model_confidence REAL;
    ALTER TABLE classification_task_reviews ADD COLUMN confidence_threshold REAL;
    ALTER TABLE classification_task_reviews ADD COLUMN model_verified_at TEXT;
    """,
    23: """
    CREATE TABLE active_detection_crops (
      detection_id INTEGER PRIMARY KEY REFERENCES yolo_detections(id) ON DELETE CASCADE,
      crop_id TEXT NOT NULL,
      source_sha256 TEXT NOT NULL,
      crop_sha256 TEXT,
      crop_path TEXT,
      bbox_xyxy TEXT NOT NULL,
      bbox_revision INTEGER,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      replaced_at TEXT
    );
    CREATE INDEX idx_active_detection_crops_hash
      ON active_detection_crops(crop_sha256);
    ALTER TABLE classification_task_reviews ADD COLUMN eligibility_registry_id TEXT;
    ALTER TABLE classification_task_reviews ADD COLUMN eligibility_registry_version TEXT;
    ALTER TABLE classification_task_reviews ADD COLUMN target_mask_json TEXT;
    ALTER TABLE classification_task_reviews ADD COLUMN cum_target INTEGER;
    ALTER TABLE classification_task_reviews ADD COLUMN cum_evaluated INTEGER NOT NULL DEFAULT 0
      CHECK(cum_evaluated IN (0,1));
    ALTER TABLE classification_task_reviews ADD COLUMN accessory_target INTEGER;
    ALTER TABLE classification_task_reviews ADD COLUMN accessory_evaluated INTEGER NOT NULL DEFAULT 0
      CHECK(accessory_evaluated IN (0,1));
    ALTER TABLE training_examples ADD COLUMN target_mask_json TEXT;
    ALTER TABLE training_examples ADD COLUMN eligibility_registry_id TEXT;
    ALTER TABLE training_examples ADD COLUMN eligibility_registry_version TEXT;
    """,
    24: """
    CREATE TABLE IF NOT EXISTS normal_crop_choices (
      proposal_id INTEGER PRIMARY KEY
    );
    ALTER TABLE normal_crop_choices ADD COLUMN body_images_cum_target INTEGER;
    ALTER TABLE normal_crop_choices ADD COLUMN body_images_cum_evaluated INTEGER NOT NULL DEFAULT 0
      CHECK(body_images_cum_evaluated IN (0,1));
    ALTER TABLE normal_crop_choices ADD COLUMN body_images_accessory_target INTEGER;
    ALTER TABLE normal_crop_choices ADD COLUMN body_images_accessory_evaluated INTEGER NOT NULL DEFAULT 0
      CHECK(body_images_accessory_evaluated IN (0,1));
    ALTER TABLE normal_crop_choices ADD COLUMN body_images_completed INTEGER NOT NULL DEFAULT 0
      CHECK(body_images_completed IN (0,1));
    """,
    25: """
    CREATE TABLE normal_processing_drafts (
      proposal_id INTEGER PRIMARY KEY REFERENCES asset_proposals(id) ON DELETE CASCADE,
      source_image_id INTEGER NOT NULL REFERENCES source_images(id) ON DELETE CASCADE,
      source_sha256 TEXT NOT NULL,
      detection_id INTEGER REFERENCES yolo_detections(id) ON DELETE SET NULL,
      bbox_revision INTEGER,
      crop_identity TEXT,
      category TEXT CHECK(category IN ('fullbody','body_images','clothing','invalid') OR category IS NULL),
      draft_json TEXT NOT NULL,
      schema_version INTEGER NOT NULL DEFAULT 1,
      taxonomy_version TEXT,
      stale_due_to_revision INTEGER NOT NULL DEFAULT 0 CHECK(stale_due_to_revision IN (0,1)),
      save_failed INTEGER NOT NULL DEFAULT 0 CHECK(save_failed IN (0,1)),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_normal_processing_drafts_source
      ON normal_processing_drafts(source_image_id,source_sha256);
    CREATE INDEX idx_normal_processing_drafts_updated
      ON normal_processing_drafts(updated_at);
    """,
}


class Database:
    """Versioned SQLite store. Connections are short-lived and thread-local."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    @staticmethod
    def _invalidate_task_reviews(connection, detection_id: int, bbox: list[float],
                                 bbox_revision: int, reason: str) -> None:
        rows = connection.execute(
            """SELECT r.* FROM classification_task_reviews r
               WHERE r.detection_id=? AND r.id=(SELECT MAX(latest.id) FROM classification_task_reviews latest
                 WHERE latest.detection_id=r.detection_id AND latest.task_head=r.task_head)
                 AND r.confirmation_status='confirmed' AND r.human_confirmed=1""",
            (int(detection_id),),
        ).fetchall()
        for row in rows:
            cursor = connection.execute(
                """INSERT INTO classification_task_reviews
                   (proposal_id,source_image_id,detection_id,task_head,target_label,suggestion_provenance_json,
                    source_sha256,crop_bbox_json,bbox_revision,registry_id,registry_version,confirmation_status,
                    human_confirmed,training_eligible,training_example_id,confirmed_at,staled_at,supersedes_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,'stale',0,0,?,?,CURRENT_TIMESTAMP,?)""",
                (row["proposal_id"], row["source_image_id"], int(detection_id), row["task_head"],
                 row["target_label"], row["suggestion_provenance_json"], row["source_sha256"],
                 json.dumps([float(value) for value in bbox]), int(bbox_revision), row["registry_id"],
                 row["registry_version"], row["training_example_id"], row["confirmed_at"], row["id"]),
            )
            if row["training_example_id"] is not None:
                connection.execute(
                    """INSERT OR IGNORE INTO training_example_suppressions
                       (training_example_id,reason,task_review_id) VALUES (?,?,?)""",
                    (row["training_example_id"], reason, int(cursor.lastrowid)),
                )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            current = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0]
            if current > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {current} is newer than app version {SCHEMA_VERSION}."
                )
            for version in range(current + 1, SCHEMA_VERSION + 1):
                script = MIGRATIONS.get(version)
                if script is None:
                    raise RuntimeError(f"Missing migration {version}.")
                try:
                    connection.executescript(
                        "BEGIN IMMEDIATE;\n" + script +
                        f"\nINSERT INTO schema_migrations(version, applied_at) "
                        f"VALUES ({version}, CURRENT_TIMESTAMP);\nCOMMIT;"
                    )
                except Exception:
                    connection.rollback()
                    raise

    def upsert_source_image(self, record: dict) -> tuple[int, int | None]:
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM source_images WHERE path=?", (record["path"],)
            ).fetchone()
            if existing:
                source_id = existing["id"]
                previous = connection.execute("SELECT content_sha256 FROM source_images WHERE id=?", (source_id,)).fetchone()
                if previous and previous["content_sha256"] != record["sha256"]:
                    connection.execute(
                        """INSERT OR IGNORE INTO source_image_versions
                           (source_image_id, path, content_sha256, width, height, file_size, modified_ns)
                           SELECT id, path, content_sha256, width, height, file_size, modified_ns
                           FROM source_images WHERE id=?""", (source_id,))
                    connection.execute("UPDATE yolo_detections SET status='stale_source_version' WHERE source_image_id=?",
                                       (source_id,))
                    connection.execute("UPDATE asset_proposals SET review_status='stale_source_version', updated_at=CURRENT_TIMESTAMP WHERE source_image_id=?",
                                       (source_id,))
                    connection.execute("UPDATE source_images SET inference_status='pending', inference_hash=NULL WHERE id=?",
                                       (source_id,))
                connection.execute(
                    """UPDATE source_images SET content_sha256=?, width=?, height=?,
                       file_size=?, modified_ns=?, source_root=COALESCE(?, source_root),
                       content_changed_at=CASE WHEN content_sha256<>? THEN CURRENT_TIMESTAMP ELSE content_changed_at END,
                       scan_status='indexed', duplicate_of_id=NULL
                       WHERE id=?""",
                    (record["sha256"], record.get("width"), record.get("height"),
                     record["file_size"], record["modified_ns"], record.get("source_root"),
                     record["sha256"], source_id),
                )
            else:
                cursor = connection.execute(
                    """INSERT INTO source_images
                       (path, content_sha256, width, height, file_size, modified_ns, source_root)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (record["path"], record["sha256"], record.get("width"),
                     record.get("height"), record["file_size"], record["modified_ns"], record.get("source_root")),
                )
                source_id = cursor.lastrowid
            duplicate = connection.execute(
                "SELECT id FROM source_images WHERE content_sha256=? AND id<>? ORDER BY id LIMIT 1",
                (record["sha256"], source_id),
            ).fetchone()
            duplicate_id = duplicate["id"] if duplicate else None
            connection.execute(
                "UPDATE source_images SET duplicate_of_id=? WHERE id=?",
                (duplicate_id, source_id),
            )
            return source_id, duplicate_id

    def source_images(self, folder: Path | str | None = None) -> list[sqlite3.Row]:
        with self.connect() as connection:
            if folder is None:
                return list(connection.execute("SELECT * FROM source_images ORDER BY path"))
            prefix = str(Path(folder).resolve())
            return list(connection.execute(
                "SELECT * FROM source_images WHERE path=? OR path LIKE ? ORDER BY path",
                (prefix, prefix.rstrip("\\/") + "\\%"),
            ))

    def detections_for_source(self, source_image_id: int) -> list[dict]:
        """Return every original YOLO box plus its latest reviewed geometry, if any."""
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT d.*, p.id AS proposal_id, p.category, p.review_status,
                          p.corrected_bbox_json,
                          (SELECT cr.corrected_payload_json FROM correction_records cr
                           WHERE cr.detection_id=d.id ORDER BY cr.id DESC LIMIT 1) AS latest_json
                   FROM yolo_detections d LEFT JOIN asset_proposals p ON p.detection_id=d.id
                   WHERE d.source_image_id=? ORDER BY d.id""", (source_image_id,)
            ).fetchall()
            task_rows = connection.execute(
                """SELECT r.* FROM classification_task_reviews r
                   WHERE r.source_image_id=? AND r.id=(SELECT MAX(latest.id) FROM classification_task_reviews latest
                     WHERE latest.detection_id=r.detection_id AND latest.task_head=r.task_head)""",
                (int(source_image_id),),
            ).fetchall()
        task_status_by_detection = {}
        for task_row in task_rows:
            task_status_by_detection.setdefault(int(task_row["detection_id"]), {})[
                task_row["task_head"]] = {
                    "label": task_row["target_label"], "status": task_row["confirmation_status"],
                "confirmation_status": task_row["confirmation_status"],
                    "human_confirmed": bool(task_row["human_confirmed"]),
                    "training_eligible": bool(task_row["training_eligible"]),
                    "cum_target": task_row["cum_target"],
                    "cum_evaluated": bool(task_row["cum_evaluated"]),
                    "accessory_target": task_row["accessory_target"],
                    "accessory_evaluated": bool(task_row["accessory_evaluated"]),
                    "target_mask": json.loads(task_row["target_mask_json"])
                    if task_row["target_mask_json"] else None,
                }
        result = []
        from app.core.yolo_registry import approved_yolo_classes
        class_names = approved_yolo_classes()
        for row in rows:
            box = [row["x1"], row["y1"], row["x2"], row["y2"]]
            edited = False
            class_name = row["class_name"]
            category = row["category"]
            annotation_class_id = annotation_class_name = None
            if row["corrected_bbox_json"]:
                box = json.loads(row["corrected_bbox_json"])
                edited = True
            if row["latest_json"]:
                latest = json.loads(row["latest_json"])
                annotation_class_id = latest.get("yolo_annotation_class_id")
                annotation_class_name = latest.get("yolo_annotation_class_name")
                class_name = (annotation_class_name or latest.get("class_name")
                              or class_names.get(latest.get("class_id"), class_name))
                category = latest.get("category", category)
                edited = (edited or latest.get("class_id") != row["class_id"]
                          or annotation_class_id is not None or bool(latest.get("category")))
            origin = "manual" if row["model_id"] == "user_manual" else "ai"
            if row["review_status"] == "rejected":
                origin = "rejected"
            result.append({"id": int(row["id"]), "proposal_id": row["proposal_id"],
                           "class_id": row["class_id"], "class_name": class_name,
                           "original_class_id": row["class_id"], "original_class_name": row["class_name"],
                           "annotation_class_id": annotation_class_id,
                           "annotation_class_name": annotation_class_name,
                           "confidence": row["confidence"], "bbox_xyxy": box,
                           "category": category,
                           "origin": origin,
                           "invalid_reason": (json.loads(row["latest_json"]).get("invalid_reason")
                                              if row["latest_json"] else None),
                           "classification_status": (task_status_by_detection.get(int(row["id"])) or
                                                      self._detection_classification_status(row["latest_json"])),
                           "edited": edited, "status": row["review_status"] or row["status"],
                           "model_id": row["model_id"], "model_digest": row["model_digest"]})
        return result

    @staticmethod
    def _detection_classification_status(latest_json: str | None) -> dict:
        latest = json.loads(latest_json) if latest_json else {}
        confirmed = set(latest.get("shared_cnn_training_tasks", []))
        values = {
            "body_images": latest.get("body_images_cnn_target"),
            "fullbody": latest.get("fullbody_cnn_target") or latest.get("state_spec"),
            "portrait": latest.get("portrait_cnn_target") or
                        (latest.get("main_tag") if latest.get("main_tag") in {"portrait", "tportrait"} else None),
            "arousal": latest.get("arousal_cnn_target"),
            "corruption": latest.get("corruption_classifier_target"),
        }
        return {head: {"label": label,
                       "status": "human_confirmed" if head in confirmed else "not_confirmed"}
                for head, label in values.items() if label}

    def invalidate_detection(self, detection_id: int, reason: str | None = None) -> int:
        """Reject one detection while preserving its proposal and immutable history."""
        with self.connect() as connection:
            detection = connection.execute(
                """SELECT d.*, s.path, s.content_sha256, p.id proposal_id, p.category,
                          p.review_status, p.corrected_bbox_json
                   FROM yolo_detections d JOIN source_images s ON s.id=d.source_image_id
                   LEFT JOIN asset_proposals p ON p.detection_id=d.id WHERE d.id=?""",
                (int(detection_id),),
            ).fetchone()
            if not detection:
                raise ValueError("Detection no longer exists.")
            if not detection["proposal_id"]:
                raise ValueError("This detection has no proposal record to review.")
            original = {"yolo": {key: detection[key] for key in
                                  ("class_id", "class_name", "confidence", "x1", "y1", "x2", "y2",
                                   "model_id", "model_digest")},
                        "proposal": {"id": detection["proposal_id"], "category": detection["category"],
                                     "review_status": detection["review_status"],
                                     "corrected_bbox_json": detection["corrected_bbox_json"]},
                        "source_path": detection["path"], "source_sha256": detection["content_sha256"]}
            payload = {"category": detection["category"], "bbox_xyxy": json.loads(detection["corrected_bbox_json"])
                       if detection["corrected_bbox_json"] else [detection[k] for k in ("x1", "y1", "x2", "y2")],
                       "invalid": True, "invalid_reason": (reason or "").strip() or None}
            cursor = connection.execute(
                """INSERT INTO correction_records
                   (proposal_id,source_image_id,source_path,source_sha256,detection_id,
                    original_snapshot_json,corrected_payload_json,decision_type,final_state,
                    user_changed_prediction,human_confirmed,taxonomy_version)
                   VALUES (?,?,?,?,?,?,?,'rejected','rejected',1,1,'newassetapp-phase9-review-v1')""",
                (detection["proposal_id"], detection["source_image_id"], detection["path"],
                 detection["content_sha256"], detection_id, json.dumps(original, sort_keys=True),
                 json.dumps(payload, sort_keys=True)),
            )
            connection.execute(
                "UPDATE asset_proposals SET review_status='rejected', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (detection["proposal_id"],),
            )
            connection.execute(
                """INSERT INTO user_decisions(proposal_id,decision,original_label,corrected_label,
                   original_bbox_json,corrected_bbox_json,notes,human_confirmed)
                   VALUES (?,'rejected',?,?,?, ?,?,1)""",
                (detection["proposal_id"], detection["category"], "invalid",
                 json.dumps([detection[k] for k in ("x1", "y1", "x2", "y2")]),
                 json.dumps(payload["bbox_xyxy"]), payload["invalid_reason"]),
            )
            return int(cursor.lastrowid)

    def restore_detection(self, detection_id: int) -> int:
        """Restore a rejected detection without deleting its invalidation event."""
        with self.connect() as connection:
            detection = connection.execute(
                """SELECT d.*, s.path, s.content_sha256, p.id proposal_id, p.category,
                          p.review_status, p.corrected_bbox_json
                   FROM yolo_detections d JOIN source_images s ON s.id=d.source_image_id
                   LEFT JOIN asset_proposals p ON p.detection_id=d.id WHERE d.id=?""",
                (int(detection_id),),
            ).fetchone()
            if not detection or not detection["proposal_id"]:
                raise ValueError("Detection proposal no longer exists.")
            if detection["review_status"] != "rejected":
                raise ValueError("Only an invalidated detection can be restored.")
            original = {"yolo": {key: detection[key] for key in
                                  ("class_id", "class_name", "confidence", "x1", "y1", "x2", "y2",
                                   "model_id", "model_digest")},
                        "proposal": {"id": detection["proposal_id"], "category": detection["category"],
                                     "review_status": detection["review_status"]},
                        "source_path": detection["path"], "source_sha256": detection["content_sha256"]}
            payload = {"category": detection["category"], "invalid": False,
                       "restored_from_invalid": True,
                       "bbox_xyxy": json.loads(detection["corrected_bbox_json"])
                       if detection["corrected_bbox_json"] else [detection[k] for k in ("x1", "y1", "x2", "y2")]}
            cursor = connection.execute(
                """INSERT INTO correction_records
                   (proposal_id,source_image_id,source_path,source_sha256,detection_id,
                    original_snapshot_json,corrected_payload_json,decision_type,final_state,
                    user_changed_prediction,human_confirmed,taxonomy_version)
                   VALUES (?,?,?,?,?,?,?,'corrected','corrected',1,1,'newassetapp-phase9-review-v1')""",
                (detection["proposal_id"], detection["source_image_id"], detection["path"],
                 detection["content_sha256"], detection_id, json.dumps(original, sort_keys=True),
                 json.dumps(payload, sort_keys=True)),
            )
            connection.execute(
                "UPDATE asset_proposals SET review_status='review_required', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (detection["proposal_id"],),
            )
            connection.execute(
                """INSERT INTO user_decisions(proposal_id,decision,original_label,corrected_label,
                   notes,human_confirmed) VALUES (?,'edited',?,'restored','Restored invalidated detection',1)""",
                (detection["proposal_id"], detection["category"]),
            )
            return int(cursor.lastrowid)

    def save_bbox_edit(self, detection_id: int, bbox_xyxy: list[float]) -> int:
        """Append a geometry correction without mutating the original detection snapshot."""
        if len(bbox_xyxy) != 4:
            raise ValueError("Edited box must contain four source-pixel coordinates.")
        x1, y1, x2, y2 = map(float, bbox_xyxy)
        with self.connect() as connection:
            detection = connection.execute(
                """SELECT d.*, s.path, s.content_sha256, s.width, s.height
                   FROM yolo_detections d JOIN source_images s ON s.id=d.source_image_id
                   WHERE d.id=?""", (detection_id,)
            ).fetchone()
            if not detection:
                raise ValueError("Detection no longer exists.")
            if not (0 <= x1 < x2 <= detection["width"] and 0 <= y1 < y2 <= detection["height"]):
                raise ValueError("Edited box must stay within source image coordinates.")
            proposal = connection.execute("SELECT * FROM asset_proposals WHERE detection_id=?", (detection_id,)).fetchone()
            original = {"yolo": {key: detection[key] for key in
                                  ("class_id", "class_name", "confidence", "x1", "y1", "x2", "y2",
                                   "model_id", "model_digest")},
                        "proposal": dict(proposal) if proposal else None,
                        "source_path": detection["path"], "source_sha256": detection["content_sha256"]}
            corrected = {"bbox_xyxy": [x1, y1, x2, y2], "class_id": detection["class_id"],
                         "class_name": detection["class_name"], "category": proposal["category"] if proposal else "others"}
            cursor = connection.execute(
                """INSERT INTO correction_records
                   (proposal_id, source_image_id, source_path, source_sha256, detection_id,
                    original_snapshot_json, corrected_payload_json, decision_type, final_state,
                    user_changed_prediction, human_confirmed, taxonomy_version)
                   VALUES (?,?,?,?,?,?,?,'bbox_corrected','corrected',1,0,'newassetapp-review-v1')""",
                (proposal["id"] if proposal else None, detection["source_image_id"], detection["path"],
                 detection["content_sha256"], detection_id, json.dumps(original, sort_keys=True),
                 json.dumps(corrected, sort_keys=True)),
            )
            if proposal:
                connection.execute("UPDATE asset_proposals SET corrected_bbox_json=?, review_status='review_required', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                                   (json.dumps([x1, y1, x2, y2]), proposal["id"]))
            latest_bbox_review = connection.execute(
                """SELECT * FROM yolo_bbox_reviews WHERE detection_id=? ORDER BY id DESC LIMIT 1""",
                (detection_id,),
            ).fetchone()
            if latest_bbox_review and latest_bbox_review["review_status"] == "approved":
                connection.execute(
                    """INSERT INTO yolo_bbox_reviews
                       (detection_id,proposal_id,source_image_id,source_sha256,
                        original_bbox_xyxy,effective_bbox_xyxy,bbox_revision,review_status,
                        human_confirmed,training_eligible,supersedes_id)
                       VALUES (?,?,?,?,?,?,?,?,0,0,?)""",
                    (int(detection_id), int(proposal["id"]) if proposal else None,
                     int(detection["source_image_id"]), detection["content_sha256"],
                     latest_bbox_review["original_bbox_xyxy"],
                     json.dumps([x1, y1, x2, y2]), int(cursor.lastrowid), "stale",
                     int(latest_bbox_review["id"])),
                )
            latest_confirmations = connection.execute(
                """SELECT task,reviewed_label,prediction_snapshot_json
                   FROM classification_review_records
                   WHERE detection_id=? AND event_type='confirmed'
                     AND id IN (SELECT MAX(id) FROM classification_review_records
                                WHERE detection_id=? GROUP BY task)""",
                (detection_id, detection_id),
            ).fetchall()
            for review in latest_confirmations:
                connection.execute(
                    """INSERT INTO classification_review_records
                       (detection_id,source_image_id,task,prediction_snapshot_json,reviewed_label,event_type,note,human_confirmed)
                       VALUES (?,?,?,?,?,'invalidated','Bounding box changed; review the classification again.',0)""",
                    (detection_id, detection["source_image_id"], review["task"],
                     review["prediction_snapshot_json"], review["reviewed_label"]),
                )
            self._invalidate_task_reviews(connection, int(detection_id), [x1, y1, x2, y2],
                                          int(cursor.lastrowid), "bbox_changed")
            return int(cursor.lastrowid)

    def approve_unchanged_bbox(self, detection_id: int) -> int:
        """Record explicit human approval of the current bbox without creating a geometry revision."""
        with self.connect() as connection:
            detection = connection.execute(
                """SELECT d.*, s.path,s.content_sha256,s.width,s.height
                   FROM yolo_detections d JOIN source_images s ON s.id=d.source_image_id
                   WHERE d.id=?""", (int(detection_id),)
            ).fetchone()
            if not detection:
                raise ValueError("Detection no longer exists.")
            integrity_reason = _source_integrity_reason(
                detection["path"], detection["content_sha256"])
            if integrity_reason:
                raise ValueError(f"Cannot approve training data: {integrity_reason}.")
            from app.core.yolo_registry import is_approved_yolo_identity
            proposal = connection.execute(
                "SELECT * FROM asset_proposals WHERE detection_id=? ORDER BY id DESC LIMIT 1",
                (int(detection_id),),
            ).fetchone()
            bbox = [float(detection[key]) for key in ("x1", "y1", "x2", "y2")]
            if proposal and proposal["corrected_bbox_json"]:
                bbox = [float(value) for value in json.loads(proposal["corrected_bbox_json"])]
            if not (0 <= bbox[0] < bbox[2] <= detection["width"]
                    and 0 <= bbox[1] < bbox[3] <= detection["height"]):
                raise ValueError("The unchanged bbox is outside the source image.")

            latest_correction = connection.execute(
                """SELECT corrected_payload_json FROM correction_records
                   WHERE detection_id=? AND decision_type='reclassified'
                   ORDER BY id DESC LIMIT 1""", (int(detection_id),)
            ).fetchone()
            effective_class = str(detection["class_name"])
            if latest_correction:
                payload = json.loads(latest_correction["corrected_payload_json"] or "{}")
                effective_class = str(payload.get("yolo_annotation_class_name") or effective_class)
                if payload.get("yolo_annotation_class_id") is not None:
                    effective_class_id = int(payload["yolo_annotation_class_id"])
                else:
                    effective_class_id = int(detection["class_id"])
            else:
                effective_class_id = int(detection["class_id"])
            if not is_approved_yolo_identity(effective_class_id, effective_class):
                raise ValueError(
                    "This historical YOLO class is not an exact match for the approved registry; "
                    "correct it to an approved class before training."
                )

            previous = connection.execute(
                """SELECT * FROM yolo_bbox_reviews WHERE detection_id=? ORDER BY id DESC LIMIT 1""",
                (int(detection_id),),
            ).fetchone()
            if previous and previous["review_status"] == "approved":
                return int(previous["id"])

            cursor = connection.execute(
                """INSERT INTO yolo_bbox_reviews
                   (detection_id,proposal_id,source_image_id,source_sha256,
                    original_bbox_xyxy,effective_bbox_xyxy,bbox_revision,review_status,
                    human_confirmed,training_eligible,supersedes_id,confirmed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
                (int(detection_id), int(proposal["id"]) if proposal else None,
                 int(detection["source_image_id"]), detection["content_sha256"],
                 json.dumps([float(detection[key]) for key in ("x1", "y1", "x2", "y2")]),
                 json.dumps(bbox), None, "approved", 1, 1,
                 int(previous["id"]) if previous else None),
            )
            review_id = int(cursor.lastrowid)

            if proposal:
                previous_example = connection.execute(
                    """SELECT * FROM training_examples
                       WHERE proposal_id=? AND task='yolo_detector'
                       ORDER BY id DESC LIMIT 1""", (int(proposal["id"]),)
                ).fetchone()
                bbox_json = json.dumps(bbox)
                registry_path = (Path(__file__).resolve().parents[2] / "TrainingDatasetStudio"
                                 / "registries" / "yolo_detector_v1.json")
                registry = json.loads(registry_path.read_text(encoding="utf-8"))
                same = (previous_example
                        and previous_example["source_sha256"] == detection["content_sha256"]
                        and previous_example["class_label"] == effective_class
                        and previous_example["crop_bbox_json"] == bbox_json)
                if not same:
                    provenance = {
                        "model_id": detection["model_id"],
                        "checkpoint_sha256": detection["model_digest"],
                        "class_id": detection["class_id"],
                        "class_name": detection["class_name"],
                        "confidence": detection["confidence"],
                        "original_bbox_xyxy": [float(detection[key]) for key in ("x1", "y1", "x2", "y2")],
                        "effective_bbox_xyxy": bbox,
                        "bbox_review_id": review_id,
                        "bbox_authority": "human_approved_unchanged",
                        "target_registry_id": registry["registry_id"],
                    }
                    cursor_example = connection.execute(
                        """INSERT INTO training_examples
                           (source_image_id,proposal_id,detection_id,supersedes_id,
                            source_sha256,crop_bbox_json,task,class_label,taxonomy_id,
                            taxonomy_version,suggestion_provenance_json,workflow,
                            human_confirmed,training_eligible,correction_record_id,bbox_review_id)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,'professional_review',1,1,?,?)""",
                        (int(detection["source_image_id"]), int(proposal["id"]),
                         int(detection["id"]), int(previous_example["id"]) if previous_example else None,
                         detection["content_sha256"], bbox_json, "yolo_detector", effective_class,
                         registry["registry_id"], str(registry["schema_version"]),
                         json.dumps(provenance, sort_keys=True), None, review_id),
                    )
                    connection.execute(
                        "UPDATE yolo_bbox_reviews SET training_example_id=? WHERE id=?",
                        (int(cursor_example.lastrowid), review_id),
                    )
            connection.execute(
                "UPDATE asset_proposals SET review_status='confirmed', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (int(proposal["id"]),),
            ) if proposal else None
            return review_id

    def save_yolo_class_correction(self, proposal_id: int, target_class_id: int,
                                   registry_id: str) -> int:
        """Save the Inspector's selected class together with the current effective bbox."""
        return self.save_yolo_annotation_correction(
            proposal_id, target_class_id, registry_id)

    def save_yolo_annotation_correction(self, proposal_id: int, target_class_id: int | None,
                                       registry_id: str,
                                       bbox_xyxy: list[float] | None = None) -> int:
        """Append a confirmed YOLO annotation correction and supersede its training example."""
        registry_path = (Path(__file__).resolve().parents[2] / "TrainingDatasetStudio"
                         / "registries" / "yolo_detector_v1.json")
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        if registry_id != registry.get("registry_id"):
            raise ValueError("Class correction must use the approved target YOLO registry.")
        classes = {int(row["id"]): str(row["name"]) for row in registry["classes"]}
        with self.connect() as connection:
            proposal = connection.execute(
                """SELECT p.*,s.path,s.content_sha256,s.width,s.height,
                          d.id AS detection_id,d.class_id,d.class_name,d.confidence,
                          d.x1,d.y1,d.x2,d.y2,d.model_id,d.model_digest
                   FROM asset_proposals p
                   JOIN source_images s ON s.id=p.source_image_id
                   LEFT JOIN yolo_detections d ON d.id=p.detection_id
                   WHERE p.id=?""", (int(proposal_id),)
            ).fetchone()
            if not proposal:
                raise ValueError("Class correction requires an existing detected proposal.")
            if proposal["detection_id"] is None:
                raise ValueError("YOLO annotation correction requires a persisted detection.")
            integrity_reason = _source_integrity_reason(
                proposal["path"], proposal["content_sha256"])
            if integrity_reason:
                raise ValueError(f"Cannot correct stale training media: {integrity_reason}.")
            if proposal["width"] is None or proposal["height"] is None:
                raise ValueError("YOLO annotation correction requires source image dimensions.")
            effective_bbox = ([float(value) for value in json.loads(proposal["corrected_bbox_json"])]
                              if proposal["corrected_bbox_json"] else
                              [float(proposal[key]) for key in ("x1", "y1", "x2", "y2")])
            current_bbox = list(effective_bbox)
            if bbox_xyxy is not None:
                if len(bbox_xyxy) != 4:
                    raise ValueError("Edited box must contain four source-pixel coordinates.")
                current_bbox = [float(value) for value in bbox_xyxy]
            if not (0 <= current_bbox[0] < current_bbox[2] <= proposal["width"]
                    and 0 <= current_bbox[1] < current_bbox[3] <= proposal["height"]):
                raise ValueError("Corrected box must stay within source image coordinates.")

            correction_rows = connection.execute(
                "SELECT corrected_payload_json FROM correction_records "
                "WHERE proposal_id=? ORDER BY id", (int(proposal_id),)
            ).fetchall()
            effective_class_id = None
            for correction_row in correction_rows:
                correction_payload = json.loads(correction_row["corrected_payload_json"] or "{}")
                if (correction_payload.get("yolo_annotation_registry_id") == registry_id
                        and correction_payload.get("yolo_annotation_class_id") is not None):
                    effective_class_id = int(correction_payload["yolo_annotation_class_id"])
            previous_class_id = (effective_class_id if effective_class_id is not None else
                                 next((item_id for item_id, name in classes.items()
                                       if name == proposal["class_name"]), None))
            if target_class_id is None:
                class_id = previous_class_id
            else:
                try:
                    class_id = int(target_class_id)
                except (TypeError, ValueError) as error:
                    raise ValueError("Choose a valid target YOLO class.") from error
            if class_id not in classes:
                raise ValueError("Choose a class from the approved target YOLO registry.")
            class_changed = class_id != previous_class_id
            bbox_changed = current_bbox != effective_bbox
            if not class_changed and not bbox_changed:
                raise ValueError("The YOLO annotation is unchanged; use bbox approval instead.")

            original = {
                "source_image_id": int(proposal["source_image_id"]),
                "source_path": proposal["path"],
                "source_sha256": proposal["content_sha256"],
                "image_width": proposal["width"],
                "image_height": proposal["height"],
                "yolo": {key: proposal[key] for key in (
                    "class_id", "class_name", "confidence", "x1", "y1", "x2", "y2",
                    "model_id", "model_digest")},
                "cnn": (dict(connection.execute(
                    "SELECT * FROM cnn_predictions WHERE id=?",
                    (proposal["prediction_id"],),
                ).fetchone()) if proposal["prediction_id"] is not None else None),
            }
            corrected = {
                "class_correction": class_changed,
                "bbox_correction": bbox_changed,
                "yolo_annotation_registry_id": registry_id,
                "yolo_annotation_class_id": class_id,
                "yolo_annotation_class_name": classes[class_id],
                "bbox_xyxy": current_bbox,
                "category": proposal["category"],
                "validity_state": "valid",
            }
            cursor = connection.execute(
                """INSERT INTO correction_records
                   (proposal_id,source_image_id,source_path,source_sha256,detection_id,
                    original_snapshot_json,corrected_payload_json,decision_type,final_state,
                    user_changed_prediction,human_confirmed,taxonomy_version)
                   VALUES (?,?,?,?,?,?,?,'corrected','confirmed',1,1,?)""",
                (int(proposal_id), int(proposal["source_image_id"]), proposal["path"],
                 proposal["content_sha256"], int(proposal["detection_id"]),
                 json.dumps(original, sort_keys=True), json.dumps(corrected, sort_keys=True),
                 str(registry.get("schema_version", "1"))),
            )
            correction_id = int(cursor.lastrowid)
            previous = connection.execute(
                """SELECT * FROM training_examples
                   WHERE proposal_id=? AND task='yolo_detector' ORDER BY id DESC LIMIT 1""",
                (int(proposal_id),),
            ).fetchone()
            provenance = {
                "yolo": {key: proposal[key] for key in (
                    "model_id", "model_digest", "class_id", "class_name", "confidence")},
                "original_bbox_xyxy": [float(proposal[key]) for key in ("x1", "y1", "x2", "y2")],
                "effective_bbox_xyxy": current_bbox,
                "human_correction_record_id": correction_id,
                "target_registry_id": registry["registry_id"],
            }
            example = connection.execute(
                """INSERT INTO training_examples
                   (source_image_id,proposal_id,detection_id,supersedes_id,
                    source_sha256,crop_bbox_json,task,class_label,taxonomy_id,
                    taxonomy_version,suggestion_provenance_json,workflow,
                    human_confirmed,training_eligible,correction_record_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,'professional_review',1,1,?)""",
                (int(proposal["source_image_id"]), int(proposal_id),
                 int(proposal["detection_id"]), int(previous["id"]) if previous else None,
                 proposal["content_sha256"], json.dumps(current_bbox), "yolo_detector",
                 classes[class_id], registry["registry_id"], str(registry["schema_version"]),
                 json.dumps(provenance, sort_keys=True), correction_id),
            )
            if class_changed or bbox_changed:
                self._invalidate_task_reviews(
                    connection, int(proposal["detection_id"]), current_bbox, correction_id,
                    "bbox_changed" if bbox_changed else "yolo_class_changed")
            connection.execute(
                """UPDATE asset_proposals
                   SET corrected_bbox_json=?,review_status='confirmed',updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (json.dumps(current_bbox), int(proposal_id)),
            )
            return correction_id

    def effective_detection_state(self, proposal_id: int) -> dict:
        """Resolve one Proposal's authoritative effective YOLO class and BBox."""
        with self.connect() as connection:
            row = connection.execute(
                """SELECT p.id proposal_id,p.detection_id,p.corrected_bbox_json,p.category,
                          d.class_id,d.class_name,d.confidence,d.x1,d.y1,d.x2,d.y2
                   FROM asset_proposals p JOIN yolo_detections d ON d.id=p.detection_id
                   WHERE p.id=?""", (int(proposal_id),)
            ).fetchone()
            if not row:
                raise ValueError("Proposal no longer exists.")
            correction = connection.execute(
                """SELECT corrected_payload_json FROM correction_records
                   WHERE proposal_id=? ORDER BY id DESC LIMIT 1""",
                (int(proposal_id),),
            ).fetchone()
            class_id = int(row["class_id"]) if row["class_id"] is not None else None
            class_name = str(row["class_name"] or "")
            bbox = ([float(value) for value in json.loads(row["corrected_bbox_json"])]
                    if row["corrected_bbox_json"] else
                    [float(row[key]) for key in ("x1", "y1", "x2", "y2")])
            if correction:
                payload = json.loads(correction["corrected_payload_json"] or "{}")
                if payload.get("yolo_annotation_class_id") is not None:
                    class_id = int(payload["yolo_annotation_class_id"])
                class_name = str(payload.get("yolo_annotation_class_name")
                                 or payload.get("class_name") or class_name)
                if payload.get("bbox_xyxy"):
                    bbox = [float(value) for value in payload["bbox_xyxy"]]
        from app.core.classification_eligibility import required_tasks
        tasks = list(required_tasks(class_name))
        return {
            "proposal_id": int(proposal_id),
            "detection_id": int(row["detection_id"]),
            "class_id": class_id,
            "class_name": class_name,
            "original_class_id": int(row["class_id"]) if row["class_id"] is not None else None,
            "original_class_name": str(row["class_name"] or ""),
            "confidence": row["confidence"],
            "bbox_xyxy": bbox,
            "eligible_tasks": tasks,
        }

    def classification_task_status(self, proposal_id: int) -> dict[str, dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT r.* FROM classification_task_reviews r
                   WHERE r.proposal_id=? AND r.id=(SELECT MAX(latest.id) FROM classification_task_reviews latest
                     WHERE latest.detection_id=r.detection_id AND latest.task_head=r.task_head)
                   ORDER BY r.task_head""", (int(proposal_id),)
            ).fetchall()
        return {row["task_head"]: dict(row) for row in rows}

    def save_classification_task_review(self, proposal_id: int, task_head: str, target_label: str,
                                        payload: dict, *, action: str = "confirmed",
                                        training_eligible: bool = True) -> int:
        """Append one task's draft/confirmation/rejection without touching sibling heads."""
        from app.core.classification_eligibility import (
            AROUSAL_LABELS, BODY_IMAGES_LABELS, CORRUPTION_LABELS, FULLBODY_LABELS,
            PORTRAIT_LABELS, is_fullbody_region, is_location_group, shared_head_eligible,
        )
        from app.core.classification_taxonomy import LOCATION_VALUES, REGISTRY_ID, REGISTRY_VERSION, validate_record
        from app.core.clothing_taxonomy import clothing_classes, validate_final_clothing_tag

        allowed_heads = {"body_images", "fullbody", "portrait", "arousal", "corruption",
                         "location", "clothing_broad", "clothing_fine"}
        if task_head not in allowed_heads:
            raise ValueError(f"Unsupported classification task: {task_head!r}")
        if action not in {"draft", "confirmed", "rejected"}:
            raise ValueError("Task action must be draft, confirmed, or rejected.")
        target_label = str(target_label or "").strip()
        if not target_label:
            raise ValueError("Choose this task's human target before saving it.")
        if training_eligible and (action != "confirmed" or payload.get("validity_state") != "valid"):
            raise ValueError("Training eligibility requires this task to be confirmed and valid.")

        with self.connect() as connection:
            proposal = connection.execute(
                """SELECT p.*,s.path,s.content_sha256,s.width,s.height,s.id source_id,
                          d.id AS detection_id,d.class_id AS yolo_class_id,d.class_name AS yolo_class_name,
                          d.confidence AS yolo_confidence,d.model_id AS yolo_model_id,d.model_digest AS yolo_model_digest,
                          d.x1,d.y1,d.x2,d.y2,c.class_name AS cnn_class_name,c.confidence AS cnn_confidence,
                          c.model_id AS cnn_model_id,c.model_digest AS cnn_model_digest
                   FROM asset_proposals p JOIN source_images s ON s.id=p.source_image_id
                   JOIN yolo_detections d ON d.id=p.detection_id
                   LEFT JOIN cnn_predictions c ON c.id=p.prediction_id WHERE p.id=?""", (int(proposal_id),)
            ).fetchone()
            if not proposal:
                raise ValueError("Classification task needs a proposal with a source detection.")
            integrity_reason = _source_integrity_reason(
                proposal["path"], proposal["content_sha256"])
            if integrity_reason:
                raise ValueError(f"Cannot save a current classification: {integrity_reason}.")
            if proposal["detection_id"] is None:
                if task_head not in {"clothing_broad", "clothing_fine"}:
                    raise ValueError(
                        "Classification tasks require a proposal linked to a YOLO or manually persisted source detection."
                    )
                raise ValueError(
                    "This proposal has no source detection. Clothing classification can only be saved for a detection-linked Clothing proposal."
                )
            latest_correction = connection.execute(
                """SELECT id,corrected_payload_json FROM correction_records
                   WHERE proposal_id=? ORDER BY id DESC LIMIT 1""", (int(proposal_id),)
            ).fetchone()
            latest_payload = json.loads(latest_correction["corrected_payload_json"] or "{}") if latest_correction else {}
            region = str(latest_payload.get("yolo_annotation_class_name") or
                         latest_payload.get("class_name") or proposal["yolo_class_name"] or "")
            effective_class_id = int(latest_payload.get(
                "yolo_annotation_class_id", proposal["yolo_class_id"]))
            from app.core.yolo_registry import is_approved_yolo_identity
            if not is_approved_yolo_identity(effective_class_id, region):
                raise ValueError(
                    "This historical YOLO class is not an exact match for the approved registry."
                )
            bbox = json.loads(proposal["corrected_bbox_json"]) if proposal["corrected_bbox_json"] else [
                proposal[key] for key in ("x1", "y1", "x2", "y2")]
            if len(bbox) != 4:
                raise ValueError("Detection has no valid source-pixel bbox.")
            previous = connection.execute(
                """SELECT * FROM classification_task_reviews WHERE proposal_id=? AND task_head=?
                   ORDER BY id DESC LIMIT 1""", (int(proposal_id), task_head)
            ).fetchone()
            previous_example_id = previous["training_example_id"] if previous else None
            if previous_example_id is None:
                example_task = "unified_body_images_fullbody" if task_head in {
                    "body_images", "fullbody", "portrait", "arousal", "corruption"} else task_head
                example_head = task_head if example_task == "unified_body_images_fullbody" else None
                old_example = connection.execute(
                    """SELECT id FROM training_examples WHERE proposal_id=? AND task=? AND task_head IS ?
                       ORDER BY id DESC LIMIT 1""", (int(proposal_id), example_task, example_head)
                ).fetchone()
                previous_example_id = int(old_example["id"]) if old_example else None

            confirmed_portrait = None

            label_sets = {"body_images": BODY_IMAGES_LABELS, "fullbody": FULLBODY_LABELS,
                          "portrait": PORTRAIT_LABELS, "arousal": AROUSAL_LABELS,
                          "corruption": CORRUPTION_LABELS}
            body_decisions = _normalize_body_images_decisions(payload, target_label) if task_head == "body_images" else None
            if task_head == "body_images":
                explicit_body_decisions = any(key in payload for key in (
                    "cum_target", "cum_evaluated", "accessory_target",
                    "accessory_evaluated", "body_images_completed"))
                if explicit_body_decisions:
                    if body_decisions["completed"]:
                        target_label = ("body_images_none"
                                        if not body_decisions["cum_target"] and not body_decisions["accessory_target"]
                                        else "body_images_multi_label")
                    elif body_decisions["cum_evaluated"] or body_decisions["accessory_evaluated"]:
                        target_label = "body_images_multi_label"
                    else:
                        target_label = "body_images_pending"
                if not (body_decisions["cum_evaluated"] or body_decisions["accessory_evaluated"]):
                    eligible = False
            if task_head in label_sets and task_head != "body_images" and target_label not in label_sets[task_head]:
                raise ValueError(f"{target_label!r} is not a registered {task_head} target.")
            if task_head in label_sets and not shared_head_eligible(
                    task_head, region, confirmed_portrait=confirmed_portrait):
                raise ValueError(f"{task_head.replace('_',' ').title()} is not eligible for YOLO region {region!r}.")
            if task_head == "location" and (not is_location_group(region) or target_label not in LOCATION_VALUES):
                raise ValueError("Location targets require a canonical label and a location_group detection.")
            if task_head in {"clothing_broad", "clothing_fine"} and proposal["category"] != "clothing":
                raise ValueError("Clothing classifications require a Clothing proposal.")
            if task_head == "clothing_broad" and target_label not in {row["class_name"] for row in clothing_classes()}:
                raise ValueError("Choose a registered broad Clothing family.")
            if task_head == "clothing_fine":
                family = payload.get("clothing_family_tag")
                if not family or not validate_final_clothing_tag(family, target_label):
                    raise ValueError("The detailed Clothing label must belong to the selected family.")
            if task_head == "body_images":
                body_tag = payload.get("body_tag") or (
                    region if region in {"face", "boobs", "ass", "pussy", "legs"} else None
                )
                if body_tag is not None:
                    validate_record("body_images", {
                        "main_tag": body_tag,
                        "subtags": payload.get("subtags", []),
                        "validity_state": payload.get("validity_state"),
                    })
                elif payload.get("subtags"):
                    raise ValueError("Body Images subtags need a canonical main tag.")

            shared_head = task_head in label_sets
            if shared_head:
                registry_id = "newassetapp_unified_body_images_fullbody"
                registry_version = "v2_five_head_shared_backbone_untrained"
                example_task, example_head = "unified_body_images_fullbody", task_head
            elif task_head == "location":
                registry_id, registry_version = REGISTRY_ID, REGISTRY_VERSION
                example_task, example_head = None, None
                training_eligible = False
            elif task_head == "clothing_broad":
                registry_id, registry_version = "clothing_classifier", "clothing-broad-v2-12class"
                example_task, example_head = "clothing_broad", None
            else:
                registry_id, registry_version = REGISTRY_ID, REGISTRY_VERSION
                example_task, example_head = "clothing_fine", None

            suggestion = {
                "yolo": {"class_id": proposal["yolo_class_id"], "class_name": proposal["yolo_class_name"],
                         "confidence": proposal["yolo_confidence"], "model_id": proposal["yolo_model_id"],
                         "model_digest": proposal["yolo_model_digest"]},
                "cnn": {"class_name": proposal["cnn_class_name"], "confidence": proposal["cnn_confidence"],
                        "model_id": proposal["cnn_model_id"], "model_digest": proposal["cnn_model_digest"]},
                "reviewed_yolo_class_name": region,
            }
            bbox_json = json.dumps([float(value) for value in bbox])
            bbox_revision = int(latest_correction["id"]) if latest_correction else None
            confirmed = action == "confirmed"
            eligible = bool(training_eligible and confirmed)
            if task_head == "body_images" and body_decisions is not None:
                if not (body_decisions["cum_evaluated"] or body_decisions["accessory_evaluated"]):
                    eligible = False
            from app.core.confidence_verification import model_verified
            model_confidence = proposal["cnn_confidence"]
            try:
                model_confidence = float(model_confidence) if model_confidence is not None else None
            except (TypeError, ValueError):
                model_confidence = None
            head_model_verified = 1 if model_verified(model_confidence) else 0
            cursor = connection.execute(
                """INSERT INTO classification_task_reviews
                   (proposal_id,source_image_id,detection_id,task_head,target_label,suggestion_provenance_json,
                    source_sha256,crop_bbox_json,bbox_revision,registry_id,registry_version,
                    confirmation_status,human_confirmed,training_eligible,training_example_id,confirmed_at,
                    staled_at,supersedes_id,model_verified,model_confidence,confidence_threshold,
                    eligibility_registry_id,eligibility_registry_version,target_mask_json,
                    cum_target,cum_evaluated,accessory_target,accessory_evaluated)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (int(proposal_id), int(proposal["source_id"]), int(proposal["detection_id"]), task_head,
                 target_label, json.dumps(suggestion, sort_keys=True), proposal["content_sha256"], bbox_json,
                 bbox_revision, registry_id, registry_version, action, int(confirmed), int(eligible),
                 previous_example_id,
                 (datetime.now(timezone.utc).isoformat() if confirmed else None),
                 None, int(previous["id"]) if previous else None,
                 head_model_verified, model_confidence, 0.77,
                 "newassetapp_task_eligibility", "task-eligibility-v1",
                 json.dumps(body_decisions["target_mask"] if body_decisions else {"cum":0,"accessory":0}),
                 body_decisions["cum_target"] if body_decisions and body_decisions["cum_target"] is not None else None,
                 int(body_decisions["cum_evaluated"]) if body_decisions else 0,
                 body_decisions["accessory_target"] if body_decisions and body_decisions["accessory_target"] is not None else None,
                 int(body_decisions["accessory_evaluated"]) if body_decisions else 0),
            )
            review_id = int(cursor.lastrowid)
            if head_model_verified:
                connection.execute(
                    "UPDATE classification_task_reviews SET model_verified_at=CURRENT_TIMESTAMP WHERE id=?",
                    (review_id,),
                )
            if previous_example_id is not None and (not eligible or action != "confirmed"):
                connection.execute(
                    """INSERT OR IGNORE INTO training_example_suppressions
                       (training_example_id,reason,task_review_id) VALUES (?,?,?)""",
                    (int(previous_example_id), f"task_{action}", review_id),
                )
            example_id = None
            if eligible and example_task:
                labels = payload.get("subtags", []) if task_head in {"body_images", "fullbody", "clothing_fine"} else (
                    [target_label] if task_head == "portrait" else [])
                example_cursor = connection.execute(
                    """INSERT INTO training_examples
                       (source_image_id,proposal_id,detection_id,supersedes_id,source_sha256,crop_bbox_json,
                        task,class_label,taxonomy_id,taxonomy_version,suggestion_provenance_json,workflow,
                        human_confirmed,training_eligible,correction_record_id,task_head,human_confirmed_labels_json,
                        target_mask_json,eligibility_registry_id,eligibility_registry_version)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,'professional_review',1,1,?,?,?, ?,?,?)""",
                    (int(proposal["source_id"]), int(proposal_id), int(proposal["detection_id"]),
                     previous_example_id, proposal["content_sha256"], bbox_json, example_task,
                     target_label, registry_id, registry_version, json.dumps(suggestion, sort_keys=True),
                     bbox_revision, example_head, json.dumps(list(dict.fromkeys(labels))),
                     json.dumps(body_decisions["target_mask"]) if body_decisions else None,
                     "newassetapp_task_eligibility" if body_decisions else None,
                     "task-eligibility-v1" if body_decisions else None),
                )
                example_id = int(example_cursor.lastrowid)
                connection.execute("UPDATE classification_task_reviews SET training_example_id=? WHERE id=?",
                                   (example_id, review_id))
            return review_id

    def output_review_records(self) -> list[dict]:
        """Return only confirmed assets with their latest human decision payload."""
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT p.*, s.path, s.content_sha256, s.width, s.height, s.id source_id,
                          (SELECT cr.id FROM correction_records cr WHERE cr.proposal_id=p.id
                           ORDER BY cr.id DESC LIMIT 1) AS correction_id,
                          (SELECT cr.corrected_payload_json FROM correction_records cr
                           WHERE cr.proposal_id=p.id ORDER BY cr.id DESC LIMIT 1) AS confirmed_json,
                          (SELECT cr.taxonomy_version FROM correction_records cr
                           WHERE cr.proposal_id=p.id ORDER BY cr.id DESC LIMIT 1) AS taxonomy_version,
                          d.model_id AS yolo_model_id, d.model_digest AS yolo_model_digest,
                          c.model_id AS cnn_model_id, c.model_digest AS cnn_model_digest,
                          sc.main_category AS structured_main_category,
                          sc.fullbody_state AS structured_fullbody_state,
                          sc.clothing_family AS structured_clothing_family,
                          sc.subtags_json AS structured_subtags_json,
                          sc.corruption_values_json AS structured_corruption_values_json,
                          sc.location_value AS structured_location_value,
                          sc.validity_state AS structured_validity_state,
                          sc.human_review_state AS structured_human_review_state,
                          sc.human_confirmed AS structured_human_confirmed,
                          sc.training_eligible AS structured_training_eligible,
                          sc.exclusion_reason AS structured_exclusion_reason,
                          sc.registry_id AS structured_registry_id,
                          sc.taxonomy_version AS structured_taxonomy_version
                   FROM asset_proposals p JOIN source_images s ON s.id=p.source_image_id
                   LEFT JOIN yolo_detections d ON d.id=p.detection_id
                   LEFT JOIN cnn_predictions c ON c.id=p.prediction_id
                   JOIN structured_classifications sc ON sc.proposal_id=p.id
                     AND sc.task=p.category AND sc.human_confirmed=1
                     AND sc.validity_state='valid' AND sc.human_review_state='confirmed'
                   WHERE p.review_status='confirmed' ORDER BY p.id"""
            ).fetchall()
            return [dict(row) for row in rows]

    def proposal_review_history(self, proposal_id: int, limit: int = 8) -> list[dict]:
        """Return append-only correction and structured classification events for review display."""
        with self.connect() as connection:
            corrections = connection.execute(
                """SELECT id,decision_type,final_state,human_confirmed,created_at,
                          corrected_payload_json FROM correction_records
                   WHERE proposal_id=? ORDER BY id DESC LIMIT ?""",
                (int(proposal_id), int(limit)),
            ).fetchall()
            structured = connection.execute(
                """SELECT e.id,e.event_type,e.after_json,e.actor,e.occurred_at
                   FROM structured_classification_events e
                   JOIN structured_classifications c ON c.id=e.classification_id
                   WHERE c.proposal_id=? ORDER BY e.id DESC LIMIT ?""",
                (int(proposal_id), int(limit)),
            ).fetchall()
        history = []
        for row in corrections:
            payload = json.loads(row["corrected_payload_json"] or "{}")
            history.append({"id": int(row["id"]), "kind": "correction",
                            "event": row["decision_type"], "status": row["final_state"],
                            "human_confirmed": bool(row["human_confirmed"]),
                            "created_at": row["created_at"],
                            "label": payload.get("yolo_annotation_class_name") or
                                     payload.get("main_tag") or payload.get("clothing_tag") or
                                     payload.get("class_name") or "review update"})
        for row in structured:
            after = json.loads(row["after_json"] or "{}")
            history.append({"id": int(row["id"]), "kind": "classification",
                            "event": row["event_type"], "status": after.get("human_review_state"),
                            "human_confirmed": bool(after.get("human_confirmed")),
                            "created_at": row["occurred_at"], "actor": row["actor"],
                            "label": after.get("main_category") or after.get("fullbody_state") or "classification update"})
        history.sort(key=lambda item: (item.get("created_at") or "", item["id"]), reverse=True)
        return history[:limit]

    def structured_classification_for_proposal(self, proposal_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM structured_classifications WHERE proposal_id=? ORDER BY id DESC LIMIT 1",
                (int(proposal_id),),
            ).fetchone()
        if not row:
            return None
        value = dict(row)
        for field, output in (("subtags_json", "subtags"),
                              ("corruption_values_json", "corruption_values"),
                              ("location_suggestions_json", "location_suggestions"),
                              ("ai_suggestion_json", "ai_suggestion")):
            try:
                value[output] = json.loads(value.pop(field) or "[]")
            except (TypeError, ValueError):
                value[output] = []
        return value

    def save_normal_processing_draft(self, proposal_id: int, draft: dict) -> dict:
        """Atomically persist the latest Normal Processing draft."""
        proposal_id = int(proposal_id)
        with self.connect() as connection:
            proposal = connection.execute(
                """SELECT p.id,p.source_image_id,p.detection_id,p.corrected_bbox_json,
                          s.content_sha256,p.updated_at
                   FROM asset_proposals p JOIN source_images s ON s.id=p.source_image_id
                   WHERE p.id=?""", (proposal_id,)
            ).fetchone()
            if not proposal:
                raise ValueError("Draft proposal no longer exists.")
            bbox_revision = draft.get("bbox_revision")
            crop_identity = draft.get("crop_identity")
            category = draft.get("category")
            taxonomy_version = draft.get("taxonomy_version")
            stale = bool(draft.get("stale_due_to_revision"))
            payload = dict(draft)
            payload.update({
                "proposal_id": proposal_id,
                "source_image_id": int(proposal["source_image_id"]),
                "source_sha256": str(proposal["content_sha256"]),
                "detection_id": int(proposal["detection_id"]) if proposal["detection_id"] is not None else None,
                "draft_schema_version": int(payload.get("draft_schema_version") or 1),
            })
            connection.execute(
                """INSERT INTO normal_processing_drafts
                   (proposal_id,source_image_id,source_sha256,detection_id,bbox_revision,
                    crop_identity,category,draft_json,schema_version,taxonomy_version,
                    stale_due_to_revision,save_failed,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
                   ON CONFLICT(proposal_id) DO UPDATE SET
                    source_image_id=excluded.source_image_id,
                    source_sha256=excluded.source_sha256,
                    detection_id=excluded.detection_id,
                    bbox_revision=excluded.bbox_revision,
                    crop_identity=excluded.crop_identity,
                    category=excluded.category,
                    draft_json=excluded.draft_json,
                    schema_version=excluded.schema_version,
                    taxonomy_version=excluded.taxonomy_version,
                    stale_due_to_revision=excluded.stale_due_to_revision,
                    save_failed=0,
                    updated_at=CURRENT_TIMESTAMP""",
                (proposal_id, int(proposal["source_image_id"]), str(proposal["content_sha256"]),
                 int(proposal["detection_id"]) if proposal["detection_id"] is not None else None,
                 int(bbox_revision) if bbox_revision is not None else None,
                 str(crop_identity) if crop_identity is not None else None,
                 str(category) if category in {"fullbody","body_images","clothing","invalid"} else None,
                 json.dumps(payload, sort_keys=True),
                 int(payload["draft_schema_version"]),
                 str(taxonomy_version) if taxonomy_version is not None else None,
                 int(stale)),
            )
        return payload

    def load_normal_processing_draft(self, proposal_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT d.*,p.detection_id,p.corrected_bbox_json,s.content_sha256
                   FROM normal_processing_drafts d
                   JOIN asset_proposals p ON p.id=d.proposal_id
                   JOIN source_images s ON s.id=d.source_image_id
                   WHERE d.proposal_id=?""", (int(proposal_id),)
            ).fetchone()
            if not row:
                return None
            payload = json.loads(row["draft_json"] or "{}")
            payload["draft_id"] = int(row["proposal_id"])
            payload["draft_save_failed"] = bool(row["save_failed"])
            payload["stale_due_to_revision"] = bool(
                row["stale_due_to_revision"]
                or str(row["source_sha256"]) != str(row["content_sha256"])
            )
            payload["latest_source_sha256"] = str(row["content_sha256"])
            payload["latest_corrected_bbox_json"] = row["corrected_bbox_json"]
            payload["updated_at"] = row["updated_at"]
            saved_identity = payload.get("crop_identity")
            latest_bbox = json.loads(row["corrected_bbox_json"]) if row["corrected_bbox_json"] else None
            if saved_identity and latest_bbox:
                latest_identity = (
                    f"{row['content_sha256']}:"
                    f"{','.join(str(round(float(value), 3)) for value in latest_bbox)}"
                )
                payload["stale_due_to_revision"] = bool(
                    payload["stale_due_to_revision"] or saved_identity != latest_identity
                )
            return payload

    def normal_processing_draft_ids(self) -> set[int]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT proposal_id FROM normal_processing_drafts"
            ).fetchall()
            return {int(row["proposal_id"]) for row in rows}

    def discard_normal_processing_draft(self, proposal_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM normal_processing_drafts WHERE proposal_id=?",
                (int(proposal_id),),
            )
            return cursor.rowcount > 0

    def mark_normal_processing_draft_save_failed(self, proposal_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE normal_processing_drafts SET save_failed=1,updated_at=CURRENT_TIMESTAMP "
                "WHERE proposal_id=?",
                (int(proposal_id),),
            )

    def ensure_active_detection_crop(self, detection_id: int) -> dict:
        """Create or reuse the one canonical crop for a Detection/effective-BBox revision."""
        from PIL import Image
        with self.connect() as connection:
            row = connection.execute(
                """SELECT d.*,p.id proposal_id,p.corrected_bbox_json,
                          s.path,s.content_sha256,s.width,s.height
                   FROM yolo_detections d JOIN source_images s ON s.id=d.source_image_id
                   LEFT JOIN asset_proposals p ON p.detection_id=d.id
                   WHERE d.id=? ORDER BY p.id DESC LIMIT 1""",
                (int(detection_id),),
            ).fetchone()
            if not row:
                raise ValueError("Detection no longer exists.")
            correction = connection.execute(
                """SELECT id,corrected_payload_json FROM correction_records
                   WHERE detection_id=? ORDER BY id DESC LIMIT 1""",
                (int(detection_id),),
            ).fetchone()
            bbox = ([float(value) for value in json.loads(row["corrected_bbox_json"])]
                    if row["corrected_bbox_json"] else
                    [float(row[key]) for key in ("x1","y1","x2","y2")])
            revision = int(correction["id"]) if correction else None
            if correction:
                payload = json.loads(correction["corrected_payload_json"] or "{}")
                if payload.get("bbox_xyxy"):
                    bbox = [float(value) for value in payload["bbox_xyxy"]]
            if len(bbox) != 4 or not (0 <= bbox[0] < bbox[2] <= int(row["width"] or 0)
                                      and 0 <= bbox[1] < bbox[3] <= int(row["height"] or 0)):
                raise ValueError("The effective Detection BBox is invalid.")
            crop_identity = (
                f"detection:{int(detection_id)}|source:{row['content_sha256']}|"
                f"bbox:{','.join(f'{value:.3f}' for value in bbox)}|generation:source_pixel_exact_v1"
            )
            crop_id = hashlib.sha256(crop_identity.encode("utf-8")).hexdigest()
            crop_root = self.path.parent / "training_media" / "crops"
            crop_root.mkdir(parents=True, exist_ok=True)
            crop_path = crop_root / f"{crop_id}.png"
            if not crop_path.is_file():
                with Image.open(row["path"]) as source:
                    rgb = source.convert("RGB")
                    x1, y1, x2, y2 = (int(round(float(value))) for value in bbox)
                    crop = rgb.crop((max(0,x1),max(0,y1),
                                     min(rgb.width,x2),min(rgb.height,y2)))
                    crop.save(crop_path, format="PNG")
                    crop.close()
                    rgb.close()
            crop_sha = hashlib.sha256(crop_path.read_bytes()).hexdigest()
            active = connection.execute(
                "SELECT * FROM active_detection_crops WHERE detection_id=?",
                (int(detection_id),),
            ).fetchone()
            if active and str(active["crop_id"]) != crop_id:
                connection.execute(
                    "UPDATE active_detection_crops SET replaced_at=CURRENT_TIMESTAMP WHERE detection_id=?",
                    (int(detection_id),),
                )
            connection.execute(
                """INSERT INTO active_detection_crops
                   (detection_id,crop_id,source_sha256,crop_sha256,crop_path,bbox_xyxy,bbox_revision,replaced_at)
                   VALUES (?,?,?,?,?,?,?,NULL)
                   ON CONFLICT(detection_id) DO UPDATE SET
                     crop_id=excluded.crop_id,source_sha256=excluded.source_sha256,
                     crop_sha256=excluded.crop_sha256,crop_path=excluded.crop_path,
                     bbox_xyxy=excluded.bbox_xyxy,bbox_revision=excluded.bbox_revision,
                     created_at=CURRENT_TIMESTAMP,replaced_at=NULL""",
                (int(detection_id), crop_id, str(row["content_sha256"]), crop_sha,
                 str(crop_path), json.dumps(bbox), revision),
            )
            return {
                "detection_id": int(detection_id),
                "proposal_id": int(row["proposal_id"]) if row["proposal_id"] is not None else None,
                "crop_id": crop_id,
                "crop_identity": crop_identity,
                "crop_path": str(crop_path),
                "crop_sha256": crop_sha,
                "bbox_xyxy": bbox,
                "bbox_revision": revision,
            }

    def normal_crop_records(self, *, folder: Path | str | None = None) -> list[dict]:
        """Return model crop candidates without reading professional review state."""
        params: list[object] = []
        folder_clause = ""
        if folder is not None:
            prefix = str(Path(folder).resolve())
            folder_clause = "AND (s.path=? OR s.path LIKE ?)"
            params.extend((prefix, prefix.rstrip("\\/") + "\\%"))
        with self.connect() as connection:
            rows = connection.execute(
                f"""SELECT p.id, p.source_image_id AS source_id, p.detection_id, p.category AS proposed_category,
                           p.asset_type, p.confidence AS proposal_confidence, p.corrected_bbox_json,
                           s.path, s.content_sha256, s.width, s.height, d.class_id AS yolo_class_id,
                           d.class_name AS yolo_class_name,d.class_id AS yolo_original_class_id,
                           d.class_name AS yolo_original_class_name,d.model_id AS yolo_model_id,
                           d.model_digest AS yolo_model_digest, d.confidence AS yolo_confidence,
                           d.x1, d.y1, d.x2, d.y2,
                           c.class_name AS cnn_class_name, c.confidence AS cnn_confidence,
                           c.model_id AS cnn_model_id, c.model_digest AS cnn_model_digest,
                           c.status AS cnn_status,
                           n.category AS chosen_category, n.body_image_main_tag,
                           n.main_tag AS normal_main_tag, n.subtags_json AS normal_subtags_json,
                           n.fullbody_state AS normal_fullbody_state,
                           n.location_value AS normal_location_value,
                           n.clothing_broad_family AS normal_clothing_broad_family,
                           n.clothing_cover_area AS normal_clothing_cover_area,
                           n.body_images_cnn_target AS normal_body_images_cnn_target,
                           n.body_images_cum_target AS normal_body_images_cum_target,
                           n.body_images_cum_evaluated AS normal_body_images_cum_evaluated,
                           n.body_images_accessory_target AS normal_body_images_accessory_target,
                           n.body_images_accessory_evaluated AS normal_body_images_accessory_evaluated,
                           n.body_images_completed AS normal_body_images_completed,
                           n.fullbody_cnn_target AS normal_fullbody_cnn_target,
                           n.arousal_cnn_target AS normal_arousal_cnn_target,
                           n.corruption_cnn_target AS normal_corruption_cnn_target,
                           n.taxonomy_version AS normal_taxonomy_version,
                           (SELECT br.id FROM yolo_bbox_reviews br
                             WHERE br.detection_id=d.id ORDER BY br.id DESC LIMIT 1) AS bbox_review_id,
                           (SELECT br.effective_bbox_xyxy FROM yolo_bbox_reviews br
                             WHERE br.detection_id=d.id ORDER BY br.id DESC LIMIT 1) AS bbox_review_json,
                           (SELECT br.review_status FROM yolo_bbox_reviews br
                             WHERE br.detection_id=d.id ORDER BY br.id DESC LIMIT 1) AS bbox_review_status,
                           (SELECT ac.crop_id FROM active_detection_crops ac
                             WHERE ac.detection_id=d.id) AS active_crop_id,
                           (SELECT ac.crop_path FROM active_detection_crops ac
                             WHERE ac.detection_id=d.id) AS active_crop_path,
                           (SELECT ac.bbox_xyxy FROM active_detection_crops ac
                             WHERE ac.detection_id=d.id) AS active_crop_bbox_json,
                           (SELECT ac.bbox_revision FROM active_detection_crops ac
                             WHERE ac.detection_id=d.id) AS active_crop_bbox_revision,
                           (SELECT cr.corrected_payload_json FROM correction_records cr
                            WHERE cr.proposal_id=p.id ORDER BY cr.id DESC LIMIT 1) AS latest_correction_json,
                           COALESCE(n.is_invalid,0) AS normal_is_invalid,
                           EXISTS(SELECT 1 FROM training_examples te WHERE te.proposal_id=p.id
                                  AND te.training_eligible=1 AND te.human_confirmed=1
                                  AND NOT EXISTS(SELECT 1 FROM correction_records reviewed WHERE reviewed.proposal_id=p.id)
                                  AND NOT EXISTS(SELECT 1 FROM training_examples later
                                                 WHERE later.supersedes_id=te.id)) AS normal_confirmed,
                           CASE WHEN EXISTS(SELECT 1 FROM correction_records cr
                             WHERE cr.proposal_id=p.id AND cr.created_at>=COALESCE(
                               (SELECT a.created_at FROM normal_crop_export_attempts a
                                WHERE a.proposal_id=p.id AND a.source_sha256=s.content_sha256
                                ORDER BY a.id DESC LIMIT 1),'') ) THEN 'stale'
                             ELSE (SELECT a.status FROM normal_crop_export_attempts a
                                   WHERE a.proposal_id=p.id AND a.source_sha256=s.content_sha256
                                   ORDER BY a.id DESC LIMIT 1) END AS normal_export_status,
                           EXISTS(SELECT 1 FROM correction_records cr WHERE cr.proposal_id=p.id)
                             AS cnn_suggestion_stale
                    FROM asset_proposals p
                    JOIN source_images s ON s.id=p.source_image_id
                    JOIN yolo_detections d ON d.id=p.detection_id
                    LEFT JOIN cnn_predictions c ON c.id=p.prediction_id
                    LEFT JOIN normal_crop_choices n ON n.proposal_id=p.id
                    WHERE p.review_status<>'stale_source_version' {folder_clause}
                    ORDER BY p.id""", params
            ).fetchall()
        records = []
        for result in rows:
            row = dict(result)
            latest_json = row.pop("latest_correction_json")
            if latest_json:
                latest = json.loads(latest_json)
                row["yolo_class_name"] = (latest.get("yolo_annotation_class_name")
                                          or latest.get("class_name") or row["yolo_class_name"])
                if latest.get("yolo_annotation_class_id") is not None:
                    row["yolo_class_id"] = latest["yolo_annotation_class_id"]
                row["reviewed_correction"] = latest
            try:
                corrected = json.loads(row.pop("corrected_bbox_json") or "null")
                box = corrected or [row["x1"], row["y1"], row["x2"], row["y2"]]
            except (TypeError, ValueError):
                box = [row["x1"], row["y1"], row["x2"], row["y2"]]
            row["bbox_xyxy"] = [float(value) for value in box]
            row["bbox_revision"] = row.get("bbox_review_id")
            row["bbox_review_status"] = row.get("bbox_review_status")
            active_box = None
            if row.get("active_crop_bbox_json"):
                try:
                    active_box = json.loads(row["active_crop_bbox_json"])
                except (TypeError, ValueError):
                    active_box = None
            row["crop_fresh"] = bool(
                row.get("active_crop_id")
                and row.get("active_crop_path")
                and active_box is not None
                and len(active_box) == 4
                and all(abs(float(active) - float(effective)) <= 0.001
                        for active, effective in zip(active_box, row["bbox_xyxy"]))
            )
            row["crop_identity"] = (
                f"{row.get('content_sha256')}:{','.join(str(round(float(value), 3)) for value in row['bbox_xyxy'])}"
                if row.get("bbox_xyxy") else None
            )
            row["normal_subtags"] = json.loads(row.pop("normal_subtags_json") or "[]")
            row["category"] = "invalid" if row.get("normal_is_invalid") else row.get("chosen_category") or (
                row["proposed_category"] if row["proposed_category"] in {"fullbody", "body_images", "clothing"}
                else None
            )
            records.append(row)
        return records

    def restore_normal_crop_invalid(self, proposal_id: int) -> None:
        """Restore one Normal Processing crop's usable state without changing its source or detection."""
        with self.connect() as connection:
            proposal = connection.execute(
                "SELECT id,source_image_id,category FROM asset_proposals WHERE id=?",
                (int(proposal_id),),
            ).fetchone()
            if not proposal:
                raise ValueError("Crop proposal no longer exists.")
            restored_category = (
                str(proposal["category"])
                if str(proposal["category"]) in {"fullbody", "body_images", "clothing"}
                else None
            )
            connection.execute(
                """INSERT INTO normal_crop_choices(proposal_id,source_image_id,category,is_invalid)
                   VALUES(?,?,?,0)
                   ON CONFLICT(proposal_id) DO UPDATE SET
                     is_invalid=0,category=excluded.category,updated_at=CURRENT_TIMESTAMP""",
                (int(proposal_id), int(proposal["source_image_id"]), restored_category),
            )
            connection.execute(
                "DELETE FROM normal_crop_invalidated_examples WHERE proposal_id=?",
                (int(proposal_id),),
            )
            connection.execute(
                "UPDATE asset_proposals SET review_status='pending',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (int(proposal_id),),
            )

    def save_normal_suggestion_review(self, proposal_id: int, action: str) -> int:
        """Persist approve/reject evidence for exactly one Proposal and its suggested task."""
        if action not in {"draft", "rejected"}:
            raise ValueError("Normal suggestion review must be approve-as-draft or reject.")
        with self.connect() as connection:
            proposal = connection.execute(
                """SELECT p.*,s.path,s.content_sha256,s.width,s.height,s.id source_id,
                          d.id detection_id,d.class_id yolo_class_id,d.class_name yolo_class_name,
                          d.confidence yolo_confidence,d.model_id yolo_model_id,d.model_digest yolo_model_digest,
                          d.x1,d.y1,d.x2,d.y2,c.class_name cnn_class_name,c.confidence cnn_confidence,
                          c.model_id cnn_model_id,c.model_digest cnn_model_digest,c.status cnn_status
                   FROM asset_proposals p JOIN source_images s ON s.id=p.source_image_id
                   JOIN yolo_detections d ON d.id=p.detection_id
                   LEFT JOIN cnn_predictions c ON c.id=p.prediction_id WHERE p.id=?""",
                (int(proposal_id),),
            ).fetchone()
            if not proposal:
                raise ValueError("Suggestion proposal no longer exists.")
            integrity_reason = _source_integrity_reason(
                proposal["path"], proposal["content_sha256"])
            if integrity_reason:
                raise ValueError(f"Cannot review a stale suggestion: {integrity_reason}.")

            latest = connection.execute(
                "SELECT id,corrected_payload_json FROM correction_records WHERE proposal_id=? ORDER BY id DESC LIMIT 1",
                (int(proposal_id),),
            ).fetchone()
            latest_payload = json.loads(latest["corrected_payload_json"] or "{}") if latest else {}
            region = str(
                latest_payload.get("yolo_annotation_class_name")
                or latest_payload.get("class_name")
                or proposal["yolo_class_name"]
                or ""
            )
            effective_class_id = int(latest_payload.get(
                "yolo_annotation_class_id", proposal["yolo_class_id"]))
            from app.core.yolo_registry import is_approved_yolo_identity
            if not is_approved_yolo_identity(effective_class_id, region):
                raise ValueError("This suggestion is based on a historical YOLO class mapping.")
            if latest:
                raise ValueError("This suggestion is stale after a YOLO annotation correction.")
            bbox = json.loads(proposal["corrected_bbox_json"]) if proposal["corrected_bbox_json"] else [
                proposal[key] for key in ("x1", "y1", "x2", "y2")
            ]

            from app.core.proposals import (
                YOLO_FULLBODY_MAIN_TAGS,
                valid_normal_cnn_suggestion,
            )
            cnn_name = str(proposal["cnn_class_name"] or "").strip()
            task_head = None
            target_label = None
            origin = "No verified model suggestion"
            confidence = proposal["cnn_confidence"]
            if cnn_name:
                origin = "CNN suggestion"
                if valid_normal_cnn_suggestion(
                        proposal["cnn_model_id"], proposal["cnn_status"], cnn_name,
                        proposal["cnn_confidence"], region):
                    task_head = "clothing_broad"
                    target_label = cnn_name
                else:
                    task_head = None
            elif region.startswith("fullbody_") and region in YOLO_FULLBODY_MAIN_TAGS:
                task_head = "fullbody"
                target_label = YOLO_FULLBODY_MAIN_TAGS[region]
                origin = "YOLO-derived final-tag suggestion"
                confidence = proposal["yolo_confidence"]
            if not task_head or not target_label:
                raise ValueError("This crop has no verified task-specific model suggestion to approve or reject.")

            previous = connection.execute(
                "SELECT * FROM classification_task_reviews WHERE proposal_id=? AND task_head=? ORDER BY id DESC LIMIT 1",
                (int(proposal_id), task_head),
            ).fetchone()
            bbox_revision = int(latest["id"]) if latest else None
            provenance = {
                "workflow": "normal_processing",
                "origin": origin,
                "yolo": {
                    "class_name": proposal["yolo_class_name"],
                    "confidence": proposal["yolo_confidence"],
                    "model_id": proposal["yolo_model_id"],
                    "model_digest": proposal["yolo_model_digest"],
                },
                "cnn": {
                    "class_name": proposal["cnn_class_name"],
                    "confidence": proposal["cnn_confidence"],
                    "model_id": proposal["cnn_model_id"],
                    "model_digest": proposal["cnn_model_digest"],
                },
                "reviewed_yolo_class_name": region,
                "suggested_value": target_label,
            }
            from app.core.classification_taxonomy import REGISTRY_ID, REGISTRY_VERSION
            if task_head == "body_images":
                registry_id, registry_version = "newassetapp_unified_body_images_fullbody", "v2_five_head_shared_backbone_untrained"
            elif task_head == "clothing_broad":
                registry_id, registry_version = "clothing_classifier", "clothing-broad-v2-12class"
            else:
                registry_id, registry_version = REGISTRY_ID, REGISTRY_VERSION
            cursor = connection.execute(
                """INSERT INTO classification_task_reviews
                   (proposal_id,source_image_id,detection_id,task_head,target_label,suggestion_provenance_json,
                    source_sha256,crop_bbox_json,bbox_revision,registry_id,registry_version,workflow,
                    confirmation_status,human_confirmed,training_eligible,confirmed_at,staled_at,supersedes_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    int(proposal_id), int(proposal["source_id"]), int(proposal["detection_id"]),
                    task_head, target_label, json.dumps(provenance, sort_keys=True),
                    proposal["content_sha256"], json.dumps([float(value) for value in bbox]),
                    bbox_revision, registry_id, registry_version, "normal_processing",
                    action, 0 if action == "draft" else 0, 0,
                    None, None, int(previous["id"]) if previous else None,
                ),
            )
            return int(cursor.lastrowid)

    def save_normal_crop_choice(self, proposal_id: int, category: str,
                                body_image_main_tag: str | None = None, *,
                                main_tag: str | None = None, fullbody_state: str | None = None,
                                subtags: list[str] | None = None, location: str | None = None,
                                clothing_broad_family: str | None = None,
                                clothing_cover_area: str | None = None,
                                body_images_cnn_target: str | None = None,
                                body_images_cum_target: bool | None = None,
                                body_images_cum_evaluated: bool | None = None,
                                body_images_accessory_target: bool | None = None,
                                body_images_accessory_evaluated: bool | None = None,
                                body_images_completed: bool | None = None,
                                fullbody_cnn_target: str | None = None,
                                arousal_cnn_target: str | None = None,
                                corruption_cnn_target: str | None = None) -> None:
        """Save ordinary-user crop routing separately from professional review."""
        if category == "invalid":
            with self.connect() as connection:
                proposal = connection.execute(
                    """SELECT p.source_image_id,n.category,n.main_tag,n.fullbody_state,n.clothing_broad_family,
                              n.body_images_cnn_target,n.fullbody_cnn_target
                       FROM asset_proposals p LEFT JOIN normal_crop_choices n ON n.proposal_id=p.id
                       WHERE p.id=?""", (int(proposal_id),)
                ).fetchone()
                if not proposal:
                    raise ValueError("Crop proposal no longer exists.")
                connection.execute(
                    """INSERT INTO normal_crop_choices(proposal_id,source_image_id,category,is_invalid)
                       VALUES(?,?,'body_images',1) ON CONFLICT(proposal_id) DO UPDATE SET
                       is_invalid=1,updated_at=CURRENT_TIMESTAMP""",
                    (int(proposal_id), int(proposal["source_image_id"])),
                )
                previous_labels = []
                if proposal["category"] == "fullbody" and (proposal["fullbody_cnn_target"] or proposal["fullbody_state"]):
                    previous_labels.append(("unified_body_images_fullbody",
                                            proposal["fullbody_cnn_target"] or proposal["fullbody_state"],
                                            "fullbody"))
                elif proposal["category"] == "body_images" and proposal["body_images_cnn_target"]:
                    previous_labels.append(("unified_body_images_fullbody",
                                            proposal["body_images_cnn_target"], "body_images"))
                elif proposal["category"] == "clothing":
                    if proposal["clothing_broad_family"]:
                        previous_labels.append(("clothing_broad", proposal["clothing_broad_family"],
                                                "clothing_broad"))
                    if proposal["main_tag"]:
                        previous_labels.append(("clothing_fine", proposal["main_tag"], "clothing_fine"))
                connection.executemany(
                    "INSERT OR IGNORE INTO normal_crop_invalidated_examples(proposal_id,task,class_label,task_head) VALUES(?,?,?,?)",
                    [(int(proposal_id), task, label, head) for task, label, head in previous_labels],
                )
                connection.execute(
                    """INSERT OR IGNORE INTO normal_crop_invalidated_examples(proposal_id,task,class_label,task_head)
                       SELECT proposal_id,task,class_label,task_head FROM training_examples te
                       WHERE te.proposal_id=? AND NOT EXISTS(
                         SELECT 1 FROM training_examples newer WHERE newer.supersedes_id=te.id)
                       AND NOT EXISTS(SELECT 1 FROM normal_crop_invalidated_examples ni
                         WHERE ni.proposal_id=te.proposal_id AND ni.task=te.task
                           AND ni.task_head IS te.task_head AND ni.class_label=te.class_label)""",
                    (int(proposal_id),),
                )
                connection.execute("UPDATE asset_proposals SET review_status='review_required',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                                   (int(proposal_id),))
            return
        if category not in {"fullbody", "body_images", "clothing"}:
            raise ValueError("Choose Fullbody, Body Images, Clothing, or Invalid for this crop.")
        from app.core.classification_taxonomy import REGISTRY_VERSION, LOCATION_VALUES, validate_record
        resolved_main = main_tag or body_image_main_tag
        clean_subtags = list(dict.fromkeys(str(value) for value in (subtags or [])))
        if category == "fullbody" and not fullbody_state:
            raise ValueError("Choose a Fullbody state before exporting this crop.")
        if location and location not in LOCATION_VALUES:
            raise ValueError("Choose a canonical location from the current taxonomy.")
        validate_record(category, {"main_tag": resolved_main,
                                   "main_tags": [resolved_main] if resolved_main else [],
                                   "subtags": clean_subtags, "location": location,
                                   "state_spec": fullbody_state,
                                   "validity_state": "valid"})
        if category == "clothing":
            from app.core.crop_rules import clothing_cover_rule
            clothing_cover_rule(clothing_broad_family or "", clothing_cover_area or "")
        if body_images_cnn_target not in {None, "", "bodypart_cum", "bodypart_acc"}:
            raise ValueError("Choose a Body Images evidence class from the shared CNN registry.")
        if fullbody_cnn_target not in {None, "", "clothed", "topless", "bottomless", "bra", "panty"}:
            raise ValueError("Choose a Fullbody target from the shared CNN registry.")
        if arousal_cnn_target not in {None, "", "aroused", "edging"}:
            raise ValueError("Choose an Arousal target from the shared CNN registry.")
        if corruption_cnn_target not in {None, "", "slut", "conservative", "whore", "u_whore"}:
            raise ValueError("Choose a Corruption target from the shared CNN registry.")
        with self.connect() as connection:
            proposal = connection.execute(
                """SELECT p.id,p.source_image_id,p.detection_id,
                          n.body_images_cum_target,n.body_images_cum_evaluated,
                          n.body_images_accessory_target,n.body_images_accessory_evaluated,
                          n.body_images_completed
                   FROM asset_proposals p
                   LEFT JOIN normal_crop_choices n ON n.proposal_id=p.id
                   WHERE p.id=?""", (int(proposal_id),)
            ).fetchone()
            if not proposal:
                raise ValueError("Crop proposal no longer exists.")
            has_explicit_decision = any(value is not None for value in (
                body_images_cum_target, body_images_cum_evaluated,
                body_images_accessory_target, body_images_accessory_evaluated,
                body_images_completed,
            ))
            previous_has_decision = bool(
                proposal["body_images_cum_evaluated"]
                or proposal["body_images_accessory_evaluated"]
                or proposal["body_images_completed"]
            )
            if has_explicit_decision or previous_has_decision:
                def merge_decision(target_key: str, evaluated_key: str,
                                   target: bool | None,
                                   evaluated: bool | None,
                                   label: str):
                    if target is None and evaluated is None:
                        previous_target = proposal[target_key]
                        previous_evaluated = bool(proposal[evaluated_key])
                        return (
                            bool(previous_target) if previous_evaluated else None,
                            previous_evaluated,
                        )
                    is_evaluated = (target is not None if evaluated is None else bool(evaluated))
                    if not is_evaluated:
                        if target is not None:
                            raise ValueError(
                                f"An unevaluated {label} target must remain pending."
                            )
                        return None, False
                    if target not in {0, 1, False, True}:
                        raise ValueError(
                            f"{label} target must be true or false when evaluated."
                        )
                    return bool(target), True

                cum_target, cum_evaluated = merge_decision(
                    "body_images_cum_target", "body_images_cum_evaluated",
                    body_images_cum_target,
                    body_images_cum_evaluated, "Cum")
                accessory_target, accessory_evaluated = merge_decision(
                    "body_images_accessory_target", "body_images_accessory_evaluated",
                    body_images_accessory_target,
                    body_images_accessory_evaluated, "Accessory")
                completed = (
                    bool(cum_evaluated and accessory_evaluated
                         and proposal["body_images_completed"])
                    if body_images_completed is None else bool(body_images_completed)
                )
                body_decisions = _normalize_body_images_decisions({
                    "cum_target": cum_target, "cum_evaluated": cum_evaluated,
                    "accessory_target": accessory_target,
                    "accessory_evaluated": accessory_evaluated,
                    "body_images_completed": completed,
                })
            else:
                body_decisions = _normalize_body_images_decisions(
                    {}, body_images_cnn_target)
            if not str(resolved_main or "").strip():
                raise ValueError("Choose a main tag before assigning this category.")
            if category == "fullbody" and proposal["detection_id"] is not None:
                detection = connection.execute(
                    "SELECT class_id,class_name FROM yolo_detections WHERE id=?",
                    (int(proposal["detection_id"]),),
                ).fetchone()
                effective = self.effective_detection_state(int(proposal_id))
                if detection and effective["class_name"].casefold() == "person":
                    raise ValueError(
                        "A YOLO person region is an Others/corruption-training ROI and cannot be classified as Fullbody."
                    )
            connection.execute(
                """INSERT INTO normal_crop_choices(proposal_id,source_image_id,category,body_image_main_tag,
                   main_tag,fullbody_state,subtags_json,location_value,taxonomy_version,clothing_broad_family,
                   clothing_cover_area,body_images_cnn_target,fullbody_cnn_target,arousal_cnn_target,
                   corruption_cnn_target,body_images_cum_target,body_images_cum_evaluated,
                   body_images_accessory_target,body_images_accessory_evaluated,body_images_completed,is_invalid)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0) ON CONFLICT(proposal_id) DO UPDATE SET
                   category=excluded.category, body_image_main_tag=excluded.body_image_main_tag,
                   main_tag=excluded.main_tag, fullbody_state=excluded.fullbody_state,
                   subtags_json=excluded.subtags_json,location_value=excluded.location_value,
                   taxonomy_version=excluded.taxonomy_version,
                   clothing_broad_family=excluded.clothing_broad_family,
                   clothing_cover_area=excluded.clothing_cover_area,
                   body_images_cnn_target=excluded.body_images_cnn_target,
                   body_images_cum_target=excluded.body_images_cum_target,
                   body_images_cum_evaluated=excluded.body_images_cum_evaluated,
                   body_images_accessory_target=excluded.body_images_accessory_target,
                   body_images_accessory_evaluated=excluded.body_images_accessory_evaluated,
                   body_images_completed=excluded.body_images_completed,
                   fullbody_cnn_target=excluded.fullbody_cnn_target,
                   arousal_cnn_target=excluded.arousal_cnn_target,
                   corruption_cnn_target=excluded.corruption_cnn_target,
                   is_invalid=0,
                   updated_at=CURRENT_TIMESTAMP""",
                (int(proposal_id), int(proposal["source_image_id"]), category,
                 resolved_main if category == "body_images" else None, resolved_main, fullbody_state,
                 json.dumps(clean_subtags), location, REGISTRY_VERSION,
                 clothing_broad_family if category == "clothing" else None,
                 clothing_cover_area if category == "clothing" else None,
                 body_images_cnn_target if category == "body_images" else None,
                 fullbody_cnn_target if category == "fullbody" else None,
                 arousal_cnn_target, corruption_cnn_target,
                 (int(body_decisions["cum_target"]) if body_decisions["cum_target"] is not None else None),
                 int(body_decisions["cum_evaluated"]),
                 (int(body_decisions["accessory_target"]) if body_decisions["accessory_target"] is not None else None),
                 int(body_decisions["accessory_evaluated"]),
                 int(body_decisions["completed"]) if category == "body_images" else 0),
            )
    def confirm_normal_crop_classification(self, proposal_id: int) -> list[int]:
        """Save confirmed Normal Processing targets under their distinct CNN heads."""
        from app.core.classification_taxonomy import REGISTRY_ID, REGISTRY_VERSION
        from app.core.clothing_taxonomy import clothing_classes
        from app.core.classification_eligibility import shared_head_eligible
        with self.connect() as connection:
            row = connection.execute(
                """SELECT p.id,p.source_image_id,p.detection_id,s.path source_path,s.content_sha256,
                          COALESCE(p.corrected_bbox_json, json_array(d.x1,d.y1,d.x2,d.y2)) bbox_json,
                          d.class_id yolo_class_id,d.class_name yolo_class_name,
                          d.class_id yolo_original_class_id,d.class_name yolo_original_class_name,d.model_id yolo_model_id,
                          d.model_digest yolo_model_digest,d.confidence yolo_confidence,
                          c.class_name cnn_class_name,c.model_id cnn_model_id,c.model_digest cnn_model_digest,
                          c.confidence cnn_confidence,n.category,n.main_tag,n.fullbody_state,
                          n.subtags_json,n.location_value,n.taxonomy_version,n.clothing_broad_family,
                          n.body_images_cnn_target,n.fullbody_cnn_target,n.arousal_cnn_target,
                          n.corruption_cnn_target,n.body_images_cum_target,n.body_images_cum_evaluated,
                          n.body_images_accessory_target,n.body_images_accessory_evaluated,n.body_images_completed,
                          (SELECT cr.corrected_payload_json FROM correction_records cr
                           WHERE cr.proposal_id=p.id ORDER BY cr.id DESC LIMIT 1) latest_correction_json
                   FROM asset_proposals p JOIN source_images s ON s.id=p.source_image_id
                   JOIN yolo_detections d ON d.id=p.detection_id
                   JOIN normal_crop_choices n ON n.proposal_id=p.id
                   LEFT JOIN cnn_predictions c ON c.id=p.prediction_id
                   WHERE p.id=? AND s.content_sha256<>''""", (int(proposal_id),)
            ).fetchone()
            if not row:
                raise ValueError("Save this crop's classification before confirming it.")
            row = dict(row)
            integrity_reason = _source_integrity_reason(
                row["source_path"], row["content_sha256"])
            if integrity_reason:
                raise ValueError(f"Cannot confirm training data: {integrity_reason}.")
            if row.get("latest_correction_json"):
                latest = json.loads(row.pop("latest_correction_json"))
                row["yolo_class_name"] = (latest.get("yolo_annotation_class_name")
                                          or latest.get("class_name") or row["yolo_class_name"])
                if latest.get("yolo_annotation_class_id") is not None:
                    row["yolo_class_id"] = latest["yolo_annotation_class_id"]
            from app.core.yolo_registry import is_approved_yolo_identity
            if not is_approved_yolo_identity(
                    int(row["yolo_class_id"]), str(row["yolo_class_name"] or "")):
                raise ValueError(
                    "This historical YOLO class is not an exact match for the approved registry; "
                    "correct it before confirming training data."
                )
            category, label = row["category"], row["main_tag"]
            choice_state = connection.execute("SELECT is_invalid FROM normal_crop_choices WHERE proposal_id=?",
                                              (int(proposal_id),)).fetchone()
            if choice_state and choice_state["is_invalid"]:
                raise ValueError("This crop is marked invalid. Assign it to a different class before confirming training data.")
            if category == "fullbody":
                if row["fullbody_state"] not in {"clothed", "topless", "bottomless"}:
                    raise ValueError("Choose a Fullbody state before confirming this crop.")
            elif category == "body_images":
                if not label:
                    raise ValueError("Choose the human-confirmed YOLO region identity before confirming this crop.")
            elif category == "clothing":
                if not label:
                    raise ValueError("Choose a detailed Clothing tag before confirming this crop.")
                valid_families = {item["class_name"] for item in clothing_classes()}
                if row["clothing_broad_family"] not in valid_families:
                    raise ValueError("Choose a broad Clothing group before confirming this crop.")
            else:
                raise ValueError("Unsupported crop category for CNN training.")
            bbox = json.loads(row["bbox_json"] or "null")
            if not bbox or len(bbox) != 4:
                raise ValueError("Crop has no valid source-pixel coordinates.")
            subtags = json.loads(row["subtags_json"] or "[]")
            suggestions = {
                "yolo": {"class_id": row["yolo_original_class_id"],
                         "class_name": row["yolo_original_class_name"],
                         "model_id": row["yolo_model_id"], "model_digest": row["yolo_model_digest"],
                         "confidence": row["yolo_confidence"]},
                "cnn": {key: row[f"cnn_{key}"] for key in ("class_name", "model_id", "model_digest", "confidence")},
            }
            suggestions["reviewed_yolo_class_name"] = row["yolo_class_name"]
            model_targets = []
            region = str(row["yolo_class_name"] or "")
            shared_registry = "newassetapp_unified_body_images_fullbody"
            shared_version = "v2_five_head_shared_backbone_untrained"
            def add_shared(head: str, class_label: str, exact_labels: list[str] | None = None):
                model_targets.append(("unified_body_images_fullbody", head, class_label,
                                      shared_registry, shared_version, exact_labels or []))

            if category == "fullbody":
                fullbody_target = row["fullbody_cnn_target"] or row["fullbody_state"]
                if fullbody_target not in {"clothed", "topless", "bottomless", "bra", "panty"}:
                    raise ValueError("Choose a Fullbody CNN target from its five-class head.")
                if region == "person" or not (region == "fullbody" or region.startswith("fullbody_")):
                    raise ValueError("Fullbody CNN targets require a YOLO Fullbody detection; person is not Fullbody.")
                add_shared("fullbody", fullbody_target, subtags)
            elif category == "body_images":
                if region in {"face", "boobs", "ass", "pussy", "legs"}:
                    cum_evaluated = bool(row["body_images_cum_evaluated"])
                    accessory_evaluated = bool(row["body_images_accessory_evaluated"])
                    if cum_evaluated or accessory_evaluated:
                        cum_target = bool(row["body_images_cum_target"]) if cum_evaluated else None
                        accessory_target = bool(row["body_images_accessory_target"]) if accessory_evaluated else None
                        if cum_evaluated and not isinstance(row["body_images_cum_target"], (int, type(None))):
                            raise ValueError("Cum target must be a binary value.")
                        if accessory_evaluated and not isinstance(row["body_images_accessory_target"], (int, type(None))):
                            raise ValueError("Accessory target must be a binary value.")
                        target_mask = json.dumps({
                            "cum": {"target": cum_target, "evaluated": cum_evaluated},
                            "accessory": {"target": accessory_target, "evaluated": accessory_evaluated},
                        }, sort_keys=True)
                        if cum_evaluated and accessory_evaluated:
                            class_label = ("body_images_none" if (
                                not cum_target and not accessory_target
                            ) else "body_images_multi_label")
                        elif cum_evaluated:
                            class_label = "bodypart_cum"
                        elif accessory_evaluated:
                            class_label = "bodypart_acc"
                        else:
                            class_label = "body_images_pending"
                        model_targets.append(("unified_body_images_fullbody", "body_images", class_label,
                                              shared_registry, shared_version, subtags))
                        model_targets[-1] = (*model_targets[-1], target_mask)
                elif region == "portrait_frame" and label in {"portrait", "tportrait"}:
                    add_shared("portrait", label, [label])
                elif row["body_images_cnn_target"]:
                    raise ValueError("Body Images evidence requires a YOLO body-region crop, not a Portrait crop.")
            if row["arousal_cnn_target"]:
                if row["arousal_cnn_target"] not in {"aroused", "edging"}:
                    raise ValueError("Choose an Arousal class from the shared CNN registry.")
                if not shared_head_eligible("arousal", region):
                    raise ValueError(f"Arousal is not eligible for YOLO region {region!r}.")
                add_shared("arousal", row["arousal_cnn_target"])
            if row["corruption_cnn_target"]:
                if row["corruption_cnn_target"] not in {"slut", "conservative", "whore", "u_whore"}:
                    raise ValueError("Choose a Corruption class from the shared CNN registry.")
                if not shared_head_eligible("corruption", region):
                    raise ValueError(f"Corruption is not eligible for YOLO region {region!r}.")
                add_shared("corruption", row["corruption_cnn_target"])
            if category == "clothing":
                if not shared_head_eligible("clothing_broad", region):
                    raise ValueError(f"Clothing Broad is not eligible for YOLO region {region!r}.")
                if not shared_head_eligible("clothing_fine", region):
                    raise ValueError(f"Clothing Detailed is not eligible for YOLO region {region!r}.")
                model_targets = [("clothing_broad", "clothing_broad", row["clothing_broad_family"],
                                  "clothing_classifier", "clothing-broad-v2-12class", []),
                                 ("clothing_fine", "clothing_fine", label,
                                  REGISTRY_ID, REGISTRY_VERSION, subtags)]
            inserted = []
            for target_row in model_targets:
                task, head, class_label, taxonomy_id, taxonomy_version = target_row[:5]
                confirmed_labels = target_row[5] if len(target_row) > 5 else []
                target_mask_json = target_row[6] if len(target_row) > 6 else None
                if not class_label:
                    continue
                exact_labels_json = json.dumps(list(dict.fromkeys(confirmed_labels)))
                invalidated = connection.execute(
                    "SELECT 1 FROM normal_crop_invalidated_examples WHERE proposal_id=? AND task=? AND task_head IS ? AND class_label=?",
                    (int(proposal_id), task, head, class_label),
                ).fetchone()
                if invalidated:
                    raise ValueError("This classification was marked invalid. Choose a different class before confirming training data.")
                previous = connection.execute(
                    "SELECT * FROM training_examples WHERE proposal_id=? AND task=? AND task_head=? ORDER BY id DESC LIMIT 1",
                    (int(proposal_id), task, head),
                ).fetchone()
                if (previous and previous["source_sha256"] == row["content_sha256"]
                        and previous["class_label"] == class_label
                        and previous["crop_bbox_json"] == json.dumps(bbox)
                        and previous["human_confirmed_labels_json"] == exact_labels_json
                        and (target_mask_json is None or previous["target_mask_json"] == target_mask_json)):
                    inserted.append(int(previous["id"]))
                    continue
                cursor = connection.execute(
                    """INSERT INTO training_examples(source_image_id,proposal_id,detection_id,supersedes_id,
                       source_sha256,crop_bbox_json,task,class_label,taxonomy_id,taxonomy_version,
                       suggestion_provenance_json,workflow,human_confirmed,training_eligible,task_head,
                       human_confirmed_labels_json,target_mask_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,'normal_processing',1,1,?,?,?)""",
                    (int(row["source_image_id"]), int(row["id"]), int(row["detection_id"]),
                     int(previous["id"]) if previous else None, row["content_sha256"], json.dumps(bbox), task,
                     class_label, taxonomy_id, taxonomy_version, json.dumps(suggestions, sort_keys=True),
                     head, exact_labels_json, target_mask_json),
                )
                inserted.append(int(cursor.lastrowid))
            return inserted

    def current_training_examples(self, task: str | None = None, *,
                                  task_head: str | None = None,
                                  include_stale_media: bool = False) -> list[dict]:
        """Return the latest human-confirmed examples with unchanged source content."""
        allowed = {"yolo_detector", "unified_body_images_fullbody", "clothing_broad", "clothing_fine"}
        if task is not None and task not in allowed:
            raise ValueError(f"Unsupported training task: {task}")
        params: tuple = tuple(value for value in (task, task_head) if value is not None)
        clause = ("" if task is None else "AND te.task=?") + (
            "" if task_head is None else " AND te.task_head=?")
        with self.connect() as connection:
            rows = connection.execute(
                f"""SELECT te.*,s.path AS source_path,s.width,s.height,
                          d.class_id AS yolo_class_id,d.class_name AS yolo_class_name
                    FROM training_examples te
                    JOIN source_images s ON s.id=te.source_image_id
                    LEFT JOIN yolo_detections d ON d.id=te.detection_id
                    WHERE te.human_confirmed=1 AND te.training_eligible=1
                      AND te.source_sha256=s.content_sha256 {clause}
                      AND (te.workflow<>'professional_review' OR EXISTS(
                          SELECT 1 FROM correction_records cr
                          WHERE cr.id=te.correction_record_id
                            AND cr.id=(SELECT MAX(latest.id) FROM correction_records latest
                                       WHERE latest.proposal_id=te.proposal_id)
                            AND cr.final_state='confirmed' AND cr.human_confirmed=1)
                        OR EXISTS(SELECT 1 FROM classification_task_reviews tr
                                  WHERE tr.training_example_id=te.id
                                    AND tr.confirmation_status='confirmed'
                                    AND tr.human_confirmed=1 AND tr.training_eligible=1)
                        OR EXISTS(SELECT 1 FROM yolo_bbox_reviews br
                                   WHERE br.id=te.bbox_review_id
                                     AND br.review_status='approved'
                                     AND br.human_confirmed=1
                                     AND br.training_eligible=1
                                     AND br.detection_id=te.detection_id
                                     AND br.source_sha256=te.source_sha256))
                      AND NOT EXISTS(SELECT 1 FROM training_example_suppressions ts
                                     WHERE ts.training_example_id=te.id)
                      AND (te.workflow<>'normal_processing' OR NOT EXISTS(
                          SELECT 1 FROM correction_records reviewed
                          WHERE reviewed.proposal_id=te.proposal_id))
                      AND NOT EXISTS(SELECT 1 FROM normal_crop_invalidated_examples ni
                                     WHERE ni.proposal_id=te.proposal_id AND ni.task=te.task
                                       AND ni.task_head IS te.task_head AND ni.class_label=te.class_label)
                      AND NOT EXISTS(SELECT 1 FROM training_examples newer
                                     WHERE newer.supersedes_id=te.id)
                    ORDER BY te.source_sha256,te.proposal_id,te.task,te.id""", params
            ).fetchall()
            proposal_ids = sorted({int(row["proposal_id"]) for row in rows if row["proposal_id"] is not None})
            corrections_by_proposal: dict[int, list[dict]] = {}
            for offset in range(0, len(proposal_ids), 500):
                batch = proposal_ids[offset:offset + 500]
                placeholders = ",".join("?" for _ in batch)
                correction_rows = connection.execute(
                    f"""SELECT proposal_id,corrected_payload_json FROM correction_records
                        WHERE proposal_id IN ({placeholders}) ORDER BY id""", batch
                ).fetchall()
                for correction in correction_rows:
                    corrections_by_proposal.setdefault(int(correction["proposal_id"]), []).append(
                        json.loads(correction["corrected_payload_json"] or "{}"))
        values = []
        integrity_cache: dict[tuple[str, str], str | None] = {}
        from app.core.yolo_registry import approved_yolo_classes, is_approved_yolo_identity
        registry_names = approved_yolo_classes()
        registry_ids = {name: class_id for class_id, name in registry_names.items()}
        for row in rows:
            item = dict(row)
            class_id = int(item["yolo_class_id"]) if item.get("yolo_class_id") is not None else None
            class_name = item.get("yolo_class_name")
            for correction in corrections_by_proposal.get(int(item["proposal_id"]), []):
                if correction.get("yolo_annotation_class_id") is not None:
                    class_id = int(correction["yolo_annotation_class_id"])
                    class_name = correction.get("yolo_annotation_class_name")
            if item.get("detection_id") is not None:
                if item["task"] == "yolo_detector":
                    target_id = registry_ids.get(str(item.get("class_label") or ""))
                    valid_yolo = (
                        target_id is not None and class_id == target_id
                        and class_name == item["class_label"]
                    )
                else:
                    valid_yolo = is_approved_yolo_identity(class_id, class_name)
                if not valid_yolo:
                    if not include_stale_media:
                        continue
                    item["_training_block_reason"] = "yolo_class_id_name_registry_mismatch"
            cache_key = (str(Path(item["source_path"]).resolve()),
                         str(item.get("source_sha256") or ""))
            integrity_reason = integrity_cache.get(cache_key)
            if cache_key not in integrity_cache:
                integrity_reason = _source_integrity_reason(*cache_key)
                integrity_cache[cache_key] = integrity_reason
            if integrity_reason:
                if not include_stale_media:
                    continue
                item["_source_integrity_reason"] = integrity_reason
            for field, output in (("crop_bbox_json", "crop_bbox_xyxy"),
                                  ("suggestion_provenance_json", "suggestion_provenance"),
                                  ("human_confirmed_labels_json", "human_confirmed_labels")):
                item[output] = json.loads(item.pop(field))
            values.append(item)
        return values

    def current_corruption_training_examples(self, *,
                                             include_stale_media: bool = False) -> list[dict]:
        """Return confirmed corruption-state targets with unchanged source hashes."""
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT te.*,s.path AS source_path,s.width,s.height,
                          d.class_id AS yolo_class_id,d.class_name AS yolo_class_name,
                          cr.original_snapshot_json,cr.corrected_payload_json
                   FROM corruption_training_examples te
                   JOIN source_images s ON s.id=te.source_image_id
                   JOIN correction_records cr ON cr.id=te.correction_record_id
                   LEFT JOIN yolo_detections d ON d.id=cr.detection_id
                   WHERE te.human_confirmed=1 AND te.training_eligible=1
                     AND te.source_sha256=s.content_sha256
                     AND EXISTS(SELECT 1 FROM correction_records latest
                               WHERE latest.id=te.correction_record_id
                                 AND latest.id=(SELECT MAX(current.id) FROM correction_records current
                                                WHERE current.proposal_id=te.proposal_id)
                                 AND latest.final_state='confirmed' AND latest.human_confirmed=1)
                     AND NOT EXISTS(SELECT 1 FROM corruption_training_examples newer
                                    WHERE newer.supersedes_id=te.id)
                   ORDER BY te.source_sha256,te.proposal_id,te.id"""
            ).fetchall()
        values = []
        integrity_cache: dict[tuple[str, str], str | None] = {}
        from app.core.yolo_registry import is_approved_yolo_identity
        for row in rows:
            item = dict(row)
            corrected = json.loads(item.get("corrected_payload_json") or "{}")
            class_id = corrected.get("yolo_annotation_class_id", item.get("yolo_class_id"))
            class_name = corrected.get("yolo_annotation_class_name", item.get("yolo_class_name"))
            if item.get("yolo_class_id") is not None and not is_approved_yolo_identity(
                    int(class_id), class_name):
                if not include_stale_media:
                    continue
                item["_training_block_reason"] = "yolo_class_id_name_registry_mismatch"
            cache_key = (str(Path(item["source_path"]).resolve()),
                         str(item.get("source_sha256") or ""))
            integrity_reason = integrity_cache.get(cache_key)
            if cache_key not in integrity_cache:
                integrity_reason = _source_integrity_reason(*cache_key)
                integrity_cache[cache_key] = integrity_reason
            if integrity_reason:
                if not include_stale_media:
                    continue
                item["_source_integrity_reason"] = integrity_reason
            item["crop_bbox_xyxy"] = json.loads(item.pop("crop_bbox_json"))
            item["suggestion_provenance"] = json.loads(item.pop("suggestion_provenance_json"))
            values.append(item)
        return values

    def record_normal_crop_export(self, proposal_id: int, source_image_id: int, source_sha256: str,
                                  output_path: str, category: str, width: int, height: int,
                                  processing: dict, export_manifest: dict | None = None) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO normal_crop_exports
                   (proposal_id,source_image_id,source_sha256,output_path,category,width,height,format,processing_json,export_manifest_json)
                   VALUES (?,?,?,?,?,?,?,'webp',?,?)""",
                (int(proposal_id), int(source_image_id), source_sha256, output_path, category,
                 int(width), int(height), json.dumps(processing, sort_keys=True),
                 json.dumps(export_manifest, sort_keys=True) if export_manifest else None),
            )
            connection.execute(
                """INSERT INTO normal_crop_export_attempts
                   (proposal_id,source_sha256,status,output_path,message)
                   VALUES (?,?,'exported',?,NULL)""",
                (int(proposal_id), source_sha256, output_path),
            )
            return int(cursor.lastrowid)

    def record_normal_crop_export_attempt(self, proposal_id: int, source_sha256: str,
                                          status: str, output_path: str | None,
                                          message: str | None = None) -> int:
        if status not in {"exported", "failed"}:
            raise ValueError("Normal export attempt status must be exported or failed.")
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO normal_crop_export_attempts
                   (proposal_id,source_sha256,status,output_path,message) VALUES (?,?,?,?,?)""",
                (int(proposal_id), source_sha256, status, output_path, message),
            )
            return int(cursor.lastrowid)

    def normal_crop_export_count(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM normal_crop_exports").fetchone()[0])

    def record_final_asset(self, proposal_id: int, output_path: str, *, width: int, height: int,
                           processing: dict, format: str = "webp") -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO final_assets(proposal_id,output_path,width,height,format,
                   processing_json,validation_status) VALUES (?,?,?,?,?,?, 'exported')""",
                (proposal_id, output_path, width, height, format,
                 json.dumps(processing, sort_keys=True)),
            )
            return int(cursor.lastrowid)

    def create_manual_detection(self, source_image_id: int, bbox_xyxy: list[float],
                                class_id: int | None = None,
                                registry_id: str | None = None) -> int:
        """Persist a user-drawn region as an explicit human-originated YOLO Detection."""
        if len(bbox_xyxy) != 4:
            raise ValueError("Manual box must contain four source-pixel coordinates.")
        x1, y1, x2, y2 = map(float, bbox_xyxy)
        registry_path = (Path(__file__).resolve().parents[2] / "TrainingDatasetStudio"
                         / "registries" / "yolo_detector_v1.json")
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        if registry_id is not None and registry_id != registry["registry_id"]:
            raise ValueError("Manual Detection must use the approved target YOLO registry.")
        classes = {int(row["id"]): str(row["name"]) for row in registry["classes"]}
        if class_id is None:
            raise ValueError("Choose a canonical YOLO class before saving a manual Detection.")
        try:
            class_id = int(class_id)
        except (TypeError, ValueError) as error:
            raise ValueError("Choose a valid target YOLO class.") from error
        if class_id not in classes:
            raise ValueError("Choose a class from the approved target YOLO registry.")
        class_name = classes[class_id]
        with self.connect() as connection:
            source = connection.execute("SELECT * FROM source_images WHERE id=?", (source_image_id,)).fetchone()
            if not source or not (0 <= x1 < x2 <= source["width"] and 0 <= y1 < y2 <= source["height"]):
                raise ValueError("Manual box must be within an indexed source image.")
            detection_id = connection.execute(
                """INSERT INTO yolo_detections(source_image_id, model_id, class_id, class_name, confidence,
                   x1,y1,x2,y2,status) VALUES (?, 'user_manual', ?, ?, NULL, ?,?,?,?,'manual')""",
                (source_image_id, class_id, class_name, x1, y1, x2, y2),
            ).lastrowid
            from app.core.proposals import yolo_detection_disposition
            routed = yolo_detection_disposition(class_id, class_name, 1.0, [x1, y1, x2, y2])
            proposal_id = connection.execute(
                """INSERT INTO asset_proposals(source_image_id,detection_id,asset_type,category,confidence,review_status)
                   VALUES (?,?,?,?,?,?)""",
                (source_image_id, detection_id, routed.get("asset_type"),
                 routed.get("candidate_category") or "others", 1.0, "confirmed"),
            ).lastrowid
            original = {
                "origin": "manual", "bbox_xyxy": [x1, y1, x2, y2],
                "class_id": class_id, "class_name": class_name,
                "yolo_annotation_registry_id": registry["registry_id"],
                "yolo_annotation_class_id": class_id,
                "yolo_annotation_class_name": class_name,
                "source_path": source["path"], "source_sha256": source["content_sha256"],
            }
            connection.execute(
                """INSERT INTO correction_records(proposal_id,source_image_id,source_path,source_sha256,
                   detection_id,original_snapshot_json,corrected_payload_json,decision_type,final_state,
                   user_changed_prediction,human_confirmed,taxonomy_version)
                   VALUES (?,?,?,?,?,?,?,'manual_annotation','confirmed',1,1,?)""",
                (proposal_id, source_image_id, source["path"], source["content_sha256"], detection_id,
                 json.dumps(original, sort_keys=True), json.dumps(original, sort_keys=True),
                 str(registry["schema_version"])),
            )
            connection.execute(
                "UPDATE asset_proposals SET corrected_bbox_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (json.dumps([x1, y1, x2, y2]), proposal_id),
            )
            return int(detection_id)

    def count_sources(self) -> int:
        with self.connect() as connection:
            return connection.execute("SELECT COUNT(*) FROM source_images").fetchone()[0]

    def source_image_by_path(self, path: Path | str) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute("SELECT * FROM source_images WHERE path=?",
                                      (str(Path(path).resolve()),)).fetchone()

    def update_source_root(self, path: Path | str, root: Path | str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE source_images SET source_root=? WHERE path=?",
                               (str(Path(root).resolve()), str(Path(path).resolve())))

    def sources_needing_inference(self, folder: Path | str | None = None) -> list[sqlite3.Row]:
        with self.connect() as connection:
            expected = "content_sha256 || ':all32-review-v2'"
            sql = f"SELECT * FROM source_images WHERE inference_hash IS NULL OR inference_hash<>{expected}"
            params = ()
            if folder is not None:
                prefix = str(Path(folder).resolve())
                sql += " AND (path=? OR path LIKE ?)"
                params = (prefix, prefix.rstrip("\\/") + "\\%")
            return list(connection.execute(sql + " ORDER BY path", params))

    def set_source_inference_status(self, source_id: int, source_hash: str, status: str) -> None:
        if status not in {"pending", "processing", "completed", "failed"}:
            raise ValueError(f"Unsupported inference status: {status}")
        with self.connect() as connection:
            connection.execute(
                """UPDATE source_images SET inference_status=?, inference_hash=? WHERE id=?
                   AND content_sha256=?""",
                (status, f"{source_hash}:all32-review-v2" if status == "completed" else None, source_id, source_hash),
            )

    def category_counts(self) -> dict[str, int]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT category, COUNT(*) count FROM asset_proposals WHERE review_status<>'stale_source_version' GROUP BY category"
            ).fetchall()
        counts = {row["category"]: row["count"] for row in rows}
        with self.connect() as connection:
            counts["fullbody"] = connection.execute(
                """SELECT COUNT(*) FROM asset_proposals WHERE category='fullbody'
                   AND COALESCE(fullbody_output_category,'fullbody')='fullbody'
                   AND review_status<>'stale_source_version'"""
            ).fetchone()[0]
            for category in ("fullbody_topless", "fullbody_bottomless"):
                counts[category] = connection.execute(
                    """SELECT COUNT(*) FROM asset_proposals WHERE fullbody_output_category=?
                       AND review_status<>'stale_source_version'""", (category,)
                ).fetchone()[0]
        return counts

    def record_yolo_detection(self, source_image_id: int, *, model_id: str, model_digest: str,
                              class_id: int, class_name: str, confidence: float,
                              bbox_xyxy: list[float]) -> dict:
        """Persist raw detector evidence and create a review proposal for its original class."""
        if len(bbox_xyxy) != 4:
            raise ValueError("YOLO box must be [x1, y1, x2, y2] in source pixels.")
        if not math.isfinite(float(confidence)) or not 0 <= float(confidence) <= 1:
            raise ValueError("YOLO confidence must be a finite probability.")
        x1, y1, x2, y2 = (float(value) for value in bbox_xyxy)
        with self.connect() as connection:
            source = connection.execute("SELECT width,height FROM source_images WHERE id=?",
                                        (source_image_id,)).fetchone()
            if not source:
                raise ValueError("Source image does not exist.")
            if not (0 <= x1 < x2 <= source["width"] and 0 <= y1 < y2 <= source["height"]):
                raise ValueError("Detection box is invalid or outside the source image.")
            existing = connection.execute(
                """SELECT id FROM yolo_detections WHERE source_image_id=? AND model_digest=?
                   AND class_id=? AND class_name=? AND confidence=? AND x1=? AND y1=? AND x2=? AND y2=?
                   AND status='original'
                   ORDER BY id LIMIT 1""",
                (source_image_id, model_digest, class_id, class_name, confidence, x1, y1, x2, y2),
            ).fetchone()
            if existing:
                detection_id = int(existing["id"])
                previous_proposal = connection.execute(
                    "SELECT id FROM asset_proposals WHERE detection_id=? ORDER BY id LIMIT 1", (detection_id,)
                ).fetchone()
                if previous_proposal:
                    return {"detection_id": detection_id, "proposal_id": int(previous_proposal["id"]),
                            "status": "already_recorded", "class_id": class_id, "class_name": class_name,
                            "confidence": confidence, "bbox_xyxy": [x1, y1, x2, y2]}
            else:
                detection_id = connection.execute(
                """INSERT INTO yolo_detections(source_image_id, model_id, model_digest, class_id,
                   class_name, confidence, x1, y1, x2, y2) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (source_image_id, model_id, model_digest, class_id, class_name, confidence, x1, y1, x2, y2),
                ).lastrowid
            from app.core.proposals import yolo_detection_disposition
            routed = yolo_detection_disposition(class_id, class_name, confidence, [x1, y1, x2, y2])
            proposal_id = connection.execute(
                """INSERT INTO asset_proposals(source_image_id, detection_id, asset_type,
                   category, confidence, review_status) VALUES (?, ?, ?, ?, ?, ?)""",
                (source_image_id, detection_id, routed.get("asset_type"),
                 routed.get("candidate_category") or "others", confidence, routed["status"]),
            ).lastrowid
            disposition = routed["status"]
            return {"detection_id": int(detection_id), "proposal_id": int(proposal_id) if proposal_id else None,
                    "status": disposition, "class_id": class_id, "class_name": class_name,
                    "confidence": confidence, "bbox_xyxy": [x1, y1, x2, y2]}

    def create_manual_proposal(self, source_image_id: int) -> int:
        """Create an explicitly human-originated review item without synthetic AI provenance."""
        with self.connect() as connection:
            if not connection.execute("SELECT 1 FROM source_images WHERE id=?", (source_image_id,)).fetchone():
                raise ValueError("Source image does not exist.")
            cursor = connection.execute(
                """INSERT INTO asset_proposals(source_image_id, asset_type, category, confidence, review_status)
                   VALUES (?, NULL, 'others', NULL, 'pending')""", (source_image_id,))
            return int(cursor.lastrowid)

    def record_cnn_prediction(self, detection_id: int, *, model_id: str, model_digest: str,
                              class_name: str, confidence: float, probabilities: dict | None = None,
                              threshold: float = 0.77) -> dict:
        import json
        from app.core.proposals import suggest_proposal
        with self.connect() as connection:
            detection = connection.execute("SELECT * FROM yolo_detections WHERE id=?", (detection_id,)).fetchone()
            if not detection:
                raise ValueError("YOLO detection does not exist.")
            prediction = connection.execute(
                """SELECT id FROM cnn_predictions WHERE detection_id=? AND model_digest=?
                   AND class_name=? AND confidence=? ORDER BY id DESC LIMIT 1""",
                (detection_id, model_digest, class_name, confidence),
            ).fetchone()
            if prediction:
                prediction_id = int(prediction["id"])
            else:
                prediction_id = connection.execute(
                    """INSERT INTO cnn_predictions(detection_id, model_id, model_digest, class_name,
                       confidence, probabilities_json, status) VALUES (?,?,?,?,?,?,?)""",
                    (detection_id, model_id, model_digest, class_name, confidence,
                     json.dumps(probabilities, sort_keys=True) if probabilities is not None else None,
                     "ok" if confidence is not None and math.isfinite(float(confidence))
                     and 0 <= float(confidence) <= 1 else "review_required"),
                ).lastrowid
            existing = connection.execute("SELECT * FROM asset_proposals WHERE detection_id=? ORDER BY id LIMIT 1",
                                          (detection_id,)).fetchone()
            from app.core.proposals import YOLO_BODY_IMAGE_MAIN_CANDIDATES, YOLO_CLOTHING_REGION_CLASSES
            yolo_name = str(detection["class_name"])
            if (yolo_name.startswith("fullbody_") or yolo_name == "portrait_frame"
                    or yolo_name in YOLO_BODY_IMAGE_MAIN_CANDIDATES
                    or int(detection["class_id"]) == 0
                    or int(detection["class_id"]) in YOLO_CLOTHING_REGION_CLASSES):
                if not existing:
                    raise RuntimeError("YOLO review candidate was not persisted before CNN prediction.")
                connection.execute("UPDATE asset_proposals SET prediction_id=? WHERE id=?",
                                   (prediction_id, existing["id"]))
                return {"prediction_id": int(prediction_id), "proposal_id": int(existing["id"]),
                        "category": existing["category"], "review_status": existing["review_status"]}
            suggestion = suggest_proposal(class_name, confidence, threshold)
            if existing:
                if existing["review_status"] in {"confirmed", "rejected"}:
                    return {"prediction_id": int(prediction_id), "proposal_id": int(existing["id"]),
                            "category": existing["category"], "asset_type": existing["asset_type"],
                            "review_status": existing["review_status"]}
                connection.execute("""UPDATE asset_proposals SET prediction_id=?, asset_type=?, category=?,
                                   confidence=?, review_status=? WHERE id=?""",
                                   (prediction_id, suggestion.asset_type, suggestion.category,
                                    confidence, suggestion.review_status, existing["id"]))
                proposal_id = int(existing["id"])
            else:
                proposal_id = connection.execute(
                    """INSERT INTO asset_proposals(source_image_id, detection_id, prediction_id, asset_type,
                       category, confidence, review_status) VALUES (?,?,?,?,?,?,?)""",
                    (detection["source_image_id"], detection_id, prediction_id, suggestion.asset_type,
                     suggestion.category, confidence, suggestion.review_status),
                ).lastrowid
            return {"prediction_id": int(prediction_id), "proposal_id": int(proposal_id),
                    "category": suggestion.category, "asset_type": suggestion.asset_type,
                    "review_status": suggestion.review_status}

    def classification_review_state(self, detection_id: int, task: str) -> dict:
        if task not in {"fullbody_state", "body_images", "clothing_family"}:
            raise ValueError("Unsupported classification review task.")
        with self.connect() as connection:
            detection = connection.execute(
                "SELECT * FROM yolo_detections WHERE id=?", (detection_id,)
            ).fetchone()
            if not detection:
                raise ValueError("Detection no longer exists.")
            prediction = connection.execute(
                "SELECT * FROM cnn_predictions WHERE detection_id=? ORDER BY id DESC LIMIT 1",
                (detection_id,),
            ).fetchone()
            latest = connection.execute(
                """SELECT * FROM classification_review_records
                   WHERE detection_id=? AND task=? ORDER BY id DESC LIMIT 1""",
                (detection_id, task),
            ).fetchone()
        predicted = prediction["class_name"] if prediction and task == "clothing_family" else None
        event = latest["event_type"] if latest else None
        return {
            "detection_id": int(detection_id), "task": task,
            "predicted_label": predicted,
            "reviewed_label": latest["reviewed_label"] if latest else predicted,
            "status": "confirmed" if event == "confirmed" else
                      "needs_confirmation" if event in {"edited", "invalidated"} else "prediction_only",
            "event_type": event,
            "human_confirmed": bool(latest["human_confirmed"]) if latest else False,
            "event_id": int(latest["id"]) if latest else None,
        }

    def save_classification_edit(self, detection_id: int, task: str, reviewed_label: str,
                                 *, note: str | None = None) -> int:
        if task not in {"fullbody_state", "body_images", "clothing_family"}:
            raise ValueError("Unsupported classification review task.")
        label = str(reviewed_label or "").strip()
        if not label:
            raise ValueError("Choose a classification before saving the edit.")
        with self.connect() as connection:
            detection = connection.execute(
                "SELECT * FROM yolo_detections WHERE id=?", (detection_id,)
            ).fetchone()
            if not detection:
                raise ValueError("Detection no longer exists.")
            prediction = connection.execute(
                "SELECT * FROM cnn_predictions WHERE detection_id=? ORDER BY id DESC LIMIT 1",
                (detection_id,),
            ).fetchone()
            snapshot = {"yolo": {key: detection[key] for key in
                                 ("class_id", "class_name", "confidence", "model_id", "model_digest")},
                        "cnn": dict(prediction) if prediction else None}
            cursor = connection.execute(
                """INSERT INTO classification_review_records
                   (detection_id,source_image_id,task,prediction_snapshot_json,reviewed_label,event_type,note,human_confirmed)
                   VALUES (?,?,?,?,?,'edited',?,0)""",
                (detection_id, detection["source_image_id"], task,
                 json.dumps(snapshot, sort_keys=True), label, note),
            )
            return int(cursor.lastrowid)

    def confirm_classification(self, detection_id: int, task: str, reviewed_label: str) -> int:
        state = self.classification_review_state(detection_id, task)
        label = str(reviewed_label or "").strip()
        if not label:
            raise ValueError("Choose a classification before confirming it.")
        if state["event_type"] in {"edited", "invalidated"} and state["reviewed_label"] != label:
            raise ValueError("Save the classification edit first, then confirm that exact value.")
        if state["event_type"] == "confirmed" and state["reviewed_label"] == label:
            return int(state["event_id"])
        if state["event_type"] is None and state["predicted_label"] != label:
            raise ValueError("Save a human classification edit before confirming a value that differs from the model prediction.")
        with self.connect() as connection:
            detection = connection.execute(
                "SELECT * FROM yolo_detections WHERE id=?", (detection_id,)
            ).fetchone()
            if not detection:
                raise ValueError("Detection no longer exists.")
            prediction = connection.execute(
                "SELECT * FROM cnn_predictions WHERE detection_id=? ORDER BY id DESC LIMIT 1",
                (detection_id,),
            ).fetchone()
            snapshot = {"yolo": {key: detection[key] for key in
                                 ("class_id", "class_name", "confidence", "model_id", "model_digest")},
                        "cnn": dict(prediction) if prediction else None}
            cursor = connection.execute(
                """INSERT INTO classification_review_records
                   (detection_id,source_image_id,task,prediction_snapshot_json,reviewed_label,event_type,note,human_confirmed)
                   VALUES (?,?,?,?,?,'confirmed',NULL,1)""",
                (detection_id, detection["source_image_id"], task,
                 json.dumps(snapshot, sort_keys=True), label),
            )
            return int(cursor.lastrowid)

    def proposals_for_category(self, category: str) -> list[sqlite3.Row]:
        if category not in {"fullbody", "fullbody_topless", "fullbody_bottomless", "body_images", "clothing", "others"}:
            raise ValueError(f"Unsupported proposal category: {category}")
        with self.connect() as connection:
            return list(connection.execute(
                """SELECT p.*, s.path, s.width, s.height, s.content_sha256,
                          d.class_id AS yolo_class_id, d.class_name AS yolo_class_name,
                          d.confidence AS yolo_confidence, d.x1 AS yolo_x1, d.y1 AS yolo_y1,
                          d.x2 AS yolo_x2, d.y2 AS yolo_y2,
                          c.class_name AS cnn_class_name, c.confidence AS cnn_confidence,
                          c.model_id AS cnn_model_id, c.model_digest AS cnn_model_digest,
                          (SELECT cr.corrected_payload_json FROM correction_records cr
                           WHERE cr.proposal_id=p.id ORDER BY cr.id DESC LIMIT 1) AS latest_correction_json
                   FROM asset_proposals p JOIN source_images s ON s.id=p.source_image_id
                   LEFT JOIN yolo_detections d ON d.id=p.detection_id
                   LEFT JOIN cnn_predictions c ON c.id=p.prediction_id
                   WHERE p.category=? AND p.review_status<>'stale_source_version'
                     AND (?<>'fullbody' OR COALESCE(p.fullbody_output_category,'fullbody')='fullbody')
                     AND (? NOT IN ('fullbody_topless','fullbody_bottomless') OR p.fullbody_output_category=?)
                   ORDER BY p.id""", ("fullbody" if category in {"fullbody_topless", "fullbody_bottomless"} else category,
                                        category, category, category)
            ))

    def proposals_for_source(self, source_image_id: int) -> list[sqlite3.Row]:
        """Return every live proposal for a source so multi-box review can continue across categories."""
        with self.connect() as connection:
            return list(connection.execute(
                """SELECT p.*, s.path, s.width, s.height, s.content_sha256,
                          d.class_id AS yolo_class_id, d.class_name AS yolo_class_name,
                          d.confidence AS yolo_confidence, d.x1 AS yolo_x1, d.y1 AS yolo_y1,
                          d.x2 AS yolo_x2, d.y2 AS yolo_y2,
                          c.class_name AS cnn_class_name, c.confidence AS cnn_confidence,
                          c.model_id AS cnn_model_id, c.model_digest AS cnn_model_digest,
                          (SELECT cr.corrected_payload_json FROM correction_records cr
                           WHERE cr.proposal_id=p.id ORDER BY cr.id DESC LIMIT 1) AS latest_correction_json
                   FROM asset_proposals p JOIN source_images s ON s.id=p.source_image_id
                   LEFT JOIN yolo_detections d ON d.id=p.detection_id
                   LEFT JOIN cnn_predictions c ON c.id=p.prediction_id
                   WHERE p.source_image_id=? AND p.review_status<>'stale_source_version'
                   ORDER BY p.id""", (int(source_image_id),)
            ))

    def photoshoot_groups(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(connection.execute(
                """SELECT g.*, COUNT(m.proposal_id) AS member_count
                   FROM photoshoot_groups g LEFT JOIN photoshoot_memberships m ON m.group_id=g.id
                   GROUP BY g.id ORDER BY g.name COLLATE NOCASE"""
            ))

    def create_photoshoot_group(self, name: str) -> int:
        clean = name.strip()
        if not clean:
            raise ValueError("Group name cannot be empty.")
        with self.connect() as connection:
            cursor = connection.execute("INSERT INTO photoshoot_groups(name) VALUES (?)", (clean,))
            return int(cursor.lastrowid)

    def rename_photoshoot_group(self, group_id: int, name: str) -> None:
        clean = name.strip()
        if not clean:
            raise ValueError("Group name cannot be empty.")
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE photoshoot_groups SET name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (clean, group_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Photoshoot group no longer exists.")

    def delete_photoshoot_group(self, group_id: int) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM photoshoot_groups WHERE id=?", (group_id,))

    def photoshoot_members(self, group_id: int) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(connection.execute(
                """SELECT p.*, s.path, s.width, s.height, s.content_sha256,
                          d.class_id AS yolo_class_id, d.class_name AS yolo_class_name,
                          d.confidence AS yolo_confidence, d.x1 AS yolo_x1, d.y1 AS yolo_y1,
                          d.x2 AS yolo_x2, d.y2 AS yolo_y2,
                          c.class_name AS cnn_class_name, c.confidence AS cnn_confidence,
                          c.model_id AS cnn_model_id, c.model_digest AS cnn_model_digest,
                          (SELECT cr.corrected_payload_json FROM correction_records cr
                           WHERE cr.proposal_id=p.id ORDER BY cr.id DESC LIMIT 1) AS latest_correction_json
                   FROM photoshoot_memberships m
                   JOIN asset_proposals p ON p.id=m.proposal_id
                   JOIN source_images s ON s.id=p.source_image_id
                   LEFT JOIN yolo_detections d ON d.id=p.detection_id
                   LEFT JOIN cnn_predictions c ON c.id=p.prediction_id
                   WHERE m.group_id=? ORDER BY s.path, p.id""", (group_id,)
            ))

    def add_proposals_to_photoshoot(self, group_id: int, proposal_ids: list[int]) -> int:
        ids = list(dict.fromkeys(int(value) for value in proposal_ids))
        if not ids:
            return 0
        with self.connect() as connection:
            if not connection.execute(
                "SELECT 1 FROM photoshoot_groups WHERE id=?", (group_id,)
            ).fetchone():
                raise ValueError("Photoshoot group no longer exists.")
            placeholders = ",".join("?" for _ in ids)
            eligible = connection.execute(
                f"SELECT id FROM asset_proposals WHERE id IN ({placeholders}) "
                "AND category IN ('fullbody','body_images','clothing','others')", ids
            ).fetchall()
            eligible_ids = [row["id"] for row in eligible]
            if len(eligible_ids) != len(ids):
                raise ValueError("Only supported asset proposals can be manually assigned.")
            cursor = connection.executemany(
                "INSERT OR IGNORE INTO photoshoot_memberships(group_id, proposal_id) VALUES (?, ?)",
                [(group_id, proposal_id) for proposal_id in ids],
            )
            return cursor.rowcount

    def remove_proposals_from_photoshoot(self, group_id: int, proposal_ids: list[int]) -> int:
        ids = list(dict.fromkeys(int(value) for value in proposal_ids))
        if not ids:
            return 0
        with self.connect() as connection:
            cursor = connection.executemany(
                "DELETE FROM photoshoot_memberships WHERE group_id=? AND proposal_id=?",
                [(group_id, proposal_id) for proposal_id in ids],
            )
            return cursor.rowcount

    def save_correction(self, proposal_id: int | None, corrected: dict, *,
                        decision_type: str, final_state: str,
                        yolo_training_eligible: bool = False,
                        target_yolo_training_eligible: bool = False,
                        cnn_training_eligible: bool = False,
                        broad_clothing_training_eligible: bool = False,
                        clothing_cnn_training_eligible: bool = False,
                        unified_cnn_training_eligible: bool = False,
                        corruption_training_eligible: bool = False,
                        shared_cnn_training_tasks: list[str] | None = None,
                        model_version: str | None = None,
                        taxonomy_version: str = "newassetapp-phase3-review-v1") -> int:
        """Append a human decision while preserving a complete immutable AI snapshot."""
        allowed_decisions = {"confirmed_prediction", "annotation_confirmation", "corrected", "bbox_corrected", "reclassified",
                             "rejected", "manual_annotation", "tag_added"}
        allowed_decisions.add("classification_confirmation")
        if decision_type not in allowed_decisions:
            raise ValueError(f"Unsupported decision type: {decision_type}")
        corrected = dict(corrected)
        # Normalize the retired Body Images sub-main field at the API boundary
        # so validation, persistence, history, and export all see one taxonomy.
        if corrected.get("sub_main_tag"):
            legacy_subtag = corrected.pop("sub_main_tag")
            if corrected.get("category") == "body_images":
                corrected["subtags"] = list(dict.fromkeys(
                    list(corrected.get("subtags", [])) + [legacy_subtag]))
            elif corrected.get("category") == "fullbody":
                state = corrected.get("state_spec")
                if legacy_subtag not in {state, "normal" if state == "clothed" else state}:
                    raise ValueError("Legacy Fullbody sub-main value conflicts with the separately reviewed state.")
        if final_state not in {"confirmed", "rejected", "unclassified_fullbody", "corrected"}:
            raise ValueError("A reviewed record needs an explicit final state.")
        if decision_type == "rejected" or final_state == "unclassified_fullbody":
            target_yolo_training_eligible = False
        if decision_type == "rejected":
            corruption_training_eligible = False
            shared_cnn_training_tasks = []
        shared_cnn_training_tasks = list(dict.fromkeys(shared_cnn_training_tasks or []))
        from app.core.classification_eligibility import (
            BODY_IMAGES_LABELS, CORRUPTION_LABELS, FULLBODY_LABELS, PORTRAIT_LABELS,
            AROUSAL_LABELS, is_location_group, shared_head_eligible,
        )
        allowed_shared_heads = {"body_images", "fullbody", "portrait", "arousal", "corruption"}
        if set(shared_cnn_training_tasks) - allowed_shared_heads:
            raise ValueError("Unsupported shared CNN output head selected for training.")
        requested_training = any((yolo_training_eligible, target_yolo_training_eligible, cnn_training_eligible,
                                  broad_clothing_training_eligible,
                                  clothing_cnn_training_eligible,
                                  unified_cnn_training_eligible, corruption_training_eligible,
                                  bool(shared_cnn_training_tasks)))
        if requested_training and (final_state != "confirmed" or corrected.get("validity_state") != "valid"):
            raise ValueError("Training eligibility requires a human-confirmed, valid classification.")
        if decision_type != "rejected":
            corrected_category = corrected.get("category")
            if corrected_category in {"fullbody", "body_images", "clothing", "others"}:
                from app.core.classification_taxonomy import validate_record
                validate_record(corrected_category, {
                    **corrected,
                    "main_tags": ([corrected.get("main_tag")] if corrected.get("main_tag") else []),
                    "human_review_state": "confirmed" if final_state == "confirmed" else "edited_unconfirmed",
                })
            self._validate_reviewed_training_payload(corrected, yolo_training_eligible,
                                                     cnn_training_eligible,
                                                     broad_clothing_training_eligible,
                                                     clothing_cnn_training_eligible,
                                                     unified_cnn_training_eligible,
                                                     corruption_training_eligible,
                                                     decision_type=decision_type)
        if target_yolo_training_eligible:
            registry_path = Path(__file__).resolve().parents[2] / "TrainingDatasetStudio" / "registries" / "yolo_detector_v1.json"
            target_registry = json.loads(registry_path.read_text(encoding="utf-8"))
            classes = {int(item["id"]): item["name"] for item in target_registry["classes"]}
            target_class_id = corrected.get("yolo_annotation_class_id")
            if (corrected.get("yolo_annotation_registry_id") != target_registry["registry_id"]
                    or target_class_id not in classes
                    or corrected.get("yolo_annotation_class_name") != classes[target_class_id]
                    or not corrected.get("bbox_xyxy")
                    or final_state != "confirmed"
                    or corrected.get("validity_state") != "valid"):
                raise ValueError("Target YOLO training needs a confirmed, valid class and box from the approved 31-class registry.")
        with self.connect() as connection:
            proposal = None
            detection = None
            prediction = None
            if proposal_id is not None:
                proposal = connection.execute(
                    """SELECT p.*, s.path, s.content_sha256, s.width, s.height, s.id source_id
                       FROM asset_proposals p JOIN source_images s ON s.id=p.source_image_id WHERE p.id=?""",
                    (proposal_id,),
                ).fetchone()
                if not proposal:
                    raise ValueError("Proposal does not exist.")
                if proposal["detection_id"] is not None:
                    detection = connection.execute("SELECT * FROM yolo_detections WHERE id=?",
                                                   (proposal["detection_id"],)).fetchone()
                if proposal["prediction_id"] is not None:
                    prediction = connection.execute("SELECT * FROM cnn_predictions WHERE id=?",
                                                    (proposal["prediction_id"],)).fetchone()
                if (detection and int(detection["class_id"] if detection["class_id"] is not None else -1) == 0
                        and str(detection["class_name"]).casefold() == "person"
                        and corrected.get("category") == "fullbody"):
                    raise ValueError(
                        "A YOLO person region is an Others/corruption-training ROI and cannot be classified as Fullbody."
                    )
            else:
                source_id = corrected.get("source_image_id")
                proposal = connection.execute(
                    "SELECT id, source_image_id, path, content_sha256, width, height FROM source_images WHERE id=?",
                    (source_id,),
                ).fetchone()
                if not proposal:
                    raise ValueError("Source image does not exist.")
            original = {
                "source_image_id": proposal["source_image_id"] if "source_image_id" in proposal.keys() else proposal["id"],
                "source_path": proposal["path"], "source_sha256": proposal["content_sha256"],
                "image_width": proposal["width"], "image_height": proposal["height"],
                "proposal": {key: proposal[key] for key in proposal.keys() if key in
                             {"id", "asset_type", "category", "confidence", "review_status", "corrected_bbox_json",
                              "proposed_tags_json"}},
                "yolo": dict(detection) if detection else None,
                "cnn": dict(prediction) if prediction else None,
            }
            if shared_cnn_training_tasks:
                if (final_state != "confirmed" or corrected.get("validity_state") != "valid"
                        or not corrected.get("bbox_xyxy") or detection is None):
                    raise ValueError("Shared CNN head targets require a confirmed crop with valid YOLO provenance.")
                region = str(corrected.get("yolo_annotation_class_name")
                             or corrected.get("class_name") or detection["class_name"] or "")
                targets = {
                    "body_images": corrected.get("body_images_cnn_target"),
                    "fullbody": corrected.get("fullbody_cnn_target") or corrected.get("state_spec"),
                    "portrait": corrected.get("main_tag") or corrected.get("body_tag"),
                    "arousal": corrected.get("arousal_cnn_target"),
                    "corruption": corrected.get("corruption_classifier_target"),
                }
                portrait_target = targets["portrait"]
                portrait_confirmed = portrait_target if (
                    "portrait" in shared_cnn_training_tasks and portrait_target in PORTRAIT_LABELS
                ) else None
                if portrait_confirmed is None and region == "portrait_frame":
                    confirmed_row = connection.execute(
                        "SELECT reviewed_label FROM classification_review_records "
                        "WHERE detection_id=? AND task='portrait' AND event_type='confirmed' "
                        "ORDER BY id DESC LIMIT 1", (int(detection["id"]),)
                    ).fetchone()
                    if confirmed_row and confirmed_row["reviewed_label"] in PORTRAIT_LABELS:
                        portrait_confirmed = confirmed_row["reviewed_label"]
                    if portrait_confirmed is None:
                        confirmed_example = connection.execute(
                            "SELECT class_label FROM training_examples WHERE detection_id=? "
                            "AND task='unified_body_images_fullbody' AND task_head='portrait' "
                            "AND human_confirmed=1 ORDER BY id DESC LIMIT 1",
                            (int(detection["id"]),),
                        ).fetchone()
                        if confirmed_example and confirmed_example["class_label"] in PORTRAIT_LABELS:
                            portrait_confirmed = confirmed_example["class_label"]
                valid_targets = {
                    "body_images": BODY_IMAGES_LABELS,
                    "fullbody": FULLBODY_LABELS,
                    "portrait": PORTRAIT_LABELS,
                    "arousal": AROUSAL_LABELS,
                    "corruption": CORRUPTION_LABELS,
                }
                for head in shared_cnn_training_tasks:
                    target = targets[head]
                    if target not in valid_targets[head]:
                        raise ValueError(f"Choose a human-confirmed {head.replace('_', ' ')} target.")
                    if head == "body_images" and (not shared_head_eligible(head, region)
                                                   or not corrected.get("subtags")):
                        raise ValueError("Body Images evidence needs a body-region crop and separate exact human tags.")
                    if head in {"fullbody", "portrait", "arousal", "corruption"} and not shared_head_eligible(
                            head, region, confirmed_portrait=portrait_confirmed):
                        if head == "arousal":
                            raise ValueError("Arousal targets require face, ass, pussy, legs, or a portrait_frame with a confirmed portrait/tportrait result.")
                        if head == "portrait":
                            raise ValueError("Portrait head targets require a YOLO portrait_frame detection.")
                        if head == "corruption":
                            raise ValueError("Corruption targets require person, portrait_frame, or Fullbody detections.")
                        raise ValueError("Fullbody head targets require a YOLO Fullbody detection, not a person region.")
            if corrected.get("location_tag") and not is_location_group(
                    corrected.get("yolo_annotation_class_name") or corrected.get("class_name")
                    or (detection["class_name"] if detection else None)):
                raise ValueError("Location labels require a separate YOLO detection assigned to location_group.")
            changed = decision_type != "confirmed_prediction"
            annotation_confirmed = final_state in {"confirmed", "rejected", "unclassified_fullbody"}
            if decision_type == "rejected":
                yolo_training_eligible = cnn_training_eligible = broad_clothing_training_eligible = clothing_cnn_training_eligible = unified_cnn_training_eligible = False
            if final_state == "unclassified_fullbody":
                cnn_training_eligible = broad_clothing_training_eligible = clothing_cnn_training_eligible = unified_cnn_training_eligible = False
            corrected_category = corrected.get("category")
            fullbody_output = corrected.get("fullbody_output_category")
            if corrected_category is not None and corrected_category not in {"fullbody", "body_images", "clothing", "others"}:
                raise ValueError("Corrected proposal category is unsupported.")
            if fullbody_output is not None and fullbody_output not in {"fullbody", "fullbody_topless", "fullbody_bottomless"}:
                raise ValueError("Fullbody state output category is unsupported.")
            state_spec = corrected.get("state_spec")
            expected_output = {"normal": "fullbody", "clothed": "fullbody", "topless": "fullbody_topless",
                               "bottomless": "fullbody_bottomless"}.get(state_spec)
            if state_spec is not None and fullbody_output != expected_output:
                raise ValueError("Fullbody state and output category must agree and be supplied by a human.")
            if state_spec is not None and (corrected_category or "fullbody") == "fullbody":
                from app.core.fullbody_classification import fullbody_classification
                fullbody_classification(corrected.get("main_tag"), state_spec)
            prior_payload = {}
            if proposal_id is not None:
                prior_row = connection.execute(
                    "SELECT corrected_payload_json FROM correction_records WHERE proposal_id=? ORDER BY id DESC LIMIT 1",
                    (int(proposal_id),),
                ).fetchone()
                if prior_row:
                    prior_payload = json.loads(prior_row["corrected_payload_json"] or "{}")
            current_bbox = (json.loads(proposal["corrected_bbox_json"]) if proposal_id is not None
                            and proposal["corrected_bbox_json"] else
                            [detection[key] for key in ("x1", "y1", "x2", "y2")] if detection else None)
            updated_bbox = corrected.get("bbox_xyxy") or current_bbox
            prior_region = str(prior_payload.get("yolo_annotation_class_name") or
                               prior_payload.get("class_name") or (detection["class_name"] if detection else ""))
            updated_region = str(corrected.get("yolo_annotation_class_name") or
                                 corrected.get("class_name") or prior_region)
            geometry_changed = (current_bbox is not None and updated_bbox is not None
                                and [float(v) for v in current_bbox] != [float(v) for v in updated_bbox])
            class_changed = updated_region != prior_region
            cursor = connection.execute(
                """INSERT INTO correction_records
                   (proposal_id, source_image_id, source_path, source_sha256, detection_id,
                    original_snapshot_json, corrected_payload_json, decision_type, final_state,
                    user_changed_prediction, human_confirmed, yolo_training_eligible,
                    cnn_training_eligible, clothing_cnn_training_eligible,
                    unified_cnn_training_eligible, broad_clothing_training_eligible,
                    corruption_training_eligible, model_version, taxonomy_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (proposal_id, original["source_image_id"], original["source_path"], original["source_sha256"],
                 detection["id"] if detection else corrected.get("detection_id"),
                 __import__("json").dumps(original, sort_keys=True),
                 __import__("json").dumps(corrected, sort_keys=True), decision_type, final_state,
                  int(changed), int(annotation_confirmed), int(yolo_training_eligible), int(cnn_training_eligible),
                 int(clothing_cnn_training_eligible), int(unified_cnn_training_eligible),
                 int(broad_clothing_training_eligible), int(corruption_training_eligible), model_version, taxonomy_version),
            )
            if detection is not None and (geometry_changed or class_changed) and updated_bbox:
                self._invalidate_task_reviews(connection, int(detection["id"]), updated_bbox,
                                              int(cursor.lastrowid),
                                              "bbox_changed" if geometry_changed else "yolo_class_changed")
            if decision_type == "classification_confirmation":
                task_label = {
                    "fullbody": ("fullbody_state", corrected.get("state_spec")),
                    "body_images": ("body_images", corrected.get("main_tag")),
                    "clothing": ("clothing_family", corrected.get("clothing_family_tag")),
                }.get(corrected_category)
                if corrected_category == "others" and corrected.get("corruption_classifier_target"):
                    task_label = ("corruption_state", corrected["corruption_classifier_target"])
                if (not task_label or not task_label[1]) and not shared_cnn_training_tasks:
                    raise ValueError("Choose a human-reviewed classification before confirming this review.")
                if detection and task_label and task_label[1] and task_label[0] != "corruption_state":
                    latest_review = connection.execute(
                        "SELECT * FROM classification_review_records WHERE detection_id=? AND task=? ORDER BY id DESC LIMIT 1",
                        (int(detection["id"]), task_label[0]),
                    ).fetchone()
                    prediction = connection.execute(
                        "SELECT * FROM cnn_predictions WHERE detection_id=? ORDER BY id DESC LIMIT 1",
                        (int(detection["id"]),),
                    ).fetchone()
                    snapshot = {"yolo": {key: detection[key] for key in
                                         ("class_id", "class_name", "confidence", "model_id", "model_digest")},
                                "cnn": dict(prediction) if prediction else None}
                    if (latest_review and latest_review["event_type"] in {"edited", "invalidated"}
                            and latest_review["reviewed_label"] != task_label[1]):
                        raise ValueError("Save the classification edit before confirming its updated label.")
                    predicted_label = (prediction["class_name"] if prediction
                                       and task_label[0] == "clothing_family" else None)
                    if not latest_review and predicted_label != task_label[1]:
                        connection.execute(
                            """INSERT INTO classification_review_records
                               (detection_id,source_image_id,task,prediction_snapshot_json,reviewed_label,
                                event_type,note,human_confirmed) VALUES (?,?,?,?,?,'edited',?,0)""",
                            (int(detection["id"]), int(original["source_image_id"]), task_label[0],
                             json.dumps(snapshot, sort_keys=True), str(task_label[1]),
                             corrected.get("notes") or "Human-selected classification"),
                        )
                        latest_review = connection.execute(
                            "SELECT * FROM classification_review_records WHERE detection_id=? AND task=? ORDER BY id DESC LIMIT 1",
                            (int(detection["id"]), task_label[0]),
                        ).fetchone()
                    if not (latest_review and latest_review["event_type"] == "confirmed"
                            and latest_review["reviewed_label"] == task_label[1]):
                        connection.execute(
                            """INSERT INTO classification_review_records
                               (detection_id,source_image_id,task,prediction_snapshot_json,reviewed_label,
                                event_type,note,human_confirmed) VALUES (?,?,?,?,?,'confirmed',NULL,1)""",
                            (int(detection["id"]), int(original["source_image_id"]), task_label[0],
                             json.dumps(snapshot, sort_keys=True), str(task_label[1])),
                        )
            if target_yolo_training_eligible:
                if proposal_id is None:
                    raise ValueError("Target YOLO training examples require a saved proposal identity.")
                bbox = [float(value) for value in corrected["bbox_xyxy"]]
                width, height = int(proposal["width"] or 0), int(proposal["height"] or 0)
                if not (width > 0 and height > 0 and
                        0 <= bbox[0] < bbox[2] <= width and 0 <= bbox[1] < bbox[3] <= height):
                    raise ValueError("Target YOLO box must stay within the source image.")
                previous = connection.execute(
                    "SELECT * FROM training_examples WHERE proposal_id=? AND task='yolo_detector' ORDER BY id DESC LIMIT 1",
                    (int(proposal_id),),
                ).fetchone()
                bbox_json = json.dumps(bbox)
                class_name = corrected["yolo_annotation_class_name"]
                if not (previous and previous["source_sha256"] == original["source_sha256"]
                        and previous["class_label"] == class_name and previous["crop_bbox_json"] == bbox_json):
                    target_registry_path = Path(__file__).resolve().parents[2] / "TrainingDatasetStudio" / "registries" / "yolo_detector_v1.json"
                    target_registry = json.loads(target_registry_path.read_text(encoding="utf-8"))
                    prediction_provenance = {
                        "model_id": (original.get("yolo") or {}).get("model_id"),
                        "checkpoint_sha256": (original.get("yolo") or {}).get("model_digest"),
                        "class_id": (original.get("yolo") or {}).get("class_id"),
                        "class_name": (original.get("yolo") or {}).get("class_name"),
                        "confidence": (original.get("yolo") or {}).get("confidence"),
                        "original_bbox_xyxy": [float((original.get("yolo") or {}).get(key))
                                                for key in ("x1", "y1", "x2", "y2")]
                            if original.get("yolo") else None,
                        "target_registry_id": target_registry["registry_id"],
                    }
                    connection.execute(
                        """INSERT INTO training_examples(source_image_id,proposal_id,detection_id,supersedes_id,
                           source_sha256,crop_bbox_json,task,class_label,taxonomy_id,taxonomy_version,
                           suggestion_provenance_json,workflow,human_confirmed,training_eligible,
                           correction_record_id)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,'professional_review',1,1,?)""",
                        (int(original["source_image_id"]), int(proposal_id),
                         int(detection["id"]) if detection else corrected.get("detection_id"),
                         int(previous["id"]) if previous else None, original["source_sha256"], bbox_json,
                         "yolo_detector", class_name, target_registry["registry_id"],
                         str(target_registry["schema_version"]),
                         json.dumps(prediction_provenance, sort_keys=True), int(cursor.lastrowid)),
                    )
            if decision_type != "rejected" and corrected_category in {"fullbody", "body_images", "clothing", "others"}:
                structured_id = self._save_structured_classification(
                    connection, int(original["source_image_id"]), proposal_id,
                    int(detection["id"]) if detection else corrected.get("detection_id"),
                    corrected_category, corrected, original,
                    human_confirmed=annotation_confirmed,
                    eligible=any((yolo_training_eligible, cnn_training_eligible,
                                  broad_clothing_training_eligible, clothing_cnn_training_eligible,
                                  unified_cnn_training_eligible, corruption_training_eligible,
                                  bool(shared_cnn_training_tasks))),
                    event_type="confirmed" if annotation_confirmed else "edited",
                )
            if (decision_type != "rejected" and annotation_confirmed and corrected.get("validity_state") == "valid"
                    and proposal_id is not None and corrected.get("bbox_xyxy")):
                from app.core.classification_taxonomy import REGISTRY_ID, REGISTRY_VERSION
                examples = []
                if unified_cnn_training_eligible:
                    examples.append(("unified_body_images_fullbody", corrected.get("unified_cnn_class"),
                                     "newassetapp_unified_body_images_fullbody",
                                     str(corrected.get("unified_cnn_task") or "structured-v1"), None, []))
                if broad_clothing_training_eligible:
                    examples.append(("clothing_broad", corrected.get("clothing_family_tag"),
                                     "clothing_classifier", "clothing-broad-v2-12class",
                                     "clothing_broad", []))
                if clothing_cnn_training_eligible:
                    examples.append(("clothing_fine", corrected.get("clothing_tag"),
                                     REGISTRY_ID, REGISTRY_VERSION, "clothing_fine",
                                     corrected.get("subtags") or []))
                suggestion_provenance = {
                    "yolo": {key: (original.get("yolo") or {}).get(key)
                             for key in ("model_id", "model_digest", "class_id", "class_name", "confidence")},
                    "cnn": {key: (original.get("cnn") or {}).get(key)
                            for key in ("model_id", "model_digest", "class_name", "confidence")},
                    "reviewed_yolo_class_name": (corrected.get("yolo_annotation_class_name")
                                                  or corrected.get("class_name")
                                                  or (original.get("yolo") or {}).get("class_name")),
                }
                bbox_json = json.dumps([float(value) for value in corrected["bbox_xyxy"]])
                for task, label, taxonomy_id, taxonomy_version, task_head, human_labels in examples:
                    if not label:
                        continue
                    previous = connection.execute(
                        "SELECT * FROM training_examples WHERE proposal_id=? AND task=? AND task_head IS ? ORDER BY id DESC LIMIT 1",
                        (int(proposal_id), task, task_head),
                    ).fetchone()
                    human_labels_json = json.dumps(list(dict.fromkeys(human_labels)))
                    if (previous and previous["source_sha256"] == original["source_sha256"]
                            and previous["class_label"] == label
                            and previous["crop_bbox_json"] == bbox_json
                            and previous["human_confirmed_labels_json"] == human_labels_json):
                        continue
                    connection.execute(
                        """INSERT INTO training_examples(source_image_id,proposal_id,detection_id,supersedes_id,
                           source_sha256,crop_bbox_json,task,class_label,taxonomy_id,taxonomy_version,
                           suggestion_provenance_json,workflow,human_confirmed,training_eligible,
                           correction_record_id,task_head,human_confirmed_labels_json)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,'professional_review',1,1,?,?,?)""",
                        (int(original["source_image_id"]), int(proposal_id),
                         int(detection["id"]) if detection else corrected.get("detection_id"),
                         int(previous["id"]) if previous else None, original["source_sha256"], bbox_json,
                         task, str(label), taxonomy_id, taxonomy_version,
                         json.dumps(suggestion_provenance, sort_keys=True), int(cursor.lastrowid), task_head,
                         human_labels_json),
                    )
                shared_registry_id = "newassetapp_unified_body_images_fullbody"
                shared_registry_version = "v2_five_head_shared_backbone_untrained"
                shared_targets = {
                    "body_images": corrected.get("body_images_cnn_target"),
                    "fullbody": corrected.get("fullbody_cnn_target") or corrected.get("state_spec"),
                    "portrait": corrected.get("main_tag") or corrected.get("body_tag"),
                    "arousal": corrected.get("arousal_cnn_target"),
                    "corruption": corrected.get("corruption_classifier_target"),
                }
                for head in shared_cnn_training_tasks:
                    label = shared_targets[head]
                    exact_labels = (corrected.get("subtags") or []) if head in {"body_images", "fullbody"} else (
                        [label] if head == "portrait" and label else [])
                    exact_labels_json = json.dumps(list(dict.fromkeys(exact_labels)))
                    previous = connection.execute(
                        "SELECT * FROM training_examples WHERE proposal_id=? AND task='unified_body_images_fullbody' AND task_head=? ORDER BY id DESC LIMIT 1",
                        (int(proposal_id), head),
                    ).fetchone()
                    if (previous and previous["source_sha256"] == original["source_sha256"]
                            and previous["class_label"] == label
                            and previous["crop_bbox_json"] == bbox_json
                            and previous["human_confirmed_labels_json"] == exact_labels_json):
                        continue
                    connection.execute(
                        """INSERT INTO training_examples(source_image_id,proposal_id,detection_id,supersedes_id,
                           source_sha256,crop_bbox_json,task,class_label,taxonomy_id,taxonomy_version,
                           suggestion_provenance_json,workflow,human_confirmed,training_eligible,
                           correction_record_id,task_head,human_confirmed_labels_json)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,'professional_review',1,1,?,?,?)""",
                        (int(original["source_image_id"]), int(proposal_id), int(detection["id"]),
                         int(previous["id"]) if previous else None, original["source_sha256"], bbox_json,
                         "unified_body_images_fullbody", str(label), shared_registry_id,
                         shared_registry_version, json.dumps(suggestion_provenance, sort_keys=True),
                         int(cursor.lastrowid), head, exact_labels_json),
                    )
                if corruption_training_eligible:
                    registry_path = (Path(__file__).resolve().parents[2] / "data" / "models" /
                                     "corruption_state_classifier" / "class_registry.json")
                    registry = json.loads(registry_path.read_text(encoding="utf-8"))
                    target = corrected["corruption_classifier_target"]
                    previous = connection.execute(
                        "SELECT * FROM corruption_training_examples WHERE proposal_id=? ORDER BY id DESC LIMIT 1",
                        (int(proposal_id),),
                    ).fetchone()
                    same_record = (previous and previous["source_sha256"] == original["source_sha256"]
                                   and previous["class_label"] == target
                                   and previous["crop_bbox_json"] == bbox_json)
                    if not same_record:
                        provenance = {
                            **suggestion_provenance,
                            "target_model_id": registry["model_id"],
                            "target_registry_id": registry["registry_id"],
                            "human_correction_record_id": int(cursor.lastrowid),
                            "bbox_authority": "human_reviewed_crop",
                        }
                        connection.execute(
                            """INSERT INTO corruption_training_examples
                               (source_image_id,proposal_id,detection_id,correction_record_id,supersedes_id,
                                source_sha256,crop_bbox_json,task,class_label,model_id,taxonomy_id,
                                taxonomy_version,suggestion_provenance_json,workflow,human_confirmed,training_eligible)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'professional_review',1,1)""",
                            (int(original["source_image_id"]), int(proposal_id),
                             int(detection["id"]) if detection else corrected.get("detection_id"),
                             int(cursor.lastrowid), int(previous["id"]) if previous else None,
                             original["source_sha256"], bbox_json, "corruption_state", target,
                             registry["model_id"], registry["registry_id"],
                             str(registry["schema_version"]), json.dumps(provenance, sort_keys=True)),
                        )
            decision = "rejected" if decision_type == "rejected" else (
                "accepted" if decision_type == "confirmed_prediction" else "edited")
            if proposal_id is not None:
                connection.execute(
                    """INSERT INTO user_decisions(proposal_id, decision, original_label, corrected_label,
                       original_bbox_json, corrected_bbox_json, notes, human_confirmed)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (proposal_id, decision,
                     original["proposal"].get("asset_type"), corrected.get("main_tag") or corrected.get("clothing_tag") or corrected.get("asset_type"),
                     original["yolo"] and __import__("json").dumps([original["yolo"][key] for key in ("x1", "y1", "x2", "y2")]),
                     __import__("json").dumps(corrected.get("bbox_xyxy")) if corrected.get("bbox_xyxy") else None,
                      corrected.get("notes"), int(annotation_confirmed)),
                )
                connection.execute(
                    """UPDATE asset_proposals SET review_status=?, category=COALESCE(?, category),
                       asset_type=COALESCE(?, asset_type),
                       fullbody_output_category=CASE WHEN ? IS NOT NULL AND ?<>'fullbody' THEN NULL
                         ELSE COALESCE(?, fullbody_output_category) END,
                       corrected_bbox_json=COALESCE(?, corrected_bbox_json), updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                    ("rejected" if decision_type == "rejected" else
                     "confirmed" if annotation_confirmed else "review_required", corrected_category,
                     corrected.get("asset_type") or corrected.get("main_tag") or corrected.get("clothing_tag"),
                     corrected_category, corrected_category, fullbody_output,
                     __import__("json").dumps(corrected.get("bbox_xyxy")) if corrected.get("bbox_xyxy") else None,
                     proposal_id),
                )
            return int(cursor.lastrowid)

    @staticmethod
    def _save_structured_classification(connection, source_id: int, proposal_id: int | None,
                                        detection_id: int | None, task: str, payload: dict,
                                        original: dict, *, human_confirmed: bool,
                                        eligible: bool, event_type: str) -> int:
        from app.core.classification_taxonomy import (
            REGISTRY_ID, REGISTRY_VERSION, LOCATION_VALUES, location_candidates,
            legacy_fullbody_state_candidate,
        )
        import json

        subtags = list(dict.fromkeys(str(value) for value in payload.get("subtags", [])))
        location = payload.get("location_tag") or payload.get("location")
        if location and location not in LOCATION_VALUES:
            raise ValueError(f"Unknown canonical location: {location!r}")
        validity = payload.get("validity_state") or "unresolved"
        if validity not in {"valid", "invalid", "unresolved"}:
            raise ValueError("Unknown classification validity state.")
        corruption_state = payload.get("corruption_state")
        allowed_corruption = {"slut", "conservative", "whore", "u_whore", "ultimate_whore"}
        if corruption_state not in {None, "", "none", *allowed_corruption}:
            raise ValueError("Unknown corruption value.")
        if validity == "invalid" and eligible:
            raise ValueError("Invalid records cannot be marked eligible for training.")
        review_state = ("rejected" if payload.get("validity_state") == "invalid" else
                        "confirmed" if human_confirmed else "edited_unconfirmed")
        exclusion_reason = payload.get("exclusion_reason")
        if not eligible and not exclusion_reason:
            exclusion_reason = "not_human_confirmed" if not human_confirmed else "other"
        yolo = original.get("yolo") or {}
        cnn = original.get("cnn") or {}
        cnn_name = cnn.get("class_name")
        asset_class_map_path = Path(__file__).resolve().parents[2] / "models" / "asset_classifier" / "asset_class_map.json"
        asset_class_map = json.loads(asset_class_map_path.read_text(encoding="utf-8"))
        legacy_cnn_class_id = asset_class_map.get(cnn_name)
        suggestion = {
            "yolo": {key: yolo.get(key) for key in ("model_id", "model_digest", "class_id", "class_name", "confidence")},
            "cnn": {"model_id": cnn.get("model_id"), "checkpoint_identity": cnn.get("model_digest"),
                    "checkpoint_path": "models/asset_classifier/asset_classifier.pth",
                    "class_id": legacy_cnn_class_id, "class_name": cnn_name,
                    "confidence": cnn.get("confidence")},
            "legacy_fullbody_candidate": legacy_fullbody_state_candidate(
                cnn_name, model_id=cnn.get("model_id"), checkpoint_digest=cnn.get("model_digest")),
        }
        location_evidence = payload.get("location_evidence_class") or yolo.get("class_name")
        location_suggestions = location_candidates(
            location_evidence, registry_id=payload.get("location_evidence_registry_id"),
            model_id=payload.get("location_evidence_model_id") or yolo.get("model_id"),
            class_id=payload.get("location_evidence_class_id") if payload.get("location_evidence_class_id") is not None else yolo.get("class_id"),
            checkpoint_digest=payload.get("location_evidence_checkpoint_digest") or yolo.get("model_digest"))
        corruption_values = [value for value in subtags if value in allowed_corruption]
        requested_corruption = payload.get("corruption_values", [])
        if not isinstance(requested_corruption, (list, tuple)):
            raise ValueError("Corruption values must be a list of supported choices.")
        for value in requested_corruption:
            if value not in allowed_corruption:
                raise ValueError(f"Unknown corruption value: {value!r}")
            normalized = "u_whore" if value == "ultimate_whore" else value
            if normalized not in corruption_values:
                corruption_values.append(normalized)
        if corruption_state not in {None, "", "none"}:
            normalized = "u_whore" if corruption_state == "ultimate_whore" else corruption_state
            if normalized not in corruption_values:
                corruption_values.append(normalized)
        after = {
            "task": task,
            "record_type": "detection_crop" if detection_id is not None else ("manual_crop" if proposal_id is not None else "source_image"),
            "main_category": payload.get("main_tag") or payload.get("clothing_tag"),
            "fullbody_state": payload.get("state_spec") if task == "fullbody" else None,
            "clothing_family": payload.get("clothing_family_tag") if task == "clothing" else None,
            "subtags": subtags,
            "corruption_values": corruption_values,
            "location": location,
            "location_suggestions": location_suggestions,
            "validity_state": validity,
            "ai_suggestion": suggestion,
            "human_review_state": review_state,
            "human_confirmed": bool(human_confirmed),
            "training_eligible": bool(eligible),
            "exclusion_reason": exclusion_reason,
            "registry_id": REGISTRY_ID,
            "taxonomy_version": REGISTRY_VERSION,
        }
        lookup = ("proposal_id=? AND task=?", (proposal_id, task)) if proposal_id is not None else (
            "detection_id=? AND task=?", (detection_id, task)) if detection_id is not None else (None, None)
        existing = (connection.execute(f"SELECT * FROM structured_classifications WHERE {lookup[0]}", lookup[1]).fetchone()
                    if lookup[0] else None)
        before = dict(existing) if existing else None
        columns = ("source_image_id,proposal_id,detection_id,task,record_type,main_category,fullbody_state,"
                   "clothing_family,subtags_json,corruption_values_json,location_value,location_suggestions_json,"
                   "validity_state,ai_suggestion_json,human_review_state,human_confirmed,training_eligible,"
                   "exclusion_reason,registry_id,taxonomy_version")
        values = (source_id, proposal_id, detection_id, task, after["record_type"], after["main_category"],
                  after["fullbody_state"], after["clothing_family"], json.dumps(subtags),
                  json.dumps(after["corruption_values"]), location, json.dumps(location_suggestions), validity,
                  json.dumps(suggestion, sort_keys=True), review_state, int(human_confirmed), int(eligible),
                  exclusion_reason, REGISTRY_ID, REGISTRY_VERSION)
        if existing:
            connection.execute(
                "UPDATE structured_classifications SET record_type=?,main_category=?,fullbody_state=?,clothing_family=?,"
                "subtags_json=?,corruption_values_json=?,location_value=?,location_suggestions_json=?,validity_state=?,"
                "ai_suggestion_json=?,human_review_state=?,human_confirmed=?,training_eligible=?,exclusion_reason=?,"
                "registry_id=?,taxonomy_version=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                values[4:] + (int(existing["id"]),),
            )
            classification_id = int(existing["id"])
        else:
            cursor = connection.execute(
                f"INSERT INTO structured_classifications({columns}) VALUES ({','.join('?' for _ in values)})", values
            )
            classification_id = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO structured_classification_events(classification_id,event_type,before_json,after_json,actor) VALUES (?,?,?,?,?)",
            (classification_id, event_type, json.dumps(before, sort_keys=True) if before else None,
             json.dumps(after, sort_keys=True), __import__("getpass").getuser()),
        )
        return classification_id

    @staticmethod
    def _validate_reviewed_training_payload(corrected: dict, yolo_eligible: bool,
                                            cnn_eligible: bool, broad_clothing_eligible: bool,
                                            clothing_eligible: bool,
                                            unified_eligible: bool,
                                            corruption_eligible: bool,
                                            *, decision_type: str) -> None:
        data_dir = Path(__file__).resolve().parents[2] / "data"
        def tag_values(group: str) -> set[str]:
            filename = {"fullbody": "fullbody_tags.json", "body_images": "body_images_tags.json",
                        "clothing": "clothing_tags.json"}[group]
            payload = json.loads((data_dir / "tags" / filename).read_text(encoding="utf-8"))
            values = {entry.get("serialized_value") for entry in payload.get("entries", [])
                      if entry.get("selectable") and not entry.get("requires_review")}
            user_file = data_dir / "tags" / "user_tags.json"
            if user_file.exists():
                users = json.loads(user_file.read_text(encoding="utf-8"))
                values.update(entry.get("serialized_value") for entry in users.get("entries", [])
                              if entry.get("group") == group and not entry.get("deprecated"))
            return values
        category = corrected.get("category")
        location_tag = corrected.get("location_tag")
        if location_tag is not None and location_tag not in {
                "bathroom", "bar", "beach", "cafeteria", "class", "clinic", "coffee_shop",
                "home", "locker_room", "mall", "office", "park", "pier", "shower", "lounge"}:
            raise ValueError("Location choice must be one of the fifteen canonical location tags.")
        shared_path = data_dir / "tags" / "shared_corruption_tags.json"
        shared = json.loads(shared_path.read_text(encoding="utf-8"))
        corruption = corrected.get("corruption_subtag")
        if corruption is not None:
            if category not in shared["available_categories"] or corruption not in shared["values"]:
                raise ValueError("Corruption subtag is unavailable for this category.")
            if corruption in corrected.get("subtags", []):
                raise ValueError("Choose a corruption subtag only in its separate manual field.")
        validity = corrected.get("validity_state")
        if validity not in {None, "", "valid", "invalid"}:
            raise ValueError("Validity state must be valid or invalid.")
        corruption_state = corrected.get("corruption_state")
        if corruption_state not in {None, "", "none", "slut", "conservative", "whore", "ultimate_whore", "u_whore"}:
            raise ValueError("Corruption state is not in the reviewed taxonomy.")
        if corrected.get("corruption_training_eligible") and validity == "invalid":
            raise ValueError("Invalid records cannot enter corruption training data.")
        if corruption_eligible:
            registry_path = data_dir / "models" / "corruption_state_classifier" / "class_registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            valid_targets = {row["class_name"] for row in registry["classes"]}
            if (category != "others"
                    or corrected.get("corruption_classifier_target") not in valid_targets
                    or not corrected.get("bbox_xyxy")):
                raise ValueError("Corruption-state training needs one human-selected target and a reviewed person crop box.")
        if corruption_state == "ultimate_whore" and corrected.get("corruption_subtag") == "u_whore":
            raise ValueError("Historical u_whore must not be reclassified as ultimate_whore.")
        tag_field = {"fullbody": "main_tag", "body_images": "main_tag", "clothing": "clothing_tag"}.get(category)
        if tag_field and corrected.get(tag_field):
            if corrected[tag_field] not in tag_values(category):
                raise ValueError(f"Tag {corrected[tag_field]!r} is not a verified selectable {category} tag.")
        if category in {"fullbody", "body_images", "clothing"}:
            from app.core.classification_taxonomy import validate_record
            validate_record(category, {
                **corrected,
                "main_tags": [corrected.get("main_tag")] if corrected.get("main_tag") else [],
            })
        state_spec = corrected.get("state_spec")
        main_tag = corrected.get("main_tag")
        if state_spec == "topless" and main_tag != "clothed":
            raise ValueError("The only documented Fullbody topless composition is clothed_topless.")
        if state_spec == "bottomless" and main_tag not in {"clothed", "bikini"}:
            raise ValueError("Documented bottomless compositions are clothed_bottomless and bikini_bottomless.")
        if yolo_eligible:
            if corrected.get("no_objects") is True:
                if decision_type != "manual_annotation":
                    raise ValueError("An empty YOLO label requires an explicit manual background annotation.")
                if cnn_eligible or clothing_eligible:
                    raise ValueError("An empty image annotation cannot train a crop classifier.")
            else:
                from app.core.yolo_registry import approved_yolo_class_ids
                allowed = approved_yolo_class_ids()
                if corrected.get("class_id") not in allowed or not corrected.get("bbox_xyxy"):
                    raise ValueError("YOLO training requires an approved active class ID and a confirmed box.")
        if cnn_eligible:
            class_path = Path(__file__).resolve().parents[2] / "models" / "asset_classifier" / "asset_class_map.json"
            class_map = json.loads(class_path.read_text(encoding="utf-8"))
            if corrected.get("asset_cnn_class") not in class_map or not corrected.get("bbox_xyxy"):
                raise ValueError("Asset CNN training needs a mapped CNN class and a confirmed crop box.")
        if clothing_eligible:
            from app.core.clothing_taxonomy import clothing_classes, validate_final_clothing_tag
            family = corrected.get("clothing_family_tag")
            valid_families = {row["class_name"] for row in clothing_classes()}
            if (category != "clothing" or family not in valid_families
                    or corrected.get("clothing_tag") not in tag_values("clothing")
                    or not validate_final_clothing_tag(family, corrected.get("clothing_tag"))
                    or not corrected.get("bbox_xyxy")):
                raise ValueError("Clothing fine-grained training needs a family-matched verified human tag and crop box.")
        if broad_clothing_eligible:
            from app.core.clothing_taxonomy import clothing_classes
            family = corrected.get("clothing_family_tag")
            valid_families = {row["class_name"] for row in clothing_classes()}
            if category != "clothing" or family not in valid_families or not corrected.get("bbox_xyxy"):
                raise ValueError("Broad Clothing training needs a human-confirmed 12-class family and crop box.")
        if unified_eligible:
            unified_path = data_dir / "models" / "unified_body_images_fullbody" / "class_registry.json"
            unified = json.loads(unified_path.read_text(encoding="utf-8"))
            task = corrected.get("unified_cnn_task")
            label = corrected.get("unified_cnn_class")
            if task not in {"body_images", "fullbody_state"} or not corrected.get("bbox_xyxy"):
                raise ValueError("Unified CNN training needs a task-specific label and confirmed crop box.")
            output_group = "fullbody" if task == "fullbody_state" else task
            classes = {row["class_name"] for row in unified["output_groups"][output_group]["classes"]}
            if label not in classes:
                raise ValueError("Unified CNN training label is not in the selected task output group.")
            if task == "body_images" and category != "body_images":
                raise ValueError("Body Images CNN examples must remain in the Body Images task group.")
            if task == "fullbody_state" and (category != "fullbody" or corrected.get("state_spec") != label):
                raise ValueError("Fullbody state examples must match the human-confirmed Fullbody state.")

    def record_tag_change(self, action: str, before: dict | None, after: dict,
                          *, source_image_id: int | None = None,
                          taxonomy_version: str = "newassetapp-phase3-review-v1") -> int:
        if action not in {"add", "edit", "deprecate"}:
            raise ValueError("Tag change action must be add, edit, or deprecate.")
        if not after or not after.get("id"):
            raise ValueError("Tag change requires the saved tag record.")
        with self.connect() as connection:
            source = None
            if source_image_id is not None:
                source = connection.execute("SELECT path,content_sha256 FROM source_images WHERE id=?",
                                            (source_image_id,)).fetchone()
                if not source:
                    raise ValueError("Associated source image does not exist.")
            cursor = connection.execute(
                """INSERT INTO tag_change_records(action, tag_id, source_image_id, source_path,
                   source_sha256, before_json, after_json, taxonomy_version)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (action, str(after["id"]), source_image_id,
                 source["path"] if source else None, source["content_sha256"] if source else None,
                 json.dumps(before, sort_keys=True) if before else None,
                 json.dumps(after, sort_keys=True), taxonomy_version),
            )
            return int(cursor.lastrowid)

    def reviewed_training_records(self, task: str) -> list[sqlite3.Row]:
        column = {"yolo": "yolo_training_eligible", "asset_cnn": "cnn_training_eligible",
                  "clothing_cnn": "clothing_cnn_training_eligible",
                  "broad_clothing": "broad_clothing_training_eligible"}.get(task)
        if column is None:
            raise ValueError(f"Unsupported training task: {task}")
        with self.connect() as connection:
            return list(connection.execute(
                f"""SELECT c.*, s.width, s.height FROM correction_records c
                    JOIN source_images s ON s.id=c.source_image_id
                    WHERE c.human_confirmed=1 AND c.final_state<>'rejected' AND c.{column}=1
                      AND c.source_sha256=s.content_sha256
                    ORDER BY c.id"""
            ))

    def reviewed_unified_cnn_records(self, task: str | None = None) -> list[sqlite3.Row]:
        if task not in {None, "body_images", "fullbody_state"}:
            raise ValueError("Unified CNN task must be body_images or fullbody_state.")
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT c.*, s.width, s.height FROM correction_records c
                   JOIN source_images s ON s.id=c.source_image_id
                   WHERE c.human_confirmed=1 AND c.final_state<>'rejected'
                     AND c.unified_cnn_training_eligible=1 AND c.source_sha256=s.content_sha256
                   ORDER BY c.id"""
            ).fetchall()
        if task is None:
            return list(rows)
        return [row for row in rows if json.loads(row["corrected_payload_json"]).get("unified_cnn_task") == task]

    def assign_split(self, family: str, source_hash: str, *, seed: int,
                     proportions: tuple[float, float, float]) -> str:
        import hashlib
        total = sum(proportions)
        if len(proportions) != 3 or any(value <= 0 for value in proportions) or abs(total - 1) > 1e-8:
            raise ValueError("Split proportions must be three positive fractions summing to 1.")
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT split FROM dataset_split_assignments WHERE dataset_family=? AND source_sha256=?",
                (family, source_hash),
            ).fetchone()
            if existing:
                return str(existing["split"])
            value = int(hashlib.sha256(f"{seed}:{source_hash}".encode()).hexdigest()[:16], 16) / 16**16
            split = "train" if value < proportions[0] else ("val" if value < proportions[0] + proportions[1] else "test")
            connection.execute(
                "INSERT INTO dataset_split_assignments(dataset_family, source_sha256, split, seed) VALUES (?,?,?,?)",
                (family, source_hash, split, seed),
            )
            return split

    def clear_split_assignments(self, family: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM dataset_split_assignments WHERE dataset_family=?", (family,))
