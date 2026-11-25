# Phase 5 Clothing Dataset Audit

Read-only inventory: 2,332 readable JPGs: train 1,883, validation 449, test 0. The twelve directory classes exactly match the approved list `bra,dress,footwear,lingerie,outerwear,pants,panty,shirt,shorts,skirt,socks,top`.

Critical review findings: exact duplicate content crosses train/validation in `socks` (`lingerie_legbd3.jpg` / `lingerie_legbd1.jpg`); exact content is assigned both `dress` and `shirt` in training (`short_dress20.jpg`). Two additional exact duplicate pairs occur within train. These were left untouched. The cross-split and cross-class cases block training pending human review. No test set is available. Heuristic filename-family matches are unverified source leakage indicators, not confirmed source identities.
