#!/usr/bin/env bash
# Build the whole Pages site (what map.yml deploys) into DIR from the current checkout, for a localhost preview.
#
#   scripts/local_site.sh DIR      # e.g. out/local-identify/site, then: python3 -m http.server -d DIR
#
# Mirrors map.yml's "Build the site" and later steps with the repo's own commands. Differences from the deploy:
# it needs `gh` (public release downloads) and network; it does not sync iNaturalist, reconcile, update the taxon
# tree, update project lists, or upload anything, so it uses the live release state as it is (no secrets needed).
# Existing files in DIR are kept; each page and data file is overwritten by the build.
set -euo pipefail

dir="${1:?usage: local_site.sh DIR}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
repo="${GITHUB_REPOSITORY:-PollockLab/what-to-id}"
export ATLAS_HF_REPO="${ATLAS_HF_REPO:-wietze/what-to-id-atlas}"  # the live variable; empty skips the photo pages
live="https://pollocklab.github.io/what-to-id/"
data="https://huggingface.co/datasets/${ATLAS_HF_REPO}/resolve/main/"
sdm="https://object-arbutus.alliancecan.ca/swift/v1/4903c6264e0c4191a74a54c93b6fe1d9/def-pollock-eckert/vertebrates_NA/ECCC_2026/manifest.json"
state="${LOCAL_SITE_STATE:-$root/out/local-site-state}"
mkdir -p "$dir" "$state"
dir="$(cd "$dir" && pwd)"

# the deploy's pool, tree, projects and daily batches, from the public releases
for f in pool.parquet taxonomy.json projects.bin resolved.parquet; do
  gh release download map-state --repo "$repo" -D "$state" -p "$f" --clobber || echo "local_site: no $f on map-state"
done
test -s "$state/pool.parquet" || { echo "local_site: no pool.parquet on map-state" >&2; exit 1; }
gh release download pool-state --repo "$repo" -D "$state" -p study.json --clobber ||
  { echo "local_site: no study.json on pool-state, using the committed preview"; cp site/study.json "$state/study.json"; }

# run each module with the repo's deps, hash-locked like the workflow's pip install
py() { PYTHONPATH="$root/src" uv run --no-project --quiet --with-requirements requirements.lock python -m "$@"; }

cp site/*.html "$dir/"
projects=(); [ -s "$state/projects.bin" ] && projects=(--projects "$state/projects.bin")
py what_to_id.page_map --pool "$state/pool.parquet" --out "$dir" --totals --freeze "$(date -u +%F)" \
  --tree "$state/taxonomy.json" "${projects[@]}" --data-url "$data" --sdm-manifest "$sdm"
py what_to_id.tree_page --out "$dir" || echo "local_site: no tree of life page"
if [ -s "$state/resolved.parquet" ]; then
  py what_to_id.map_resolved build --log "$state/resolved.parquet" --pool "$state/pool.parquet" \
    --tree "$state/taxonomy.json" --out "$dir" || echo "local_site: no pool-resolved.bin"
fi
py what_to_id.page_lookalike --out "$dir" --data-url "$data" || echo "local_site: no look-alike stats"
py what_to_id.pool_levels --out "$dir" --data-url "$data"
py what_to_id.page_identify --out "$dir" --study "$state/study.json"  # no --goatcounter: no analytics from localhost
py what_to_id.page_confusion --out "$dir" --data-url "$data" || echo "local_site: no confused pairs page"
py what_to_id.terms_page --out "$dir" --data-url "$data" --study "$state/study.json"
# atlas_page.sh runs python3 directly, so give it a wrapper that carries the deps
wrap="$state/python"
printf '#!/usr/bin/env bash\nexec uv run --no-project --quiet --with-requirements %q python "$@"\n' "$root/requirements.lock" > "$wrap"
chmod +x "$wrap"
PYTHON="$wrap" scripts/atlas_page.sh "$dir"
for p in identify explore map; do if [ -f "$dir/$p.html" ]; then cp "$dir/$p.html" "$dir/index.html"; break; fi; done
py what_to_id.site_files keep --site "$dir" --url "$live" || echo "local_site: could not copy the live data files"
echo "local_site: built $dir"
