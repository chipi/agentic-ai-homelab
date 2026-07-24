# Reporter knowledge — orrery-fly-physics

What I know as the reporter/maintainer (intent only — I don't know which
file or function is responsible):

- The broken readout is the **spacecraft speed shown on the /fly HUD**
  ("NN km/s"), which is computed from the vis-viva relation using the
  spacecraft's current radius and the transfer orbit's semi-major axis.
- It shows **NaN when the spacecraft's radius goes beyond the transfer
  orbit's apohelion** (aphelion) — i.e. when the vis-viva radicand goes
  negative.
- Expected behavior (my design decision as maintainer):
  - beyond apohelion, the readout should **fall back to the local circular
    orbital speed** at that radius (sqrt(mu / r)) — NOT extrapolate, NOT
    clamp to the apohelion speed, NOT hide the readout;
  - at radius = 0 it should return **0**, not NaN.
- The transfer semi-major axis input itself is not what I'm reporting —
  keep the inputs as they are; the speed function's out-of-range behavior
  is the bug.
