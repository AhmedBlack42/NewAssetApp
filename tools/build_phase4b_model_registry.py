from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_MAP_PATH = ROOT / "models" / "asset_classifier" / "asset_class_map.json"
UNIFIED_DIR = ROOT / "data" / "models" / "unified_body_images_fullbody"
BODY_DATASET = ROOT / "train_data" / "unified_body_images_fullbody"
CLOTHING_DATASET = ROOT / "train_data" / "clothing_classifier"
PHASE_REGISTRY = ROOT / "data" / "models" / "phase4_model_registry.json"
BODY_SOURCE_MAP = {"bodypart_portrait_clothed": "portrait",
                   "bodypart_portrait_topless": "tportrait"}
NEW_TO_SOURCE = {"portrait": "bodypart_portrait_clothed",
                 "tportrait": "bodypart_portrait_topless"}
BODY_IMAGE_CLASSES = ["portrait", "tportrait", "bodypart_cum", "bodypart_acc"]
FULLBODY_STATES = ["clothed", "topless", "bottomless"]
YOLO_LOCATIONS = {"location_home": "home", "location_class": "class",
                  "location_office": "office", "location_bathroom": "bathroom",
                  "location_bar": "bar"}
CLOTHING_CLASSES = ["bra", "dress", "footwear", "lingerie", "outerwear", "pants",
                    "panty", "shirt", "shorts", "skirt", "socks", "top"]


def dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    original_map = json.loads(ORIGINAL_MAP_PATH.read_text(encoding="utf-8"))
    original_by_id = {index: name for name, index in original_map.items()}
    body_entries = []
    for class_id, name in enumerate(BODY_IMAGE_CLASSES):
        original_name = NEW_TO_SOURCE.get(name)
        old_id = original_map.get(original_name) if original_name else None
        app_tag = BODY_SOURCE_MAP.get(original_name) if original_name else None
        body_entries.append({"class_id": class_id, "class_name": name,
                             "original_class_id": old_id, "original_class_name": original_name,
                             "canonical_application_mapping": app_tag,
                             "task": "body_images", "trainable": True,
                             "human_review_required": True,
                             "mapping_status": "added_evidence_class_requires_labels" if old_id is None else "explicit_source_class_mapping"})
    fullbody_entries = [{"class_id": class_id, "class_name": name,
                         "original_class_id": None, "original_class_name": None,
                         "canonical_application_mapping": name,
                         "task": "fullbody_state", "trainable": True,
                         "human_review_required": True,
                         "mapping_status": "new_state_class_not_mapped_from_legacy_asset_cnn"}
                        for class_id, name in enumerate(FULLBODY_STATES)]
    old_fullbody = [{"original_class_id": original_map[name], "original_class_name": name,
                     "revised_mapping": None,
                     "status": "provenance_only_no_equivalence_to_three_state_head"}
                    for name in ("fullbody_clothed_states", "fullbody_costume_states", "fullbody_nude_states")]
    unified = {
        "schema_version": 1,
        "model_id": "unified_body_images_fullbody_cnn",
        "version": "v1_architecture_untrained",
        "model_identity_count": 1,
        "checkpoint_identity": "unified_body_images_fullbody_v1",
        "checkpoint_path": "models/unified_body_images_fullbody/asset_classifier_initialization_26class.pth",
        "checkpoint_status": "initialization_only_untrained",
        "source_checkpoint": "models/asset_classifier/asset_classifier.pth",
        "source_checkpoint_sha256": "EB1251DADE9293098E327F3E708BF92F0C5FC09C272C6CDDB0F4F04F210AE6D2",
        "architecture": "one ResNet-18 model identity with task-context-selected Body Images (4 logits) and Fullbody State (3 logits) output heads; one unified training pipeline/checkpoint",
        "backbone_reuse": ["conv1", "bn1", "layer1", "layer2", "layer3", "layer4"],
        "reinitialized_heads": {"body_images": {"input_features": 512, "output_count": 4},
                                "fullbody_state": {"input_features": 512, "output_count": 3}},
        "total_grouped_output_logits": 7,
        "original_asset_class_registry_count": 26,
        "output_groups": {
            "body_images": {"class_count": len(body_entries), "classes": body_entries,
                             "class_names_file": "train_data/unified_body_images_fullbody/classes/body_images_classes.txt"},
            "fullbody_state": {"class_count": len(fullbody_entries), "classes": fullbody_entries,
                                "class_names_file": "train_data/unified_body_images_fullbody/classes/fullbody_state_classes.txt"},
        },
        "legacy_fullbody_classes": old_fullbody,
        "training_performed": False,
        "review_policy": "AI outputs are proposals; human confirmation required; Body Images and Fullbody examples remain task-labeled within one dataset.",
    }
    UNIFIED_DIR.mkdir(parents=True, exist_ok=True)
    dump(UNIFIED_DIR / "class_registry.json", unified)
    for path in (UNIFIED_DIR / "body_images_classes.txt", BODY_DATASET / "classes" / "body_images_classes.txt"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(BODY_IMAGE_CLASSES) + "\n", encoding="utf-8")
    dump(BODY_DATASET / "classes" / "registry.json", unified)
    (UNIFIED_DIR / "fullbody_state_classes.txt").write_text("\n".join(FULLBODY_STATES) + "\n", encoding="utf-8")
    clothing = {"schema_version": 2, "model_id": "clothing_classifier",
                "checkpoint_identity": "clothing_classifier_12class_v1",
                "checkpoint_path": "models/clothing_classifier/clothing_classifier_12class.pth",
                "checkpoint_status": "not_trained_dataset_review_blocked",
                "architecture": "ResNet-18, output dimension 12",
                "taxonomy_version": "clothing-broad-v2-12class",
                "class_count": len(CLOTHING_CLASSES),
                "classes": [{"class_id": index, "class_name": name,
                             "display_name": name.replace("_", " ").title(),
                             "broad_family": name, "active": True,
                             "application_role": "broad_family_prediction",
                             "detailed_tag_selection": "human_only",
                             "taxonomy_version": "clothing-broad-v2-12class"}
                            for index, name in enumerate(CLOTHING_CLASSES)],
                "class_names_file": "train_data/clothing_classifier/classes/classes.txt",
                "legacy_checkpoint_provenance": {
                    "identity": "asset_classifier_26class_legacy",
                    "checkpoint": "models/clothing_classifier/clothing_classifier.pth",
                    "source_checkpoint": "models/asset_classifier/asset_classifier.pth",
                    "source_class_map": "models/asset_classifier/asset_class_map.json",
                    "class_count": 26,
                    "class_order_preserved": True,
                    "sha256": "EB1251DADE9293098E327F3E708BF92F0C5FC09C272C6CDDB0F4F04F210AE6D2"},
                "training_performed": False}
    dump(ROOT / "data" / "models" / "clothing_classifier_registry.json", clothing)
    dump(ROOT / "data" / "models" / "clothing_classifier_12class_map.json",
         {row["class_name"]: row["class_id"] for row in clothing["classes"]})
    dump(CLOTHING_DATASET / "classes" / "registry.json", clothing)
    (CLOTHING_DATASET / "classes" / "classes.txt").write_text("\n".join(CLOTHING_CLASSES) + "\n", encoding="utf-8")
    registry = {
        "schema_version": 2,
        "status": "one_unified_body_fullbody_cnn_plus_one_clothing_cnn",
        "models": {
            "yolo_detector": {"task": "object_detection", "checkpoint": "models/yolo/best.pt",
                              "source_manifest": "models/model_manifest.json#/models/yolo",
                              "class_count": 32, "class_names": "models/model_manifest.json#/models/yolo/class_names",
                              "training_performed": False},
            "unified_body_images_fullbody_cnn": {"task": "body_images_and_fullbody_state", "version": "v2_body_images_4class_fullbody_3state_untrained",
                                                  "registry": "data/models/unified_body_images_fullbody/class_registry.json",
                                                  "checkpoint": unified["checkpoint_path"], "checkpoint_status": "initialization_only_untrained",
                                                  "output_groups": {"body_images": 4, "fullbody_state": 3},
                                                  "one_model_identity": True, "training_performed": False},
            "clothing_classifier": {"task": "broad_clothing_family_classification", "version": "clothing-broad-v2-12class",
                                    "registry": "data/models/clothing_classifier_registry.json",
                                    "checkpoint": clothing["checkpoint_path"], "checkpoint_status": clothing["checkpoint_status"],
                                    "class_count": 12, "taxonomy_version": clothing["taxonomy_version"],
                                    "training_performed": False},
        },
        "retired_model_identities": {
            "portrait_classifier_v1": {"status": "superseded_by_unified_model", "checkpoint_preserved": "models/portrait_classifier/asset_classifier_26class_initialization.pth"},
            "fullbody_state_v1": {"status": "superseded_by_unified_model"},
            "asset_cnn_clothing_baseline": {"status": "renamed_application_role_clothing_classifier", "original_checkpoint_id_preserved": "asset_classifier"},
        },
    }
    dump(PHASE_REGISTRY, registry)
    pairs = {"supported_fluid_submain_pairs": ["boobs_cum", "ass_creampie"],
             "supported_submain_pairs": ["ass_bb"],
             "unsupported_or_unverified": "All other cum/creampie main/sub-main pairs remain per-record review blockers until confirmed.",
             "mutually_exclusive": True,
             "ordinary_subtag_values": ["slut", "conservative", "whore", "u_whore", "park"],
             "serialization": "<main>_<sub-main>-<ordinary-subtags><sequence>.webp",
             "source_conflict": "The legacy guide describes cum/creampie as subtags; latest user instruction makes them sub-main tags. Preserve legacy parser read support separately."}
    dump(ROOT / "data" / "models" / "body_images_composition_policy.json", pairs)
    location = {"schema_version": 1, "taxonomy_version": "locations-v2-15",
                "canonical_locations": ["bathroom", "bar", "beach", "cafeteria", "class", "clinic",
                                        "coffee_shop", "home", "locker_room", "mall", "office", "park",
                                        "pier", "shower", "lounge"],
                "yolo_class_mappings": YOLO_LOCATIONS,
                "unmapped_yolo_classes": {"location_outdoor": None, "location_bed": None},
                "automatic_tagging": False}
    dump(ROOT / "data" / "models" / "location_class_map.json", location)


if __name__ == "__main__":
    main()
