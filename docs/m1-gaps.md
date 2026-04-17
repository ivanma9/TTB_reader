# M1 Gap List

## gs_021 / gs_023 relabeling
Originally spec'd as `unreadable_image` (heavy glare / perspective skew). PP-OCRv4
reads both cleanly in practice, so they were relabeled to `match`. The
`unreadable_fallback_accuracy` gate now covers gs_020, gs_022, gs_024.

Implication: the gate denominator is 3 cases (not 4). This is fine for M1 synthetic
fixtures. Re-evaluate once real-world labels with actual degradation are added.

## Warning body fuzzy tolerance
The warning body matcher uses exact normalized comparison + ≥97 fuzz fallback to
`needs_review`. Real small-print OCR may produce 94-96 scores on legitimate labels —
monitor and tune when real labels are available.

## Multi-line brand / uppercase FL OZ
Both fixed in this same commit. Verified against golden set. No regressions.
