#!/usr/bin/env bash
# Move the static atlas index between a local directory and its host.
#
#   scripts/atlas_sync.sh pull DIR [ids]   download the index into DIR; with "ids" only the
#                                          manifest and the id files (enough for `atlas_update plan`)
#   scripts/atlas_sync.sh push DIR         upload DIR; part files first, manifest.json last, so a
#                                          reader only sees a part once the manifest names it
#
# ATLAS_HOST picks the host:
#   hf     Hugging Face dataset repo ATLAS_HF_REPO (needs HF_TOKEN; the `hf` CLI, or huggingface-cli)
#   r2     Cloudflare R2 bucket ATLAS_R2_BUCKET at ATLAS_R2_ENDPOINT (needs R2_ACCESS_KEY_ID and
#          R2_SECRET_ACCESS_KEY; the aws CLI)
#   local  the directory ATLAS_LOCAL_DIR, for tests and rehearsals
# After the manifest, push removes remote files that DIR no longer has (parts that a compaction
# folded away), so only push a directory that came from a full pull.
# ATLAS_SYNC_LOG, if set, gets one line per transferred file in transfer order.
set -euo pipefail

die() {
  echo "atlas_sync: $*" >&2
  exit 1
}

cmd=${1:-}
dir=${2:-}
only=${3:-}
[ -n "$dir" ] || die "usage: atlas_sync.sh {pull,push} DIR [ids]"
host=${ATLAS_HOST:-}

log() { [ -z "${ATLAS_SYNC_LOG:-}" ] || echo "$1" >>"$ATLAS_SYNC_LOG"; }

hf_cli() {
  if command -v hf >/dev/null 2>&1; then hf "$@"; else huggingface-cli "$@"; fi
}

check_pushable() {
  [ -s "$dir/manifest.json" ] || die "$dir has no manifest.json; push only a full index"
  local f
  while read -r f; do
    [ -f "$dir/$f" ] || die "manifest names $f but $dir lacks it; pull the full index before pushing"
  done < <(jq -r '.parts[].name | (.+".offsets.u32", .+".ids.u32", .+".codes.u8")' "$dir/manifest.json")
}

pull_local() {
  [ -n "${ATLAS_LOCAL_DIR:-}" ] && [ -s "$ATLAS_LOCAL_DIR/manifest.json" ] || die "no index at ATLAS_LOCAL_DIR"
  local f
  for f in "$ATLAS_LOCAL_DIR"/*; do
    case "$(basename "$f")" in
      manifest.json | *.ids.u32) ;;
      *) [ -z "$only" ] || continue ;;
    esac
    cp "$f" "$dir/"
    log "pull $(basename "$f")"
  done
}

push_local() {
  [ -n "${ATLAS_LOCAL_DIR:-}" ] || die "ATLAS_LOCAL_DIR is not set"
  mkdir -p "$ATLAS_LOCAL_DIR"
  local f
  for f in "$dir"/*; do
    case "$(basename "$f")" in
      manifest.json | *.tmp) ;;
      *) cp "$f" "$ATLAS_LOCAL_DIR/" && log "push $(basename "$f")" ;;
    esac
  done
  cp "$dir/manifest.json" "$ATLAS_LOCAL_DIR/" && log "push manifest.json"
  for f in "$ATLAS_LOCAL_DIR"/*; do
    [ -e "$dir/$(basename "$f")" ] || rm -f "$f"
  done
}

pull_hf() {
  [ -n "${ATLAS_HF_REPO:-}" ] || die "ATLAS_HF_REPO is not set"
  local include=()
  [ -z "$only" ] || include=(--include manifest.json "*.ids.u32")
  hf_cli download "$ATLAS_HF_REPO" --repo-type dataset --local-dir "$dir" ${include[@]+"${include[@]}"}
}

push_hf() {
  [ -n "${ATLAS_HF_REPO:-}" ] || die "ATLAS_HF_REPO is not set"
  hf_cli upload "$ATLAS_HF_REPO" "$dir" . --repo-type dataset --exclude manifest.json "*.tmp" ".cache/*" \
    --commit-message "atlas parts"
  hf_cli upload "$ATLAS_HF_REPO" "$dir/manifest.json" manifest.json --repo-type dataset \
    --commit-message "atlas manifest"
  hf_cli upload "$ATLAS_HF_REPO" "$dir" . --repo-type dataset --exclude "*.tmp" ".cache/*" --delete "*" \
    --commit-message "atlas prune"
}

r2_env() {
  [ -n "${ATLAS_R2_BUCKET:-}" ] && [ -n "${ATLAS_R2_ENDPOINT:-}" ] || die "ATLAS_R2_BUCKET and ATLAS_R2_ENDPOINT are required"
  export AWS_ACCESS_KEY_ID=${R2_ACCESS_KEY_ID:?R2_ACCESS_KEY_ID is not set}
  export AWS_SECRET_ACCESS_KEY=${R2_SECRET_ACCESS_KEY:?R2_SECRET_ACCESS_KEY is not set}
  export AWS_DEFAULT_REGION=auto
}

pull_r2() {
  r2_env
  local filter=()
  [ -z "$only" ] || filter=(--exclude "*" --include manifest.json --include "*.ids.u32")
  aws s3 sync "s3://$ATLAS_R2_BUCKET/" "$dir" --endpoint-url "$ATLAS_R2_ENDPOINT" --only-show-errors ${filter[@]+"${filter[@]}"}
}

push_r2() {
  r2_env
  aws s3 sync "$dir" "s3://$ATLAS_R2_BUCKET/" --endpoint-url "$ATLAS_R2_ENDPOINT" --only-show-errors \
    --exclude manifest.json --exclude "*.tmp"
  aws s3 cp "$dir/manifest.json" "s3://$ATLAS_R2_BUCKET/manifest.json" --endpoint-url "$ATLAS_R2_ENDPOINT" \
    --only-show-errors --cache-control "no-cache"
  aws s3 sync "$dir" "s3://$ATLAS_R2_BUCKET/" --endpoint-url "$ATLAS_R2_ENDPOINT" --only-show-errors \
    --exclude "*.tmp" --delete
}

case "$cmd:$host" in
  pull:local | pull:hf | pull:r2)
    mkdir -p "$dir"
    "pull_$host"
    [ -s "$dir/manifest.json" ] || die "no manifest.json after pull; seed the host first (see .github/workflows/atlas.yml)"
    ;;
  push:local | push:hf | push:r2)
    check_pushable
    "push_$host"
    ;;
  *) die "usage: ATLAS_HOST={hf,r2,local} atlas_sync.sh {pull,push} DIR [ids] (got $cmd, host '${host}')" ;;
esac
