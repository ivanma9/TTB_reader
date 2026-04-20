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

## Post-Category-A update (2026-04-17)

The Category A fixes (`net_contents` unit aliases + OCR-typo tolerance,
`brand_name` fuzzy-contains over wider pool, `country_of_origin` widened
to the full non-warning region) shipped on branch `real-label-category-a`.
New per-field counts (43 cases, 17 imports / 26 domestic):

| Field | match | mismatch | needs_review | not_applicable |
|-------|------:|---------:|-------------:|---------------:|
| brand_name | **22** | 9 | 12 | 0 |
| net_contents | **22** | 0 | 21 | 0 |
| country_of_origin | **3** | 9 | 10 | 21 |
| alcohol_content | 31 | 1 | 11 | 0 |
| class_type | 1 | 23 | 19 | 0 |
| producer_name_address | 0 | 25 | 18 | 0 |
| government_warning | 0 | 4 | 39 | 0 |

### Residual `country_of_origin` gaps (9 imports still `missing_required`)

**A' — anchor-prefix limitation (fixable in a follow-up, not shipped here):**
- `ttb_18011001000033` (Peru) — front has
  "Producto peruano/Product of Peru", but `_find_country_anchor` only
  checks the line's leading chars. Scan-anywhere (word-boundary guarded)
  would unlock this case. Tracked as follow-up.

**E — country name embedded without a standard anchor phrase:**
- `ttb_18250001000290` (Greece) — "GREECE" appears inside
  "DISTILLERY-TYRNAVOS-GREECE". No "product of / made in / imported from"
  phrase.
- `ttb_18095001001312` (Mexico) — "MEXICO" embedded in
  "JALISCOMEXICO"; only addresses mention it.
- `ttb_18199001000406` — country name reachable only via typo'd OCR with
  no standard anchor.

**F — foreign-language anchor (vocabulary gap):**
- `ttb_18074001000816` (Mexico) — "Hecho en Tequila, Mexicc." Spanish
  anchor + OCR typo; would require extending `COUNTRY_ANCHORS` with
  "hecho en" and handling the city/country comma pattern.

**C — country genuinely absent from front-label OCR (back label required,
deferred to the Category B front+back-image work):**
- `ttb_18113001000679` (Japan) — front has 4 OCR lines; no country.
- `ttb_18046001000056`, `ttb_18291001000107`, `ttb_18043001000147`
  (France) — Cognac/Armagnac front labels never say "France".

### Ship criteria met

Category A plan targets:
- `net_contents` ≥ 20/43 → **22/43** ✓
- `brand_name` ≥ 20/43 → **22/43** ✓
- `country_of_origin` ≥ 3/25* → **3/17 imports** ✓

*Plan target "3/25" was a pre-eval estimate; the built eval set has 17
imports + 26 domestic = 43 cases.

---

## Category C residuals (2026-04-18)

Hand-labeled 6 cases (target was 20; partial pass) via
`scripts/label_real_cases` during the Category C pass. After merging
`evals/real_labels/corrections.jsonl` through the adapter, the
labeled-subset scoring is:

| Field | match | mismatch | needs_review | not_applicable |
|-------|------:|---------:|-------------:|---------------:|
| class_type (6 labeled) | 0 | 3 | 3 | 0 |
| producer_name_address (6 labeled) | 0 | 4 | 2 | 0 |

No regression on the 37 unlabeled cases.

### Category A — matcher bug (on-label value IS in OCR; verifier didn't pick it up)

- `ttb_18052001000241` · `class_type` — CSV truth `"straight bourbon whisky"`
  appears verbatim multiple times in OCR observed text
  (`"THE RESULT IS A STRAIGHT BOURBON WHISKEY..."`,
  `"STRAIGHT BOURBON WHISKEY BATCH 010"`), but `class_type_actual` is
  `mismatch`. Matcher isn't finding an exact-phrase hit inside narrative
  OCR lines — likely only scanning anchor lines / large-header text.
- `ttb_18052001000241` · `producer_name_address` — hand label
  `"Chattanooga, TN"`. Observed is `"2 31 1 OF 3"` (garbage region),
  but `"CHATTANOOGA,TN"` appears in the OCR dump used for `class_type`.
  Producer matcher and class matcher appear to be reading different
  OCR regions for the same image — investigate region selection.
- `ttb_18046001000210` · `class_type` — hand label `"bourbon whiskey"`.
  Observed OCR contains `"KENTUCKY STRAIGHT"` and the label is a
  Wild Turkey product; matcher should trigger on the `"bourbon"` keyword
  that appears in adjacent lines. `mismatch` with non-bourbon phrasing
  in observed suggests the same region/phrase selection issue.

### Category B — OCR quality (front-label OCR doesn't contain the on-label value)

- `ttb_18029001000772` · both fields — `unreadable` with empty observed.
  No usable OCR. Likely back-label only or low-contrast front.
- `ttb_18043001000147` · both fields — `unreadable` with empty observed.
  Cognac label; producer/class likely back-label.
- `ttb_18046001000056` · `class_type` — `unreadable`; `producer_name_address`
  observed `"750ml"` only. Brandy label with producer likely on back.

All three Category-B cases overlap with the Category-A' front/back gap
already tracked in the `country_of_origin` residuals above — same
underlying "front-only OCR" eval-setup limitation.

### Category C — label ambiguity (re-label recommended)

- `ttb_18011001000033` (Pisco) — saved with empty corrections. OCR clearly
  contains `"Intipalka Pisco Mosto Verde"` and producer
  `"Santiago Queirolo S.A.C ... Lima, Peru"`. CSV truth
  (`"other grape brandy (pisco, grappa) fb"` / `"David Eber, FL"`) is the
  structural default the plan exists to correct — the empty-corrections
  save means the reviewer saw it but didn't override. Re-label in a
  follow-up pass.
- `ttb_18046001000210` · `producer_name_address` — hand label
  `"Lawrenceburg, KY"` (Wild Turkey distillery) does not appear anywhere
  in OCR. Observed has `"BARDSTOWN,KY"` (Jewish Whisky Company bottler).
  The label shows both distiller and bottler; reviewer picked the
  distiller but the verifier target is the bottler string. Re-label as
  the bottler, or widen producer semantics.

### Follow-ups

- Complete the remaining 14 labels to hit the plan's 20-case target.
- Open Category-A issue: matcher region/phrase selection for `class_type`
  and `producer_name_address` on narrative OCR lines
  (`ttb_18052001000241`, `ttb_18046001000210`).
- Category B overlaps with the existing back-label eval-setup gap — no
  new work needed beyond the front+back plan already tracked.

---

Per-case details: `docs/real-label-gaps.csv`
