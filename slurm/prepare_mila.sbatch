#!/bin/bash
#SBATCH --job-name=what-to-id-prepare
#SBATCH --time=18:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=6
#SBATCH --gres=gpu:rtx8000:1
#SBATCH --partition=unkillable

# Usage: sbatch --dependency=afterok:STAGE_JOB --output=RUN/prepare-%j.log \
#   slurm/prepare_mila.sbatch RUN POOL FROZEN_REFERENCE MODEL_SNAPSHOT
# RUN/src must contain the verified source snapshot. No credentials or publication.
set -euo pipefail
export RUN="${1:?durable run directory}"
POOL="${2:?complete candidate pool parquet}"
REFERENCE="${3:?frozen reference parquet}"
MODEL="${4:?frozen model snapshot directory}"
export HF_HOME="$SCRATCH/hf_cache"
export UV_CACHE_DIR="$SCRATCH/uv_cache"
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$RUN/src"
export PYTHONUNBUFFERED=1
export HF_HUB_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
cd "$SLURM_TMPDIR"
uv venv --python 3.11 .venv
export VIRTUAL_ENV="$SLURM_TMPDIR/.venv"
export PATH="$VIRTUAL_ENV/bin:$PATH"
uv pip install --require-hashes -r "$RUN/requirements.lock"
uv pip install 'torch==2.8.0' 'torchvision==0.23.0' 'open_clip_torch==3.1.0' 'pillow==11.3.0'
uv pip freeze > "$RUN/preparation-environment.txt"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
python - "$RUN" "$POOL" "$REFERENCE" <<'PY_CHECK'
import sys
from pathlib import Path
from what_to_id.manifest import sha256_file
run, pool, reference = map(Path, sys.argv[1:])
for kind, source in (("candidate", pool), ("reference", reference)):
    if (run / "photos" / kind / "pool.sha256").read_text().strip() != sha256_file(source):
        raise ValueError(f"{kind} photo archives belong to a different pool")
PY_CHECK
mkdir -p reference
if [[ -d "$RUN/work" ]]; then
    rsync -a "$RUN/work/" work/
fi
# Photos remain on node-local storage; preserve completed vectors and attestations.
persist() {
    mkdir -p "$RUN/work" "$RUN/reference"
    rsync -a --exclude=photos work/ "$RUN/work/"
    rsync -a --exclude=photos reference/ "$RUN/reference/"
}
trap persist EXIT
python - "$REFERENCE" "$MODEL" <<'PY'
import json
import sys
from contextlib import nullcontext
from pathlib import Path
import pandas as pd
from what_to_id.embed import emb_cache_path, embed_group, load_embeddings
from what_to_id.manifest import sha256_file
from what_to_id.prepare_embeddings import _verify_snapshot, MODEL_REVISION, extracted_photos
pool, model = map(Path, sys.argv[1:])
_verify_snapshot(model)
from what_to_id.prepare_embeddings import verify_reference_cache
import os
import subprocess
prior = Path(os.environ["RUN"]) / "reference"
verify_reference_cache(prior, pool, model)
if prior.exists():
    subprocess.run(["rsync", "-a", "--exclude=photos", str(prior) + "/", "reference/"], check=True)
rows = pd.read_parquet(pool)
if len(rows) != 10000 or rows.id.duplicated().any():
    raise ValueError("expected the frozen unique 10,000-row reference sample")
for name, group in rows.groupby("iconic_taxon", sort=True):
    target = emb_cache_path(Path("reference"), name, "bioclip25")
    complete = target.exists() and set(group.id) <= set(load_embeddings(target)[0])
    photos = nullcontext() if complete else extracted_photos(
        Path(os.environ["RUN"]) / "photos/reference" / f"{name}.tar", Path("reference"))
    with photos:
        embed_group(group, cache_dir=Path("reference"), backbone="bioclip25",
                    device="cuda", batch=64, model_snapshot=model)
    Path("reference/provenance.json").write_text(json.dumps({
        "pool_sha256": sha256_file(pool), "model_revision": MODEL_REVISION,
        "model_sha256": _verify_snapshot(model),
        "reference_sha256": {p.name: sha256_file(p) for p in Path("reference").glob("*.npz")},
    }, indent=2) + "\n")
    subprocess.run(["rsync", "-a", "--exclude=photos", "reference/",
                    os.environ["RUN"] + "/reference/"], check=True)
PY
python -m what_to_id.prepare_embeddings --pool "$POOL" \
    --reference-embeddings "$SLURM_TMPDIR/reference/emb_{group}_bioclip25.npz" \
    --reference-pool "$REFERENCE" \
    --model-snapshot "$MODEL" --work-dir "$SLURM_TMPDIR/work/candidates" \
    --out "$RUN/bundle" --device cuda --batch 64 \
    --photo-archive-dir "$RUN/photos/candidate" --checkpoint-dir "$RUN/work/candidates"
python -m what_to_id.artifacts verify "$RUN/bundle"
