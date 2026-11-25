# Girl Packer tag taxonomy extraction

Tag definitions live in the four group JSON files under `data/tags/`. `tag_inventory.json` is a derived audit index, not a second editable source.

| Group | Entries | Selectable | Review flagged | Sources |
|---|---:|---:|---:|---|
| fullbody | 23 | 19 | 2 | docs/girlpack_Guide.md, database/asset_tags/fullbody.json, database/asset_tags/fullbody_compositions.json, utils/fullbody_tags.py |
| body_images | 37 | 28 | 1 | docs/girlpack_Guide.md, database/asset_tags/bodyparts.json, database/vid_tags.json |
| photoshoots | 122 | 98 | 0 | docs/girlpack_Guide.md, database/shoots_tags.json, database/shoots_config.json |
| clothing | 223 | 111 | 6 | docs/girlpack_Guide.md, database/asset_tags/clothing.json, database/asset_tags/clothing_modifiers.json, database/clothing_definitions.json, gui/components/image_workshop_panel.py |

## Context and separation

Every record preserves source spelling, serialized value, parent/context, and provenance. `metadata` nodes describe source UI fields and are not selectable. Duplicate words in different contexts remain separate.

- **Fullbody** contains guide clothing states and only the three explicit current compositions. Clothing states are separate from standalone clothing assets.
- **Body Images** contains the guide's body-part bases and the stated subtags. Numeric suffixes such as `ass1` identify image-set variants, not tags.
- **Photoshoots** contains the shoot-helper vocabulary. Assignment and group membership are manual-only; model assignment is prohibited. Shoot names and workflow type IDs are metadata, not tags.
- **Clothing** contains the active standalone asset map. Modifier buckets and gameplay clothing definitions are kept in nonselectable namespaces. No colors are defined by the inspected active sources.

See `tag_review_required.json` and `reports/TAG_REVIEW_QUESTIONS.md` for unresolved spellings, parents, and combinations. `requires_review` entries are not normal suggestions. No tag is normalized or rewritten.
