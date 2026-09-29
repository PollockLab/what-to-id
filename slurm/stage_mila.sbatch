#!/bin/bash
#SBATCH --job-name=what-to-id-photos
#SBATCH --time=1-23:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=2
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
export PYTHONUNBUFFERED=1
cd "$SLURM_TMPDIR"
uv venv --python 3.11 .venv
export VIRTUAL_ENV="$SLURM_TMPDIR/.venv"
export PATH="$VIRTUAL_ENV/bin:$PATH"
uv pip install --require-hashes -r "$RUN/requirements.lock"
uv pip install 'pillow==11.3.0'
python -m what_to_id.staging stage "$RUN" "$POOL" "$REFERENCE"
