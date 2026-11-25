from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from app.core.database import Database
from app.core.proposals import YOLO_CLOTHING_REGION_CLASSES, active_yolo_class_ids
from app.core.yolo_registry import approved_yolo_classes
from app.core.classification_eligibility import eligible_shared_heads


APP_ROOT = Path(__file__).resolve().parents[2]
YOLO_CHECKPOINT = APP_ROOT / "models" / "yolo" / "best.pt"
CLOTHING_CHECKPOINT = APP_ROOT / "models" / "clothing_classifier" / "clothing_classifier_12class.pth"
CLOTHING_CLASS_MAP = APP_ROOT / "data" / "models" / "clothing_classifier_12class_map.json"
ASSET_CHECKPOINT = CLOTHING_CHECKPOINT  # backward-compatible import alias
ASSET_CLASS_MAP = CLOTHING_CLASS_MAP
CLOTHING_YOLO_CLASS_IDS = YOLO_CLOTHING_REGION_CLASSES
CLOTHING_BROAD_CLASSES = {"bra", "dress", "footwear", "lingerie", "outerwear", "pants",
                          "panty", "shirt", "shorts", "skirt", "socks", "top"}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def active_inference_class_ids() -> tuple[int, ...]:
    """All checkpoint classes are candidates; review and training roles are separate."""
    return tuple(sorted(active_yolo_class_ids()))


def eligible_shared_heads_for_detection(database: Database, detection: dict,
                                        class_name: str) -> set[str]:
    confirmed_portrait = None
    proposal_id = detection.get("proposal_id")
    if class_name == "portrait_frame" and proposal_id is not None:
        portrait = database.classification_task_status(int(proposal_id)).get("portrait") or {}
        if portrait.get("confirmation_status") == "confirmed" and portrait.get("human_confirmed"):
            confirmed_portrait = portrait.get("target_label")
    return eligible_shared_heads(class_name, confirmed_portrait=confirmed_portrait)


class ImageAssetAnalyzer:
    """YOLO plus the 12-class Clothing CNN when its reviewed checkpoint is installed."""

    def __init__(self, *, yolo_path: Path = YOLO_CHECKPOINT,
                 cnn_path: Path = CLOTHING_CHECKPOINT, class_map_path: Path = CLOTHING_CLASS_MAP,
                 yolo_confidence: float = 0.25, cnn_confidence: float = 0.77):
        import torch
        import torch.nn as nn
        from torchvision import models, transforms
        from ultralytics import YOLO

        self.torch = torch
        self.yolo_confidence = float(yolo_confidence)
        self.cnn_confidence = float(cnn_confidence)
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        yolo_path = self._resolve_path(yolo_path, YOLO_CHECKPOINT)
        cnn_path = self._resolve_path(cnn_path, CLOTHING_CHECKPOINT)
        class_map_path = self._resolve_path(class_map_path, CLOTHING_CLASS_MAP)
        expected_names = approved_yolo_classes()
        self.yolo = YOLO(str(yolo_path))
        raw_names = self.yolo.names
        names = {int(key): str(value) for key, value in raw_names.items()} if isinstance(raw_names, dict) else dict(enumerate(raw_names))
        if names != expected_names:
            raise ValueError(
                "YOLO checkpoint class IDs/names do not match the approved Studio registry; "
                "the checkpoint is historical-only and cannot create active detections."
            )
        self.yolo_digest = file_sha256(yolo_path)
        self.class_map = json.loads(class_map_path.read_text(encoding="utf-8"))
        if sorted(self.class_map.values()) != list(range(len(self.class_map))) or len(self.class_map) != 12:
            raise ValueError("Clothing CNN map must be the verified contiguous 12-label mapping.")
        expected_registry = json.loads((APP_ROOT / "data/models/clothing_classifier_registry.json").read_text(encoding="utf-8"))
        if [row["class_name"] for row in expected_registry["classes"]] != [
                name for name, _ in sorted(self.class_map.items(), key=lambda item: item[1])]:
            raise ValueError("Clothing model registry and 12-class map order differ.")
        self.index_to_label = {int(index): name for name, index in self.class_map.items()}
        self.clothing_indices = [index for index, name in self.index_to_label.items()
                                 if name in CLOTHING_BROAD_CLASSES]
        self.cnn = None
        self.cnn_digest = None
        self.cnn_disabled_reason = None
        self.transform = transforms.Compose([
            transforms.Resize(256), transforms.CenterCrop(224), transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        from app.core.shared_model_artifacts import load_active_shared_model
        self.shared_cnn, self.shared_model_info = load_active_shared_model(APP_ROOT)
        self.shared_head_registry = (json.loads((APP_ROOT / "data/models/unified_body_images_fullbody/class_registry.json").read_text(encoding="utf-8"))
                                     if self.shared_cnn is not None else None)
        if not cnn_path.is_file():
            self.cnn_disabled_reason = "12-class Clothing checkpoint has not been trained/installed."
        else:
            self.cnn_digest = file_sha256(cnn_path)
            model = models.resnet18(weights=None)
            model.fc = nn.Linear(model.fc.in_features, 12)
            checkpoint = torch.load(cnn_path, map_location="cpu")
            metadata = checkpoint.get("metadata", {}) if isinstance(checkpoint, dict) else {}
            weights = checkpoint.get("state_dict") if isinstance(checkpoint, dict) else None
            if metadata.get("class_count") != 12 or metadata.get("class_names") != [
                    name for name, _ in sorted(self.class_map.items(), key=lambda item: item[1])]:
                raise ValueError("Clothing checkpoint metadata does not match the current 12-class order.")
            if not isinstance(weights, dict):
                raise ValueError("Clothing CNN checkpoint is not a state dict.")
            model.load_state_dict(weights, strict=True)
            self.cnn = model.to(self.device).eval()

    @staticmethod
    def _resolve_path(path: Path | str | None, default: Path) -> Path:
        resolved = Path(path) if path else default
        return resolved if resolved.is_absolute() else (APP_ROOT / resolved).resolve()

    def analyze(self, database: Database, source_row: dict) -> dict:
        source_path = Path(source_row["path"])
        if file_sha256(source_path) != source_row["content_sha256"]:
            raise ValueError("Source changed after indexing; rescan before analysis.")
        results = self.yolo.predict(str(source_path), classes=list(active_inference_class_ids()),
                                    conf=self.yolo_confidence, verbose=False, device=str(self.device))
        detections = 0
        proposals = 0
        shared_suggestions = []
        # Body Images and Fullbody remain human-reviewed; Clothing CNN is optional
        # until its verified 12-class checkpoint is installed.
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                class_id = int(box.cls.item())
                class_name = str(result.names[class_id])
                if expected_name := approved_yolo_classes().get(class_id):
                    if class_name != expected_name:
                        raise ValueError("YOLO inference returned a class name inconsistent with the approved registry.")
                else:
                    raise ValueError("YOLO inference returned a class ID outside the approved registry.")
                confidence = float(box.conf.item())
                xyxy = [float(value) for value in box.xyxy[0].tolist()]
                detection = database.record_yolo_detection(
                    int(source_row["id"]), model_id="legacy_yolo", model_digest=self.yolo_digest,
                    class_id=class_id, class_name=class_name, confidence=confidence, bbox_xyxy=xyxy)
                detections += int(detection["status"] != "already_recorded")
                proposals += int(detection.get("proposal_id") is not None)
                x1, y1, x2, y2 = (int(round(value)) for value in xyxy)
                width, height = int(source_row["width"]), int(source_row["height"])
                x1, y1, x2, y2 = max(0, x1), max(0, y1), min(width, x2), min(height, y2)
                if x2 <= x1 or y2 <= y1:
                    continue
                with Image.open(source_path) as image:
                    crop = image.convert("RGB").crop((x1, y1, x2, y2))
                if self.shared_cnn is not None:
                    shared_tensor = self.shared_model_info["transform"](crop).unsqueeze(0)
                    with self.torch.inference_mode():
                        outputs = self.shared_cnn(shared_tensor)
                        groups = self.shared_head_registry["output_groups"]
                        eligible_heads = eligible_shared_heads_for_detection(
                            database, detection, class_name)
                        for head, logits in outputs.items():
                            if head not in eligible_heads:
                                continue
                            values = self.torch.softmax(logits, dim=1)[0]
                            score, class_index = values.max(dim=0)
                            label = groups[head]["classes"][int(class_index.item())]["class_name"]
                            shared_suggestions.append({
                                "detection_id": int(detection["detection_id"]), "task_head": head,
                                "class_label": label, "confidence": float(score.item()),
                                "probabilities": {item["class_name"]: float(values[index].item())
                                                  for index, item in enumerate(groups[head]["classes"])},
                                "model_id": "unified_body_images_fullbody_cnn",
                                "checkpoint_sha256": self.shared_model_info["checkpoint_sha256"],
                                "human_confirmed": False, "review_required": True,
                            })
                if class_id not in CLOTHING_YOLO_CLASS_IDS or self.cnn is None:
                    crop.close()
                    continue
                tensor = self.transform(crop).unsqueeze(0).to(self.device)
                crop.close()
                with self.torch.inference_mode():
                    logits = self.cnn(tensor)
                    if tuple(logits.shape) != (1, len(self.class_map)) or not bool(self.torch.isfinite(logits).all()):
                        raise ValueError("Asset CNN returned invalid logits.")
                    probabilities_tensor = self.torch.softmax(logits, dim=1)[0]
                    family_scores = probabilities_tensor.clone()
                    excluded = set(range(len(self.index_to_label))) - set(self.clothing_indices)
                    if excluded:
                        family_scores[list(excluded)] = float("-inf")
                    score, class_index = family_scores.max(dim=0)
                index = int(class_index.item())
                probabilities = {self.index_to_label[i]: float(probabilities_tensor[i].item())
                                 for i in range(len(self.index_to_label))}
                outcome = database.record_cnn_prediction(
                    detection["detection_id"], model_id="clothing_classifier", model_digest=self.cnn_digest,
                    class_name=self.index_to_label[index], confidence=float(score.item()),
                    probabilities=probabilities, threshold=self.cnn_confidence)
        database.set_source_inference_status(int(source_row["id"]), source_row["content_sha256"], "completed")
        status = "completed" if self.cnn is not None else "completed_with_clothing_model_unavailable"
        return {"source_image_id": int(source_row["id"]), "detections": detections,
                "proposals": proposals, "status": status, "device": str(self.device),
                "clothing_model_status": self.cnn_disabled_reason or "ready",
                "yolo_digest": self.yolo_digest, "clothing_classifier_digest": self.cnn_digest,
                "shared_cnn_status": ("ready" if self.shared_cnn is not None else "not_activated"),
                "shared_cnn_suggestions": shared_suggestions}
