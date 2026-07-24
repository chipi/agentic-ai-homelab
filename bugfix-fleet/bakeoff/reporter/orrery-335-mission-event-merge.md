# Reporter knowledge — orrery-335-mission-event-merge

What I know as the reporter/maintainer (intent only — I don't know which
file or function is responsible):

- The bug: on multi-flyby missions (e.g. Cassini) the CAPCOM event ticker
  shows every flyby as the generic label "FLYBY" with an empty note.
- The mission data itself carries rich per-event text — specific labels
  like "Venus #1 — gravity assist" and "Saturn orbit insertion", plus
  multi-sentence descriptions — but none of it reaches the ticker.
- Expected behavior: when an event supplies its **own label/description,
  use those**; fall back to the generic type-based label/note **only when
  the event doesn't** supply them.
- Event severity/colour must **stay driven by the event type** — that part
  is correct today and must not change.
