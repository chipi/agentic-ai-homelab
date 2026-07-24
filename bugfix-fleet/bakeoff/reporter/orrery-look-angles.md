# Reporter knowledge — orrery-look-angles

What I know as the reporter/maintainer (intent only — I don't know which
file or function is responsible):

- The bug: the observer's Earth-centered position used for satellite
  look-angles is computed on a **spherical Earth** (fixed radius
  ~6378.137 km at every latitude). That is the wrong geodetic model — the
  input latitude is WGS84 geodetic.
- Expected behavior (my acceptance):
  - use the **WGS84 ellipsoid with flattening**, standard constants
    a = 6378.137 km, 1/f = 298.257223563;
  - the observer position magnitude must equal the **equatorial radius
    a = 6378.137 km at latitude 0** and the **polar radius
    b = a·(1−f) ≈ 6356.752 km at latitude 90°** (currently the pole is
    wrong by ~21 km);
  - the observer's **altitude argument** (km above the ellipsoid) must be
    incorporated **along the geodetic normal** — the horizontal components
    scale with (N + alt) and the polar component with (N·(1−e²) + alt),
    where N is the prime vertical radius of curvature — so a positive
    altitude increases the position magnitude accordingly.
- The spherical-trig alt/az math itself was never my complaint — the
  observer position model is.
