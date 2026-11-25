from __future__ import annotations

import json
import os
import uuid
from pathlib import Path


GROUP_FILES = {
    "fullbody": "fullbody_tags.json",
    "body_images": "body_images_tags.json",
    "photoshoots": "photoshoot_tags.json",
    "clothing": "clothing_tags.json",
}


class TagLibrary:
    """Dynamically load the extracted JSON vocabulary and persist user tags separately."""

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)
        self.user_file = self.data_dir / "user_tags.json"

    def _builtins(self) -> list[dict]:
        result = []
        for group, filename in GROUP_FILES.items():
            payload = json.loads((self.data_dir / filename).read_text(encoding="utf-8"))
            if payload.get("group") != group:
                raise ValueError(f"Tag library group mismatch in {filename}.")
            result.extend(payload.get("entries", []))
        shared_path = self.data_dir / "shared_corruption_tags.json"
        if shared_path.exists():
            shared = json.loads(shared_path.read_text(encoding="utf-8"))
            for category in shared["available_categories"]:
                for value in shared["values"]:
                    if any(row.get("group") == category and row.get("serialized_value") == value
                           and row.get("selectable", True) for row in result):
                        continue
                    result.append({"id": f"shared_corruption|{value}", "name": value,
                                   "display_name": value, "serialized_value": value,
                                   "group": category, "tag_type": "subtag",
                                   "selectable": True, "requires_review": False,
                                   "source": "shared_corruption_vocabulary",
                                   "confidence": "confirmed", "context_path": ["corruption"]})
        return result

    def _user_entries(self) -> list[dict]:
        if not self.user_file.exists():
            return []
        payload = json.loads(self.user_file.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1 or not isinstance(payload.get("entries"), list):
            raise ValueError("user_tags.json has an unsupported schema; it was not changed.")
        return payload["entries"]

    def entries(self, *, group: str | None = None, include_metadata: bool = False,
                include_review: bool = False, include_deprecated: bool = False) -> list[dict]:
        values = self._builtins() + self._user_entries()
        return [dict(entry) for entry in values
                if (group is None or entry.get("group") == group)
                and (include_metadata or (entry.get("selectable", True) and entry.get("tag_type") != "metadata"))
                and (include_review or not entry.get("requires_review", False))
                and (include_deprecated or not entry.get("deprecated", False))
                and (include_metadata or entry.get("selectable", True))]

    def search(self, query: str, *, group: str | None = None,
               include_review: bool = False) -> list[dict]:
        needle = str(query or "").casefold().strip()
        rows = self.entries(group=group, include_metadata=True,
                            include_review=include_review, include_deprecated=True)
        if not needle:
            return rows
        fields = ("name", "display_name", "serialized_value", "description", "source")
        return [row for row in rows if any(needle in str(row.get(k, "")).casefold() for k in fields)]

    def _write_user_entries(self, entries: list[dict]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temp = self.user_file.with_name(self.user_file.name + ".tmp")
        content = json.dumps({"schema_version": 1, "entries": entries}, indent=2, ensure_ascii=False) + "\n"
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self.user_file)

    def add_user_tag(self, *, group: str, name: str, serialized_value: str,
                     parent_id: str | None = None, tag_type: str = "main",
                     description: str = "", examples: list[str] | None = None,
                     separators: list[str] | None = None) -> dict:
        if group not in GROUP_FILES:
            raise ValueError(f"Unknown tag group: {group}")
        if not str(name).strip() or not str(serialized_value).strip():
            raise ValueError("Both the original tag name and serialized value are required.")
        if tag_type not in {"main", "subtag", "modifier", "compound", "tag"}:
            raise ValueError(f"Invalid user tag type: {tag_type}")
        all_rows = self._builtins() + self._user_entries()
        parent = None
        if parent_id is not None:
            parent = next((row for row in all_rows if row.get("id") == parent_id), None)
            if parent is None or parent.get("group") != group:
                raise ValueError("A selected parent must exist in the same tag group.")
        context = list(parent.get("context_path", [])) + [parent.get("name", "")] if parent else ["user_created"]
        if any(row.get("group") == group and row.get("context_path") == context
               and row.get("serialized_value") == serialized_value for row in all_rows):
            raise ValueError("That serialized value already exists in this tag context.")
        row = {
            "id": f"user:{uuid.uuid4()}", "name": str(name), "display_name": str(name),
            "serialized_value": str(serialized_value), "group": group,
            "parent_id": parent_id, "tag_type": tag_type,
            "description": str(description), "examples": list(examples or []),
            "separators": list(separators or []), "source": "user_created",
            "source_reference": str(self.user_file), "confidence": "confirmed",
            "requires_review": False, "selectable": True, "context_path": context,
            "deprecated": False,
        }
        user_rows = self._user_entries()
        user_rows.append(row)
        self._write_user_entries(user_rows)
        return dict(row)

    def edit_user_tag(self, tag_id: str, **changes) -> dict:
        allowed = {"name", "serialized_value", "parent_id", "tag_type", "description", "examples", "separators"}
        if set(changes) - allowed:
            raise ValueError("Only user-created tag fields can be edited.")
        rows = self._user_entries()
        entry = next((row for row in rows if row.get("id") == tag_id), None)
        if entry is None:
            raise ValueError("Built-in tags are immutable; only user-created tags can be edited.")
        if changes.get("parent_id") is not None:
            parent = next((row for row in self._builtins() + rows if row.get("id") == changes["parent_id"]), None)
            if parent is None or parent.get("group") != entry["group"]:
                raise ValueError("A selected parent must exist in the same tag group.")
            entry["context_path"] = list(parent.get("context_path", [])) + [parent.get("name", "")]
        elif "parent_id" in changes:
            entry["context_path"] = ["user_created"]
        entry.update(changes)
        self._write_user_entries(rows)
        return dict(entry)

    def deprecate_user_tag(self, tag_id: str) -> dict:
        rows = self._user_entries()
        entry = next((row for row in rows if row.get("id") == tag_id), None)
        if entry is None:
            raise ValueError("Built-in tags cannot be deprecated; only user-created tags can be changed.")
        entry["deprecated"] = True
        self._write_user_entries(rows)
        return dict(entry)
