# Operations: embeddings, daily build, publishing

The detail behind the short commands in the README. Everything here is for the person who runs the build, not for a reader of the study.

## Install notes

The `similarity` extra installs `labelfirst`, a private repository pinned by commit in `pyproject.toml`, so it needs access to that repository. Only the look-alike list's seed picker and the separability report use it. The four-list daily build needs this extra; an explicit `recency,gap_first` build still runs without it. CI uses the `LABELFIRST_DEPLOY_KEY` secret, the private half of a dedicated read-only deploy key on `traitlab/labelfirst`, to check out the pinned library and test the integration.

The base CI job installs exact, hash-pinned versions from `requirements.lock` (`pip install --require-hashes -r requirements.lock`, then run with `PYTHONPATH=src`). After changing the dependencies in `pyproject.toml`, regenerate it with `uv pip compile pyproject.toml --extra dev --universal --python-version 3.11 --generate-hashes -o requirements.lock`.

## Read-back denominator

The read-back denominator is the served records only: `assign.parquet` covers the whole pool, but `batches.parquet` (one build) and the served log (every daily build) hold just the records placed in a served batch. Both work as `--assign` and `--served`; the served log needs `--label-map`.

## Embeddings

Prepare embeddings separately from daily serving. `slurm/stage_mila.sbatch` downloads photos on CPU into resumable group archives; `slurm/prepare_mila.sbatch` then regenerates the frozen 10,000-row Research Grade reference and candidate embeddings on GPU using the verified BioCLIP 2.5 checkpoint. Each group archive is bound to the IDs and photo URLs of its own rows, so archives copied from a run whose pool differed only in other groups are resumed without re-downloading. Candidate records whose photo cannot be fetched from either iNaturalist host are excluded before assignment and listed in `RUN/excluded.json`, and the bundle's pool omits them; staging stops instead if more than 0.1% of a group fails or any reference photo fails. Ten minutes before either job's time limit, staging archives the group in progress without marking it complete and preparation stops its current step and persists completed vectors, so resubmitting resumes. The scripts take explicit input paths and never publish.

The daily runner does not embed: each day `python -m what_to_id.assemble_bundle` builds the bundle for that day's pool from a base release of float16 `base_{group}.npz` vectors and the frozen reference `emb_{group}_bioclip25.npz` files, plus the atlas job's `raw-delta-*.npz` files on the `atlas-state` release (a later delta wins over an earlier one and over the base), so a new record enters the study about a day after the atlas embeds it. Records with no vector yet are listed in `uncovered.json`, left out of that day's bundle and picked up on a later day; if more than 1% of a group is uncovered (`--max-uncovered-share`) the build fails and the cluster preparation is the fallback.

### Reusing a prior preparation

For subsequent pool snapshots, reuse only an attested prior preparation. The command retains observations whose ID, taxon group and photo URL match, embeds new or changed rows, drops removed IDs and keeps the supplied reference files unchanged. `slurm/prepare_mila.sbatch` passes the same three inputs when `PREVIOUS_POOL`, `CANDIDATE_CACHE` and `PREVIOUS_PREPARATION` are all exported at submission; the earlier bundle is only read:

```bash
python -m what_to_id.prepare_embeddings --pool data/pool-next.parquet \
  --previous-pool data/previous-bundle/pool.parquet \
  --candidate-cache 'data/previous-bundle/embeddings_{group}.npz' \
  --previous-preparation data/previous-bundle/preparation.json \
  --reference-embeddings 'data/frozen-reference/emb_{group}_bioclip25.npz' \
  --reference-pool data/frozen-reference.parquet --model-snapshot data/frozen-model \
  --work-dir data/preparation-next --out data/bundle-next
```

`--model-snapshot` must contain the exact config and safetensors weights for revision `6e3d04e3d6522012c88181085c5ae666e14c45cd`; hashes are checked before encoding. Cache reuse verifies the previous pool, model and vector file hashes. Legacy caches without that record require regeneration. URL identity does not detect image bytes changed at the same URL. A work directory resumes only the same inputs, and packing requires complete candidate coverage. Publish the resulting pool, provenance and embeddings together as a new immutable bundle.

### Packing verified caches

```bash
python -m what_to_id.artifacts pack --pool data/pool_YYYY-MM-DD.parquet --embeddings 'data/candidates/emb_{group}.npz' --reference-embeddings 'data/reference/emb_{group}.npz' --out data/embedding-bundle
python -m what_to_id.artifacts verify data/embedding-bundle
what-to-id build --pool data/pool_YYYY-MM-DD.parquet --freeze YYYY-MM-DD --d1 YYYY-MM-DD --seed 0 --key-env WHAT_TO_ID_KEY --arms recency,gap_first,similarity,novelty --design rotation --embedding-bundle data/embedding-bundle --out out/build
```

### Releasing a bundle

Run `python -m what_to_id.bundle_transport stage-release --bundle data/embedding-bundle --out data/release-assets`, then publish all files in `data/release-assets` together as assets of a versioned release. The transport uses hashed parts below GitHub's per-file size limit. `EMBEDDING_RELEASE` names the release that holds the base vectors (default `embedding-base-2026-10-15`; set `EMBEDDING_REPO` if hosted elsewhere), and the daily job assembles its bundle into `EMBEDDING_BUNDLE`, which defaults to `data/embedding-bundle` and must not exist yet. The operator must provide release access where needed. Production rollout still requires embedding preparation, release upload, secret configuration and deployment.

### What a build records

A build records each candidate/reference file's content hash, dimensions, row count and backbone by taxon group. Replay accepts the original bundle or matching `--embeddings` and `--reference-embeddings` inputs; it refuses changed files. Builds using score files also require the original `--surprise-scores` or `--sinr-scores`. Older image-list build records without complete per-file fingerprints must be rebuilt before this replay path can verify them. Production bundles require candidate embeddings for every pool ID and nonempty references for each group. The daily job refreshes the pool, assembles the bundle for it, uses that bundle's pool, and removes served observations that no longer need identification. It never serves an observation ahead of its embedding. Exploratory builds with individual cache inputs retain the arm's recency fallback for missing candidates.

The `gap_first` arm reads where-to-blitz's `cluster_results/ca`; point `--webapp-dir` or the `WHERE_TO_BLITZ_CA` environment variable at a checkout of it.

## Publish

The live page is served at https://pollocklab.github.io/what-to-id/. The daily workflow (`.github/workflows/daily.yml`) rebuilds it every evening (UTC) once the repository variable `DAILY_ENABLED` is `true` (and on demand from the Actions tab), and saves it as `study.html` on the `pool-state` release. It does not deploy. The map workflow (`map.yml`) runs after each successful daily run and is the only workflow that publishes the full site: the Explore page at the root, and the study page, taken from that release while `DAILY_ENABLED` is `true` and from the committed `site/study.html` otherwise. It reads the key from the `WHAT_TO_ID_KEY` secret and the blitz start from the `BLITZ_D1` variable, and runs `scripts/daily.sh`. The script defaults to four lists with rotation and requires a prepared embedding bundle. Configure its versioned release and LabelFirst repository access before enabling this workflow. It refuses to keep a page that names a list, and reruns the day's build from its snapshot and stops unless that matches the served log exactly. The `pool-state` release keeps the pool, the served log (letters only), and each day's pool snapshot and public build record. Set the repository variable `CODE_REF` to a tag to run the same code for the whole blitz; each build record names the commit that ran. Actions are pinned by commit SHA. GitHub turns a schedule off after 60 days without a push to the repository, so push at least once in that window while it runs.

A one-off build is published instead by copying `out/build/site/*.html` over `site/`, which `map.yml` publishes (the Pages workflow only starts it when `site/` changes on main); a rotation build writes only `study.html`, so delete the old `arm_*.html` pages when switching. Both the daily and map workflows refuse any file that is not HTML and any page that names an arm. Keep the key, and a real build's manifest and seed, out of the repo: with the public code and the same pool, any of them recovers which list is which.

The current page is a rotation preview of all four lists, built from a 10,000-record sample frozen on 2026-09-11 (`--max-batches 20`), not the blitz build. Its lists are assigned with a private key, like the daily build, so the public code and pool do not show which list is which.
