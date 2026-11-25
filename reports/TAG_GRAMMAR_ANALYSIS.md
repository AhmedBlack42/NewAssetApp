# Tag grammar analysis

## Documented Body Images filename form

The guide gives `{main_tag},{main_tag2}-{sub_tag},{sub_tag2}.webp`. In that context, the first comma-separated section contains main tags; the hyphen separates the optional subtag section; commas then separate subtags. The guide's concrete example is `face-cum.webp`. It says the image number matters and gives `ass1`, `boobs1`, `pussy1`, and `face1`; that suffix associates a numbered image set and is not described as a tag.

The guide names corruption values, `cum`, `creampie`, and locations as possible subtags. The guide does not define which subtag combinations apply to each main tag, list ordering within either comma group, or all exclusivity constraints. The active `bodyparts.json` is only a base-tag map; the current Image Workshop does not provide a matching Body Images subtag editor. Therefore the new library preserves these values but does not claim that combination/export rules are fully implemented.

## Fullbody form and compound tags

The guide's example is `clothed-bottomless.webp`, optionally with a comma-separated corruption value. Current code defines a distinct composition allowlist: `clothed_topless`, `clothed_bottomless`, and `bikini_bottomless`. The writer composes an underscore value, while the parser reads `clothed-bottomless` as a legacy alias. The alias is retained separately and hidden from normal selection pending a spelling decision. Do not generate other combinations from the base-state list.

## Separator meanings

| Token | Evidence-based meaning | Limit |
|---|---|---|
| `<` | No definition or use found in the guide or active asset tag serializer. | Unsupported until an external source is identified. |
| `-` | Body Images main/subtag boundary; also occurs literally within terms and in the legacy Fullbody alias. | Context-sensitive; never globally replace or normalize it. |
| `_` | Literal part of serialized values (for example `coffee_shop`) and current Fullbody composition joiner. | Not a universal hierarchy operator. |
| `,` | Multiple main tags or multiple subtags in the Body Images filename template. | The source leaves combination validity and within-list order open. |
| spaces | Human-readable label text in maps and forms. | No rule permits converting spaces to underscores automatically. |
| `.` | Filename stem/extension boundary, such as `.webp`. | Not part of a tag value. |

The curly braces in the filename template are placeholders, not literal filename characters. A hyphen or underscore inside a source term stays exactly as written. `tag_grammar.json` is the machine-readable version of these observations; `tag_review_required.json` includes unresolved uses.

## Hierarchy versus grouping

- Body Images use main tags and subtags in the documented filename template; exact compatibility remains pending.
- Fullbody composition records are compound complete values with an explicit allowlist.
- Clothing slot names and Photoshoot helper field names are schema/UI groupings represented by nonselectable metadata nodes. They are not automatically semantic parent tags.
- Clothing modifier buckets become children of an asset tag only when the source token matches exactly. Unmatched parent mappings are review-required.
- Photoshoot group names and shoot titles are user metadata/identifiers, not model labels or taxonomy values.

## Tag order and combinations

Only the Body Images main-before-subtag section order and explicit Fullbody composition allowlist are established. The implementation must not sort, merge, or rewrite the source strings. No arbitrary clothing or Photoshoot cross-products are generated. The review queue identifies the remaining composition rules.
