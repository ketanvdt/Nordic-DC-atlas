# Extraction schemas

JSON Schemas defining the contract for each data point kind extracted
from source documents (PDFs, registers, open data feeds). Extracted
records live under `data/extracted/<doc_key>/<schema_id>/*.json` and
validate against the matching schema here.

## Language convention — English only

All extracted data and all schemas are written in English: field names,
enum values, narrative descriptions, and schema documentation. No
Swedish anywhere except:

- **Proper nouns** preserve their original Swedish spelling: place names
  (Halland, Mölndal, Östergötland), substation names (Lindome, Älvsjö,
  Forsmark), company names (Ellevio, Vattenfall Eldistribution, Härjeåns
  elnät), program names (NordSyd), document titles.
- **Source-published area names** in `macro_area_name` / `subarea_name`
  fields keep their original spelling because that is how the source
  document references them. The English equivalent goes in
  `macro_area_short_name` / a translation field where one is needed.

Source documents are mostly Swedish. Translate narrative content to
English on extraction. Do NOT include "(Swedish: <term>)"
parentheticals in the data — if the original Swedish phrasing matters
for traceability, the page number in `source_page` is the link back.

## Why staging files instead of direct DB inserts

Schemas iterate. Postgres migrations are forward-only — splitting a
column or renaming an enum after a million rows are loaded is
expensive. We stage extracted data as JSON files until the schema has
stabilized (no changes across two extraction passes + spot-check
confirms correctness), then promote to a SQL migration + loader script
in one batch.

`sql/draft/` holds candidate migrations not yet wired into
`sql/migrations/`; `scripts/run_migrations.py` only auto-applies the
latter.

## Provenance contract

Every extracted record MUST carry these six fields, written by the
extractor (not hand-edited later):

- `source_doc_key` — string key resolving to `source_documents.doc_key`
  once migration 007 graduates from `sql/draft/` (e.g.
  `ellevio_nup_2025_2034`).
- `source_page` — page number in the source PDF.
- `extraction_method` — always `llm_extracted` for these.
- `extraction_run_id` — string identifying the extraction batch
  (date + doc + section + version, e.g.
  `2026-05-03-ellevio-nup-1.2-v1`). Lets us re-run extraction and diff
  outputs.
- `extraction_prompt_version` — version of the extraction prompt.
- `confidence_tier` — one of:
  - `observed` — direct quote / explicit number from the page
  - `derived` — computed from page facts using deterministic rules
  - `estimated` — inferred with caveats (note required)
  - `narrative` — qualitative only, no number

Loaders MUST reject records missing any of these.

## Naming

- Identifier fields and enum values are ASCII snake_case English
  (e.g. `subarea_key`, `regional_grid_only`, `gas_turbine`).
- Free-text fields are English narrative.
- Proper nouns preserve original Swedish spelling with diacritics
  (e.g. `municipality_name: "Mölndal"`, `station_name: "Älvsjö"`).

## Current schemas

| Schema | Source doc | Section | Status |
|---|---|---|---|
| `ellevio_subarea_profile.json` | `ellevio_nup_2025_2034` | §1.2 (p.7-15) | first pass extracted, awaiting validation |
| `vattenfall_macro_area_profile.json` | `vattenfall_eldistribution_nup_2025_2034` | §1.2 (p.5-6) | first pass extracted, awaiting validation |

## Reviewing extracted data

Two ways:

1. Open the raw JSON files under `data/extracted/<doc_key>/<schema_id>/`.
   One file per record. Diff-friendly in git.
2. Open the flattened CSVs under `data/extracted/_review/`. Easier
   spreadsheet-style validation.

If the review surfaces missing fields, schema drift, or wrong values,
fix the schema or re-extract — do NOT hand-patch the JSON files. They
are regenerable artifacts.

## Graduation criteria

Per data point kind, we promote to a SQL migration + loader when:

1. Schema hasn't changed in two extraction passes.
2. ≥10% of extracted rows have been spot-checked and confirmed correct.
3. Cross-doc joins (e.g. station-name aliasing) resolve at the rate
   we expect.

Then we batch-author migrations 007–009+ from the frozen schemas, write
loaders, and import everything in one shot.
