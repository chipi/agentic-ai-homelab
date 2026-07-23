# src/lib/mission-arc.ts — module notes

Mission Arc geometry (ADR-009/ADR-010): pure functions that build the
heliocentric transfer geometry the `/fly` route renders. Coordinate system:
heliocentric ecliptic plane, AU.

Who does what:

- **`earthPos` / `marsPos` / `destinationPos`** — body positions at a
  simulation day (circular / Keplerian approximations).
- **`outboundArc`** — the outbound half-ellipse from Earth to the destination,
  apsides rotated to the actual launch position.
- **`transferEllipse`** — builds the rendered transfer-arc polyline between
  two transfer points. This function owns the arc's *shape*: endpoints stay
  pinned to the supplied transfer points, and the shape between them derives
  from the mission's transfer parameters.

Mission parameters come from the mission data (per-destination transfer
constants and, where a mission defines it, the **arrival hyperbolic excess
velocity V∞** — the arrival-energy term of the transfer). Arc geometry is
expected to reflect the mission's parameters, not just the two endpoints.
