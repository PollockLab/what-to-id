#!/usr/bin/env bash
# Manual Fir job: write confusion.parquet beside the atlas index. CPU only, no --partition.
# The account comes from the environment, not a #SBATCH line: SBATCH_ACCOUNT=def-xxx sbatch scripts/confusion_fir.sbatch
#SBATCH --time=02:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=8
#SBATCH --job-name=confusion-fir
#
# Flow (DIR = ATLAS_DIR below, holding manifest.json and the taxa-* files; a pull skips the latter):
#   scripts/atlas_sync.sh pull DIR     the full index, or just curl manifest.json from the HF repo
#   hf download $ATLAS_HF_REPO --repo-type dataset --include 'taxa-*' --local-dir DIR
#   ATLAS_DIR=DIR sbatch scripts/confusion_fir.sbatch    from the repo root, runs the fir subcommand
#   scripts/atlas_sync.sh push DIR     uploads confusion.parquet, then manifest.json last
# The per-job venv on node-local disk follows the atlas index job (Fir compute nodes have internet).
set -euo pipefail
BULK=/scratch/wietze/what-to-id/bulk-2026-10-15
DIR=${ATLAS_DIR:?ATLAS_DIR is not set}
module purge; module load StdEnv/2023 python/3.11 arrow/17.0.0
virtualenv --no-download "$SLURM_TMPDIR/env"; source "$SLURM_TMPDIR/env/bin/activate"
pip install --no-index -q numpy pandas
export PYTHONPATH=src${PYTHONPATH:+:$PYTHONPATH} OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-8} PYTHONUNBUFFERED=1
/usr/bin/time -v python -m what_to_id.confusion fir \
  --emb "$BULK/completed/E.npy" --ids "$BULK/completed/ids.npy" \
  --pool "$BULK/inputs/pool.parquet" \
  --taxa-names "$(ls "$DIR"/taxa-*.tsv.gz)" --taxa-vectors "$(ls "$DIR"/taxa-*.f16)" \
  --atlas-dir "$DIR" 2>&1 | grep -vE "^\s+(Page|Socket|Signals|Swaps|File system|Average|Exit|Voluntary|Involuntary|Minor|Major|Percent|System|User time|Command)"
