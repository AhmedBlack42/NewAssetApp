# Phase 4B training readiness

**Training status: not started.** No examples are currently training-eligible. Existing examples and generated crops are staged for review only; no model head was trained.

| Task/group | Candidate evidence | Eligible now | State |
|---|---:|---:|---|
| Unified Body Images legacy folder examples | 356 | 0 | Historical labels need human confirmation |
| Unified Fullbody legacy broad-group examples | 490 | 0 | No safe mapping from old groups to new states |
| Unified Body Images YOLO-derived crops | 1,637 | 0 | Candidate-only; portrait frames remain ambiguous |
| Unified Fullbody YOLO-derived crops | 1,438 | 0 | Candidate-only; state requires human confirmation |
| Clothing CNN | 0 copied | 0 | User will manually review/map examples |
| YOLO | 652 active pairs; 1 quarantined | 652 available, semantic review pending | Structural labels validate; source semantics remain legacy |

Body Images crop groups: face 665, unresolved portrait frame 521, boobs 142, legs 171, pussy 97, ass 41. Fullbody proposal groups: person 801, broad type candidates 465, topless 52, bottomless 63, unresolved bare 57. Every crop is marked unconfirmed and ineligible.

YOLO active data: train 401 pairs / 3,217 annotations; validation 251 pairs / 1,982 annotations; test 0. All 32 IDs appear in the source registry. One zero-width annotation on source line 8 was quarantined with its pair. Source-hash grouping prevents crops from one source crossing proposed splits. The audited Body subset had no duplicate-content groups crossing splits; the broader legacy CNN inventory had five duplicate groups, one crossing train/validation.

Remaining work: human review and corrected labels, manual Clothing dataset population, enough examples for each revised output, then a separately reviewed training plan. No accuracy or calibration claim is available.
