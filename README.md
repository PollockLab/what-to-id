# what-to-id

Does the order of the iNaturalist identification queue change how much gets identified, and what? what-to-id tests this with unlabelled, randomised lists and reads the answer back from iNaturalist. First deployment: British Columbia, autumn 2026, with Blitz the Gap.

It is a method, tested first in BC. A result from one blitz holds for that blitz's region and identifiers; other regions have to run it to know.

Companion to [where-to-blitz](https://github.com/PollockLab/where-to-blitz), which answers where to go and record. Both serve Blitz the Gap.

## What the lists test

Every list holds the same kind of records and differs only in order. The orders fall into two families, each with its own question:

- **Speed** lists change how many IDs an hour of identifier effort gives. `similarity` puts look-alike photos together, on the hypothesis that fewer context switches make identifying faster.
- **Value** lists change which gaps the IDs fill. `gap_first` puts records from data-poor places first, aimed at the gap in where species are known to occur (the Wallacean shortfall, [Hortal et al. 2015](https://doi.org/10.1146/annurev-ecolsys-112414-054400)). `novelty` puts the photos least like any verified photo of their group first, aimed at the gap in what verified photos cover.
- `recency`, newest first, is the control for both.

Each family is judged on its own measure: speed lists on species-level IDs per identifier, value lists on the same count weighted by how data-poor the record's place is (`gap_first`) or on new species per grid cell (`novelty`).

## The experiment in one picture

```mermaid
flowchart TB
  pool["<b>The day's pool</b><br/>records that need an ID"]
  split(["`each record goes to one list 
  by a keyed hash of its id, 
  the same list every day`"])
  pool --> split
  split --> L1["<b>List 1</b><br/>newest first<br/><i>the control</i>"]
  split --> L2["<b>List 2</b><br/>data-poor places first"]
  split --> L3["<b>List 3</b><br/>look-alikes together"]
  split --> L4["<b>List 4</b><br/>unfamiliar photos first"]
  L1 & L2 & L3 & L4 --> page["<b>One page, lists unnamed</b><br/>each Next batch press<br/>serves the next list"]
  page --> work["Identifiers work each batch<br/>in iNaturalist, as usual"]
  work --> count["<b>Count</b> species-level IDs<br/>per identifier, per list"]
  count --> cmp["<b>Compare</b> each list with List 1<br/>within each identifier"]
```

Each record sits on exactly one list and keeps it in every daily build. Because the list comes from a keyed hash of the record id, every list gets a like mix of taxon groups and of the observers who posted the records on average, so the lists differ only in the order they show their records. That order is the one thing under test.

The lists are unlabelled rather than blind: the page never names them, but a batch of look-alike photos shows which list it came from.

**Every identifier works every list.** A few identifiers make most of the IDs. If each identifier kept one list, the list that drew the busiest identifier would win whatever its order. So each browser draws its own random cycle of the four lists once, and every press of Next batch takes the next list in that cycle:

| | Their cycle | Press 1 | Press 2 | Press 3 | Press 4 | Press 5 | Press 6 | Over the blitz |
|---|---|---|---|---|---|---|---|---|
| Identifier who does 40 batches | 3 → 1 → 4 → 2 | 3 | 1 | 4 | 2 | 3 | 1 | 10 batches from each list |
| Identifier who does 4 batches | 2 → 4 → 1 → 3 | 2 | 4 | 1 | 3 | | | 1 batch from each list |

IDs are credited to iNaturalist accounts and each record's list is fixed, so a second device only adds a second balanced cycle. Each identifier is then compared with themself: their IDs on List 2 against their IDs on List 1, and so on. A busy identifier adds the same effort to every list, so their skill cancels out. `python -m what_to_id.power` simulates both designs.

| | One list per identifier | Every identifier works every list |
|---|---|---|
| A busy identifier's effort goes to | one list | all lists, equally |
| A list scores high because of | who landed on it | its order |
| Compared unit | list totals | each identifier with themself |

## How it works

1. **Pull.** Pull the needs-ID records with a photo, observed since a start date. The daily job then adds only the records created since its last run and, before each build, drops served records that no longer need an ID. The region is BC (iNaturalist place 7085), set in `inat.py` and `batches.py`.
2. **Assign.** Each record goes to one list by a keyed hash of its record id (`--key-env`), so it stays on that list in every daily build. The key is private. Without it, a one-off build randomises once with a seed, balanced within taxon group and observer.
3. **Compose.** Each arm orders its records into batches:
   - `recency`: newest first as of the build, close to what an identifier gets from iNaturalist today.
   - `gap_first`: records from data-poor places first, using the where-to-blitz cell scores.
   - `similarity`: look-alike photos together, from BioCLIP 2.5 image embeddings.
   - `novelty`: photos least like any Research Grade photo of the same group and region first.
4. **Serve.** A static page shows lists labelled A to D, each a stack of Identify links. The arm behind each letter is recorded only in the build's `manifest.json`, never on the page. By default each identifier takes one list; `--design rotation` serves the one-page rotation pictured above. Each daily build appends its served records, by letter, to a served log (`--served-log`).
5. **Read back.** Every served record, from every daily build, is fetched again. Identifications keep their own timestamps, so the per-identifier comparison is fixed when the blitz ends and is read back within a week of it; the record-level outcomes are read back 30 days after.

## First deployment: British Columbia

The first run is a BC identification blitz in autumn 2026, with Blitz the Gap. The protocol and the outcomes fixed before the blitz are in [docs/protocol.md](docs/protocol.md), a draft for co-design with the BC team. The proposed set-up is two lists, `recency` and `gap_first`, over four weeks, with the look-alike and unfamiliar-photo lists left to a later round.

## Install

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"      # add ,embed for the image-embedding step, ,similarity for look-alike batches
```

The `similarity` extra installs `labelfirst`, a private repository pinned by commit in `pyproject.toml`, so it needs access to that repository. Only the look-alike list's seed picker and the separability report use it; the two-list build and the daily job run without it.

The daily job and CI install exact, hash-pinned versions from `requirements.lock` (`pip install --require-hashes -r requirements.lock`, then run with `PYTHONPATH=src`). After changing the dependencies in `pyproject.toml`, regenerate it with `uv pip compile pyproject.toml --extra dev --universal --python-version 3.11 --generate-hashes -o requirements.lock`.

## Use

```bash
# Freeze the needs-ID pool (hours for all groups; --groups and --cap-pages for a sample).
# An interrupted pull resumes from the groups already saved.
python -m what_to_id.inat --d1 2025-01-01 --freeze YYYY-MM-DD --out data/pool_YYYY-MM-DD.parquet

# Research Grade reference pool for the novelty arm
python -m what_to_id.inat --d1 2025-01-01 --freeze YYYY-MM-DD --quality research --out data/ref_YYYY-MM-DD.parquet

# Build assignment, batches, manifest and site. --max-batches serves only the first N
# batches per arm and taxon group, so the read-back denominator is fixed before the blitz.
# --design rotation (opt-in) writes one page where each "Next batch" press takes the identifier
# to the next list, so every identifier's work splits evenly across lists.
what-to-id build --pool data/pool_YYYY-MM-DD.parquet --freeze YYYY-MM-DD --d1 YYYY-MM-DD --seed <private-seed> --max-batches N --out out/build

# Daily build, the same script .github/workflows/daily.yml runs: fetch the pool state, add new records,
# build with the private key, drop served records that no longer need an ID, rebuild, log what was served,
# keep the day's pool and build record, check for leaks and replay the build. WTB_DIR is a where-to-blitz
# checkout at the commit in what_to_id.manifest.WHERE_TO_BLITZ_REF. OFFLINE=1 rehearses on a saved pool.
export WTB_DIR=../where-to-blitz/cluster_results/ca BLITZ_D1=<blitz-start>
scripts/daily.sh fetch && scripts/daily.sh build     # scripts/daily.sh save uploads the state

# Rerun any past day from its snapshot; exits 1 unless it serves exactly what the served log says
python -m what_to_id.replay --pool state/days/pool-YYYY-MM-DD.parquet --record state/days/build-YYYY-MM-DD.json --served-log state/served.parquet --webapp-dir "$WTB_DIR" --key-env WHAT_TO_ID_KEY

# After the blitz, open the key: letter -> list map for the read-back and the analysis
python -c "import json; from what_to_id.manifest import blind_labels_keyed as b, key_from_env as k; print(json.dumps({v: a for a, v in b(['recency', 'gap_first'], k()).items()}))" > labels.json

# Read back outcomes after the blitz: within a week for the per-identifier comparison, again at 30 days
python -m what_to_id.readback --pool state/pool.parquet --assign state/served.parquet --label-map labels.json --out out/outcomes.parquet

# Build the participants file --users reads below, from project members or a sign-up form's logins
python -m what_to_id.participants --project ID_OR_SLUG --out participants.txt
python -m what_to_id.participants --logins signups.txt --out participants.txt

# Pre-registered per-identifier comparison for the rotation design: participants only, plus a pre-blitz placebo.
# --weight cell_score gives the weighted count, the primary for gap_first; each run also reports a sign test (p_sign)
python -m what_to_id.analysis --idents out/outcomes_idents.parquet --served state/served.parquet --label-map labels.json --weight cell_score --control recency --start <blitz-start> --cutoff <read-back-cutoff> --users participants.txt --placebo-start <placebo-start> --obs out/outcomes_obs.parquet
```

The read-back denominator is the served records only: `assign.parquet` covers the whole pool, but `batches.parquet` (one build) and the served log (every daily build) hold just the records placed in a served batch. Both work as `--assign` and `--served`; the served log needs `--label-map`.

The similarity and novelty arms need image embeddings: embed the records assigned to them with `python -m what_to_id.embed` (a GPU job, see `slurm/embed_mila.sbatch`), then pass `--embeddings` and `--reference-embeddings` to `build`. The `gap_first` arm reads where-to-blitz's `cluster_results/ca`; point `--webapp-dir` or the `WHERE_TO_BLITZ_CA` environment variable at a checkout of it.

## Publish

The live page is served at https://pollocklab.github.io/what-to-id/. The daily workflow (`.github/workflows/daily.yml`) rebuilds and deploys it every morning once the repository variable `DAILY_ENABLED` is `true`, and on demand from the Actions tab. It reads the key from the `WHAT_TO_ID_KEY` secret and the blitz start from the `BLITZ_D1` variable, and runs `scripts/daily.sh`. It refuses to deploy a page that names a list, reruns the day's build from its snapshot and stops unless that matches the served log exactly, and deploys before it saves the state, so the served log never lists a page that did not go live. The `pool-state` release keeps the pool, the served log (letters only), and each day's pool snapshot and public build record. Set the repository variable `CODE_REF` to a tag to run the same code for the whole blitz; each build record names the commit that ran. Actions are pinned by commit SHA. GitHub turns a schedule off after 60 days without a push to the repository, so push at least once in that window while it runs.

A one-off build is published instead by copying `out/build/site/*.html` over `site/`, which the Pages workflow deploys on a push to main (while `DAILY_ENABLED` is `true`, only when run by hand from the Actions tab, so a push never overwrites the daily page); a rotation build writes only `index.html`, so delete the old `arm_*.html` pages when switching. Both workflows refuse any file that is not HTML and any page that names an arm. Keep the key, and a real build's manifest and seed, out of the repo: with the public code and the same pool, any of them recovers which list is which.

The current page is a preview built from a 10,000-record sample frozen on 2026-09-11 (seed 7), not the blitz build.

## Tests

```bash
pytest              # network tests are skipped by default
pytest -m network   # hits the live iNaturalist API
```

## References

- Hortal J, de Bello F, Diniz-Filho JAF, Lewinsohn TM, Lobo JM, Ladle RJ (2015). Seven shortfalls that beset large-scale knowledge of biodiversity. Annual Review of Ecology, Evolution, and Systematics 46:523-549. [doi:10.1146/annurev-ecolsys-112414-054400](https://doi.org/10.1146/annurev-ecolsys-112414-054400).
