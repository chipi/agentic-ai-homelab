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
- **If asked "what should the middle of the arc look like" (definition of
  done), my answer is:** the mid-arc shape must respond to the mission's
  arrival V-infinity — zero/low V∞ leaves the arc essentially the baseline
  ellipse; high V∞ visibly bends the middle away from that baseline while
  both endpoints stay pinned. Done means: same mission data, arcs with high
  arrival V∞ render with a bent mid-arc, and missions without it are
  unchanged.
