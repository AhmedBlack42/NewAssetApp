# Existing Asset CNN to game clothing source mapping

**Status:** Evidence crosswalk only. CNN outputs remain raw suggestions; none are automatically renamed or confirmed. The Phase 4A audit found that Girl Packer's original `ai/naming.py` contains explicit broad-category mappings for `footwear`→`shoes`, `outerwear`→`outer`, and `panty`→`panties`. NewAssetApp now exposes these as pending category suggestions while preserving the original CNN labels; they do not select a specific garment.

The copied checkpoint strictly loads as torchvision ResNet-18 with a 26-output linear layer. Its exact index/name map is in `models/asset_classifier/asset_class_map.json`. Preprocessing is RGB, `Resize(256)`, `CenterCrop(224)`, `ToTensor()`, and ImageNet normalization (`mean=[0.485,0.456,0.406]`, `std=[0.229,0.224,0.225]`). The application retains the raw class, probability vector, checkpoint digest, crop/source relation, and human review outcome. The 0.75 threshold is a routing heuristic, not a measured calibration or accuracy result.

## Garment-related outputs

| CNN class (original ID) | Source evidence | Mapping status | Safe use |
|---|---|---|---|
| `bra` (7) | Exact source catalog category and `clothing_type`; multiple item records sit below it. | Broader category only | Suggest the bra family; require a human to select an actual source item. |
| `dress` (8) | Exact source item ID/tag exists; source `clothing_tags` token appears on several items. | Exact token plus one-to-many family | Preserve the raw output; do not choose one dress item automatically. |
| `footwear` (9) | No exact item token; Girl Packer `ai/naming.py` explicitly maps this model class to source category `shoes`. | Source-defined broad category candidate | Suggest `shoes` for human review; keep raw class and require selection of a specific garment. |
| `outerwear` (13) | The game catalog has category/type `outer`; Girl Packer `ai/naming.py` explicitly maps the model class to it. | Source-defined broad category candidate | Suggest `outer` for human review; keep raw class and require selection of a specific garment. |
| `pants` (14) | Exact `clothing_tags` token appears on two lower-body catalog items (including jeans/leggings examples). | Exact broad source token; several items | Suggest a broad family only; keep the crop reviewable. |
| `panty` (15) | Source category is plural `panties`; Girl Packer `ai/naming.py` explicitly maps this model class to that category. A `t_panty` video tag is also present. | Source-defined category candidate with distinct model spelling | Suggest `panties` for human review; preserve `panty` as original model class. |
| `pantyhose` (16) | Exact source item identifier and tag occur in a socks-category item. | Exact item/token | Candidate source item exists; confidence and correctness still require human review. |
| `shirt` (17) | Exact `clothing_tags` token appears on seven source items. | Exact broad source token; one-to-many items | Suggest a family; require item selection by a reviewer. |
| `shorts` (18) | Exact source tag appears on eight source items. | Exact broad source token; one-to-many items | Suggest a family; require item selection by a reviewer. |
| `skirt` (19) | Exact source tag appears on thirteen source items. | Exact broad source token; one-to-many items | Suggest a family; require item selection by a reviewer. |
| `socks` (20) | Exact source catalog category and `clothing_type`; individual entries include socks and stockings. | Broader category only | Suggest the source category; require a specific item decision. |
| `special_wear` (21) | No exact source item/category/tag match found. | No supported match | Preserve raw historical output; route to review/`others`. |
| `stockings` (22) | Exact source tag appears on seven items, including named stocking variants. | Exact broad source token; one-to-many items | Suggest a family; require a specific item decision. |
| `sweater` (23) | Exact source tag appears on one item (`uniform_sweater`). | Exact source token, narrow evidence | Keep as a suggestion only; one source item does not establish model reliability. |
| `utility_cover` (24) | No exact source item/category/tag match found. | No supported match | Preserve raw historical output; route to review/`others`. |
| `vest` (25) | No exact source item/category/tag match found. | No supported match | Preserve raw historical output; route to review/`others`. |

The other ten original CNN labels (`bodypart_ass`, `bodypart_boobs`, `bodypart_face`, `bodypart_legs`, `bodypart_portrait_clothed`, `bodypart_portrait_topless`, `bodypart_pussy`, and the three broad Fullbody state-group labels) are outside the clothing-item taxonomy. They remain unchanged in the original 26-class map.

## Architecture recommendation

Retain this CNN as a baseline and review-suggestion model. Keep its 26 labels, indices, raw score/vector, model digest, and source/crop identity immutable. A future clothing classifier can compare on the same human-confirmed, source-disjoint records. Its suitable use is parent-family suggestions where a source token exists; a garment-specific class must not be inferred from a broad output.

The source inventory defines category, individual item ID/name, `clothing_tags`, `covered_parts`, `base_value`, `revealingness`, and `protection`. Read these from the selected source record after a human selects an item. Do not make the CNN predict them. The source has `value` values in its separate quality-tag modifier mapping, but does not define an item field named `value`, `price`, or `coverage`; item `base_value` and `covered_parts` are kept under their exact names.

The other source-defined category bridges in `ai/naming.py` are suggestions only. A family/category candidate is not a canonical serialized garment tag; a reviewer must select a specific selectable item before output or training eligibility.

## Future Clothing CNN

Prefer a hierarchy: source catalog category → specific source item → optional source `clothing_tags` attributes. A class may be trained only when the item is visually distinguishable and has enough human-confirmed examples. The 140 source records include ten explicit `None` slot sentinels, which are retained but not offered as garment labels. No accuracy or reliability claim is made for the existing CNN without a held-out human-labeled set.
