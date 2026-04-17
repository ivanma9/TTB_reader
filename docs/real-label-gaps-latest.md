# Real-label eval gaps

Cases: **43** (source: TTB COLA 2018 demo via Kaggle)


## Overall verdict distribution

- `needs_review`: 41
- `mismatch`: 2

## Recommended-action distribution

- `request_better_image`: 41
- `manual_review`: 2

## Per-field actual-status distribution

`wrong_na` = verifier returned not_applicable when a value was expected (silent regression).

| Field | match | mismatch | needs_review | correct_na | wrong_na |
|-------|-------|----------|--------------|------------|----------|
| brand_name | 22 | 9 | 12 | 0 | 0 |
| class_type | 1 | 23 | 19 | 0 | 0 |
| alcohol_content | 31 | 1 | 11 | 0 | 0 |
| net_contents | 22 | 0 | 21 | 0 | 0 |
| producer_name_address | 0 | 25 | 18 | 0 | 0 |
| country_of_origin | 3 | 9 | 10 | 21 | 0 |
| government_warning | 0 | 4 | 39 | 0 | 0 |

## Top failure reasons per field


### brand_name
- `unreadable`: 12
- `wrong_value`: 9

### class_type
- `wrong_value`: 23
- `unreadable`: 19

### alcohol_content
- `unreadable`: 11
- `wrong_value`: 1

### net_contents
- `unreadable`: 21

### producer_name_address
- `wrong_value`: 25
- `unreadable`: 18

### country_of_origin
- `unreadable`: 10
- `missing_required`: 9

### government_warning
- `unreadable`: 39
- `warning_text_mismatch`: 4

---

Per-case details: `docs/real-label-gaps.csv`
