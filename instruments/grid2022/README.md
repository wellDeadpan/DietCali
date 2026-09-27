# Harvard Grid 2022 FFQ

Instrument-specific files. Nothing here refers to a particular dataset's
variable names; the link from data variables to questions lives in
`datasets/<name>/var_map.csv`.

| File | Content |
|---|---|
| `questionnaire.csv` | The printed form (FINAL-GRID-2022 proof, 4 pages) transcribed by hand: one row per question / food item, with printed label, section, portion, examples, include/exclude instructions, response type and options. `q_id` is the stable key. |
| `frequency_factors.yml` | Grid 2022 frequency factors (ffwgt0–ffwgt9) as servings/day. The `value` codes are the response coding of the dataset (perls9: value = ffwgt + 1). |

Notes on `questionnaire.csv`
- Q5 food items use the 9-level frequency scale; each Q5 section also has a passthru (P) bubble.
- `portion_text` is blank where the form prints no portion (checked against the PDF render and text layer).
