"""Reproducible 5-assembly/5-read technical pilot. No model training.

Windows usage: python ceftazidime_sequence_pilot.py prepare|download|setup|process
Sources: NCBI E-utilities/Genomes FTP, ENA Portal API, Bioconda.
Only saved development samples are eligible; labels stratify the technical
pilot, while predictions/errors/test data are never used for selection.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(r"D:\ResistMap-AI")
OUT = ROOT / "results/ceftazidime_sequence_pilot"
READY = ROOT / "results/ceftazidime_sequence_readiness"
WSL = ["wsl", "-d", "Ubuntu", "--"]


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def save_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def fetch(url):
    cache = OUT / "metadata_cache"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (hashlib.sha256(url.encode()).hexdigest() + ".txt")
    if path.exists():
        return path.read_text(encoding="utf-8")
    for attempt in range(4):
        try:
            time.sleep(.4)
            request = urllib.request.Request(url, headers={"User-Agent": "ResistMapPilot/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response:
                text = response.read().decode("utf-8")
            path.write_text(text, encoding="utf-8")
            save_json(path.with_suffix(".source.json"), {"url": url, "retrieved_unix": time.time()})
            return text
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def eutils(endpoint, **params):
    params["tool"] = "ResistMapPilot"
    return json.loads(fetch("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/" + endpoint + "?" + urllib.parse.urlencode(params)))


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "pilot_manifest.csv"
    if manifest_path.exists():
        selected = read_csv(manifest_path)
    else:
        inventory = read_csv(READY / "development_assembly_manifest.csv")
        split = read_csv(ROOT / "results/ceftazidime_clsi_split_v2.csv")
        allowed = {row["BioSample"] for row in split if row["partition"] == "train"}
        # Read only the observed class, never error/prediction/probability fields.
        label_rows = read_csv(ROOT / "results/ceftazidime_rf_oof_predictions.csv")
        labels = {row["BioSample"]: int(row["actual"]) for row in label_rows}
        if len(labels) != len(label_rows) or set(labels) != allowed:
            raise ValueError("Development label audit does not match the saved split")
        sources = {row["BioSample"]: row for row in read_csv(
            READY / "ncbi_source_lookup/missing_assembly_source_manifest.csv")}
        selected = []
        for source, status in [("assembly", "ready"), ("reads", "missing_or_invalid_accession")]:
            pool = [row for row in inventory if row["status"] == status]
            if source == "reads":
                pool = [row for row in pool if sources[row["BioSample"]]["source_status"] == "raw_read_candidate"
                        and len(sources[row["BioSample"]]["candidate_paired_Illumina_WGS_runs"].split(";")) == 1]
            projects = set()
            used = set()
            for label in [0, 1, 0, 1, 1]:
                eligible = [row for row in pool if labels[row["BioSample"]] == label and row["BioSample"] not in used]
                if not eligible:
                    raise ValueError("Cannot construct the predefined stratified pilot")
                row = min(eligible, key=lambda r: (
                    r["BioProject"] in projects,
                    hashlib.sha256(("pilot-42:" + r["BioSample"]).encode()).hexdigest()))
                sample = row["BioSample"]
                if sample not in allowed or row["partition"] != "development":
                    raise ValueError("Non-development sample selected")
                selected.append({"BioSample": sample, "Isolate": row["Isolate"], "BioProject": row["BioProject"],
                                 "target": label, "source": source, "Assembly": row["Assembly"],
                                 "Run": sources[sample]["candidate_paired_Illumina_WGS_runs"] if source == "reads" else ""})
                used.add(sample)
                projects.add(row["BioProject"])
        save_csv(manifest_path, selected)
    if len(selected) != 10 or len({r['BioSample'] for r in selected}) != 10:
        raise ValueError("Invalid pilot manifest")
    downloads = []
    for row in selected:
        sample = row["BioSample"]
        if row["source"] == "assembly":
            accession = row["Assembly"]
            search = eutils("esearch.fcgi", db="assembly", term=accession, retmode="json", retmax=20)["esearchresult"]
            if not search["idlist"]:
                raise ValueError("Assembly lookup failed: " + accession)
            result = eutils("esummary.fcgi", db="assembly", id=",".join(search["idlist"]), retmode="json")["result"]
            matches = [result[uid] for uid in result["uids"] if result[uid].get("biosampleaccn") == sample
                       and accession in (result[uid].get("assemblyaccession"), result[uid].get("synonym", {}).get("genbank"))]
            if len(matches) != 1:
                raise ValueError("Ambiguous or mismatched assembly BioSample: " + sample)
            base = matches[0]["ftppath_genbank"].replace("ftp://", "https://").rstrip("/")
            name = base.rsplit("/", 1)[1] + "_genomic.fna.gz"
            checksums = dict((line.split()[1].removeprefix("./"), line.split()[0])
                             for line in fetch(base + "/md5checksums.txt").splitlines() if len(line.split()) == 2)
            downloads.append({"BioSample": sample, "kind": "assembly", "url": base + "/" + name,
                              "md5": checksums[name], "bytes": None,
                              "relative_path": "downloads/" + sample + ".fna.gz"})
        else:
            url = "https://www.ebi.ac.uk/ena/portal/api/filereport?" + urllib.parse.urlencode({
                "accession": row["Run"], "result": "read_run", "format": "json",
                "fields": "run_accession,sample_accession,secondary_sample_accession,fastq_ftp,fastq_md5,fastq_bytes"})
            reports = json.loads(fetch(url))
            if len(reports) != 1 or reports[0]["run_accession"] != row["Run"] or sample not in (
                reports[0]["sample_accession"], reports[0]["secondary_sample_accession"]):
                raise ValueError("ENA run-to-BioSample mismatch: " + sample)
            report = reports[0]
            urls, md5s, sizes = (report[key].split(";") for key in ("fastq_ftp", "fastq_md5", "fastq_bytes"))
            if len(urls) != len(md5s) or len(urls) != len(sizes):
                raise ValueError("Incomplete ENA file metadata")
            mates = {}
            for remote, checksum, size in zip(urls, md5s, sizes):
                match = re.search(r"_([12])\.fastq\.gz$", remote)
                if match:
                    mate = match.group(1)
                    if mate in mates:
                        raise ValueError("Duplicate mate in ENA report")
                    mates[mate] = {"BioSample": sample, "kind": "read" + mate,
                        "url": "https://" + remote.removeprefix("ftp://").removeprefix("https://"),
                        "md5": checksum, "bytes": int(size),
                        "relative_path": "downloads/" + sample + "_" + mate + ".fastq.gz"}
            if set(mates) != {"1", "2"}:
                raise ValueError("Paired FASTQ files unavailable; preserve this sample for review: " + sample)
            downloads.extend(mates.values())
        print("Verified source:", sample, row["source"], flush=True)
    save_json(OUT / "download_manifest.json", downloads)
    print("Pilot: 10 samples, 4 susceptible / 6 resistant; 5 assemblies / 5 read pairs")
    print("FASTQ download GB:", round(sum(item["bytes"] or 0 for item in downloads) / 1e9, 3))


def digest(path, algorithm="md5"):
    value = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def download_file(item):
    path = OUT / item["relative_path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and digest(path) == item["md5"]:
        return path
    partial = path.with_name(path.name + ".part")
    for attempt in range(4):
        try:
            print("Downloading:", path.name, flush=True)
            expected = item.get("bytes")
            if expected:
                offset = partial.stat().st_size if partial.exists() else 0
                if offset > expected:
                    raise ValueError("Partial download exceeds expected length")
                # Bounded range requests provide resumability and progress on
                # slow ENA transfers. Server ranges are checked before appending.
                while offset < expected:
                    end = min(offset + 8 * 1024 * 1024 - 1, expected - 1)
                    request = urllib.request.Request(item["url"], headers={"Range": f"bytes={offset}-{end}"})
                    with urllib.request.urlopen(request, timeout=45) as response:
                        if response.status != 206 or response.headers.get("Content-Range") != f"bytes {offset}-{end}/{expected}":
                            raise ValueError("Server did not honor the requested byte range")
                        block = response.read()
                    if len(block) != end - offset + 1:
                        raise ValueError("Incomplete range response")
                    with partial.open("ab") as handle:
                        handle.write(block)
                    offset += len(block)
                    print(f"{path.name}: {offset / expected:.0%}", flush=True)
            else:
                with urllib.request.urlopen(item["url"], timeout=90) as response, partial.open("wb") as handle:
                    shutil.copyfileobj(response, handle, 1024 * 1024)
            if item.get("bytes") is not None and partial.stat().st_size != item["bytes"]:
                raise ValueError("Download size mismatch")
            if digest(partial) != item["md5"]:
                with partial.open("wb"):
                    pass
                raise ValueError("Download checksum mismatch")
            partial.replace(path)
            return path
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def download():
    items = json.loads((OUT / "download_manifest.json").read_text())
    if shutil.disk_usage(ROOT).free < 20 * 1024 ** 3:
        raise RuntimeError("At least 20 GiB free space is required for this technical pilot")
    with ThreadPoolExecutor(max_workers=2) as pool:
        paths = list(pool.map(download_file, items))
    for index, (item, path) in enumerate(zip(items, paths), 1):
        print(f"Verified {index}/{len(items)}: {path.name}", flush=True)
        if item["kind"] == "assembly":
            fasta = OUT / "assemblies" / (item["BioSample"] + ".fna")
            fasta.parent.mkdir(exist_ok=True)
            with gzip.open(path, "rb") as source, fasta.open("wb") as target:
                shutil.copyfileobj(source, target)
            if not fasta.read_bytes().startswith(b">"):
                raise ValueError("Invalid genome FASTA")
    print("All 15 sequence files passed source MD5 checks.")


def linux_path(path):
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:]


def wsl_output(args):
    return subprocess.check_output(WSL + args, text=True, encoding="utf-8").strip()


def setup():
    if (OUT / "linux_environment.json").exists():
        print("Pilot environment already configured; keeping the recorded database and packages.")
        return
    tools = OUT / "tools"
    tools.mkdir(exist_ok=True)
    binary = tools / "micromamba"
    if not binary.exists():
        url = "https://micro.mamba.pm/api/micromamba/linux-64/latest"
        with urllib.request.urlopen(url, timeout=90) as response:
            archive = response.read()
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:bz2") as tar:
            member = tar.getmember("bin/micromamba")
            if not member.isfile():
                raise ValueError("Unexpected micromamba archive")
            binary.write_bytes(tar.extractfile(member).read())
        save_json(tools / "micromamba_source.json", {"url": url, "sha256": digest(binary, "sha256")})
    subprocess.run(WSL + ["chmod", "+x", linux_path(binary)], check=True)
    home = wsl_output(["printenv", "HOME"])
    base = home + "/.local/share/resistmap-sequence-pilot"
    env = base + "/env"
    command = WSL + ["env", "MAMBA_ROOT_PREFIX=" + base, linux_path(binary)]
    log = OUT / "setup.log"
    with log.open("a", encoding="utf-8") as handle:
        subprocess.run(command + ["create", "-y", "-p", env, "--override-channels",
                       "-c", "conda-forge", "-c", "bioconda", "--strict-channel-priority",
                       "python=3.12", "ncbi-amrfinderplus", "fastp", "skesa"],
                       stdout=handle, stderr=subprocess.STDOUT, check=True)
        subprocess.run(command + ["run", "-p", env, "amrfinder", "-u"],
                       stdout=handle, stderr=subprocess.STDOUT, check=True)
    version = subprocess.check_output(command + ["run", "-p", env, "amrfinder", "-V"], stderr=subprocess.STDOUT, text=True)
    organisms = subprocess.check_output(command + ["run", "-p", env, "amrfinder", "-l"], stderr=subprocess.STDOUT, text=True)
    (OUT / "amrfinder_versions.txt").write_text(version, encoding="utf-8")
    (OUT / "amrfinder_organisms.txt").write_text(organisms, encoding="utf-8")
    explicit = subprocess.check_output(command + ["list", "-p", env, "--explicit"], text=True)
    (OUT / "environment_explicit.txt").write_text(explicit, encoding="utf-8")
    save_json(OUT / "linux_environment.json", {"base": base, "env": env, "micromamba": linux_path(binary)})
    print(version)
    print("Linux environment ready. Package and database versions saved.")


def fasta_stats(path):
    lengths = []
    length = 0
    ambiguous = 0
    with path.open() as handle:
        for line in handle:
            if line.startswith(">"):
                if length:
                    lengths.append(length)
                length = 0
            else:
                sequence = line.strip().upper()
                length += len(sequence)
                ambiguous += sum(base not in "ACGT" for base in sequence)
    if length:
        lengths.append(length)
    total = sum(lengths)
    if not total:
        raise ValueError("Empty assembly: " + str(path))
    cumulative = 0
    for n50 in sorted(lengths, reverse=True):
        cumulative += n50
        if cumulative >= total / 2:
            break
    return {"length_bp": total, "contigs": len(lengths), "N50": n50, "ambiguous_bases": ambiguous}


def process(assemblies_only=False, wait_downloads=False):
    config = json.loads((OUT / "linux_environment.json").read_text())
    command = WSL + ["env", "MAMBA_ROOT_PREFIX=" + config["base"], config["micromamba"], "run", "-p", config["env"]]
    current_version = subprocess.check_output(command + ["amrfinder", "-V"], stderr=subprocess.STDOUT, text=True)
    def version_fields(text):
        return [line.strip() for line in text.splitlines()
                if line.startswith(("Software version:", "Database version:", "Database directory:"))]
    if version_fields(current_version) != version_fields((OUT / "amrfinder_versions.txt").read_text(encoding="utf-8")):
        raise ValueError("AMRFinderPlus software/database changed; preserve the pilot's recorded versions")
    organism_text = (OUT / "amrfinder_organisms.txt").read_text()
    if "Klebsiella_pneumoniae" not in organism_text:
        raise ValueError("Check supported organism options before running AMRFinderPlus")
    reports = OUT / "amrfinder"
    qc = OUT / "qc"
    assemblies = OUT / "assemblies"
    for directory in (reports, qc, assemblies, OUT / "logs"):
        directory.mkdir(exist_ok=True)
    selected = read_csv(OUT / "pilot_manifest.csv")
    if assemblies_only:
        selected = [row for row in selected if row["source"] == "assembly"]
    input_manifest = json.loads((OUT / "download_manifest.json").read_text())
    summary = []
    feature_rows = {}
    for row in selected:
        sample = row["BioSample"]
        for item in (item for item in input_manifest if item["BioSample"] == sample):
            path = OUT / item["relative_path"]
            if wait_downloads and not path.exists():
                print("Waiting for verified download:", path.name, flush=True)
                deadline = time.monotonic() + 1800
                while not path.exists() and time.monotonic() < deadline:
                    time.sleep(2)
            if not path.exists() or digest(path) != item["md5"]:
                raise ValueError("Input missing or checksum mismatch; run download stage: " + item["relative_path"])
        fasta = assemblies / (sample + ".fna")
        if row["source"] == "assembly":
            # Separate analysis copies avoid concurrent decompression by the
            # downloader changing a FASTA that BLAST is currently reading.
            analysis = OUT / "analysis_inputs"
            analysis.mkdir(exist_ok=True)
            fasta = analysis / (sample + ".fna")
            if not fasta.exists():
                with gzip.open(OUT / "downloads" / (sample + ".fna.gz"), "rb") as src, fasta.open("wb") as dest:
                    shutil.copyfileobj(src, dest)
        print("Processing:", sample, row["source"], flush=True)
        def run(args, log_name):
            print("Running", args[0], "for", sample, flush=True)
            save_json(OUT / "logs" / (log_name + ".command.json"), args)
            with (OUT / "logs" / (log_name + ".log")).open("w", encoding="utf-8") as handle:
                subprocess.run(command + args, stdout=handle, stderr=subprocess.STDOUT, check=True)
            print("Finished", args[0], "for", sample, flush=True)
        if row["source"] == "reads" and not fasta.exists():
            read1, read2 = [OUT / "downloads" / (sample + f"_{mate}.fastq.gz") for mate in (1, 2)]
            clean1, clean2 = [qc / (sample + f"_{mate}.fastq.gz") for mate in (1, 2)]
            run(["fastp", "-i", linux_path(read1), "-I", linux_path(read2),
                 "-o", linux_path(clean1), "-O", linux_path(clean2), "--thread", "4",
                 "--detect_adapter_for_pe", "--json", linux_path(qc / (sample + ".json")),
                 "--html", linux_path(qc / (sample + ".html"))], sample + "_fastp")
            partial = fasta.with_suffix(".partial.fna")
            run(["skesa", "--reads", linux_path(clean1) + "," + linux_path(clean2),
                 "--cores", "4", "--memory", "4", "--contigs_out", linux_path(partial)], sample + "_skesa")
            fasta_stats(partial)
            partial.replace(fasta)
        stats = fasta_stats(fasta)
        report = reports / (sample + ".tsv")
        if not report.exists():
            partial = report.with_suffix(".partial.tsv")
            run(["amrfinder", "-n", linux_path(fasta), "-O", "Klebsiella_pneumoniae",
                 "--threads", "4", "--plus", "--mutation_all", linux_path(reports / (sample + ".all_mutations.tsv")),
                 "-o", linux_path(partial)], sample + "_amrfinder")
            partial.replace(report)
        with report.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            columns = reader.fieldnames or []
            symbol_field = next((name for name in ("Element symbol", "Gene symbol") if name in columns), None)
            identity_field = next((name for name in ("% Identity to reference", "% Identity to reference sequence") if name in columns), None)
            coverage_field = next((name for name in ("% Coverage of reference", "% Coverage of reference sequence") if name in columns), None)
            if not all((symbol_field, identity_field, coverage_field)):
                raise ValueError("Unexpected AMRFinderPlus report format")
            hits = list(reader)
        features = {}
        for hit in hits:
            gene = hit[symbol_field]
            if not gene or gene == "NA":
                continue
            features["present:" + gene] = 1
            features["method:" + gene + ":" + hit["Method"]] = 1
            for field, prefix in [(identity_field, "identity:"), (coverage_field, "coverage:")]:
                try:
                    value = float(hit[field]) / 100
                except (ValueError, KeyError):
                    continue
                features[prefix + gene] = max(features.get(prefix + gene, 0), value)
        feature_rows[sample] = features
        summary.append({**row, **stats, "AMR_report_rows": len(hits), "feature_count": len(features),
                        "assembly_sha256": digest(fasta, "sha256")})
        save_csv(OUT / "pilot_processing_summary.csv", summary)
        save_json(OUT / "pilot_genomic_features.json", feature_rows)
        print("Completed:", sample, "contigs", stats["contigs"], "report rows", len(hits), flush=True)
    print(f"Technical processing completed for {len(selected)} requested samples. No accuracy measured or model trained.")


def audit():
    selected = read_csv(OUT / "pilot_manifest.csv")
    summary = read_csv(OUT / "pilot_processing_summary.csv")
    features = json.loads((OUT / "pilot_genomic_features.json").read_text())
    expected = {row["BioSample"] for row in selected}
    development = {row["BioSample"] for row in read_csv(ROOT / "results/ceftazidime_clsi_split_v2.csv")
                   if row["partition"] == "train"}
    if len(summary) != 10 or {row["BioSample"] for row in summary} != expected or set(features) != expected:
        raise ValueError("All ten pilot samples must finish before the final audit")
    if not expected <= development:
        raise ValueError("Pilot includes a non-development sample")
    for row in summary:
        sample = row["BioSample"]
        values = features[sample]
        if not values or not all(key.startswith(("present:", "method:", "identity:", "coverage:"))
                                 and isinstance(value, (int, float)) and math.isfinite(value)
                                 and 0 <= value <= 1 for key, value in values.items()):
            raise ValueError("Invalid genomic feature dictionary: " + sample)
        row["identity_features"] = sum(key.startswith("identity:") for key in values)
        row["coverage_features"] = sum(key.startswith("coverage:") for key in values)
        row["reads_retained_pct"] = ""
        row["post_QC_Q30_pct"] = ""
        row["estimated_depth_x"] = ""
        row["sampled_quality_levels"] = ""
        row["QC_review_note"] = "Species/contamination and mapped coverage not assessed"
        if row["source"] == "reads":
            qc = json.loads((OUT / "qc" / (sample + ".json")).read_text())["summary"]
            before, after = qc["before_filtering"], qc["after_filtering"]
            row["reads_retained_pct"] = round(100 * after["total_reads"] / before["total_reads"], 2)
            row["post_QC_Q30_pct"] = round(100 * after["q30_rate"], 2)
            # This is a rough base-count ratio, not mapped-depth measurement.
            row["estimated_depth_x"] = round(after["total_bases"] / int(row["length_bp"]), 1)
            mate_levels = {}
            for mate in (1, 2):
                levels = set()
                with gzip.open(OUT / "downloads" / (sample + f"_{mate}.fastq.gz"), "rt") as handle:
                    for _ in range(1000):
                        if not handle.readline():
                            break
                        sequence = handle.readline().strip()
                        plus = handle.readline()
                        qualities = handle.readline().strip()
                        if not plus.startswith("+") or len(sequence) != len(qualities):
                            raise ValueError("Malformed FASTQ record: " + sample)
                        levels.update(ord(value) - 33 for value in qualities)
                mate_levels[str(mate)] = sorted(levels)
            row["sampled_quality_levels"] = json.dumps(mate_levels)
            if any(len(levels) == 1 for levels in mate_levels.values()):
                row["QC_review_note"] = "Uniform quality scores in first 1000 reads of at least one mate; Q30 needs source review. " + row["QC_review_note"]
    save_csv(OUT / "pilot_qc_summary.csv", summary)
    result = {"status": "technical_pilot_complete", "samples": len(summary),
              "existing_assemblies": sum(row["source"] == "assembly" for row in summary),
              "read_assemblies": sum(row["source"] == "reads" for row in summary),
              "feature_counts": {row["BioSample"]: int(row["feature_count"]) for row in summary},
              "accuracy_measured": False, "model_trained": False,
              "uniform_quality_review_samples": [row["BioSample"] for row in summary
                                                  if row["QC_review_note"].startswith("Uniform")],
              "biological_QC_remaining": "Review species identity/contamination, mapped coverage and assembly quality before scaling.",
              "estimated_depth_definition": "Post-fastp total bases divided by assembly length; not mapped depth."}
    save_json(OUT / "pilot_status.json", result)
    print(json.dumps(result, indent=2))
    print("QC table:", OUT / "pilot_qc_summary.csv")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "download", "setup", "process", "audit"])
    parser.add_argument("--assemblies-only", action="store_true", help="Process the five existing assemblies while reads download")
    parser.add_argument("--wait-downloads", action="store_true", help="Wait up to 30 minutes per input for an already-running downloader")
    args = parser.parse_args()
    if args.stage == "process":
        process(assemblies_only=args.assemblies_only, wait_downloads=args.wait_downloads)
    else:
        {"prepare": prepare, "download": download, "setup": setup, "audit": audit}[args.stage]()
