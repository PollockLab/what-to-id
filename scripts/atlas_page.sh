#!/usr/bin/env bash
# Add the serverless photo-search page (search.html) to a Pages site directory.
#
#   scripts/atlas_page.sh DIR
#
# Every Pages deploy uploads a whole new site, so each deploy path calls this right before upload.
# ATLAS_HF_REPO names the Hugging Face dataset repo holding the atlas index; unset or empty means
# no atlas yet, so the site is left as it is. Needs only python3 and the repo's src/.
set -euo pipefail

dir="${1:?usage: atlas_page.sh DIR}"
if [ -z "${ATLAS_HF_REPO:-}" ]; then
  echo "atlas_page: ATLAS_HF_REPO is not set, skipping search.html"
  exit 0
fi
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m what_to_id.atlas_search_page \
  --out "$dir" --data-url "https://huggingface.co/datasets/${ATLAS_HF_REPO}/resolve/main/"
echo "atlas_page: wrote $dir/search.html"
