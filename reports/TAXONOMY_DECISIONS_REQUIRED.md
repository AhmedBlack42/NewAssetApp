# Taxonomy Decisions Required

These decisions remain genuinely open after source comparison. No sample processing should begin until the user reviews them.

## 1. Promote Fullbody `athletic` as the canonical spelling?

- **Competing spellings:** guide `athletic`; YOLO class `fullbody_athletic`; source Fullbody map and current NewAssetApp serialized value `atheletic` (review-required).
- **Evidence:** Girl Packer guide's Fullbody type list and the unchanged YOLO class both use `athletic`; `database/asset_tags/fullbody.json` has the typo `Atheletic`→`atheletic`.
- **Current NewAssetApp behavior:** the row is retained with source provenance and blocked from ordinary selection; YOLO evidence routes as a review candidate. No alias is currently added.
- **Choices/consequences:** keep `atheletic` preserves source token exactly but leaves a spelling mismatch; use `athletic` for new canonical records and retain an `atheletic` read alias, without altering existing correction records or model class 23.
- **Recommendation:** make `athletic` canonical for new records after confirmation; retain `atheletic` as a legacy read alias and preserve `Atheletic` in source metadata.

## 2. Keep Body Images subtag compatibility/order unrestricted or define rules?

- **Competing interpretations:** guide permits multiple comma-separated subtags and lists corruption, fluid and location values, but gives no allowed combinations, exclusivity rules, or ordering semantics.
- **Current NewAssetApp behavior:** subtags are separately stored and serialized in reviewer order; all taxonomy-valid subtags can be composed, and shared corruption values remain manual.
- **Consequences:** unrestricted order preserves reviewer intent; allowlists by main tag reduce invalid game filenames but need source evidence.
- **Recommendation:** retain order and explicit human review until an authoritative game parser or more detailed guide defines compatibility.

## 3. Original modifier-parent hierarchy

- **Unresolved parents:** `t-shirt`, `skirt`, `bra`, `panty`, `thigh-high-stockings`, and `boots` appear as modifier groups in `clothing_modifiers.json` without exact matching selectable item parents in the current clothing item taxonomy.
- **Current NewAssetApp behavior:** preserve these source modifier groups as nonselectable/informational; no inferred parent or serialized alias is created.
- **Consequences:** linking by approximate spelling may attach modifiers to the wrong garment family; leaving unlinked preserves data without enabling category selection.
- **Recommendation:** keep informational until a source-level parent mapping is confirmed.
