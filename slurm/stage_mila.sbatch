#!/bin/bash
#SBATCH --job-name=what-to-id-photos
#SBATCH --time=1-23:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=2
#SBATCH --partition=unkillable-cpu
#SBATCH --signal=B:USR1@600
# Usage: sbatch --dependency=afterok:PULL_JOB --output=RUN/stage-%j.log \
#   slurm/stage_mila.sbatch RUN POOL FROZEN_REFERENCE
set -euo pipefail
RUN="${1:?durable run directory}"
POOL="${2:?candidate pool parquet}"
REFERENCE="${3:?frozen reference parquet}"
export UV_CACHE_DIR="$SCRATCH/uv_cache"
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$RUN/src"
export PYTHONUNBUFFERED=1
cd "$SLURM_TMPDIR"
uv venv --python 3.11 .venv
export VIRTUAL_ENV="$SLURM_TMPDIR/.venv"
export PATH="$VIRTUAL_ENV/bin:$PATH"
uv pip install --require-hashes -r "$RUN/requirements.lock"
uv pip install 'pillow==11.3.0'
# Ten minutes before the limit, the stager archives its current group without a status.
# A trap runs only once wait returns, so the stager runs in the background.
trap 'kill -USR1 "${child:-}" 2>/dev/null || true' USR1
python -m what_to_id.staging stage "$RUN" "$POOL" "$REFERENCE" &
child=$!
status=0
wait "$child" || status=$?
while kill -0 "$child" 2>/dev/null; do
    status=0
    wait "$child" || status=$?
done
exit "$status"
