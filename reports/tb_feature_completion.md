# TB feature construction — 2026-11-15

Completed and reloaded the descriptive binary sparse mutation matrix:

- 51,012 samples, 1,850,698 features, 74,783,493 nonzero entries.
- 404,897 matched binary label rows across 28 drugs.
- Quarantined 38 mapping rows affecting 19 ambiguous sample accessions.
- Excluded 22 further samples without valid mutation features; these were not interpreted as wild type.
- Saved artifacts: `data/processed/multispecies/tuberculosis/features/`.

Reload checks passed for matrix dimensions, binary values, nonempty rows, unique accession/genome mappings, contiguous row numbers, unique sample/drug labels, feature-name alignment and dashboard report agreement. Synthetic regression check passed for duplicated mutation records, ambiguous mappings, missing features and Arrow index handling.

This vocabulary is descriptive and uses the full retained cohort. TB grouped partitioning, training-only feature selection and model evaluation remain pending. No TB accuracy or independent validation is claimed.

Dashboard frontend production build passed. Four dashboard API tests and six prediction/input checks passed. Two speech tests failed because the selected Python environment lacks speech dependencies and the real speech-test WAV fixture is absent. The existing speech model files alone do not establish working voice inference. Local server startup succeeded on http://127.0.0.1:8011. Public deployment and email-dependent external validation remain pending.
