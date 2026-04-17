# TTB COLA Online — Public Endpoints

Reference for `scripts/ttb_eval_builder.py` when fetching real COLA records to
expand the golden set beyond synthetic renders.

## Structured detail (metadata only)

```
GET https://www.ttbonline.gov/colasonline/viewColaDetails.do
    ?action=publicDisplaySearchBasic&ttbid={ttb_id}
```

Returns the HTML search-result view. No label imagery — use this when you only
need the applicant's claimed fields (brand, class/type, ABV, net contents,
producer, origin).

## Printable form (metadata + embedded label images)

```
GET https://www.ttbonline.gov/colasonline/viewColaDetails.do
    ?action=publicFormDisplay&ttbid={ttb_id}
```

Returns the printable COLA form as HTML with the submitted label images
embedded. Use this when you need both the applicant payload and the label
imagery for the eval fixture.

## Notes

- COLA data is US public record; fetching is permitted but rate-limit politely.
- `{ttb_id}` comes from the Kaggle `colacloud/ttb-colas-demo` CSV.
- Image `src` URLs in the form HTML are relative to `ttbonline.gov` — resolve
  against the base when downloading.
