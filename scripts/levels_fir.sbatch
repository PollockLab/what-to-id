#!/usr/bin/env bash
# Manual Fir job: write identify.parquet (every pool record scored) beside the atlas index. CPU only, no --partition.
# The account comes from the environment, not a #SBATCH line: SBATCH_ACCOUNT=def-xxx sbatch scripts/levels_fir.sbatch
#SBATCH --time=04:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=8
#SBATCH --job-name=levels-fir
#
# Flow (DIR = ATLAS_DIR below, holding manifest.json and the taxa-* files; TREE = map-state taxonomy.json):
#   scripts/atlas_sync.sh pull DIR     the full index: push deletes remote files DIR lacks
#   ATLAS_DIR=DIR TREE=taxonomy.json sbatch scripts/levels_fir.sbatch    from the repo root
#   scripts/atlas_sync.sh pull DIR again if atlas.yml ran meanwhile, then
#   scripts/atlas_sync.sh push DIR     uploads identify.parquet, then manifest.json last
# Prints the records per level and iconic group at the end. levels.parquet is not touched.
set -euo pipefail
BULK=/scratch/wietze/what-to-id/bulk-2026-10-15
DIR=${ATLAS_DIR:?ATLAS_DIR is not set}
TREE=${TREE:?TREE is not set (map-state taxonomy.json)}
module purge; module load StdEnv/2023 python/3.11 arrow/17.0.0
virtualenv --no-download "$SLURM_TMPDIR/env"; source "$SLURM_TMPDIR/env/bin/activate"
pip install --no-index -q numpy pandas
export PYTHONPATH=src${PYTHONPATH:+:$PYTHONPATH} OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-8} PYTHONUNBUFFERED=1
/usr/bin/time -v python -m what_to_id.levels \
  --emb "$BULK/completed/E.npy" --ids "$BULK/completed/ids.npy" \
  --pool "$BULK/inputs/pool.parquet" \
  --taxa-names "$(ls "$DIR"/taxa-*.tsv.gz)" --taxa-vectors "$(ls "$DIR"/taxa-*.f16)" \
  --atlas-dir "$DIR" --tree "$TREE" --identify 2>&1 | grep -vE "^\s+(Page|Socket|Signals|Swaps|File system|Average|Exit|Voluntary|Involuntary|Minor|Major|Percent|System|User time|Command)"
