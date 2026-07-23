# src/lib/credits-grouping.ts — source-section taxonomy

The credits page groups every image/text by *originating agency or program*,
not by hosting site. `provenanceSourceId()` / `textSourceId()` map a
provenance entry to its section id; `groupBySource()` builds the page model.

Taxonomy rules maintainers should keep in mind:

- **Hosting is not sourcing.** Material that merely *arrives via* Wikimedia
  Commons is credited to its originating agency's section; `wikimedia-commons`
  is only for material with no more specific origin.
- **National programs fold into their agency's section**: China's crewed
  program CMSA (China Manned Space Agency) belongs in the CNSA section
  (`cnsa`), the same way USAF space imagery belongs with USSF in the US
  military space section (`us-space-force`).
- **Independent organizations get their own section**: SpaceIL (`spaceil`),
  CSA — the Canadian Space Agency (`csa`).
- **Joint credits group under the first-listed (primary) agency**: a
  "CSA / NASA" credit sits in `csa`; a "NASA / ESA" credit sits in `nasa`.
- Per-instrument orbital imagery keeps its per-instrument sections (#360).
