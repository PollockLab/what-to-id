#!/usr/bin/env bash
# Add the serverless photo-search page (search.html) and the photo-space page (embeddings.html) to a Pages site directory.
#
#   scripts/atlas_page.sh DIR
#
# Every Pages deploy uploads a whole new site, so each deploy path calls this right before upload.
# ATLAS_HF_REPO names the Hugging Face dataset repo holding the atlas index; unset or empty means
# no atlas yet, so the site is left as it is. Needs only python3 and the repo's src/.
set -euo pipefail

dir="${1:?usage: atlas_page.sh DIR}"
if [ -z "${ATLAS_HF_REPO:-}" ]; then
  echo "atlas_page: ATLAS_HF_REPO is not set, skipping search.html and embeddings.html"
  exit 0
fi
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
data="https://huggingface.co/datasets/${ATLAS_HF_REPO}/resolve/main/"
for page in atlas_search_page embeddings_page; do
  PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m "what_to_id.$page" --out "$dir" --data-url "$data"
done
PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m what_to_id.split_page --out "$dir" --data-url "$data"
echo "atlas_page: wrote $dir/search.html, $dir/embeddings.html and $dir/split.html"
