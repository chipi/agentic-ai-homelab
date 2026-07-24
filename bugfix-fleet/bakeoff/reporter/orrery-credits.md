# Reporter knowledge — orrery-credits

What I know as the reporter/maintainer (intent only — I don't know which
file or function is responsible):

- The bug: on /credits several agencies' images are misfiled under the
  "Wikimedia Commons contributors" section.
- The intended mapping (my editorial decisions as maintainer):
  - **CMSA** (China Manned Space Agency) folds into China's existing
    section → section id **`cnsa`** (no separate CMSA section);
  - **SpaceIL** gets its own section → **`spaceil`**;
  - **USAF** (like USSF / "air force") folds into the US military space
    section → **`us-space-force`**;
  - **CSA** (Canadian Space Agency) → **`csa`** when CSA is the primary
    (first) token of the credit, e.g. "CSA / NASA";
  - NASA-first joint credits (e.g. "NASA / ESA") must still map to
    **`nasa`** — do not regress that.
- The existing CNSA → `cnsa` mapping must not regress.
- One trap I'm aware of from a previous attempt: "CSA" is a substring of
  "CNSA"/"CMSA" — matching must respect token boundaries, not bare
  substrings.
- The primary-credit rule: the first agency token (split on " / ") decides
  the section.
