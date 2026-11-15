"""Run the resumable assembly stage and persist an explicit final job state."""
import argparse
import json
import os
import time
import traceback

import process_ceftazidime_assemblies as pipeline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()
    out = pipeline.OUT
    state_file = out / 'assembly_job_status.json'
    if args.status:
        for path in [state_file, out / 'assembly_progress.json', out / 'assembly_stage_status.json']:
            if path.exists():
                print(path.name)
                print(path.read_text())
        return
    out.mkdir(parents=True, exist_ok=True)
    lock = out / 'assembly_stage.lock'
    # Avoid concurrent writers. A stale lock after an OS/process crash must be
    # inspected with the recorded PID before manually removing that one file.
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, json.dumps({'pid': os.getpid(), 'started_unix': time.time()}).encode())
    os.close(fd)
    started = time.time()
    stage = 'resolve'
    def state(status, error=None):
        pipeline.atomic_json(state_file, {'status': status,'stage': stage,'pid': os.getpid(),
                             'started_unix': started,'updated_unix': time.time(),'error': error,
                             'scope': '310 available development assemblies; no model training'})
    try:
        state('running')
        if not (out / 'assembly_download_manifest.json').exists():
            pipeline.resolve()
        stage = 'process'
        state('running')
        pipeline.process(workers=2)
        stage = 'species'
        state('running')
        pipeline.species()
        stage = 'audit'
        state('running')
        pipeline.audit()
        state('completed')
    except BaseException as exc:
        state('failed', str(exc))
        traceback.print_exc()
        raise
    finally:
        lock.unlink()


if __name__ == '__main__':
    main()
