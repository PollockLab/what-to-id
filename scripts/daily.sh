#!/usr/bin/env bash
# One daily build of the rotation page. GitHub Actions (.github/workflows/daily.yml) runs
# exactly these steps, and so can a laptop:
#
#   scripts/daily.sh fetch   download the pool and served log from the pool-state release
#   scripts/daily.sh build   update the pool, build, drop records identified since, rebuild,
#                            keep the day's pool and build record, check for leaks, replay
#   scripts/daily.sh save    upload the state back to the release
#
# build needs WHAT_TO_ID_KEY (the private list key) and WTB_DIR (where-to-blitz's
# cluster_results/ca, checked out at the commit in what_to_id.manifest.WHERE_TO_BLITZ_REF).
# OFFLINE=1 skips the two iNaturalist calls, to rehearse the rest on a saved pool.
# Nothing here may print the key or anything that maps list letters to lists.
set -euo pipefail
cd "$(dirname "$0")/.."

STATE=${STATE_DIR:-state}
OUT=${OUT_DIR:-out}
TODAY=${TODAY:-$(date -u +%F)}
D1=${D1:-2025-01-01}
STATE_TAG=${STATE_TAG:-pool-state}
MAX_BATCHES=${MAX_BATCHES:-20}
PY=${PYTHON:-python}
export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"

die() {
  echo "daily: $*" >&2
  exit 1
}

fetch() {
  mkdir -p "$STATE"
  if ! gh release view "$STATE_TAG" >/dev/null 2>&1; then
    echo "no $STATE_TAG release yet: the first build pulls the whole pool"
    return
  fi
  local assets
  assets=$(gh release view "$STATE_TAG" --json assets --jq '.assets[].name')
  for f in pool.parquet served.parquet; do
    if grep -qx "$f" <<<"$assets"; then
      gh release download "$STATE_TAG" -D "$STATE" -p "$f" --clobber
    fi
  done
  if grep -q '^build-.*\.json$' <<<"$assets" && [ ! -s "$STATE/served.parquet" ]; then
    die "the release holds earlier builds but no served log; restore served.parquet before building"
  fi
  ls -la "$STATE"
}

check_wtb() {
  [ -n "${WTB_DIR:-}" ] || die "set WTB_DIR to where-to-blitz's cluster_results/ca"
  [ -f "$WTB_DIR/provenance.json" ] || die "$WTB_DIR has no provenance.json"
  local want have
  want=$($PY -c "from what_to_id.manifest import WHERE_TO_BLITZ_REF as r; print(r.split('@')[1])")
  have=$(git -C "$WTB_DIR" rev-parse HEAD)
  [ "$want" = "$have" ] || die "where-to-blitz is at $have, the code expects $want"
}

check_leaks() {
  local site="$OUT/final/site"
  [ -s "$site/index.html" ] || die "no page was built"
  if find "$site" -type f ! -name '*.html' | grep -q .; then
    die "the site must hold only HTML pages"
  fi
  if grep -ril -E 'recency|gap_first|gap first|similarity|novelty' "$site"; then
    die "a list name leaked into the site"
  fi
  if grep -rlF "$WHAT_TO_ID_KEY" "$site" "$STATE"; then
    die "the list key leaked into a file that is published or uploaded"
  fi
  $PY - "$STATE/served.parquet" "$STATE/days/build-$TODAY.json" <<'EOF'
import json, sys
import pandas as pd
served = pd.read_parquet(sys.argv[1])
assert "arm" not in served.columns, "the served log names lists"
record = json.load(open(sys.argv[2]))
for k in ("arm_labels", "batches"):
    assert k not in record, f"the build record carries {k}"
EOF
}

build() {
  [ -n "${WHAT_TO_ID_KEY:-}" ] || die "WHAT_TO_ID_KEY is not set"
  : "${BLITZ_D1:?set BLITZ_D1, the blitz start date (YYYY-MM-DD)}"
  check_wtb
  $PY -m pytest -q -p no:cacheprovider

  mkdir -p "$STATE/days"
  if [ "${OFFLINE:-}" = 1 ]; then
    [ -s "$STATE/pool.parquet" ] || die "OFFLINE=1 needs a saved $STATE/pool.parquet"
  elif [ "${FULL_PULL:-}" = true ] || [ ! -s "$STATE/pool.parquet" ]; then
    $PY -m what_to_id.inat --d1 "$D1" --freeze "$TODAY" --out "$STATE/pool.parquet"
  else
    $PY -m what_to_id.pool_state update --pool "$STATE/pool.parquet" --d1 "$D1"
  fi

  local common=(--pool "$STATE/pool.parquet" --freeze "$TODAY" --d1 "$BLITZ_D1"
    --design rotation --max-batches "$MAX_BATCHES" --key-env WHAT_TO_ID_KEY
    --webapp-dir "$WTB_DIR")
  rm -rf "$OUT/draft" "$OUT/final"
  $PY -m what_to_id.cli build "${common[@]}" --out "$OUT/draft"
  if [ "${OFFLINE:-}" != 1 ]; then
    $PY -m what_to_id.pool_state refresh --pool "$STATE/pool.parquet" --ids "$OUT/draft/batches.parquet"
  fi
  $PY -m what_to_id.cli build "${common[@]}" --out "$OUT/final" --served-log "$STATE/served.parquet"

  # The day's exact inputs, kept so this build can be rerun later.
  cp "$STATE/pool.parquet" "$STATE/days/pool-$TODAY.parquet"
  cp "$OUT/final/build_record.json" "$STATE/days/build-$TODAY.json"
  check_leaks
  $PY -m what_to_id.replay --pool "$STATE/days/pool-$TODAY.parquet" \
    --record "$STATE/days/build-$TODAY.json" --served-log "$STATE/served.parquet" \
    --webapp-dir "$WTB_DIR" --key-env WHAT_TO_ID_KEY
}

save() {
  local files=("$STATE/pool.parquet" "$STATE/served.parquet"
    "$STATE/days/pool-$TODAY.parquet" "$STATE/days/build-$TODAY.json")
  for f in "${files[@]}"; do
    [ -s "$f" ] || die "missing $f; run build first"
  done
  gh release view "$STATE_TAG" >/dev/null 2>&1 || gh release create "$STATE_TAG" \
    --prerelease --latest=false --title "Daily pool state" \
    --notes "Pool, served log (list letters only), and each day's pool and build record, kept between daily builds."
  local attempt
  for attempt in 1 2 3; do
    if gh release upload "$STATE_TAG" "${files[@]}" --clobber; then
      return
    fi
    echo "upload failed (attempt $attempt), retrying"
    sleep $((attempt * 30))
  done
  die "could not save the state to the $STATE_TAG release"
}

case "${1:-}" in
  fetch) fetch ;;
  build) build ;;
  save) save ;;
  *) die "usage: scripts/daily.sh fetch|build|save" ;;
esac
