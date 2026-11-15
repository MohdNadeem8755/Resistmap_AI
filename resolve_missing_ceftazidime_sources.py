"""Resolve missing development-sequence sources; download metadata only.

Uses the saved development manifest, never test labels. Public NCBI responses
are cached with their source URLs for reproducibility. No model is trained.
"""
import csv
import hashlib
import io
import json
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def main():
    root = Path(r"D:\ResistMap-AI")
    parent = root / "results/ceftazidime_sequence_readiness"
    out = parent / "ncbi_source_lookup"
    cache = out / "responses"
    cache.mkdir(parents=True, exist_ok=True)
    with (parent / "development_assembly_manifest.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert rows and all(row["partition"] == "development" for row in rows)
    missing = [row for row in rows if row["status"] != "ready"]
    samples = [row["BioSample"] for row in missing]
    assert len(samples) == len(set(samples))

    def fetch(endpoint, **params):
        params["tool"] = "ResistMapSequenceSourceAudit"
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/" + endpoint
        url += "?" + urllib.parse.urlencode(params)
        key = hashlib.sha256(url.encode()).hexdigest()
        path = cache / (key + ".txt")
        if path.exists():
            return path.read_text(encoding="utf-8")
        for attempt in range(4):
            try:
                time.sleep(0.4)
                request = urllib.request.Request(url, headers={
                    "User-Agent": "ResistMapSequenceSourceAudit/1.0"
                })
                with urllib.request.urlopen(request, timeout=45) as response:
                    text = response.read().decode("utf-8")
                if endpoint == "esearch.fcgi":
                    parsed = json.loads(text)
                    if "esearchresult" not in parsed or parsed.get("error"):
                        raise ValueError("NCBI returned an API error")
                if endpoint == "efetch.fcgi" and not text.startswith("Run,"):
                    raise ValueError("NCBI did not return a RunInfo CSV")
                path.write_text(text, encoding="utf-8")
                path.with_suffix(".json").write_text(json.dumps({
                    "url": url, "retrieved_utc": datetime.now(timezone.utc).isoformat()
                }, indent=2), encoding="utf-8")
                return text
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)

    def search(database, identifiers):
        result = json.loads(fetch(
            "esearch.fcgi", db=database, term=" OR ".join(identifiers),
            retmode="json", retmax=10000
        ))["esearchresult"]
        if int(result["count"]) != len(result["idlist"]):
            raise ValueError("Search was truncated; do not report incomplete coverage")
        return result["idlist"]

    control = next(row for row in rows if row["status"] == "ready")
    if not search("assembly", [control["BioSample"]]):
        raise ValueError("Positive assembly search control failed")
    assembly_candidates = set()
    sra_ids = set()
    for start in range(0, len(samples), 45):
        batch = samples[start:start + 45]
        assembly_candidates.update(search("assembly", batch))
        sra_ids.update(search("sra", batch))
        print(f"Looked up {min(start + 45, len(samples))}/{len(samples)} BioSamples", flush=True)

    # New assembly hits require explicit BioSample verification before use.
    (out / "assembly_candidate_uids.json").write_text(
        json.dumps(sorted(assembly_candidates), indent=2), encoding="utf-8"
    )
    run_map = {}
    sra_ids = sorted(sra_ids)
    wanted = set(samples)
    rejected_run_count = 0
    for start in range(0, len(sra_ids), 100):
        body = fetch("efetch.fcgi", db="sra", id=",".join(sra_ids[start:start + 100]),
                     rettype="runinfo", retmode="text")
        for run in csv.DictReader(io.StringIO(body)):
            sample = run.get("BioSample", "").strip().upper()
            if sample not in wanted:
                rejected_run_count += 1
                continue
            accession = run["Run"]
            if accession in run_map and run_map[accession] != run:
                raise ValueError("Conflicting SRA metadata for " + accession)
            run_map[accession] = run
    runs = list(run_map.values())
    by_sample = {sample: [] for sample in samples}
    for run in runs:
        by_sample[run["BioSample"].strip().upper()].append(run)
    manifest = []
    for row in missing:
        found = by_sample[row["BioSample"]]
        usable = [run for run in found
                  if run.get("LibraryStrategy") == "WGS"
                  and run.get("LibrarySource") == "GENOMIC"
                  and run.get("Platform") == "ILLUMINA"
                  and run.get("LibraryLayout") == "PAIRED"
                  and run.get("Consent") == "public"]
        manifest.append({**row, "SRA_runs": ";".join(run["Run"] for run in found),
                         "candidate_paired_Illumina_WGS_runs": ";".join(run["Run"] for run in usable),
                         "source_status": "raw_read_candidate" if usable else
                             "other_reads_need_review" if found else "no_SRA_runinfo_match"})

    def save_csv(name, records):
        if records:
            with (out / name).open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(records[0]))
                writer.writeheader()
                writer.writerows(records)

    save_csv("missing_assembly_source_manifest.csv", manifest)
    save_csv("matched_sra_runinfo.csv", runs)
    sizes = [float(run["size_MB"]) for run in runs if run.get("size_MB")]
    summary = {
        "development_samples": len(rows), "existing_assembly_accessions": len(rows)-len(missing),
        "missing_assembly_samples": len(missing),
        "assembly_search_candidate_records": len(assembly_candidates),
        "samples_with_SRA_runinfo": sum(bool(value) for value in by_sample.values()),
        "matched_SRA_runs": len(runs),
        "source_status_counts": dict(Counter(row["source_status"] for row in manifest)),
        "platforms": dict(Counter(run.get("Platform", "") for run in runs)),
        "layouts": dict(Counter(run.get("LibraryLayout", "") for run in runs)),
        "reported_SRA_size_MB_sum": round(sum(sizes), 2),
        "runs_missing_size": len(runs)-len(sizes),
        "unmatched_runinfo_rows": rejected_run_count,
        "note": "Metadata availability only. Reads not downloaded or QC checked. SRA size is not FASTQ/assembly disk requirement.",
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("Saved:", out)


if __name__ == "__main__":
    main()
