# Multi-species expansion

The current validated training dataset is for *Klebsiella pneumoniae* only.
This directory reserves separate inputs for the next cohorts so species are
never mixed without species-aware labels and preprocessing.

Planned cohorts:

- `escherichia_coli/`
- `acinetobacter_baumannii/`

For each cohort, store the source accession list, downloaded assemblies,
antimicrobial-susceptibility table, and a provenance file. Do not train a
cross-species model until the species labels and antibiotic definitions have
been harmonized.
