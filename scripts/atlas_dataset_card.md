---
# Dataset card for the Hugging Face repo that hosts the photo-search index. Upload it once as
# README.md when seeding: hf upload <repo> scripts/atlas_dataset_card.md README.md --repo-type dataset
# The daily update never touches it (atlas_sync.sh prunes index files only).
license: TODO  # choose before seeding; the vectors are derived from iNaturalist photos under their own licences
pretty_name: what-to-id photo-search index
tags:
  - biology
  - image-retrieval
  - inaturalist
  - bioclip
size_categories:
  - 1M<n<10M
---

# what-to-id photo-search index

A static IVF-PQ index of BioCLIP 2.5 image embeddings for British Columbia iNaturalist observations that need an ID. It is read in the browser over HTTP Range requests by the what-to-id photo search page (`atlas_search.html` in [PollockLab/what-to-id](https://github.com/PollockLab/what-to-id)), with no server.

## Contents

- `manifest.json`: layout version, model, parts, neighbour sets, text model. Read it first; it is the only file rewritten in place.
- `centroids.f16`, `pq.f32`: coarse centroids and product-quantizer codebooks.
- `<part>.offsets.u32`, `<part>.ids.u32`, `<part>.codes.u8`: one base part plus daily delta parts, rows grouped by coarse list.
- `neighbors*.bin`, `neighbors*.dir.u32`: 12 precomputed nearest neighbours per observation.
- `model/`: the int8 ONNX BioCLIP 2.5 text tower and its BPE merges, for free-text search in the browser.

Ids are iNaturalist observation ids. No photos, names, places or user data are stored; the page fetches those live from the iNaturalist API.

## Updates

A GitHub Actions workflow (`.github/workflows/atlas.yml`) adds the day's new observations as a delta part after each map refresh and compacts weekly, dropping observations that no longer need an ID. Weekly compaction squashes this repo's history, so older revisions are not kept.

## Model

Image and text embeddings: [imageomics/bioclip-2.5-vith14](https://huggingface.co/imageomics/bioclip-2.5-vith14), revision recorded in `manifest.json`.
