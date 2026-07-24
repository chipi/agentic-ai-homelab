# Reporter knowledge — orrery-mission-arc

What I know as the reporter/maintainer (intent only — I don't know which
file or function is responsible):

- The transfer arcs I'm complaining about are the mission transfer arcs
  drawn between two bodies (e.g. Earth → destination).
- Missions carry an **arrival V-infinity** (hyperbolic excess velocity) in
  their data. The arc drawing currently **ignores it** — that's the bug.
- Expected behavior: both endpoints must stay **pinned to the transfer
  points** exactly. A **high arrival V-infinity should bend the middle of
  the arc away** from the baseline (pure-ellipse) shape; a low/zero arrival
  V-infinity should leave the arc close to the baseline ellipse.
- The wrong "shape" I reported is exactly this: the mid-arc bend is wrong
  because the arrival V-infinity is not being applied.
- It affects missions that have a meaningful arrival V-infinity in their
  data; endpoints were never the problem.
