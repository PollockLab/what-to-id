#!/bin/bash
#SBATCH --job-name=what-to-id-embed
#SBATCH --output=/network/scratch/s/suijkerw/what-to-id/embed-%j.out
#SBATCH --error=/network/scratch/s/suijkerw/what-to-id/embed-%j.err
#SBATCH --time=03:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=6
#SBATCH --gres=gpu:rtx8000:1
#SBATCH --partition=unkillable

# Stage iNaturalist photos and embed them with BioCLIP 2.5 for one pool parquet.
# Usage: sbatch slurm/embed_mila.sbatch <pool.parquet> [backbone] [extra embed args...]
# Photos and npz files land in $SLURM_TMPDIR/cache during the job, then the npz
# files and a photo tarball are copied to $SCRATCH/what-to-id/<pool-stem>/.

set -euo pipefail
POOL="${1:?pool parquet required}"
BACKBONE="${2:-bioclip25}"
shift $(( $# >= 2 ? 2 : $# ))
STEM="$(basename "$POOL" .parquet)"
OUT="$SCRATCH/what-to-id/$STEM"
mkdir -p "$OUT"

export HF_HOME="$SCRATCH/hf_cache"
export UV_CACHE_DIR="$SCRATCH/uv_cache"   # home is at quota; keep wheels on scratch
export PATH="$HOME/.local/bin:$PATH"

cd "$SLURM_TMPDIR"
uv venv --python 3.11 .venv && source .venv/bin/activate
# labelfirst (a private git dependency) is not needed for embedding, and the cluster has no
# GitHub credentials, so install the runtime deps directly and import the package from src.
uv pip install "numpy>=1.26" "pandas>=2.2" "pyarrow>=15" "requests>=2.31" "scipy>=1.11" \
  "torch>=2.1" "torchvision>=0.16" "open_clip_torch>=2.24" "pillow>=10.0"
export PYTHONPATH="$HOME/what-to-id/src"

nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
mkdir -p cache
python -m what_to_id.embed --pool "$POOL" --backbone "$BACKBONE" --cache cache --batch 64 "$@"

cp cache/*.npz "$OUT/"
tar cf "$OUT/photos.tar" -C cache photos
ls -la "$OUT"
