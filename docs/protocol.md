# Identification-queue order: protocol, first run in British Columbia (draft for co-design, not sent)

Status: draft for the BC-team meeting. The set-up below is a proposal. Nothing here is final until Nathan, Laura and David have said yes.

## The question

Does the order in which the iNaturalist identification queue shows records change how much gets identified, and what? The method is general: split the records that need an ID into lists at random, change only the order each list shows, let identifiers work all lists in turn, and read the result back from iNaturalist. The first run is a British Columbia identification blitz with Blitz the Gap. Its results hold for that blitz's region and identifiers; other regions have to run it to know.

Orders answer one of two questions:

- **Speed:** does the order change how many IDs an hour of effort gives? Example: look-alike photos together.
- **Value:** does the order change which gaps the IDs fill? Examples: records from data-poor places first, which targets the gap in where species are known to occur (the Wallacean shortfall, [Hortal et al. 2015](https://doi.org/10.1146/annurev-ecolsys-112414-054400)); unfamiliar photos first, which targets the gap in what verified photos cover.

Newest first, close to what iNaturalist shows today, is the control for both.

## Proposed set-up for BC

- Two lists: newest first (the control) and data-poor places first. Look-alikes together and unfamiliar photos first are left to a later round.
- Four weeks in November 2026.
- All ten iNaturalist taxon groups.
- Participants join an iNaturalist project, so the analysis knows who took part.
- The page is hosted on the PollockLab GitHub Pages site and works in any web browser; a laptop works best, because Identify is built for a large screen.

## What identifiers see

One web page. An identifier picks a taxon group they know and presses "Next batch". Each press opens iNaturalist's Identify tool on a batch of about 120 British Columbia records that need an ID and have a photo. Identifiers work inside iNaturalist as usual: their IDs carry their name, count toward Research Grade, and flow to GBIF. Nothing about identifying changes. We only choose which records sit together in a batch.

Each browser draws its own random cycle of the lists once, and every press takes the next list in that cycle, so every identifier's batches split evenly over all lists and nobody's effort lands on one list only. The page shows only "Batch N". A few identifiers make most of the IDs, and if each identifier kept one list, the list that drew the busiest identifier would win whatever its order; the rotation borrows the within-person comparison of interleaved search evaluation ([Chapelle et al. 2012](https://doi.org/10.1145/2094072.2094078)).

The lists are unlabelled rather than blind. The page never names them, but an identifier who looks can often tell a list by its batches, most clearly with look-alike photos. This is why the test compares each identifier with themself and does not depend on anyone not knowing.

Identify shows records newest-first and lets people skip freely, so the batches control composition, not sequence. Records an identifier has already reviewed drop out of the batch automatically, and records that reach Research Grade drop out for everyone.

Verified 2026-09-11 in a logged-in browser: an Identify URL with an explicit `id=` list of five BC records showed exactly the four that still needed an ID; the fifth had reached Research Grade since the pull and was filtered out by Identify's default needs-ID filter, which is the intended behaviour.

## The lists

The page is rebuilt every day from the British Columbia records that need an ID and have a photo at that time, observed since 2025-01-01. Each record goes to one list by a keyed hash of its record id, so it stays on the same list in every daily build and the lists hold the same mix of taxa and observers on average. The key is kept privately and opened after the read-back. Each daily build serves the first 20 batches per list and taxon group, so the newest-first list stays new through the four weeks and records that were identified in the meantime drop out.

- Newest first: batches are the newest records, as iNaturalist shows them today.
- Data-poor places first: batches are drawn from cells where iNaturalist has few or old records, using the where-to-blitz map scores. An ID there is often the only species record for that cell and goes straight into the models the lab uses to name 2027 field sites.
- Later round, look-alikes together: batches are built so photos that look alike by an image model sit together, on the hypothesis that fewer context switches make identifying faster. The image model is BioCLIP 2.5, chosen on a 10,000-record BC sample where it placed same-species photos closer together than BioCLIP 2, DINOv2 and DINOv3 in every taxon group. It is weakest on fungi and fish (nearest-neighbour species agreement 43 and 53 percent, against 84 for amphibians), so look-alike batches in those groups will be looser.
- Later round, unfamiliar photos first: each photo is compared by the same image model with every Research Grade BC photo of the same group, and batches are drawn from the records that look least like anything already verified. An ID there is the most likely to add a species, or a look of a species, that the verified record does not cover yet.

Every batch also carries two numbers in the build record, kept as information and never used to filter: how much its photos resemble each other, and how far they sit from verified photos of the same group. They are only available once the image embeddings are.

## What we measure, decided before the blitz

Only participants' identifications made during the blitz count. Each identification keeps its own timestamp, so this count is fixed when the blitz ends; it is read back within a week of the end. Record-level outcomes are read back 30 days after the end.

Each order is judged on the measure for its question. For each participant and list we count the records they gave a species-level ID:

- Speed orders: the plain count.
- Data-poor places first: each record weighted by its where-to-blitz cell score, so an ID in a data-poor cell counts for more.
- Unfamiliar photos first: species that reached Research Grade in a grid cell with no Research Grade record of that species before the blitz.

For BC:

1. Primary: per participant, the weighted count on data-poor places first minus the weighted count on newest first. The test is a paired sign-flip permutation test on the sum of these differences, two-sided at 0.05. Busy identifiers add the same effort to both lists, so their skill cancels out.
2. Secondary: the same comparison on the plain count, and a sign test on how many participants did better on each list.
3. Secondary, at 30 days: share of served records whose community taxon reached species, and Research Grade records added, weighted by cell score, per list.
4. Checks: the same test over the days before the blitz, when participants had not seen the page, should find nothing; and each participant's reviewed records should split about evenly over the lists, which is what the rotation assumes.

Expectation stated up front: newest first will likely win on the plain count, because records from remote cells have worse photos and are skipped more. Data-poor places first should win on the weighted count. If it loses on both, it is dropped.

Simulated on BC identifier effort from August 2026, two lists with 25 participants detect a 20 percent difference almost always over a month of effort (power 1.00) and about 6 times in 10 over one week (0.62).

## What we are not claiming

- A method, tested first in BC. A result holds for this blitz's region and identifiers.
- No sorting by identification difficulty. That idea failed its pre-registered test and is not in this design.
- No wait-time numbers for the backlog. The pilot columns that produced them are censored.
- No value-of-information claims.
- No claim that batches change the order in which someone identifies, only which records they meet together.

## Reproducibility

Each daily build comes from a pull of the iNaturalist API at a recorded time, the private list key, and a pinned where-to-blitz commit whose grid is recorded by its hash in every build. Every day's served batches and record ids are logged by list letter, so exposure is fully known and the read-back is a join, not a reconstruction. The key maps letters to lists after the read-back.

## Open with the BC team

- Blitz dates.
- Whether data-poor places first is the one order to test against newest first, or another.
- Which taxon groups identifiers will cover, if not all ten.
- The iNaturalist project participants join.
