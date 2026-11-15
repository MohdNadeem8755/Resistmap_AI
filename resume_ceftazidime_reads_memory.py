"""Resume the unchanged read runner with a recorded, bounded SKESA memory retry.

Only retries the explicit sorted-counter insufficient-memory diagnostic.
Does not subsample reads, change biological parameters, or alter old checkpoints.
"""
import json
from pathlib import Path
import subprocess
import time

import process_ceftazidime_reads as runner

original_run = runner.run
original_process = runner.process_one
POLICY = 'SKESA: original 4 GB; retry 6 GB only after explicit insufficient-memory failure'


def memory_available_kib():
    data = subprocess.check_output(runner.pilot.WSL + ['cat', '/proc/meminfo'], text=True)
    return int(next(line for line in data.splitlines() if line.startswith('MemAvailable:')).split()[1])


def run_with_memory_retry(command, args, sample, name):
    if name != 'skesa':
        return original_run(command, args, sample, name)
    try:
        return original_run(command, args, sample, name)
    except subprocess.CalledProcessError:
        log = runner.OUT / 'logs' / f'{sample}.skesa.log'
        if 'Memory provided is insufficient' not in log.read_text(errors='replace'):
            raise
        available = memory_available_kib()
        # 6 GiB plus 256 MiB available; no global WSL configuration change.
        if available < (6 * 1024 + 256) * 1024:
            raise RuntimeError('6 GB assembler retry needs at least 6.25 GiB available WSL memory')
        stamp = str(time.time_ns())
        archived = log.with_name(f'{sample}.skesa.memory4_failed_{stamp}.log')
        archived.write_bytes(log.read_bytes())
        retried = list(args)
        index = retried.index('--memory') + 1
        if retried[index] != '4':
            raise ValueError('Unexpected original SKESA memory budget')
        retried[index] = '6'
        metadata = {'policy': POLICY, 'sample': sample, 'available_kib_before_retry': available,
                    'original_command': command + args, 'retry_command': command + retried,
                    'failed_log': str(archived.relative_to(runner.OUT)),
                    'failed_log_sha256': runner.pilot.digest(archived, 'sha256'),
                    'retry_started_unix': time.time(), 'retry_status': 'running',
                    'wrapper_sha256': runner.pilot.digest(Path(__file__), 'sha256')}
        record = runner.OUT / 'logs' / f'{sample}.assembly_resource_retry.json'
        runner.atomic(record, metadata)
        print('Memory retry:', sample, '4 GB -> 6 GB; all reads retained', flush=True)
        try:
            original_run(command, retried, sample, 'skesa_memory6')
            metadata['retry_status'] = 'completed'
        except BaseException as exc:
            metadata['retry_status'] = 'failed'
            metadata['error'] = str(exc)
            raise
        finally:
            metadata['finished_unix'] = time.time()
            runner.atomic(record, metadata)


def process_with_resources(*args, **kwargs):
    summary = original_process(*args, **kwargs)
    sample = summary['BioSample']
    summary.setdefault('assembly_memory_retry_GB', '')
    summary.setdefault('assembly_resource_policy', 'Original 4 GB budget')
    record = runner.OUT / 'logs' / f'{sample}.assembly_resource_retry.json'
    if record.exists():
        metadata = json.loads(record.read_text())
        if metadata['retry_status'] != 'completed':
            raise ValueError('Assembly resource retry not complete')
        done = runner.OUT / 'completed' / (sample + '.json')
        saved = json.loads(done.read_text())
        summary['assembly_memory_retry_GB'] = 6
        summary['assembly_resource_policy'] = POLICY
        saved['summary'] = summary
        evidence = [record, runner.OUT / metadata['failed_log'],
                    runner.OUT / 'logs' / f'{sample}.skesa_memory6.command.json',
                    runner.OUT / 'logs' / f'{sample}.skesa_memory6.log']
        for path in evidence:
            saved['output_sha256'][str(path.relative_to(runner.OUT))] = runner.pilot.digest(path, 'sha256')
        runner.atomic(done, saved)
    return summary


if __name__ == '__main__':
    runner.run = run_with_memory_retry
    runner.process_one = process_with_resources
    runner.main()
