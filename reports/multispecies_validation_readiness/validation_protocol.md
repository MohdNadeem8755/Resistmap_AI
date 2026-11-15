# Independent validation readiness

No independent E. coli or A. baumannii cohort has been established by this audit.
The existing data have been explored; another split cannot be described as an untouched external test.
Previously seen keys include all raw isolate records, including excluded records.
Artifact hashes preserve current development provenance; they do not select or certify a final model.

## Required before evaluation

1. Obtain a separately sourced cohort with documented sampling, species, dates, BioSample, assembly version, annotation pipeline/database, and available quality evidence.
2. Check BioSample, assembly (including paired/version aliases), known SNP cluster, and exact profile overlap against all development data. Review project overlap and lineage relationships; identifier separation alone does not prove independence.
3. Confirm the assembly underlying each annotation. A newly retrieved assembly for an old BioSample is neither a new sample nor proof of annotation provenance.
4. Predeclare quality exclusions, missing-data handling, the model, preprocessing, and endpoints before examining new outcomes. Do not remove unusual profiles merely because they are unusual.
5. Fit vocabulary/scaling/reduction on development data only; freeze them for validation. Report unseen features and zero-retained-feature records separately.
6. For unsupervised evaluation, report stability and blinded independent review with an explicit reference standard. Without that standard, do not report anomaly accuracy, sensitivity, or specificity.
7. Where phenotype labels support a separate supervised endpoint, retain the natural test distribution, restrict balancing to training, and report per-drug support and group-aware uncertainty. Do not tune on the external cohort.

Missing quality fields remain unknown. Current lookup results and metadata audits do not establish raw-read QC or biological validity.
