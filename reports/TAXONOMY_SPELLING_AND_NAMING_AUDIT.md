# Taxonomy, Spelling and Naming Audit

**Scope:** NewAssetApp taxonomy, UI routing, serialization, registries and cross-references compared with read-only Girl Packer references. No Girl Packer files were changed. This audit is before sample processing; no sample processing, dataset export, or model training was performed.

## Authoritative sources inspected

- Girl Packer `docs/girlpack_Guide.md`, including repeated Body Images, Fullbody and Corruption sections.
- Girl Packer `database/asset_tags/bodyparts.json`, `fullbody.json`, `fullbody_compositions.json`, `clothing.json`, `clothing_modifiers.json`, and `database/vid_tags.json`.
- Girl Packer `ai/naming.py` for its model-to-source-category mappings, Body Images filename validation and sequence proposal; `tools/pack_spec.py` for filename grammar validation.
- NewAssetApp `data/tags/{clothing_tags,fullbody_tags,body_images_tags,photoshoot_tags,shared_corruption_tags}.json`, `tag_inventory.json`, `tag_review_required.json`, `tag_grammar.json`, and clothing source inventory.
- NewAssetApp `data/models/yolo_class_policy.json`, `fullbody_classification_policy.json`, `models/model_manifest.json`, YOLO checkpoint file metadata, and Asset CNN `asset_class_map.json` / checkpoint.
- NewAssetApp `app/core/proposals.py`, `filename_grammar.py`, `fullbody_classification.py`, `output_exporter.py`, `database.py`, `dataset_exporter.py`, `gui/correction_dialog.py`, tests, and prior taxonomy/mapping reports.

## Taxonomy inventory

### Clothing main tags

- `ankle_socks` — game_source_clothing/socks, socks
- `assless_panties` — game_source_clothing/panties, panties
- `athletic_bra` — bra, game_source_clothing/bra
- `athletic_shorts` — game_source_clothing/lower, lower
- `bikini_bottom` — game_source_clothing/panties, lower
- `bikini_top` — game_source_clothing/bra, upper
- `blouse` — game_source_clothing/upper, upper
- `booty_shorts` — game_source_clothing/lower, lower
- `brief_panties` — game_source_clothing/panties, panties
- `buttplug` — buttplug, game_source_clothing/buttplug
- `calf_socks` — game_source_clothing/socks, socks
- `casual_leggings` — game_source_clothing/lower, lower
- `casual_shorts` — game_source_clothing/lower, lower
- `casual_skirt` — game_source_clothing/lower, lower
- `cheer_bloomers` — game_source_clothing/panties, panties
- `cheerleader skirt` — game_source_clothing/lower
- `cheerleader_top` — game_source_clothing/upper
- `clogs` — game_source_clothing/shoes, shoes
- `corset_top` — game_source_clothing/upper, upper
- `crop_top` — game_source_clothing/upper, upper
- `crotchless_butterfly_panties` — game_source_clothing/panties, panties
- `crotchless_panties` — game_source_clothing/panties, panties
- `denim_micro_shorts` — game_source_clothing/lower, lower
- `denim_shorts` — game_source_clothing/lower, lower
- `denim_skirt` — game_source_clothing/lower, lower
- `dress` — game_source_clothing/upper, upper
- `fishnet_stockings` — game_source_clothing/socks, socks
- `flip_flops` — game_source_clothing/shoes, shoes
- `g_string` — game_source_clothing/panties, panties
- `halter_top` — game_source_clothing/upper, upper
- `heels` — game_source_clothing/shoes, shoes
- `high_cut_panties` — game_source_clothing/panties, panties
- `high_heel_anklestrap` — game_source_clothing/shoes, shoes
- `high_heel_laceup` — game_source_clothing/shoes, shoes
- `high_heel_opentoe` — game_source_clothing/shoes, shoes
- `high_heel_platform` — game_source_clothing/shoes, shoes
- `high_heel_pump` — game_source_clothing/shoes, shoes
- `high_leg_panties` — game_source_clothing/panties, panties
- `hoodie` — game_source_clothing/outer, outer
- `jacket` — game_source_clothing/outer, outer
- `jean_shorts` — game_source_clothing/lower
- `jeans` — game_source_clothing/lower, lower
- `knee_socks` — game_source_clothing/socks, socks
- `lace_bra` — bra, game_source_clothing/bra
- `lace_panties` — game_source_clothing/panties, panties
- `lacy_bra` — game_source_clothing/bra
- `lacy_panties` — game_source_clothing/panties
- `latex_dress` — game_source_clothing/upper, upper
- `latex_stockings` — game_source_clothing/socks, socks
- `leather_corset_top` — game_source_clothing/upper, upper
- `leather_jacket` — game_source_clothing/outer, outer
- `leather_skirt` — game_source_clothing/lower, lower
- `leather_stockings` — game_source_clothing/socks, socks
- `leggings` — game_source_clothing/lower, lower
- `leotard` — game_source_clothing/upper, upper
- `lingerie_bd` — game_source_clothing/upper, upper
- `lingerie_botsp` — game_source_clothing/panties, panties
- `lingerie_legbd` — game_source_clothing/socks
- `lingerie_legsp` — game_source_clothing/socks, socks
- `lingerie_topsp` — bra, game_source_clothing/bra
- `micro_bikini_bottom` — game_source_clothing/panties, panties
- `micro_bikini_top` — bra, game_source_clothing/bra
- `micro_skirt` — game_source_clothing/lower, lower
- `micro_uniform_skirt` — game_source_clothing/lower, lower
- `mini_dress` — game_source_clothing/upper, upper
- `mini_skirt` — game_source_clothing/lower, lower
- `nippleclamp` — game_source_clothing/nipple_acc
- `onepiece_swimsuit` — game_source_clothing/upper, upper
- `open_cup_bra` — bra, game_source_clothing/bra
- `ordinary_bra` — bra, game_source_clothing/bra
- `pantyhose` — game_source_clothing/socks, socks
- `pasties` — game_source_clothing/nipple_acc
- `pasties_tassels` — game_source_clothing/nipple_acc
- `peekaboo_bikini_bottom` — game_source_clothing/panties, panties
- `peekaboo_bikini_top` — bra, game_source_clothing/bra
- `plain_bra` — bra, game_source_clothing/bra
- `plain_panties` — game_source_clothing/panties, panties
- `pussyclamp` — game_source_clothing/pussy_acc
- `pussyplug` — game_source_clothing/pussy_acc
- `pussyweights` — game_source_clothing/pussy_acc
- `scheerleader skirt` — game_source_clothing/lower
- `scheerleader_top` — game_source_clothing/upper
- `school_shirt` — game_source_clothing/upper
- `school_shirt_slut` — game_source_clothing/upper, upper
- `school_skirt` — game_source_clothing/lower, lower
- `school_skirt_slut` — game_source_clothing/lower, lower
- `sexy_corset` — game_source_clothing/upper, upper
- `sexy_maid_skirt` — game_source_clothing/lower, lower
- `sexy_maid_top` — game_source_clothing/upper, upper
- `sexy_nurse_bra` — bra, game_source_clothing/bra
- `sexy_nurse_dress` — game_source_clothing/upper, upper
- `sexy_nurse_thong` — game_source_clothing/panties, panties
- `sexy_princess` — game_source_clothing/upper, upper
- `sheer_bra` — bra, game_source_clothing/bra
- `sheer_corset` — game_source_clothing/upper, upper
- `sheer_dress` — game_source_clothing/upper, upper
- `sheer_panties` — game_source_clothing/panties, panties
- `sheer_shorts` — game_source_clothing/lower, lower
- `sheer_top` — game_source_clothing/upper, upper
- `short_dress` — game_source_clothing/upper, upper
- `short_shorts` — game_source_clothing/lower, lower
- `short_skirt` — game_source_clothing/lower, lower
- `short_socks` — game_source_clothing/socks, socks
- `skinny_jeans` — game_source_clothing/lower, lower
- `sleeveless_shirt` — game_source_clothing/upper, upper
- `sneakers` — game_source_clothing/shoes, shoes
- `sports_bra` — bra, game_source_clothing/bra
- `strapless_bra` — bra, game_source_clothing/bra
- `strapless_top` — game_source_clothing/upper, upper
- `sundress` — game_source_clothing/upper, upper
- `t_shirt` — game_source_clothing/upper, upper
- `tail_buttplug` — game_source_clothing/buttplug
- `tank_top` — game_source_clothing/upper, upper
- `tennis_shoe` — game_source_clothing/shoes, shoes
- `thigh_stockings` — game_source_clothing/socks, socks
- `thong` — game_source_clothing/panties, panties
- `transparent_bra` — bra, game_source_clothing/bra
- `transparent_panties` — game_source_clothing/panties, panties
- `transparent_stockings` — game_source_clothing/socks, socks
- `transparent_top` — game_source_clothing/upper, upper
- `tube_top` — game_source_clothing/upper, upper
- `uniform_flats` — game_source_clothing/shoes, shoes
- `uniform_shirt` — game_source_clothing/upper, upper
- `uniform_skirt` — game_source_clothing/lower, lower
- `uniform_stockings` — game_source_clothing/socks, socks
- `uniform_sweater` — game_source_clothing/outer, outer
- `vibrating_buttplug` — buttplug, game_source_clothing/buttplug
- `vibrating_nippleclamp` — game_source_clothing/nipple_acc
- `vibrating_pussyplug` — game_source_clothing/pussy_acc
- `weighted_pussyplug` — game_source_clothing/pussy_acc

### Clothing subtags and modifiers

- `ankle-boots` — clothing_modifiers/boots
- `bomber` — clothing_modifiers/jacket
- `bootcut` — clothing_modifiers/jeans
- `cheerleader` — clothing_modifiers/skirt
- `combat-boots` — clothing_modifiers/boots
- `crotchless` — clothing_modifiers/panty
- `denim` — clothing_modifiers/jacket, clothing_modifiers/skirt
- `fishnets` — clothing_modifiers/pantyhose
- `garter` — clothing_modifiers/thigh-high-stockings
- `graphic` — clothing_modifiers/t-shirt
- `harness` — clothing_modifiers/bra, clothing_modifiers/panty
- `knee-high-boots` — clothing_modifiers/boots
- `lace` — clothing_modifiers/bra, clothing_modifiers/panty
- `lace-top` — clothing_modifiers/thigh-high-stockings
- `latex` — clothing_modifiers/thigh-high-stockings
- `latex-dress` — clothing_modifiers/dress
- `leather` — clothing_modifiers/jacket, clothing_modifiers/skirt
- `leather-dress` — clothing_modifiers/dress
- `maid-dress` — clothing_modifiers/dress
- `nurse-dress` — clothing_modifiers/dress
- `opaque` — clothing_modifiers/pantyhose
- `open-cup` — clothing_modifiers/bra
- `pencil-skirt` — clothing_modifiers/skirt
- `plain` — clothing_modifiers/t-shirt, clothing_modifiers/thigh-high-stockings
- `platform` — clothing_modifiers/heels
- `pleated` — clothing_modifiers/skirt
- `puffer` — clothing_modifiers/jacket
- `pumps` — clothing_modifiers/heels
- `regular-fit` — clothing_modifiers/jeans
- `ripped` — clothing_modifiers/jeans
- `ruffled` — clothing_modifiers/blouse
- `satin` — clothing_modifiers/blouse
- `satin-dress` — clothing_modifiers/dress
- `see-through-dress` — clothing_modifiers/dress
- `sheer` — clothing_modifiers/blouse, clothing_modifiers/bra, clothing_modifiers/panty, clothing_modifiers/pantyhose
- `skinny` — clothing_modifiers/jeans
- `slutty` — clothing_modifiers/skirt
- `sport` — clothing_modifiers/jacket
- `stiletto` — clothing_modifiers/heels
- `strappy` — clothing_modifiers/heels
- `striped` — clothing_modifiers/t-shirt
- `thigh-high-boots` — clothing_modifiers/boots
- `transparent` — clothing_modifiers/bra, clothing_modifiers/skirt
- `uniform` — clothing_modifiers/skirt

### Fullbody main tags

- `atheletic` — clothed_states (review required)
- `bare` — nude_states
- `bikini` — clothed_states, costume_states
- `bottomless` — nude_states
- `clothed` — clothed_states
- `cosplay` — costume_states
- `lingerie` — clothed_states
- `maid` — costume_states
- `nurse` — costume_states
- `shower` — nude_states
- `swimsuit` — costume_states
- `topless` — nude_states
- `underwear` — clothed_states
- `uniform` — costume_states
- `work` — costume_states

### Fullbody sub-main tags / states

- `clothed`
- `topless`
- `bottomless`
- `clothed` is the base clothing state; three-state registry is separate from main type.

### Fullbody subtags

- `slut`
- `conservative`
- `whore`
- `u_whore`
- `park`

### Body Images main tags

- `ass` — lower_body
- `boobs` — upper_body
- `face` — face
- `legs` — limbs
- `portrait` — portrait
- `pussy` — lower_body
- `tportrait` — portrait

### Body Images sub-main tags

The source guide defines an ordered comma-separated main-tag list, not a separate sub-main taxonomy. NewAssetApp's `sub_main_tag` is the optional second ordered main tag used for that list.

### Body Images subtags

- `bar` — subtags/location_tags
- `bathroom` — subtags/location_tags
- `beach` — subtags/location_tags
- `cafeteria` — subtags/location_tags
- `class` — subtags/location_tags
- `clinic` — subtags/location_tags
- `coffee_shop` — subtags/location_tags
- `conservative` — subtags/corruption_level
- `creampie` — subtags/fluids
- `cum` — subtags/fluids
- `home` — subtags/location_tags
- `locker_room` — subtags/location_tags
- `lounge` — subtags/location_tags
- `mall` — subtags/location_tags
- `office` — subtags/location_tags
- `park` — subtags/location_tags
- `pier` — subtags/location_tags
- `shower` — subtags/location_tags
- `slut` — subtags/corruption_level
- `u_whore` — subtags/corruption_level
- `whore` — subtags/corruption_level

### Shared corruption subtags

- `slut`
- `conservative`
- `whore`
- `u_whore`

### Location and contextual tags

Body Images location subtags:

- `bar` — subtags/location_tags
- `bathroom` — subtags/location_tags
- `beach` — subtags/location_tags
- `cafeteria` — subtags/location_tags
- `class` — subtags/location_tags
- `clinic` — subtags/location_tags
- `coffee_shop` — subtags/location_tags
- `home` — subtags/location_tags
- `locker_room` — subtags/location_tags
- `lounge` — subtags/location_tags
- `mall` — subtags/location_tags
- `office` — subtags/location_tags
- `park` — subtags/location_tags
- `pier` — subtags/location_tags
- `shower` — subtags/location_tags

Photoshoot tags by source context:

#### configuration_types

- *(none)*

#### item_action_tags

- *(none)*

#### item_action_tags/Creampie Actions

- `creampie_ass` — item_action_tags/Creampie Actions
- `creampie_mouth` — item_action_tags/Creampie Actions
- `creampie_pussy` — item_action_tags/Creampie Actions

#### item_action_tags/Cumshot Actions

- `cumshot_ass` — item_action_tags/Cumshot Actions
- `cumshot_boobs` — item_action_tags/Cumshot Actions
- `cumshot_face` — item_action_tags/Cumshot Actions
- `cumshot_feet` — item_action_tags/Cumshot Actions
- `cumshot_pussy` — item_action_tags/Cumshot Actions
- `cumshot_stomach` — item_action_tags/Cumshot Actions

#### item_action_tags/Dildo/Toy Insertion (Self)

- `dildo_anal_self` — item_action_tags/Dildo/Toy Insertion (Self)
- `dildo_pussy_self` — item_action_tags/Dildo/Toy Insertion (Self)

#### item_action_tags/Manual and Other Stimulation

- `give_boobjob` — item_action_tags/Manual and Other Stimulation
- `give_footjob` — item_action_tags/Manual and Other Stimulation
- `give_handjob` — item_action_tags/Manual and Other Stimulation

#### item_action_tags/Miscellaneous Actions

- `kiss` — item_action_tags/Miscellaneous Actions
- `tease` — item_action_tags/Miscellaneous Actions

#### item_action_tags/Oral Actions

- `get_oral` — item_action_tags/Oral Actions
- `get_rimjob` — item_action_tags/Oral Actions
- `give_oral` — item_action_tags/Oral Actions
- `give_rimjob` — item_action_tags/Oral Actions
- `multi_oral` — item_action_tags/Oral Actions

#### item_action_tags/Penetrative Actions

- `anal` — item_action_tags/Penetrative Actions
- `boob_fuck` — item_action_tags/Penetrative Actions
- `face_fuck` — item_action_tags/Penetrative Actions
- `fuck_dp` — item_action_tags/Penetrative Actions
- `vaginal` — item_action_tags/Penetrative Actions

#### item_action_tags/Playing with Body Parts

- `play_ass` — item_action_tags/Playing with Body Parts
- `play_boob` — item_action_tags/Playing with Body Parts
- `play_feet` — item_action_tags/Playing with Body Parts
- `play_nipple` — item_action_tags/Playing with Body Parts
- `play_pussy` — item_action_tags/Playing with Body Parts

#### item_action_tags/Self Fingering and Fisting

- `finger_ass_self` — item_action_tags/Self Fingering and Fisting
- `finger_pussy_self` — item_action_tags/Self Fingering and Fisting
- `fist_ass_self` — item_action_tags/Self Fingering and Fisting
- `fist_pussy_self` — item_action_tags/Self Fingering and Fisting

#### item_action_tags/Showing Body Parts

- `show_ass` — item_action_tags/Showing Body Parts
- `show_boobs` — item_action_tags/Showing Body Parts
- `show_feet` — item_action_tags/Showing Body Parts
- `show_panty` — item_action_tags/Showing Body Parts
- `show_pussy` — item_action_tags/Showing Body Parts

#### item_action_tags/Undress Actions

- `get_undress` — item_action_tags/Undress Actions
- `give_undress` — item_action_tags/Undress Actions
- `undress_self` — item_action_tags/Undress Actions

#### item_main_tags

- `bare` — item_main_tags
- `clothed` — item_main_tags
- `half_dressed` — item_main_tags
- `hardcore` — item_main_tags
- `revealing` — item_main_tags
- `sex` — item_main_tags
- `softcore` — item_main_tags
- `underwear` — item_main_tags

#### item_sub_tags

- `closeup` — item_sub_tags
- `nobot` — item_sub_tags
- `noface` — item_sub_tags
- `notop` — item_sub_tags

#### item_thirdparty_tags

- `group_female` — item_thirdparty_tags
- `group_male` — item_thirdparty_tags
- `orgy` — item_thirdparty_tags
- `tp_fem` — item_thirdparty_tags
- `tp_male` — item_thirdparty_tags

#### location_tags

- `indoor_private` — location_tags
- `indoor_public` — location_tags
- `outdoor_private` — location_tags
- `outdoor_public` — location_tags
- `photo_studio` — location_tags

#### participant_tags

- `duo` — participant_tags
- `orgy` — participant_tags
- `solo` — participant_tags
- `threesome` — participant_tags

#### shoot_subtypes

- `clothed` — shoot_subtypes
- `gangbang` — shoot_subtypes
- `hardcore` — shoot_subtypes
- `lesbian` — shoot_subtypes
- `nude` — shoot_subtypes
- `orgy` — shoot_subtypes
- `revealing` — shoot_subtypes
- `sex` — shoot_subtypes
- `softcore` — shoot_subtypes
- `underwear` — shoot_subtypes

#### theme_tags

- `bath` — theme_tags
- `bathroom` — theme_tags
- `bdsm` — theme_tags
- `beach` — theme_tags
- `bedroom` — theme_tags
- `bikini` — theme_tags
- `bridal` — theme_tags
- `cosplay` — theme_tags
- `lingerie` — theme_tags
- `massage` — theme_tags
- `nature` — theme_tags
- `office` — theme_tags
- `party` — theme_tags
- `pool` — theme_tags
- `real_estate` — theme_tags
- `school` — theme_tags
- `sex_toy` — theme_tags
- `shower` — theme_tags
- `workout` — theme_tags

### YOLO class names

- ID 0: `person`
- ID 1: `face`
- ID 2: `portrait_frame`
- ID 3: `boobs`
- ID 4: `ass`
- ID 5: `pussy`
- ID 6: `legs`
- ID 7: `action_event`
- ID 8: `pussy_cover_item`
- ID 9: `ass_cover_item`
- ID 10: `boobs_cover_item`
- ID 11: `leg_cover_item`
- ID 12: `location_home`
- ID 13: `location_class`
- ID 14: `location_office`
- ID 15: `location_bathroom`
- ID 16: `location_bar`
- ID 17: `location_outdoor`
- ID 18: `location_bed`
- ID 19: `fullbody_shower`
- ID 20: `fullbody_maid`
- ID 21: `fullbody_nurse`
- ID 22: `fullbody_uniform`
- ID 23: `fullbody_athletic`
- ID 24: `fullbody_swim`
- ID 25: `fullbody_lingerie`
- ID 26: `fullbody_work`
- ID 27: `fullbody_casual`
- ID 28: `accessory_footwear`
- ID 29: `fullbody_topless`
- ID 30: `fullbody_bottomless`
- ID 31: `fullbody_bare`

### Asset CNN class names

- ID 0: `bodypart_ass`
- ID 1: `bodypart_boobs`
- ID 2: `bodypart_face`
- ID 3: `bodypart_legs`
- ID 4: `bodypart_portrait_clothed`
- ID 5: `bodypart_portrait_topless`
- ID 6: `bodypart_pussy`
- ID 7: `bra`
- ID 8: `dress`
- ID 9: `footwear`
- ID 10: `fullbody_clothed_states`
- ID 11: `fullbody_costume_states`
- ID 12: `fullbody_nude_states`
- ID 13: `outerwear`
- ID 14: `pants`
- ID 15: `panty`
- ID 16: `pantyhose`
- ID 17: `shirt`
- ID 18: `shorts`
- ID 19: `skirt`
- ID 20: `socks`
- ID 21: `special_wear`
- ID 22: `stockings`
- ID 23: `sweater`
- ID 24: `utility_cover`
- ID 25: `vest`

### Future CNN class names

- Fullbody-state plan: `clothed`, `topless`, `bottomless` (no checkpoint; no training).
- No corruption classifier class list has been approved or trained.

## Model-to-taxonomy cross-reference

The generated `data/models/model_tag_crosswalk.json` records all 32 original YOLO IDs/names and 26 original Asset CNN IDs/names, keeps raw labels separate from application candidates, and marks every mapping as requiring human confirmation. The embedded YOLO checkpoint names were read from `models/yolo/best.pt` with the installed Ultralytics runtime and matched all 32 manifest/policy entries in order. Asset CNN uses its 26-entry `asset_class_map.json`; its classifier head has 26 outputs. Existing dataset export uses the policy/registry labels; YOLO dense training IDs are mapped back to original IDs in the emitted `class_map.json`. No model checkpoint class or ID was changed.

Key crosswalk findings:

- Asset CNN `bodypart_boobs` (ID 1) maps to canonical Body Images `boobs`; YOLO class ID 3 is also exactly `boobs`.
- Asset CNN `bodypart_portrait_clothed` and `bodypart_portrait_topless` map to distinct `portrait` and `tportrait` application tags. The guide explicitly says T-Portrait is used when topless.
- The original Girl Packer `ai/naming.py` explicitly maps Asset CNN `footwear`→`shoes`, `outerwear`→`outer`, and `panty`→`panties` as broad category suggestions. NewAssetApp now records those as pending category suggestions, not final garment tags; raw CNN class IDs/names remain intact.
- YOLO `fullbody_athletic` maps to the current source-derived `atheletic` row, which remains review-required. No canonical spelling rewrite or checkpoint change is made in this audit.
- `u_whore` is an original video-tag serialization (`vid_tags.json`: `Ultimate Whore`→`u_whore`); the app preserves that token exactly. `Ultimate_whore` is a displayed guide spelling, not a different output token.

## Filename grammar and parser cross-check

- **Fullbody:** `<main>_<state>-<subtag1>,<subtag2>N.webp`; tested examples include `clothed_topless-slut1.webp` and `clothed_topless-slut,park1.webp`. The writer uses the verified composition allowlist; legacy guide aliases remain parse-only.
- **Clothing:** `<verified_main>_<subtag1>,<subtag2>N.webp`; the underscore is literal category grammar. The writer refuses unverified main tags; old hyphen filenames are identified as legacy by the parser.
- **Body Images:** single main uses `<main>-<subtags>N.webp` (`boobs-cum1.webp`, `boobs-cum,whore1.webp`); grouped mains retain paired guide numbering such as `ass3,boobs3-cum.webp`. `boobs` passes canonical serializer/parser checks; `bobbs` is rejected and has no alias.
- **Shared tokens:** corruption values remain exact subtags, including `u_whore`; the taxonomy and category validator keep them separate from main tags. Fullbody state is stored in its own field and mirrored as `sub_main_tag` for the hierarchy audit.

## Spelling and naming findings

| Current spelling | Original source spelling / location | Classification | Recommended canonical spelling | Alias / compatibility | Impact |
|---|---|---|---|---|---|
| `bobbs` | Earlier NewAssetApp test/report example only; absent from inspected guide, source Body Images map, YOLO and Asset CNN registries | Incorrect prior example, not an historical source alias | `boobs` | No parser alias; no historical file evidence found | Remove from canonical serializer; no database rewrite; existing ID 3 and CNN IDs unchanged |
| `boobs` | Guide Body Images; Girl Packer `bodyparts.json` `Boobs`; YOLO ID 3 `boobs`; Asset CNN ID 1 `bodypart_boobs` | Canonical | `boobs` | None | No model/database identity change |
| `Atheletic` / `atheletic` | Girl Packer `fullbody.json` key/value; NewAssetApp Fullbody main entry (review-required); guide says `athletic`; YOLO ID 23 `fullbody_athletic` | Source typo versus guide/model spelling; unresolved selection promotion | `athletic` is recommended by guide and model spelling | If corrected later, accept legacy `atheletic` for old DB/correction records; do not edit records/checkpoint | Taxonomy value change affects new labels; append-only DB and model ID 23 must remain unchanged |
| `panty` | Asset CNN ID 15 and Girl Packer video clothing tag/modifier parent; source clothing slot is `panties` | Intentional model/source vocabulary difference; category crosswalk exists | Use `panties` only as broad source category; keep `panty` as model class | Explicit review-only mapping in crosswalk; no class alias/renaming | Does not alter CNN ID 15 or stored predictions |
| `footwear` / `shoes` | Asset CNN ID 9 / YOLO `accessory_footwear` ID 28 versus source Clothing category `shoes`; Girl Packer `ai/naming.py` maps footwear→shoes | Model label vs source category; explicit broad-family mapping | `shoes` for application category suggestion | Keep raw `footwear` and YOLO class name; candidate is review-only | No model ID or database evidence changes |
| `outerwear` / `outer` | Asset CNN ID 13 versus source category `outer`; Girl Packer helper maps outerwear→outer | Model label vs source category; explicit broad-family mapping | `outer` for application category suggestion | Keep raw `outerwear`; candidate is review-only | No model ID or existing record change |
| `u_whore` / `Ultimate_whore` | Original Girl Packer `vid_tags.json` maps display `Ultimate Whore` to `u_whore`; guide uses `Ultimate_whore`; NewAssetApp shared token is `u_whore` | Display spelling and serialized token intentionally differ | `u_whore` | Preserve exact token; no normalization | No impact to IDs/records |
| `portrait` / `tportrait` | Source `bodyparts.json` has `Clothed Portrait`→`portrait`, `Topless Portrait`→`tportrait`; guide specifies topless T-Portrait | Two distinct intended tags, not a typo | Preserve both | Explicit CNN mapping from clothed/topless model classes | Keep separate model classes and application labels |
| `crempie` / `creampie` | `crempie`: zero matches in inspected NewAssetApp/source files. `creampie`: guide and Body Images source subtag | `crempie` unsupported spelling; `creampie` canonical | `creampie` | No alias absent evidence of historical files | No database/model change |
| `fullbody_swim` / `swimsuit` | YOLO class ID 24 / source Fullbody token `swimsuit` | Model abbreviation to source tag candidate | `swimsuit` | Explicit review-only candidate | Keep YOLO label and ID |
| `clothed-bottomless` / `clothed_bottomless` | Guide uses hyphen; original composition registry/current NewAssetApp uses underscore and read alias | Intentional legacy filename alias | `clothed_bottomless` in current composition data | Keep parser alias, do not rewrite historical records | No model impact |

## Integrity check results

`validate_tag_library.py`: PASS (0 findings). It checks duplicate IDs, duplicate canonical values in the same context, review-record references, and tag inventory consistency. Added audit checks also reject case-insensitive spelling collisions and a canonical token registered under conflicting tag types. Exact duplicate `bikini` main-tag values in separate source contexts are retained intentionally.
- No `bobbs` alias is added. No other case-only spelling duplicate was found among selectable canonical tags.
- `u_whore` remains exact; underscores and hyphens in meaningful values such as `coffee_shop`, `pencil-skirt`, and `t-shirt` remain literal taxonomy values, not normalized separators.
- Original AI evidence remains in immutable model prediction/detection records; corrections append human-selected canonical tags and do not rename class registries.
- Final verification: `NewAssetApp .venv -m unittest discover -q` passed 59 tests. The taxonomy validator reported zero findings. No samples were processed, no datasets were exported, and no models were trained.
