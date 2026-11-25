# Tag review questions

**Status:** 11 decisions are pending. No ambiguous source spelling or rule was normalized.

## 1. review-fullbody-athletic-spelling

**Group:** `fullbody`
**Exact original tag / syntax:** `Atheletic`

**Where found:**
- database/asset_tags/fullbody.json $.nude_states["Atheletic"]
- docs/girlpack_Guide.md > Fullbody ("athletic")

**Evidence-supported interpretation:** The database label/value may be a misspelling of the guide term athletic; the serialized value is atheletic.

**Why it needs review:** Guide and active map differ in spelling; the model label fullbody_athletic is a separate context.

**Decision requested:** Should NewAssetApp preserve the map spelling, add an explicit alias, or wait for a game-compatible tag decision?

**Affected entries:** `Atheletic` (`atheletic`)

## 2. review-fullbody-separator

**Group:** `fullbody`
**Exact original tag / syntax:** `clothed-bottomless`

**Where found:**
- docs/girlpack_Guide.md > Fullbody example
- database/asset_tags/fullbody_compositions.json $.compositions / $.legacy_read_aliases
- utils/fullbody_tags.py compose_fullbody_tag/parse_fullbody_tag

**Evidence-supported interpretation:** Guide example uses a hyphen; current writer emits clothed_bottomless with an underscore; parser reads the hyphen alias.

**Why it needs review:** The guide example and current writer differ.

**Decision requested:** Which spelling should NewAssetApp offer and write?

**Affected entries:** `clothed-bottomless` (`clothed-bottomless`), `Clothed Bottomless` (`clothed_bottomless`)

## 3. review-body-ultimate-whore

**Group:** `body_images`
**Exact original tag / syntax:** `Ultimate_whore`

**Where found:**
- docs/girlpack_Guide.md > Vids > Corruption Levels
- database/vid_tags.json $.corruption_level["Ultimate Whore"]

**Evidence-supported interpretation:** Guide spelling is Ultimate_whore; current database token is u_whore.

**Why it needs review:** The Body Images section reuses the video tag system but does not specify whether to reuse this implementation token.

**Decision requested:** Which exact serialized value should Body Images use?

**Affected entries:** `Ultimate_whore` (`u_whore`)

## 4. review-body-subtag-combinations

**Group:** `body_images`
**Exact original tag / syntax:** `{main_tag},{main_tag2}-{sub_tag},{sub_tag2}`

**Where found:**
- docs/girlpack_Guide.md > Body_images update

**Evidence-supported interpretation:** Comma-separated main tags, optional hyphen separator, comma-separated subtags; face-cum is an explicit example.

**Why it needs review:** Per-main compatibility, ordering within lists, and multiple corruption-value restrictions are not defined.

**Decision requested:** Confirm valid subtag combinations and ordering before enabling tag composition/export controls.

**Affected entries:** `cum` (`cum`), `creampie` (`creampie`), `Conservative` (`conservative`), `Slut` (`slut`), `Whore` (`whore`), `Ultimate_whore` (`u_whore`), `Bathroom` (`bathroom`), `Bar` (`bar`), `Beach` (`beach`), `Cafeteria` (`cafeteria`), `Class` (`class`), `Clinic` (`clinic`), `Coffee Shop` (`coffee_shop`), `Home` (`home`), `Locker Room` (`locker_room`), `Mall` (`mall`), `Office` (`office`), `Park` (`park`), `Pier` (`pier`), `Shower` (`shower`), `Lounge` (`lounge`)

## 5. review-clothing-modifier-parent-t-shirt

**Group:** `clothing`
**Exact original tag / syntax:** `t-shirt`

**Where found:**
- database/asset_tags/clothing_modifiers.json $["t-shirt"]
- database/asset_tags/clothing.json slot values

**Evidence-supported interpretation:** The modifier key may correspond to a similarly spelled asset tag or gameplay clothing definition.

**Why it needs review:** No exact serialized-value parent match exists; spelling normalization would be a guess.

**Decision requested:** Confirm the parent asset tag or keep this modifier bucket informational and nonselectable.

**Affected entries:** `t-shirt` (``), `plain` (`plain`), `graphic` (`graphic`), `striped` (`striped`)

## 6. review-clothing-modifier-parent-skirt

**Group:** `clothing`
**Exact original tag / syntax:** `skirt`

**Where found:**
- database/asset_tags/clothing_modifiers.json $["skirt"]
- database/asset_tags/clothing.json slot values

**Evidence-supported interpretation:** The modifier key may correspond to a similarly spelled asset tag or gameplay clothing definition.

**Why it needs review:** No exact serialized-value parent match exists; spelling normalization would be a guess.

**Decision requested:** Confirm the parent asset tag or keep this modifier bucket informational and nonselectable.

**Affected entries:** `skirt` (``), `pleated` (`pleated`), `denim` (`denim`), `leather` (`leather`), `uniform` (`uniform`), `transparent` (`transparent`), `slutty` (`slutty`), `cheerleader` (`cheerleader`), `pencil-skirt` (`pencil-skirt`)

## 7. review-clothing-modifier-parent-bra

**Group:** `clothing`
**Exact original tag / syntax:** `bra`

**Where found:**
- database/asset_tags/clothing_modifiers.json $["bra"]
- database/asset_tags/clothing.json slot values

**Evidence-supported interpretation:** The modifier key may correspond to a similarly spelled asset tag or gameplay clothing definition.

**Why it needs review:** No exact serialized-value parent match exists; spelling normalization would be a guess.

**Decision requested:** Confirm the parent asset tag or keep this modifier bucket informational and nonselectable.

**Affected entries:** `bra` (``), `lace` (`lace`), `sheer` (`sheer`), `open-cup` (`open-cup`), `transparent` (`transparent`), `harness` (`harness`)

## 8. review-clothing-modifier-parent-panty

**Group:** `clothing`
**Exact original tag / syntax:** `panty`

**Where found:**
- database/asset_tags/clothing_modifiers.json $["panty"]
- database/asset_tags/clothing.json slot values

**Evidence-supported interpretation:** The modifier key may correspond to a similarly spelled asset tag or gameplay clothing definition.

**Why it needs review:** No exact serialized-value parent match exists; spelling normalization would be a guess.

**Decision requested:** Confirm the parent asset tag or keep this modifier bucket informational and nonselectable.

**Affected entries:** `panty` (``), `lace` (`lace`), `sheer` (`sheer`), `crotchless` (`crotchless`), `harness` (`harness`)

## 9. review-clothing-modifier-parent-thigh-high-stockings

**Group:** `clothing`
**Exact original tag / syntax:** `thigh-high-stockings`

**Where found:**
- database/asset_tags/clothing_modifiers.json $["thigh-high-stockings"]
- database/asset_tags/clothing.json slot values

**Evidence-supported interpretation:** The modifier key may correspond to a similarly spelled asset tag or gameplay clothing definition.

**Why it needs review:** No exact serialized-value parent match exists; spelling normalization would be a guess.

**Decision requested:** Confirm the parent asset tag or keep this modifier bucket informational and nonselectable.

**Affected entries:** `thigh-high-stockings` (``), `plain` (`plain`), `latex` (`latex`), `lace-top` (`lace-top`), `garter` (`garter`)

## 10. review-clothing-modifier-parent-boots

**Group:** `clothing`
**Exact original tag / syntax:** `boots`

**Where found:**
- database/asset_tags/clothing_modifiers.json $["boots"]
- database/asset_tags/clothing.json slot values

**Evidence-supported interpretation:** The modifier key may correspond to a similarly spelled asset tag or gameplay clothing definition.

**Why it needs review:** No exact serialized-value parent match exists; spelling normalization would be a guess.

**Decision requested:** Confirm the parent asset tag or keep this modifier bucket informational and nonselectable.

**Affected entries:** `boots` (``), `ankle-boots` (`ankle-boots`), `knee-high-boots` (`knee-high-boots`), `thigh-high-boots` (`thigh-high-boots`), `combat-boots` (`combat-boots`)

## 11. review-angle-bracket-token

**Group:** `tag_grammar`
**Exact original tag / syntax:** `<`

**Where found:**
- User Phase 1 brief Section 5; no occurrence/definition in the inspected guide or active asset serializer

**Why it needs review:** No use or definition was found in the source guide or active image-tag implementation.

**Decision requested:** Is < part of an external naming/schema rule that NewAssetApp must support?

## Approval gate

These questions affect display/serialized names, tag compatibility, or class filtering. Keep `requires_review` entries out of ordinary suggestions, and keep the YOLO proposal-route policy marked pending until reviewed. Photoshoot assignment remains manual regardless of these decisions.
