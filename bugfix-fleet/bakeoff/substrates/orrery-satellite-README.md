# src/lib/satellite — module map

Satellite tracking for the observer-sky views. What lives where:

- **`tle.ts` / `tle-source.ts` / `station-tles.json`** — TLE parsing and the
  bundled station element sets.
- **`propagate.ts`** — orbit propagation from TLEs to satellite ECI states.
- **`look-angles.ts`** — the topocentric transform: satellite ECI − observer
  ECI → local SEZ → altitude/azimuth. `observerEci()` produces the observer's
  Earth-centered position; `lookAngle()` turns a satellite position into the
  observer's sky coordinates.
- **`stations.ts`** — the ground-station/observer catalog.

Conventions: all distances km, angles radians internally (degrees only at the
display boundary). **Earth model for observer geometry is the WGS84
ellipsoid** (equatorial radius a = 6378.137 km, inverse flattening
1/f = 298.257223563, polar radius ≈ 6356.752 km) — observer positions and
altitudes are relative to the ellipsoid, not a sphere; a low-orbit target is
dominated by the observer's offset from Earth's centre, so ellipsoid-level
accuracy matters here.
