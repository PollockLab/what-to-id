#!/bin/bash
#SBATCH --job-name=what-to-id-bakeoff
#SBATCH --output=/network/scratch/s/suijkerw/what-to-id/bakeoff-%j.out
#SBATCH --error=/network/scratch/s/suijkerw/what-to-id/bakeoff-%j.err
#SBATCH --time=04:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=6
#SBATCH --gres=gpu:rtx8000:1
#SBATCH --partition=unkillable

# Embed the same staged photos with several backbones so their separability can be compared.
# Usage: sbatch slurm/bakeoff_mila.sbatch <pool.parquet> <backbone,backbone,...>
# Reuses $SCRATCH/what-to-id/<pool-stem>/photos.tar written by embed_mila.sbatch, so no photo
# is downloaded twice. One npz per (group, backbone) lands next to the tarball.

set -euo pipefail
POOL="${1:?pool parquet required}"
BACKBONES="${2:?comma-separated backbones required}"
STEM="$(basename "$POOL" .parquet)"
OUT="$SCRATCH/what-to-id/$STEM"
test -f "$OUT/photos.tar" || { echo "missing $OUT/photos.tar; run embed_mila.sbatch first" >&2; exit 2; }

export HF_HOME="$SCRATCH/hf_cache"
export UV_CACHE_DIR="$SCRATCH/uv_cache"
export PATH="$HOME/.local/bin:$PATH"

cd "$SLURM_TMPDIR"
uv venv --python 3.11 .venv && source .venv/bin/activate
uv pip install "numpy>=1.26" "pandas>=2.2" "pyarrow>=15" "requests>=2.31" "scipy>=1.11" \
  "torch>=2.1" "torchvision>=0.16" "open_clip_torch>=2.24" "pillow>=10.0" "timm>=1.0" \
  "transformers>=4.56"
export PYTHONPATH="$HOME/what-to-id/src"

nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
mkdir -p cache && tar xf "$OUT/photos.tar" -C cache
echo "[bakeoff] $(ls cache/photos | wc -l) photos staged"

IFS=, read -ra BB <<< "$BACKBONES"
for b in "${BB[@]}"; do
  echo "[bakeoff] backbone=$b start $(date +%T)"
  python -m what_to_id.embed --pool "$POOL" --backbone "$b" --cache cache --batch 64 --device cuda
  echo "[bakeoff] backbone=$b done $(date +%T)"
done

cp cache/*.npz "$OUT/"
ls -la "$OUT"
