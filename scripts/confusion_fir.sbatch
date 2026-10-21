#!/usr/bin/env bash
# Manual Fir job: write confusion.parquet beside the atlas index. CPU only, no --partition.
# The account comes from the environment, not a #SBATCH line: SBATCH_ACCOUNT=def-xxx sbatch scripts/confusion_fir.sbatch
#SBATCH --time=02:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=4
#SBATCH --job-name=confusion-fir
#
# Flow (DIR = ATLAS_DIR below; ATLAS_HF_REPO and HF_TOKEN set):
#   scripts/atlas_sync.sh pull DIR     the full index (manifest.json); a pull skips the text vectors
#   hf download $ATLAS_HF_REPO --repo-type dataset --include 'taxa-*' --local-dir DIR
#   sbatch scripts/confusion_fir.sbatch    runs the fir subcommand below
#   scripts/atlas_sync.sh push DIR     uploads confusion.parquet, then manifest.json last
set -euo pipefail
BULK=/scratch/wietze/what-to-id/bulk-2026-10-15
DIR=${ATLAS_DIR:?ATLAS_DIR is not set}
PYTHONPATH=src python -m what_to_id.confusion fir \
  --emb "$BULK/completed/E.npy" --ids "$BULK/completed/ids.npy" \
  --pool "$BULK/inputs/pool.parquet" \
  --taxa-names "$(ls "$DIR"/taxa-*.tsv.gz)" --taxa-vectors "$(ls "$DIR"/taxa-*.f16)" \
  --atlas-dir "$DIR"
