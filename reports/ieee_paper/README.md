# ResistMap AI conference-paper draft

The live project is https://www.overleaf.com/project/6af0292a5d645cc78305eb67 and its main source is `ResistMap_AI.tex`.

This is an editable research draft, not a submission. The author and affiliation follow the existing Overleaf file. The original source was downloaded before editing and preserved in `original_overleaf_backup.zip`.

## Evidence and claims

- The principal V2 result is mean development-fold accuracy 90.37% and balanced accuracy 83.66%. These are selection scores, not external-validation results.
- Pooled out-of-fold accuracy is 90.56%; pooled balanced accuracy is 84.91%. The manuscript distinguishes the aggregation rules.
- The historical 114-isolate V1 test is not independent validation for V2, because its results informed subsequent development.
- The sequencing pilot and assembly checkpoint establish processing progress, not improved predictive accuracy. The assembly checkpoint is explicitly identified as a saved stage, not an assertion about current completion of every processing job.
- No new classifier training was performed for the manuscript. `audit_results.py` reconstructs counts and scores from the saved predictions and records checksums of the source evidence.

## References

The paper includes exactly 18 cited publications, with DOI or publisher links. Bibliographic details and relevant claims were checked against publisher pages and PubMed/PMC records. Google Scholar access was unavailable through the research tool; direct Scholar indexing was not independently confirmed. The three pre-2018 sources are foundational algorithm/software papers (random forests, Extra Trees, and scikit-learn). No similarity-checker or AI-detector score is claimed.

## Editing and reproducibility

All figures are native TikZ/PGFPlots inside the main source; external image uploads are unnecessary. The scatter plot uses every selected-model development prediction. Seed-42 horizontal jitter is visual only. The pie chart describes cohort class composition, not population prevalence.

The expansion to the requested page length was additive: `expansion.diff` verifies that the earlier draft lost no lines. The `add_methods.tex`, `add_setup.tex`, and `add_results.tex` files preserve the inserted material for review. They are not separate LaTeX inputs; their contents are already integrated in the main file. Do not rerun the expansion script on an already expanded document.

Before submission, the author should review scientific interpretation, the venue's page limit and disclosure requirements, data provenance, and any new independent-validation results. Update text, figures, and tables together when the experiments change.
