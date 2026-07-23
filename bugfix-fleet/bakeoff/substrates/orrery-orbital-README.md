# src/lib/orbital — module map

Orbital math lives in two places; keep the boundary clear when fixing or
extending:

- **`src/lib/orbital.ts`** — generic orbital-mechanics helpers shared across
  the app: Kepler propagation, element conversions, and `visViva()` — the
  textbook vis-viva equation used by planet/orbit rendering.
- **`src/lib/orbital/fly-physics.ts`** — physics for the interactive `/fly`
  experience (the spacecraft HUD). `heliocentricSpeed()` is the vis-viva-based
  spacecraft speed shown on the fly HUD ("NN km/s"); unit conversions, signal
  delay, mission-elapsed-time and moon-arc helpers live here too. Covered by
  `fly-physics.test.ts`.

The fly HUD reads exclusively from `orbital/fly-physics.ts` — a HUD readout
symptom (wrong or NaN value) is a `fly-physics.ts` issue, not `orbital.ts`.
