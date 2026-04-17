# Real-label eval gaps

**Cases:** 43 (TTB COLA 2017 demo via Kaggle `colacloud/ttb-colas-demo`)
**Target:** `alc_label_verifier.adapter:target` (v1 verifier)
**Run:** 2026-04-17

## Summary vs synthetic golden set

| Metric | Synthetic (28) | Real (43) |
|--------|---------------:|----------:|
| overall_verdict_accuracy | 1.00 | **0.00** |
| field_status_accuracy | 1.00 | **0.17** |
| recommended_action_accuracy | 1.00 | **0.00** |
| conditional_rule_accuracy | 1.00 | **0.42** |

Every real-label case resolved to `needs_review → request_better_image`,
because at least one field returned `needs_review` and the verdict cascades.

## Per-field actual-status distribution

| Field | match | mismatch | needs_review | not_applicable |
|-------|-------|----------|--------------|----------------|
| brand_name | 7 | 18 | 18 | 0 |
| class_type | 1 | 21 | 21 | 0 |
| alcohol_content | 26 | 1 | 16 | 0 |
| net_contents | 0 | 0 | 43 | 0 |
| producer_name_address | 0 | 22 | 21 | 0 |
| country_of_origin | 0 | 8 | 17 | 18 |
| government_warning | 0 | 4 | 39 | 0 |

## Top failure modes (prioritized)

### 1. `government_warning` — 39/43 unreadable, 4/43 mismatch
**Root cause:** the TTB government warning lives on the **back** label, not
the front. Our eval only feeds the front image. Verifier correctly reports
`unreadable` — this is an eval-setup gap, not a verifier bug.
**Fix path:** either (a) feed front+back concatenated OCR, or (b) split
ground-truth so front-only cases skip warning scoring. Option (a) mirrors
how the real workflow should work.

### 2. `net_contents` — 0/43 match, 100% unreadable
**Root cause:** CSV gives `"750 milliliters"`; real labels say `"750 mL"` /
`"750ML"`. The `match_net_contents` anchor detection appears to miss real
on-label variants. Also partly a front-vs-back issue — net contents is
sometimes on the back.
**Fix path:** inspect `match_net_contents` anchor heuristic against real
OCR lines; broaden unit aliases; consider back-label fallback.

### 3. `producer_name_address` — 0/43 match
**Root cause:** CSV `APPLICANT_NAME` is the permit holder (often a legal
entity or individual, e.g. `"Claudia Sicard"`) while the label shows the
bottler/producer (e.g. `"Destillaria Jaguari, Brazil"`). These are
structurally different values.
**Fix path:** this field can't be scored against applicant name from the
CSV. Either hand-label the producer for the eval set, or drop this field
from scoring on the real-labels set.

### 4. `class_type` — 1/43 match
**Root cause:** CSV has normalized class codes like `"other rum gold fb"`,
`"canadian whisky fb"` — these strings never appear verbatim on labels.
Labels show fanciful names ("Kentucky Straight Bourbon Whiskey"). The
verifier's class matcher also over-reads — observed values are entire
paragraphs of marketing copy (see ttb_18011001000033 in CSV).
**Fix path:** class matching needs a class-code → display-string map, plus
tighter class-line detection. Or hand-label class from labels.

### 5. `brand_name` — 7/43 match (16%)
**Root cause:** header-line selection picks the most prominent header
text, which is frequently a class keyword ("CACHACA"), a location
("OREGON"), or a producer attribution ("DISTILLED & BOTTLED BY ...")
instead of the brand. Brand is often smaller than the class/fanciful
name on real distilled-spirits labels.
**Fix path:** brand-detection heuristic needs more than "biggest text in
the header" — consider position-weighted scoring or fuzzy contains against
the expected brand.

### 6. `country_of_origin` — 0/18 imports match, 17/43 unreadable
**Root cause:** `match_country_of_origin` requires a `"Country of Origin:
X"` anchor, but import labels usually phrase it as `"Product of Brazil"`
or `"Imported from France"` — the anchor doesn't match these variants.
**Fix path:** broaden anchor patterns in `_is_country_anchor` to cover
"product of X", "imported from X", "made in X".

## Eval-setup issues to address before v2

1. **Feed both front + back images** — warnings, net contents, and some
   producer lines live on the back panel. The verifier currently only
   accepts one image path. Consider extending the contract.
2. **CSV-as-truth caveats**: `APPLICANT_NAME` ≠ producer on label;
   `CLASS_NAME` ≠ on-label class text. Consider hand-labeling these two
   fields for ~15 cases to get real ground truth.
3. **ABV/volume ground truth** is COLA Cloud's own OCR — if our verifier
   disagrees with theirs on a case, we can't tell who's right without
   hand-verification.

## Next actions (suggested)

1. Land this eval as a regression baseline (don't gate on it — use as
   diagnostic). Metrics: 0 / 17% / 0 / 42%.
2. Tackle **country_of_origin anchor broadening** (smallest fix, quickest
   win — ~10 lines in `matching.py`).
3. Decide on front+back eval contract before touching `net_contents` and
   `government_warning` fixes.
4. Defer `class_type` and `producer_name_address` until we have real
   labeled ground truth for those fields.

---

Per-case details: `docs/real-label-gaps.csv`
