"""Build a reproducible QC manifest for the 445-sample development cohort.

This is a conservative screening audit. It never deletes data and it does not
claim that species identification or self-mapping alone excludes contamination.
Optional CheckM2/ConFindr columns can be merged later when their result files are
available.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCALE = ROOT / "results" / "ceftazidime_sequence_scaleup"
READS = SCALE / "reads"
PILOT = ROOT / "results" / "ceftazidime_sequence_pilot"
OUT = SCALE / "qc_review"

# Conservative, explicit screening thresholds. Flags request review; only a
# species mismatch is an automatic exclusion before contamination results exist.
LIMITS = {
    "genome_length_min_bp": 4_500_000,
    "genome_length_max_bp": 6_500_000,
    "contigs_max": 500,
    "n50_min_bp": 20_000,
    "ambiguous_bases_max": 1_000,
    "reads_retained_min_pct": 80.0,
    "post_qc_q30_min_pct": 70.0,
    "primary_mapped_min_pct": 95.0,
    "assembly_breadth_ge10x_min_pct": 90.0,
    "mean_depth_min_x": 20.0,
    "checkm2_completeness_min_pct": 90.0,
    "checkm2_contamination_max_pct": 5.0,
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, str], key: str) -> float | None:
    value = row.get(key, "").strip()
    return None if value == "" else float(value)


def truthy(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes"}


def pilot_read_rows() -> list[dict[str, str]]:
    processing = {r["BioSample"]: r for r in read_csv(PILOT / "pilot_processing_summary.csv")}
    biological = {r["BioSample"]: r for r in read_csv(
        PILOT / "biological_qc" / "pilot_biological_qc_summary.csv")}
    general = {r["BioSample"]: r for r in read_csv(PILOT / "pilot_qc_summary.csv")}
    rows = []
    for sample, base in processing.items():
        if base["source"] != "reads":
            continue
        bio, qc = biological[sample], general[sample]
        rows.append({
            **base,
            "species": bio["species"],
            "species_match": bio["species_match"],
            "QC_warnings": bio["Kleborate_QC_warnings"],
            "reads_retained_pct": qc.get("reads_retained_pct", ""),
            "post_QC_Q30_pct": qc.get("post_QC_Q30_pct", ""),
            "primary_mapped_pct": bio["primary_reads_mapped_pct"],
            "assembly_bases_ge10x_pct": bio["assembly_breadth_ge10x_pct"],
            "mean_depth_MQ20_overlap_removed": bio["mapped_depth_MQ20"],
            "uniform_sampled_quality": "True" if bio["source_quality_note"] else "False",
            "source_quality_note": bio["source_quality_note"],
        })
    return rows


def optional_checkm2() -> dict[str, dict[str, str]]:
    path = OUT / "checkm2" / "quality_report.tsv"
    if not path.exists():
        return {}
    rows = read_csv(path)
    result = {}
    for row in rows:
        name = row.get("Name", row.get("name", ""))
        result[name] = row
    return result


def audit(row: dict[str, str], checkm: dict[str, str] | None) -> dict[str, str]:
    hard, review, notes = [], [], []
    if row.get("species") != "Klebsiella pneumoniae" or row.get("species_match") != "strong":
        hard.append("species_mismatch")
    if row.get("QC_warnings", "-") not in {"", "-"}:
        review.append("kleborate_qc_warning")

    tests = [
        (number(row, "length_bp"), "genome_length_outside_4.5_6.5Mb",
         lambda x: x < LIMITS["genome_length_min_bp"] or x > LIMITS["genome_length_max_bp"]),
        (number(row, "contigs"), "contigs_gt_500", lambda x: x > LIMITS["contigs_max"]),
        (number(row, "N50"), "n50_lt_20kb", lambda x: x < LIMITS["n50_min_bp"]),
        (number(row, "ambiguous_bases"), "ambiguous_bases_gt_1000",
         lambda x: x > LIMITS["ambiguous_bases_max"]),
    ]
    if row.get("source") == "reads":
        tests.extend([
            (number(row, "reads_retained_pct"), "reads_retained_lt_80pct",
             lambda x: x < LIMITS["reads_retained_min_pct"]),
            (number(row, "post_QC_Q30_pct"), "post_qc_q30_lt_70pct",
             lambda x: x < LIMITS["post_qc_q30_min_pct"]),
            (number(row, "primary_mapped_pct"), "primary_mapped_lt_95pct",
             lambda x: x < LIMITS["primary_mapped_min_pct"]),
            (number(row, "assembly_bases_ge10x_pct"), "breadth_ge10x_lt_90pct",
             lambda x: x < LIMITS["assembly_breadth_ge10x_min_pct"]),
            (number(row, "mean_depth_MQ20_overlap_removed"), "mean_depth_lt_20x",
             lambda x: x < LIMITS["mean_depth_min_x"]),
        ])
        if truthy(row.get("uniform_sampled_quality", "False")):
            review.append("uniform_sampled_quality")
    for value, flag, failed in tests:
        if value is not None and failed(value):
            review.append(flag)

    completeness = contamination = None
    if checkm:
        completeness = float(checkm.get("Completeness", checkm.get("completeness", "nan")))
        contamination = float(checkm.get("Contamination", checkm.get("contamination", "nan")))
        if completeness < LIMITS["checkm2_completeness_min_pct"]:
            review.append("checkm2_completeness_lt_90pct")
        if contamination >= LIMITS["checkm2_contamination_max_pct"]:
            hard.append("checkm2_contamination_ge_5pct")
    else:
        notes.append("dedicated_contamination_screen_pending")

    if hard:
        decision = "exclude"
    elif review:
        decision = "manual_review"
    else:
        decision = "provisional_pass" if checkm else "provisional_pass_contamination_pending"
    return {
        "BioSample": row["BioSample"],
        "BioProject": row.get("BioProject", ""),
        "source": row.get("source", ""),
        "species": row.get("species", ""),
        "species_match": row.get("species_match", ""),
        "length_bp": row.get("length_bp", ""),
        "contigs": row.get("contigs", ""),
        "N50": row.get("N50", ""),
        "ambiguous_bases": row.get("ambiguous_bases", ""),
        "reads_retained_pct": row.get("reads_retained_pct", ""),
        "post_QC_Q30_pct": row.get("post_QC_Q30_pct", ""),
        "primary_mapped_pct": row.get("primary_mapped_pct", ""),
        "assembly_bases_ge10x_pct": row.get("assembly_bases_ge10x_pct", ""),
        "mean_depth_MQ20_overlap_removed": row.get("mean_depth_MQ20_overlap_removed", ""),
        "checkm2_completeness_pct": "" if completeness is None else str(completeness),
        "checkm2_contamination_pct": "" if contamination is None else str(contamination),
        "decision": decision,
        "hard_exclusion_reasons": ";".join(sorted(set(hard))),
        "review_flags": ";".join(sorted(set(review))),
        "notes": ";".join(notes + ([row.get("source_quality_note", "")] if row.get("source_quality_note") else [])),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    assembly = read_csv(SCALE / "assembly_qc_summary.csv")
    reads = read_csv(READS / "read_qc_summary.csv")
    pilot_reads = pilot_read_rows()
    rows = assembly + reads + pilot_reads
    samples = [r["BioSample"] for r in rows]
    if len(rows) != 445 or len(set(samples)) != 445:
        raise ValueError(f"Expected 445 unique samples, got {len(rows)} rows/{len(set(samples))} unique")

    checkm = optional_checkm2()
    audited = [audit(row, checkm.get(row["BioSample"])) for row in rows]
    fields = list(audited[0])
    with (OUT / "development_qc_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(audited)

    decisions = Counter(r["decision"] for r in audited)
    flags = Counter(flag for r in audited for flag in r["review_flags"].split(";") if flag)
    exclusions = Counter(flag for r in audited for flag in r["hard_exclusion_reasons"].split(";") if flag)
    summary = {
        "cohort_samples": len(audited),
        "sources": dict(Counter(r["source"] for r in audited)),
        "decisions": dict(decisions),
        "hard_exclusion_reasons": dict(exclusions),
        "review_flags": dict(flags),
        "dedicated_contamination_results_available": bool(checkm),
        "thresholds": LIMITS,
        "important_limitation": (
            "Species, assembly and own-assembly mapping screens do not prove absence of contamination. "
            "Until CheckM2/ConFindr or an equivalent dedicated screen is merged, passes are provisional."
        ),
    }
    (OUT / "qc_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
