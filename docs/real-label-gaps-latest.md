# Real-label eval gaps

Cases: **43** (source: TTB COLA 2018 demo via Kaggle)


## Overall verdict distribution

- `needs_review`: 43

## Recommended-action distribution

- `request_better_image`: 43

## Per-field actual-status distribution

`wrong_na` = verifier returned not_applicable when a value was expected (silent regression).

| Field | match | mismatch | needs_review | correct_na | wrong_na |
|-------|-------|----------|--------------|------------|----------|
| brand_name | 7 | 18 | 18 | 0 | 0 |
| class_type | 1 | 21 | 21 | 0 | 0 |
| alcohol_content | 26 | 1 | 16 | 0 | 0 |
| net_contents | 0 | 0 | 43 | 0 | 0 |
| producer_name_address | 0 | 22 | 21 | 0 | 0 |
| country_of_origin | 1 | 7 | 17 | 18 | 0 |
| government_warning | 0 | 4 | 39 | 0 | 0 |

## Top failure reasons per field


### brand_name
- `wrong_value`: 18
- `unreadable`: 18

### class_type
- `unreadable`: 21
- `wrong_value`: 21

### alcohol_content
- `unreadable`: 16
- `wrong_value`: 1

### net_contents
- `unreadable`: 43

### producer_name_address
- `wrong_value`: 22
- `unreadable`: 21

### country_of_origin
- `unreadable`: 17
- `missing_required`: 7

### government_warning
- `unreadable`: 39
- `warning_text_mismatch`: 4

---

Per-case details: `docs/real-label-gaps.csv`
