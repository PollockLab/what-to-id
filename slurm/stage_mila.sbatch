#!/bin/bash
#SBATCH --job-name=what-to-id-photos
#SBATCH --time=1-23:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=4
#SBATCH --partition=unkillable-cpu
# Usage: sbatch --dependency=afterok:PULL_JOB --output=RUN/stage-%j.log \
#   slurm/stage_mila.sbatch RUN POOL FROZEN_REFERENCE
set -euo pipefail
RUN="${1:?durable run directory}"
POOL="${2:?candidate pool parquet}"
REFERENCE="${3:?frozen reference parquet}"
export UV_CACHE_DIR="$SCRATCH/uv_cache"
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$RUN/src"
cd "$SLURM_TMPDIR"
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install --require-hashes -r "$RUN/requirements.lock"
python - "$RUN" "$POOL" "$REFERENCE" <<'PY'
import json
import shutil
import subprocess
import sys
from pathlib import Path
import pandas as pd
from what_to_id.embed import stage_images
from what_to_id.manifest import sha256_file
run, pool, ref = map(Path, sys.argv[1:])
for kind, source in (("candidate", pool), ("reference", ref)):
    out = run / "photos" / kind
    out.mkdir(parents=True, exist_ok=True)
    identity = out / "pool.sha256"
    digest = sha256_file(source)
    if identity.exists() and identity.read_text().strip() != digest:
        raise ValueError("photo staging belongs to a different pool")
    identity.write_text(digest + "\n")
    for group, rows in pd.read_parquet(source).groupby("iconic_taxon", sort=True):
        archive = out / f"{group}.tar"
        status = out / f"{group}.json"
        if archive.exists() and status.exists() and not json.loads(status.read_text())["failures"]:
            continue
        cache = Path("stage")
        shutil.rmtree(cache, ignore_errors=True)
        cache.mkdir()
        if archive.exists():
            subprocess.run(["tar", "xf", str(archive), "-C", str(cache)], check=True)
        result = stage_images(rows, cache, workers=4)
        failed = result.attrs.get("failed", [])
        partial = archive.with_suffix(".partial")
        subprocess.run(["tar", "cf", str(partial), "-C", str(cache), "photos"], check=True)
        partial.replace(archive)
        (out / f"{group}.json").write_text(json.dumps({"expected": len(rows), "failures": failed}))
        shutil.rmtree(cache)
        if failed:
            raise RuntimeError(f"{group}: {len(failed)} photos failed, rerun staging before GPU")
PY
