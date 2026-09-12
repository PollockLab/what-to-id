# BC identification blitz: batch protocol (draft for co-design, not sent)

Status: draft for the September BC-team meeting. Arm set is a proposal. Nothing here is final until Nathan, Laura and David have said yes.

## What identifiers see

A web page with up to four lists, labelled A, B, C and D. Each list is a stack of links. Each link opens iNaturalist's Identify tool on a batch of about 120 British Columbia records that need an ID and have a photo. Identifiers work inside iNaturalist as usual: their IDs carry their name, count toward Research Grade, and flow to GBIF. Nothing about identifying changes. We only choose which records sit together in a batch.

Identify shows records newest-first and lets people skip freely, so the batches control composition, not sequence. Records an identifier has already reviewed drop out of the batch automatically, and records that reach Research Grade drop out for everyone.

Verified 2026-09-11 in a logged-in browser: an Identify URL with an explicit `id=` list of five BC records showed exactly the four that still needed an ID; the fifth had reached Research Grade since the pull and was filtered out by Identify's default needs-ID filter, which is the intended behaviour.

## The lists

Every needs-ID record with a photo from British Columbia since 2025-01-01 is assigned at random to one list. Randomisation is per record, balanced within each taxon group (birds, insects, plants, fungi, and so on) and within each observer, so every list has the same mix of taxa and observers. Identifiers choose whichever taxon group they know.

- One list is the plain reference: batches are simply the newest records. This is what an identifier gets from iNaturalist today.
- One list puts records from data-poor places first: batches are drawn from cells where iNaturalist has few or old records, using the same map scores as where-to-blitz. An ID there is often the only species record for that cell and goes straight into the models the lab uses to name 2027 field sites.
- One list groups look-alikes: batches are built so photos that look alike (by an image model) sit together, on the hypothesis that fewer context switches make identifying faster. This list is only run if the image embeddings are ready by mid-October; otherwise the blitz runs with two lists. The image model is BioCLIP 2.5, chosen on a 10,000-record BC sample where it placed same-species photos closer together than BioCLIP 2, DINOv2 and DINOv3 in every taxon group; adding a down-weighted DINOv3 block moved the score by under one point either way, so it is not used. It is weakest on fungi and fish (nearest-neighbour species agreement 43 and 53 percent, against 84 for amphibians), so look-alike batches in those groups will be looser.
- One list puts the least familiar photos first: each needs-ID photo is compared (by the same image model) with every Research Grade BC photo of the same group, and batches are drawn from the records that look least like anything already verified. An ID there is the most likely to add a species, or a look of a species, that BC's verified record does not cover yet. This list needs the same embeddings as the look-alike list plus a reference set of Research Grade photos, so it has the same mid-October condition.

Identifiers are not told which list is which. The mapping is recorded once in the build manifest and opened after the read-back. Each identifier is given a list at random by the page on first visit and the choice is remembered in their browser, so identifier effort is balanced across lists in expectation without anyone assigning people by hand. An identifier can switch, but the page asks them not to.

Every batch in every list also carries two numbers in the manifest, recorded as information and never used to filter: how much its photos resemble each other (cohesion) and how far they sit from verified BC photos of the same group (novelty). They are shown on the batch cards in plain words. After the blitz they let us ask, across all lists at once, whether tighter or more unfamiliar batches got more species-level IDs. Batch size trades against tightness: on the sample, batches of 30 came out clearly tighter than batches of 120.

## What we measure, decided before the blitz

Thirty days after the blitz, every served record is read back from the iNaturalist API.

1. Primary: share of served records whose community taxon has reached species level, per list.
2. Secondary: Research Grade records added, weighted by how data-poor the record's cell is, per list.
3. Exploratory: identifications per identifier per day, from iNaturalist timestamps, stated as approximate because we do not see when someone opened a batch.
4. Exploratory: species reached at Research Grade that had no Research Grade record in the same grid cell before the blitz, per list. Counted from the read-back against the frozen reference pull, so it is a join, not a judgement.

Expectation stated up front: the plain list will likely win on 1, because remote-cell records have worse photos and more skips. The data-poor list should win on 2. If it loses on both, it is dropped. The least-familiar list will likely do worst on 1, because unfamiliar photos are the hard ones; its case rests on 4, and it is dropped if it does not lead there.

## What we are not claiming

- No sorting by identification difficulty. That idea failed its pre-registered test and is not in this design.
- No wait-time numbers for the backlog. The pilot columns that produced them are censored.
- No value-of-information claims.
- No claim that batches change the order in which someone identifies, only which records they meet together.

## Reproducibility

One command builds the lists from a frozen pull of the iNaturalist API (freeze date recorded), a fixed random seed, the published where-to-blitz grid release and a pinned labelfirst commit. The manifest lists every batch and every record id, so the exposure is fully known and the read-back is a join, not a reconstruction.

## Open with the BC team

- Blitz dates, which set the freeze date for the pool.
- Whether two, three or four lists. Each extra list splits the same records further, so with four lists each one gets a quarter of the pool and the read-back needs more identifications per list to tell them apart.
- Which taxon groups identifiers will cover, so batches exist for each.
- Where the page is hosted (a PollockLab GitHub Pages site or ours).
