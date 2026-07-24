# AGENTS.md — Orrery

Instructions for any AI / coding agent working on this codebase. Read this before touching any file.

This is the **canonical** instruction file. `CLAUDE.md` and `.cursor/rules/orrery.mdc` are thin pointers to this document so there's a single source of truth — no 2-way drift between tool-specific copies. Tool-specific notes (e.g. a Claude Code bash-output caveat) live in those thin files when they only apply to one agent.

---

## Where to start — read these before touching code

**Single-page architecture map: [`docs/adr/TA.md`](docs/adr/TA.md).** v2.0 is current as of v0.6.0; it documents every route, subsystem, 3D scene, asset pipeline, contract, and constraint, each with the ADR that locked it. Read it first when a task touches anything outside one file.

Then drill into the matching doc by question type:

| Question | Where to look |
|---|---|
| Why was X chosen? What are the alternatives? | `docs/adr/` — locked decisions (ADR-001 through ADR-058) |
| What is the user value? What's the v1 scope? | `docs/prd/` — product requirements (PRD-001 through PRD-014) |
| What is the open architecture question being deliberated? | `docs/rfc/` — RFCs in flight (RFC-001 through RFC-017) |
| What does the UI look like? | `docs/uxs/` — UX specifications |
| Per-language translation rules? | `docs/guides/i18n-style-guide.md` (binding per ADR-033) |
| Image / link / text provenance? | `static/data/{image,link}-provenance.json` + ADR-046 / ADR-047 / ADR-051 |
| How is a specific 3D scene built? | TA.md §rendering + `src/routes/<route>/+page.svelte` |
| How does the build pipeline work? | TA.md §pipelines (10 pipelines documented) |

**Anti-drift rule:** when code and TA.md disagree, one is wrong — fix it. The same applies to README, CHANGELOG, and TECH-BOM. Do not tolerate divergence.

---

## What this project is

Orrery is a browser-based solar system explorer, mission simulator, encyclopedia, station explorer, and spaceflight fleet inventory rolled into one. Eleven primary nav destinations, real orbital mechanics, **42 missions** in the catalog (21 Moon + 17 Mars + 4 outer-system: Galileo, Voyager 2, New Horizons, Dawn), **137 fleet entries** across 9 categories cross-linked bidirectionally to the rest of the corpus, and a canonical **ORRERY-1** free-return Mars flyby scenario for generic `/fly` runs. It runs entirely in the browser, deploys offline, and has no backend or user accounts. Built for millions of users worldwide — mobile-first, internationalised in **14 locales** at 100% UI parity (en-US + es / fr / de / pt-BR / it / nl / zh-CN / ja / ko / hi / ar / ru / sr-Cyrl).

The eleven primary nav destinations:

| Route | Screen | File |
|---|---|---|
| `/explore` | Solar System Explorer | `src/routes/explore/+page.svelte` |
| `/plan` | Mission Configurator (Earth → 9 destinations, LANDING/FLYBY) | `src/routes/plan/+page.svelte` |
| `/fly` | Mission Arc (heliocentric + cislunar Earth-centered scenes) | `src/routes/fly/+page.svelte` |
| `/missions` | Mission Catalog | `src/routes/missions/+page.svelte` |
| `/earth` | Hybrid scene — default orbital mode (ISS, Tiangong, satellites, LEO/MEO/GEO regime rings, atmosphere shell, ozone overlay) + surface mode (`?mode=surface`) with 14 launchpad markers via shared `SurfaceScene` per ADR-072. Mode toggle top-center. | `src/routes/earth/+page.svelte` (router) + `src/routes/earth/EarthOrbitalScene.svelte` (bespoke orbital scene) |
| `/moon` | Lunar surface map — rectangular hotspot regions (ADR-061), per-mission lander glyphs, lunar orbiters, tidal-lock overlay, sphere → flat-patch view at deep zoom (ADR-062) | `src/routes/moon/+page.svelte` (thin shell over `src/lib/surface-scene/SurfaceScene.svelte` per ADR-072) |
| `/mars` | Martian surface map — rectangular hotspot regions, per-mission lander glyphs, rover traverses with curated stops, atmosphere shell, 25.19° axial tilt, sphere → flat-patch view at deep zoom | `src/routes/mars/+page.svelte` (thin shell over `src/lib/surface-scene/SurfaceScene.svelte` per ADR-072) |
| `/iss` | ISS Explorer (18 pickable modules + visiting spacecraft) | `src/routes/iss/+page.svelte` |
| `/tiangong` | Tiangong Explorer (Tianhe + Wentian + Mengtian with module overlays) | `src/routes/tiangong/+page.svelte` |
| `/science` | Encyclopedia (85 sections × 10 tabs + Space-101 landing) | `src/routes/science/+page.svelte` |
| `/fleet` | Spaceflight Fleet (166 entries × 11 categories — `launcher`, `crewed-spacecraft`, `cargo-spacecraft`, `station`, `rover`, `lander`, `orbiter`, `observatory`, `space-suit`, `constellation`, `launch-site` — with bidirectional cross-links) | `src/routes/fleet/+page.svelte` |

Plus three read-only pages: `/credits` (per-image provenance + text-source attributions), `/library` (bill-of-links across the entire app — every outbound LEARN link with provenance), and `/posters` (Orrery art-print gallery — 11 hand-authored SVG posters across three style families: JPL travel-poster, era-matched, indie-pop).

Other routes under `src/routes/` are landing pages or experiments (see repo layout).

---

## Stack — locked decisions

Do not propose alternatives. If a locked decision needs revisiting, write an ADR superseding the relevant one.

| Concern | Decision | ADR |
|---|---|---|
| Language | TypeScript, `strict: true` | ADR-011 |
| Framework | SvelteKit | ADR-012 |
| 3D rendering | Three.js r128, local bundle | ADR-001 |
| Bundler | Vite (via SvelteKit) | ADR-012 |
| Routing | History API via SvelteKit router | ADR-013 |
| CI + preview | GitHub Actions + GitHub Pages | ADR-014 |
| Unit tests | Vitest | ADR-015 |
| E2e tests | Playwright | ADR-015 |
| External assets | Resolved at build time | ADR-016 |
| Imagery sourcing | Agency-first fetch priority; NASA as fallback library | ADR-046 |
| Outbound LEARN links | Agency-first per-link provenance; native-language priority; `rel="noopener noreferrer external"` + `hreflang` everywhere; public `/library` bill-of-links; link-checker chained into `npm run fetch` | ADR-051 |
| Provenance + license stewardship | Per-image manifest + text manifest + fail-closed validate-data; public `/credits` page | ADR-047 |
| i18n | Paraglide-js + locale overlay files | ADR-017 |
| Design approach | Mobile-first, bottom sheet panels | ADR-018 |
| Data validation | ajv JSON schema on PR | ADR-019 |
| Mission data | Static JSON under `static/data/` (served as `/data/...`) | ADR-006 |
| Mission flight params | Optional `flight` sub-object + `flight_data_quality` honesty flag | ADR-027 |
| Panel tabs + galleries | Tabbed detail panels (OVERVIEW · GALLERY · TECHNICAL · SIZES · LEARN · FLIGHT); GALLERY is always the 2nd tab when present (conditional on per-category manifest); LEARN links in locale overlays | ADR-017, ADR-016 |
| Lambert solver | Web Worker | ADR-008 |
| Default fly scenario | ORRERY-1 free-return flyby (library missions add landings / cislunar arcs) | ADR-009 |
| Transfer arc | Keplerian half-ellipses | ADR-010 |
| `/science` math rendering | KaTeX server-rendered at build; client receives plain HTML, no JS math library | ADR-034 |
| `/science` diagrams | Hand-coded SVG sources committed under `static/diagrams/science/`; fail-closed `validate-diagrams.ts` integrity check chained into `validate-data` | ADR-035 |
| `/science` cross-screen `?` chips | Click navigates to `/science/[tab]/[section]`; desktop hover shows section intro_sentence as `title` tooltip; min 24×24px hit area | ADR-036 |
| Service worker / PWA | `@vite-pwa/sveltekit`; offline shell after first paint; `data-high-contrast` attribute on `<html>` is the pattern Science Lens copies | ADR-029 |
| Translation workflow | LLM-direct (in the Claude Code session — no offline-NMT pipeline, no model downloads); sr-Cyrl hand-authored | ADR-033 |
| Fonts + script strategy | Wave 1 (Latin+Cyrillic) bundled Inter + Crimson Pro; Wave 2 CJK Noto Sans/Serif CJK; RTL Arabic via `dir="rtl"`; sr-Cyrl Cyrillic gate | ADR-032, ADR-043, ADR-044, ADR-045 |
| `/fly` trajectory math | Pure-function isolation + per-mission validation harness; committed expected values catch regressions | ADR-030 |
| `/fly` cislunar view | Earth-centered second camera + per-mission `flight.cislunar_profile` block on Moon missions; auto-switches when destination is MOON | ADR-058 |
| Science Lens + multi-layer state | Attribute-on-`<html>` + MutationObserver subscription; 12 per-layer toggles gated on the master lens; CSS reacts via `:global([data-science-layer-*='on'])` with zero imports | ADR-055 |
| Fleet schema + cross-refs | Per-category folders + generated index manifest; bidirectional `fleet_refs` ↔ `linked_missions`/`linked_sites` enforced by symmetric-link validator (fail-closed) | ADR-052 |
| Fleet imagery + i18n | Same agency-first pipeline as the rest of the corpus; 137 entries × 14 locales = 1,918 overlay files translated in-session by the LLM | ADR-053, ADR-054 |
| E2e readiness signals | Every canvas route exposes `window.__pickAt(x, y)` + `data-route-ready` + `data-loading` attributes; no `sleep(N)` polling in Playwright tests | ADR-056 |
| Locale persistence | Single `orrery_locale` cookie is the ONLY exception to "no client storage"; everything else stays runtime-only | ADR-057 |

For the complete locked-decision matrix (all 58 ADRs, every component, every contract, every constraint, every 3D scene, every pipeline), see [`docs/adr/TA.md`](docs/adr/TA.md). This table is the dev-facing day-to-day reference; TA.md is the authoritative architectural map.

Superseded (do not use): ADR-002 (vanilla JS), ADR-003 (Vite standalone), ADR-004 (hash routing), ADR-005 (Docker Compose only).

---

## Repository structure

```
/
├── AGENTS.md               ← this file (canonical universal AI / agent instructions)
├── CLAUDE.md               ← thin pointer to AGENTS.md + Claude-Code-specific notes
├── .cursor/rules/orrery.mdc ← thin pointer to AGENTS.md for Cursor
├── IMPLEMENTATION.md       ← implementation slices and gates
├── README.md               ← public project introduction
├── LICENSE                 ← MIT
├── .gitignore
│
├── src/
│   ├── routes/             ← SvelteKit file-based routing (11 primary nav + 3 read-only)
│   │   ├── +layout.svelte  ← nav bar, i18n provider, locale picker, footer
│   │   ├── explore/+page.svelte
│   │   ├── plan/+page.svelte
│   │   ├── fly/+page.svelte           ← v0.5.0 cislunar Earth-centered scene (ADR-058)
│   │   ├── missions/+page.svelte
│   │   ├── earth/+page.svelte
│   │   ├── moon/+page.svelte
│   │   ├── mars/+page.svelte           ← v0.4.0 (PRD-009 / RFC-012)
│   │   ├── iss/+page.svelte            ← v0.5.0 (PRD-010 / RFC-013)
│   │   ├── tiangong/+page.svelte       ← v0.5.0 (PRD-011 / RFC-014)
│   │   ├── science/                    ← v0.5.0 (PRD-008 / RFC-011) — encyclopedia
│   │   ├── fleet/+page.svelte          ← v0.6.0 (PRD-012 / RFC-016 / ADR-052/053/054)
│   │   ├── credits/+page.svelte        ← v0.4.0 (ADR-047) — image provenance
│   │   └── library/+page.svelte        ← v0.5.0 (ADR-051) — outbound link inventory
│   ├── lib/
│   │   ├── components/
│   │   │   ├── Nav.svelte                     ← shared 52px nav bar + locale picker
│   │   │   ├── AudioOverlay.svelte            ← v0.7 audio narration overlay (PRD-016 / RFC-019)
│   │   │   ├── ScienceLensBanner.svelte       ← collapsible banner (ADR-055)
│   │   │   ├── ScienceLayersPanel.svelte      ← per-layer sub-toggles (12 layers)
│   │   │   ├── ScienceChip.svelte             ← cross-screen `?` chip (ADR-036)
│   │   │   ├── FlightDirectorBanner.svelte    ← /fly 5-phase narration
│   │   │   ├── WhyPopover.svelte              ← inline value-explanations
│   │   │   ├── StationModulePanel.svelte      ← shared by /iss + /tiangong
│   │   │   ├── ObservatoryShowcase.svelte     ← /science 12-shot strip (v0.6)
│   │   │   └── ...
│   │   ├── data.ts                       ← fetch + cache + i18n shallow merge (ADR-017)
│   │   ├── orbital.ts                    ← keplerPos(), visViva() — planet/orbit rendering helpers (NOT the /fly HUD)
│   │   ├── orbital/                      ← /fly spacecraft physics + camera/frame logic
│   │   │   ├── fly-physics.ts            ← heliocentricSpeed() = the /fly HUD speed readout ("NN km/s"), unit conversions, signal delay, MET
│   │   │   └── ...                       ← mission-arc, flyby/camera planning, debug frames
│   │   ├── scale.ts                      ← auToPx(), altToOrbitRadius()
│   │   ├── lambert.ts                    ← solver (worker only)
│   │   ├── cislunar-geometry.ts          ← Earth-Centered Inertial trajectory builder (ADR-058)
│   │   ├── science-lens.ts               ← attribute-on-<html> lens state (ADR-055)
│   │   ├── science-layers.ts             ← multi-flag layer state (12 layers, ADR-055)
│   │   ├── orbit-overlays.ts             ← lens-layer 3D helpers (gravity arrows, conics, …)
│   │   ├── microgravity-axes.ts          ← /iss + /tiangong axis overlay
│   │   ├── station-geometry.ts           ← shared mesh helpers (ADR-049)
│   │   ├── katex.ts                      ← KaTeX server-rendered wrapper (ADR-034)
│   │   ├── earth-satellite-models.ts     ← 20 per-mission /earth + lunar-orbiter builders
│   │   ├── moon-lander-models.ts         ← 11 per-mission /moon surface builders (v0.6.0)
│   │   ├── mars-lander-models.ts         ← 9 per-mission /mars surface builders
│   │   ├── surface-scene/                 ← canonical /moon + /mars renderer (ADR-072)
│   │   │   ├── SurfaceScene.svelte       ← shared 3D scene + animation loop + HUD + panel state
│   │   │   ├── SurfaceFlatPatch.svelte   ← flat 2D ground-patch view at deep zoom (ADR-062)
│   │   │   ├── types.ts                  ← SurfaceSceneConfig — 8 body-justified knobs
│   │   │   ├── README.md                 ← contract: before adding a 9th knob, read this
│   │   │   └── debug-info.ts, register-{moon,mars}-hotspot-builders.ts
│   │   ├── iss-proxy-model.ts            ← ISS proxy model + module pickability (ADR-040/041)
│   │   ├── tiangong-proxy-model.ts       ← Tiangong proxy model (ADR-049)
│   │   ├── moon-marker-category.ts       ← category fallback for unknown lunar mission ids
│   │   ├── link-provenance.ts            ← LEARN-link locale fallback chain (ADR-051)
│   │   ├── image-credits.ts              ← per-image TASL parsing for lightbox
│   │   ├── credits-grouping.ts           ← /credits page section grouping
│   │   ├── library-grouping.ts           ← /library page section grouping
│   │   └── license-allowlist.ts          ← canonical license allowlist (ADR-047)
│   ├── workers/
│   │   └── lambert.worker.ts
│   └── types/
│       ├── mission.ts      ← Mission, MissionIndex interfaces
│       ├── science.ts
│       ├── iss-module.ts
│       ├── tiangong-module.ts
│       └── planet.ts
│
├── static/                 ← SvelteKit static dir (copied to build/ root)
│   ├── fonts/              ← self-hosted (fetched at build)
│   ├── textures/           ← planet textures (fetched at build)
│   ├── logos/              ← agency logos (fetched at build, Wikimedia Commons)
│   ├── images/missions/    ← build-time fetch (agency-first per ADR-046; Wikimedia + NASA fallback)
│   ├── images/rockets/     ← Wikimedia rocket reference photos
│   ├── diagrams/
│   │   ├── science/        ← 71 hand-coded SVGs (61 sections + 10 covers, ADR-035)
│   │   └── spacecraft/     ← 9 visiting-craft ANATOMY diagrams
│   ├── images/fleet-galleries/         ← per-fleet-entry hero + gallery (ADR-053)
│   ├── images/crew/                    ← per-flight crew portraits (ADR-053)
│   ├── data/               ← all app JSON: missions, fleet, i18n overlays, schemas, planets, porkchop, …
│   │   ├── missions/
│   │   │   ├── index.json  ← lightweight manifest (42 entries)
│   │   │   ├── mars/       ← base mission files (language-neutral) — `flight.interplanetary_profile` per ADR-058 third amendment
│   │   │   ├── moon/       ← Moon missions (incl. `flight.cislunar_profile` per ADR-058)
│   │   │   ├── ceres/ jupiter/ neptune/ pluto/  ← outer-system missions (`flight.interplanetary_profile`)
│   │   ├── fleet/          ← 137 entries × 9 categories (ADR-052; PRD-012 / RFC-016)
│   │   │   ├── index.json                    ← generated manifest (drives /fleet card grid)
│   │   │   ├── launcher/                     ← per-entry base files (language-neutral)
│   │   │   ├── crewed-spacecraft/
│   │   │   ├── cargo-spacecraft/
│   │   │   ├── station/  rover/  lander/  orbiter/  observatory/  space-suit/
│   │   ├── mars-traverses/ ← rover route polylines (Curiosity, Perseverance, Opportunity, Spirit)
│   │   ├── scenarios/      ← ORRERY-1 free-return + others
│   │   ├── science/        ← 10 tab folders × ~7 sections each (ADR-034); 85 sections total
│   │   ├── i18n/
│   │   │   ├── en-US/      ← English overlays (source language)
│   │   │   ├── es/  fr/  de/  pt-BR/  it/  nl/  ← Wave 1 locales (Latin)
│   │   │   ├── zh-CN/  ja/  ko/                ← Wave 2 (CJK, ADR-044)
│   │   │   └── hi/  ar/  ru/  sr-Cyrl/         ← Wave 3 (RTL + Devanagari + Cyrillic, ADR-043/045)
│   │   ├── schemas/                  ← 33 ajv schemas (mission, fleet, surface-site, science-section, provenance, …)
│   │   ├── porkchop/                 ← pre-computed grids (ADR-026 + ADR-028); 9 destinations
│   │   ├── image-provenance.json     ← per-image manifest (ADR-047, auto-generated)
│   │   ├── link-provenance.json      ← per-link manifest (ADR-051, auto-generated)
│   │   ├── license-waivers.json      ← image-license waivers (ADR-047)
│   │   ├── text-sources.json         ← per-text editorial provenance (ADR-047)
│   │   ├── source-logos.json         ← 28 publisher logo + license entries (ADR-047)
│   │   ├── iss-modules.json
│   │   ├── tiangong-modules.json
│   │   ├── moon-sites.json           ← surface sites (`fleet_refs` per ADR-052)
│   │   ├── mars-sites.json           ← surface sites (`fleet_refs` per ADR-052)
│   │   ├── earth-objects.json        ← satellites + observatories (`fleet_refs` per ADR-052)
│   │   ├── planets.json
│   │   └── rockets.json
│   └── .nojekyll           ← required for GitHub Pages
│
├── scripts/                            ← build-time pipelines (TA.md §pipelines documents all 10)
│   ├── fetch-assets.ts                  ← agency-first imagery fetch (ADR-046)
│   ├── build-image-provenance.ts        ← writes static/data/image-provenance.json + diff report (ADR-047)
│   ├── build-link-provenance.ts         ← writes static/data/link-provenance.json (ADR-051)
│   ├── check-learn-links.ts             ← outbound-link freshness gate (ADR-051 L-E)
│   ├── build-fleet-index.ts             ← writes static/data/fleet/index.json from per-category files (ADR-052)
│   ├── audit-fleet-heroes.ts            ← flags low-quality fleet heroes; output to docs/provenance/ (ADR-053)
│   ├── fix-fleet-heroes.ts              ← Wikipedia-API filename substitution helper (ADR-053)
│   ├── scaffold-fleet-entries.ts        ← one-time fleet entry scaffolder (archival)
│   ├── migrate-fleet-*.ts               ← one-time fleet migrations (archival; do not re-run)
│   ├── license-allowlist.ts             ← canonical license allowlist + normaliser (ADR-047)
│   ├── precompute-porkchops.ts          ← pre-computes 9 per-destination porkchop grids (ADR-026 + ADR-028)
│   ├── build-science-index.ts           ← Cmd-K search index + ?-chip vocabulary for /science
│   ├── validate-data.ts                 ← ajv validation + provenance + diagram integrity + symmetric fleet cross-refs
│   ├── validate-diagrams.ts             ← SVG integrity gate (ADR-035)
│   ├── build-tech-bom.ts                ← license audit of npm deps; writes docs/TECH-BOM.md
│   └── capture-screenshots.ts           ← Playwright-driven README + user-guide screenshot regeneration
│
├── tests/                  ← Playwright e2e tests
├── docs/                   ← all documentation
│
├── svelte.config.js
├── vite.config.ts
├── tsconfig.json
├── playwright.config.ts
└── .github/workflows/
    ├── ci.yml
    ├── docker-e2e.yml         # canonical Playwright gate + GHCR publish (ADR-071 supersedes ADR-066 trigger surface)
    ├── deploy-docs.yml        # docs site, CI-gated (ADR-070)
    ├── preview.yml            # full app+docs, docker-e2e-gated (ADR-070, retargeted by ADR-071)
    ├── deploy-prod.yml        # tailnet VPS deploy, manual (#260)
    ├── refresh-launches.yml   # cron — launches.json refresh
    ├── regen-snapshots.yml    # manual — visual-baseline regen
    └── release.yml            # tag → GitHub Release
```

---

## Audio narration — read before touching `src/lib/audio-*` or `scripts/audio/`

v0.7 ships an in-overlay narrated episode system (PRD-016 / RFC-019). en-US only — v0.8 adds the Anthropic translation pipeline + 12-locale Curator Tour.

- **Source of truth.** Episode scripts live in `content/episodes/<locale>/<episode-id>.md` (YAML frontmatter + SSML body). Voice ID map: `static/data/audio/voices.json`. Generated assets: `static/audio/<locale>/<persona>/<id>.<hash8>.{mp3,vtt,txt}` (content-addressed). Manifest: `static/data/audio/audio-provenance.json` (schema: `static/data/schemas/audio-provenance.schema.json`).
- **Pipeline triggers.** Operator-only: `npm run audio:generate -- --episode <id> [--locale en-US] [--provider google|elevenlabs]`. Cost ledger gates at $50/mo soft, $200/mo hard. `npm run audio:check-cost` is wired into `npm run preflight` so an over-cap state blocks pushes.
- **Runtime contract.** AudioOverlay reads the manifest via `src/lib/audio-registry.svelte.ts`. Adding/renaming an episode without regenerating provenance leaves it invisible to the runtime. The Curator Tour playlist + cue-banner stage hooks live in `src/lib/audio-tour.ts` — every id in `CURATOR_FULL_TOUR` and every key in `EPISODE_STAGES` MUST resolve to a provenance row (unit test enforces).
- **Transparency.** Every audio asset's text authorship + voice provider + tts_model + voice id surface on `/credits`. Provider/model/voice-id never elided.
- **Operator runbook:** [docs/guides/audio-pipeline-setup.md](docs/guides/audio-pipeline-setup.md). Adding a new provider: implement `TtsProvider`, list it in `PROVIDER_NAMES` + `PROVIDER_MODELS` (`scripts/audio/generate.ts`), add a voices.json key, update `ProviderName` in `src/lib/audio-types.ts`. Pipeline picks up the rest.

---

## i18n rules — follow these exactly

**UI strings:** never hardcode user-facing text in `.svelte` files. All UI strings go through Paraglide-js.

```typescript
import { t } from '$lib/i18n'
// correct
<button>{t('nav.fly')}</button>
// wrong
<button>FLY</button>
```

**Mission content:** base mission files (`static/data/missions/`) contain only language-neutral data. Editorial strings (name display, description, first-line, type label, CAPCOM event notes) live in locale overlay files (`static/data/i18n/[locale]/missions/`). The data client merges them at fetch time.

**Fallback:** always fall back to `en-US` for missing translations. Never show a translation key to the user.

---

## Data layer rules

All data access goes through `src/lib/data.ts`. Never `fetch` a JSON file directly.

```typescript
import { getMissionIndex, getMission, planets } from '$lib/data'

const missions = await getMissionIndex()              // card grid
const mission  = await getMission('curiosity','mars') // detail panel
```

Base mission files contain: `id`, `agency`, `dest`, `status`, `year`, `sector`, `color`, `departure_date`, `arrival_date`, `transit_days`, `vehicle`, `payload`, `delta_v`, `data_quality`, `credit`, `links`, `flight` (per ADR-027 — includes optional `flight.cislunar_profile` for Moon missions per ADR-058), `fleet_refs[]` (forward pointer to fleet entries per ADR-052).

Locale overlay files add: `name`, `description`, `first`, `type`, `events[].note`.

Fleet entries, surface sites, and other localised records follow the same base + overlay pattern. Full contract shapes live in `docs/adr/TA.md` §contracts and in `static/data/schemas/`. For fleet specifically: bidirectional `fleet_refs` ↔ `linked_missions`/`linked_sites` is enforced by the symmetric-link validator (ADR-052).

**NON-NEGOTIABLE — overlay-completeness rule.** When you add a new ID to any base-data registry, you MUST create the matching en-US overlay file in the same commit:

| Base registry | Required en-US overlay |
|---|---|
| `static/data/earth-objects.json` (any new id) | `static/data/i18n/en-US/earth-objects/{id}.json` |
| `static/data/fleet/index.json` (any new id) | `static/data/fleet/{category}/{id}.json` + `static/data/i18n/en-US/fleet/{category}/{id}.json` |
| `static/data/moon-sites.json` (any new id) | `static/data/i18n/en-US/moon-sites/{id}.json` |
| `static/data/mars-sites.json` (any new id) | `static/data/i18n/en-US/mars-sites/{id}.json` |
| `static/data/science/{tab}/_index.json` (any new id) | `static/data/i18n/en-US/science/{tab}/{id}.json` + `static/data/science/{tab}/{id}.json` |
| `static/data/iss-modules.json` / `static/data/tiangong-modules.json` (any new id) | `static/data/i18n/en-US/{file}/{id}.json` |
| `static/data/launches.json` (any new id) | (no overlay required — schema is monolingual) |

`validate-data` enforces this at preflight (and pre-push) — missing overlays will fail before push. Other locales fall back to en-US, so en-US alone is enough to ship; translations follow in a separate commit per the i18n pipeline. **History note:** GH #83 (May 2026) shipped 11 constellation entries without overlays, causing CI e2e failures + a follow-up fix commit. Layer 1 validator (added that same day) prevents recurrence.

---

## Mobile-first rules

Design at 375px first. Desktop is progressive enhancement.

```css
/* correct — mobile base, desktop enhancement */
.panel { position: fixed; bottom: 0; width: 100%; }
@media (min-width: 768px) { .panel { right: 0; width: 314px; top: 52px; bottom: 0; } }

/* wrong — desktop base, mobile override */
.panel { position: fixed; right: 0; width: 314px; }
@media (max-width: 767px) { .panel { bottom: 0; width: 100%; } }
```

Touch targets: minimum 44×44px. Three.js screens: single-finger orbit, two-finger zoom. Bottom sheet dismisses with swipe-down.

---

## Physics — do not change without ADR

All orbital mechanics use Keplerian two-body formulation. Constants from IAU:

```typescript
const MU_SUN      = 4 * Math.PI ** 2  // AU³/yr²
const AU_TO_KM    = 149597870.7        // IAU 2012
const AU_TO_LMIN  = 8.317
const AUPYR_TO_KMS = 4.7404

function keplerPos(a: number, e: number, L0: number, T: number, t: number) {
  const nu = L0 + (2 * Math.PI / T) * t
  const r  = a * (1 - e*e) / (1 + e * Math.cos(nu))
  return { x: Math.cos(nu) * r, y: Math.sin(nu) * r, r }
}

function visViva(a: number, r: number): number {
  return Math.sqrt(MU_SUN * (2/r - 1/a)) * AUPYR_TO_KMS
}
```

Transfer arc: Keplerian half-ellipses, not Bezier. Do not replace. 3D scene units: AU. Do not mix pixel scale.

---

## Debugging — `?debug=1` is the in-app inspector

Every route surfaces a built-in DebugPanel when you append `?debug=1` to the URL (e.g. `/fly?debug=1`, `/mars?debug=1`, `/?debug=1`). Mounted from the root layout (`src/routes/+layout.svelte`) via Svelte context, so it's available on every page. Use it instead of bolting on ad-hoc `console.log` calls or one-off panels.

Tabs:

- **Page** — page-specific instrumentation. Only shown when the route registered content (today: `/fly` exposes the 2D `FlybyDebugViewer` for camera-math iteration). Add this tab to a page when you're solving a hard visual / spatial / interaction problem that's faster to debug against a derived 2D / numeric view than in the live 3D scene.
- **Perf** — live FPS + frame time. Use when you're investigating perceived jank or a quality-tier downgrade. Stub for rolling avg / low-1% — extend it when needed rather than spinning up an external profiler for routine work.
- **i18n** — current locale + (stub) key-resolution warnings. Extend when triaging translation regressions.
- **Route** — `pathname` / `search` / `hash`. Useful when chasing a routing or deep-link bug.

Wiring a page-specific tab:

```svelte
<!-- in your page -->
<script lang="ts">
  import DebugPanelRegistrar from '$lib/components/DebugPanelRegistrar.svelte';
  // ...
</script>

<!-- label-only (header shows "DEBUG · MARS", no Page tab) -->
<DebugPanelRegistrar label="MARS" />

<!-- with a Page-tab snippet (e.g. /fly + FlybyDebugViewer) -->
{#snippet pageDebugContent()}
  <MyPageInspector ... />
{/snippet}
<DebugPanelRegistrar label="FLY" content={pageDebugContent} />
```

The registrar handles cleanup on navigation — no stale labels leak across routes. Context lives in `src/lib/components/debug-panel-context.ts`; panel in `src/lib/components/DebugPanel.svelte`.

**Use this proactively.** When you hit a visual or timing problem that's hard to reason about in the live scene — camera math, spatial composition, animation phase, perf jank, locale bleed, deep-link state — your first move should be: can I add a Page tab here, or extend Perf/i18n/Route with the signal I need? Expand the panel's stubs (perf rolling avg, i18n missing-key list, route history) as you fix issues rather than reading them in isolation. A growing debug surface is the whole point — each iteration teaches the next agent how the system actually behaves.

Generic pages (no `DebugPanelRegistrar`) still show Perf / i18n / Route — you don't have to opt in to get the baseline.

---

## Testing rules

**Unit tests** (Vitest, colocated): every function in `src/lib/orbital.ts` must have tests. Physics functions are the highest-priority testing surface.

```typescript
// src/lib/orbital.test.ts
it('Earth at 1 AU ≈ 29.78 km/s', () =>
  expect(visViva(1.0, 1.0)).toBeCloseTo(29.78, 1))
```

**E2e tests** (Playwright, in `tests/`): smoke covers every primary route load without console errors; dedicated specs exercise deeper flows per screen where needed.

---

## Design system — do not change without UXS update

```
Background:    #04040c
Accent blue:   #4466ff
Teal:          #4ecdc4
Mars red:      #c1440e
Earth blue:    #4b9cd3
Gold:          #ffc850

font-display:   'Bebas Neue'    titles, names
font-mono:      'Space Mono'    data, labels, HUD
font-editorial: 'Crimson Pro'   descriptions (always italic)

Nav bar:        height 52px, z-index 20
Panel (mobile): bottom sheet, full width
Panel (desktop): right drawer, 314px wide
Touch targets:  min 44×44px
```

Three.js r128 only. `THREE.CapsuleGeometry` does not exist in r128.

---

## CI — what runs on every PR

```
typecheck   → npm run typecheck (i18n:compile + svelte-kit sync + svelte-check)
lint        → npm run lint (prettier --check . && eslint .)
test        → npm run test (vitest run)
validate    → npm run validate-data (ajv + consistency checks on JSON under static/data/)
build       → npm run build (i18n:compile + validate-data + precompute-porkchops + vite build)
precompute  → npm run precompute-porkchops (9 porkchop grids; chained into build)
doc-check   → grep checks from guide §18
```

E2e (Playwright) runs on push to `main`, not on every PR.

### Before pushing — `npm run preflight`

Mirrors CI step-for-step locally. Runs typecheck → lint → test → validate-data → build. **If preflight passes, push is safe; if it fails, do not push.** A `.husky/pre-push` hook auto-runs it on `git push` and blocks the push on failure (use `git push --no-verify` only when explicitly intended).

Hooks self-activate after `npm install` via the `prepare` script (`git config core.hooksPath .husky`). No new dependencies — `.husky/pre-push` is a plain bash script.

> **Concurrency lock — parallel agents in the same checkout.** `npm run preflight` is wrapped by `scripts/with-lock.mjs` so two simultaneous invocations (e.g. two agents working the same branch) serialize instead of racing the `.svelte-kit/output` rimraf at build start. The second caller prints the offender's pid + command and polls every 2 s; lock auto-clears after 30 min if a process crashed mid-run. Coverage is `npm run preflight` only — direct `npx vitest`, `npx playwright test`, and raw `vite build` are NOT locked, so prefer the npm script for anything that touches the build output. If you need to lock another command, the wrapper takes any child: `node scripts/with-lock.mjs <name> -- <cmd> [args...]`.

> **Caveat — `tsc --noEmit` ≠ svelte-check:** `tsc` only type-checks `.ts` files. CI uses `svelte-check`, which type-checks `.svelte` content too. Use `npm run typecheck` (which calls svelte-check) when validating Svelte component changes. Errors like "Property X does not exist on type Y" inside a `.svelte` file will only surface via svelte-check.

> **Caveat — preflight does NOT run e2e.** Preflight covers typecheck / lint / unit / validate / build, but the Playwright e2e suite only runs on push-to-main in CI. Routine PR pushes may pass preflight and still break e2e. For tag / release readiness, see the next section.

> **Optional smoke layer — `PREFLIGHT_INCLUDE_SMOKE=1` (GH #83 follow-up).** The pre-push hook will additionally run `landing.spec.ts` + `smoke.spec.ts` (desktop-chromium, ~30-60s) when this env var is set. Catches runtime route 404s that preflight cannot see (e.g. missing i18n overlays). Recommended when your tree change touches `/earth`, `/moon`, `/mars`, or `/fleet` data files; not needed for typical refactors. Toggle:
> ```bash
> PREFLIGHT_INCLUDE_SMOKE=1 git push
> ```

> **Layer 1 — overlay-completeness check (also GH #83 follow-up).** `validate-data` now verifies every ID in earth-objects / fleet-index / moon-sites / mars-sites / science _index has a matching `i18n/en-US/...` overlay. Missing overlays fail validate-data → fail preflight → block push. This closes the exact gap that caused the #83 e2e regression. See the data-layer "overlay-completeness rule" above.

---

### Before tagging or releasing — full local e2e on BOTH projects

**The pre-push hook is not enough to ship a release.** It runs preflight, which excludes e2e. The CI e2e gate is what holds the auto-deploy chain (`ci.yml` → `docker-e2e.yml` → `preview.yml`) together (per ADR-071); if docker-e2e is red on the tagged commit, the GH Pages deploy never fires and shipping turns into a CI ping-pong.

**Rule: before moving a tag or cutting a GitHub Release, run the full e2e suite locally against both viewports until both are clean.**

```bash
# Two viewports (desktop-chromium + mobile-chromium) — both must be green.
npm run test:e2e -- --workers=1                  # all specs, both projects
# Or while iterating on a subset:
npx playwright test --workers=1 --project=mobile-chromium tests/e2e/i18n-de.spec.ts ...
```

**Why `--workers=1`:** the vite preview server is shared across workers. With the default 2 local workers, concurrent rAF + canvas tests destabilise the preview server enough that it sometimes crashes mid-run (`net::ERR_CONNECTION_REFUSED` on subsequent tests). Single worker is slower (~3 min for the full suite) but deterministic. CI already uses one worker; matching it locally also matches CI failure modes.

**Why BOTH projects:** desktop-chromium and mobile-chromium hit different viewport breakpoints (≤640 px collapses the nav into the hamburger drawer, the science rail loses its Search button, /fly HUD collapses, etc.). The mobile project catches the layout regressions desktop can't see. Skipping mobile is how the v0.6.0 → v0.6.1 release cycle ended up with 60+ mobile failures discovered post-tag.

**Visual regression baselines (`tests/e2e/visual.spec.ts`):** baselines are committed as `*-darwin.png` (maintainer's local machine) AND `*-linux.png` (CI runner). Each platform pair must stay in lockstep. Local darwin runs use the darwin baselines; CI runs use the linux baselines.

**When to regenerate linux baselines (NON-NEGOTIABLE):** any change that affects the rendered DOM under the watched selectors — `section.credits > header.head` on `/credits` and `main / .science-page / nav.tabs / body` on `/science` — must be followed by a manual trigger of the regen workflow BEFORE pushing:

```bash
gh workflow run "Regenerate visual snapshots" --ref <branch>
```

The bot regenerates the four linux baselines (credits-head + science-tabs × desktop + mobile) on a linux CI runner and commits them back to the branch. CI e2e will fail on push if you skip this step and changed the layout — that's the system working. **History note:** the visual:69 + science-tabs failures of 2026-05-25 were caused by parallel /credits + /science layout work that didn't queue the regen workflow. ADR-069 follow-up: AGENTS.md now flags this rule. See `docs/guides/visual-regression-baselines.md` for the full lifecycle.

**Pre-tag dry run checklist:**

1. `npm run preflight` — green
2. `npm run test:e2e -- --workers=1` — both projects green (or known-broken specs explicitly skipped with a comment)
3. `git push` — pre-push hook runs preflight again, must pass
4. Push completes — wait for CI + e2e workflows on main, confirm both green
5. Only then move the tag / cut the GitHub Release

**Order of operations when something is broken on CI but green locally:** trust CI. The CI environment is Ubuntu, runs in Docker, uses 1 worker, and the install / build / preview path can drift from the local setup. Reproduce locally with `--workers=1` and the latest `npm ci` before debugging.

---

### No fix-and-pray on CI — local reproduction is mandatory

**Rule: when CI e2e fails, the next step is `npx playwright test --workers=1 --project=<failing-project> <failing-spec>` locally — not a speculative patch pushed straight to CI.** Push only after the failure reproduces locally AND the fix makes the local run green. Every speculative push pollutes the workflow history, wastes 15-40 min of CI time, races the launches-bot cron (which auto-cancels in-flight runs), and burns runner-minutes for no information gain — CI tells you "still red" but not "why a different way".

**The expected loop is:**

1. Pull the failing test name + error-context.md from the CI artifact (`gh run view <id> --log` → find the `>` line + locator + timeout).
2. Run that exact spec locally on the failing project: `npx playwright test --workers=1 --project=mobile-chromium tests/e2e/<spec>.ts`. If it doesn't reproduce, raise that explicitly — don't guess at fixes for failures you can't see.
3. Iterate the fix until the local run is green. Re-run 2-3 times to confirm the fix isn't itself flaky.
4. Run the broader spec set the change touches (e.g. all of `explore.spec.ts moon.spec.ts mars.spec.ts` if the fix is cross-cutting).
5. *Then* push. The CI run becomes the final verification, not the debugging tool.

**Push-and-wait-for-CI is a debugging anti-pattern.** Each iteration costs at least 25 min wall-clock vs. ~2 min for a single local spec. The maintainer (Marko) has flagged this explicitly: deliberate, precise, expected — not "let's see what CI says".

**When to escape this rule (rare):** the failure depends on a CI-only condition that genuinely can't be reproduced locally — Ubuntu+Docker filesystem case-sensitivity, runner network latency, GH Actions concurrency racing the launches-bot cron. In those cases, say so out loud, and instrument the push (e.g. add a CI-only debug log) so the next CI run yields new information. "Let's try this and see" is not in scope.

**Stale-monitor caveat:** when a CI run shows `cancelled` from a successor push, that's the auto-supersede behaviour, not a real cancel — confirm by checking whether a newer run exists on a newer sha. Don't treat supersede-cancellations as either pass or fail; just re-arm the monitor on the live run.

---

### Spec-writing patterns — viewport-aware, locale-resilient

E2e tests must run identically on desktop-chromium and mobile-chromium. Most regressions in this codebase land because a spec was written for the desktop layout and silently failed on mobile-chromium for months until a release exposed it. Follow these patterns:

**1. Use viewport-aware navigation helpers, not raw `nav a.link` selectors.**

The desktop nav strip (`<nav .center a.link>`) is `display: none` on ≤640 px viewports; the hamburger drawer (`button.menu-toggle` → `<a.drawer-link>`) takes over. Helpers in `tests/e2e/_helpers/nav.ts`:

```ts
import { clickNavLink, localeChip } from './_helpers/nav';
await clickNavLink(page, '/missions');   // opens drawer first on mobile
await expect(localeChip(page).first()).toContainText('DE');
```

Never write `await page.locator('nav a.link[href*="/missions"]').first().click()` — it works on desktop and silently fails on mobile.

**2. Prefer `html[lang]` over body-text translation tokens for locale assertions.**

```ts
// ✓ Authoritative, viewport-agnostic, set by src/lib/locale.ts on hydration.
await expect(page.locator('html')).toHaveAttribute('lang', 'es');

// ✗ Fragile — body text often only exists as a nav link (display:none on mobile).
await expect(page.getByText('NUESTRO SISTEMA SOLAR').first()).toBeVisible();
```

Combine `html[lang]` + chip + URL preservation as the three locale assertions. They cover Paraglide load, locale-picker state, and URL canonicalisation respectively, and all three survive viewport breakpoints.

**3. Scope chip locators to the locale picker.**

`button.chip` collides with filter chips on `/fly`, `/missions`, `/fleet`. Use `[data-locale-picker] button.chip` (already wrapped in the `localeChip(page)` helper) — never bare `button.chip.first()`.

**4. Use the readiness signals from ADR-056, not magic sleeps.**

`window.__pickAt(x, y)` / `data-route-ready` / `data-loading` are the deterministic signals. `waitForTimeout(N)` will eventually flake on CI under load.

**5. Mobile-only `test.skip()` blocks need a comment explaining why.**

```ts
test.describe('/science Cmd-K search', () => {
  test.skip(({ viewport }) => (viewport?.width ?? 1280) < 700, 'desktop-only affordance');
  // ...
});
```

The Search button is `display:none` on mobile (rail collapses). Skipping is correct; not skipping flakes both attempts. Always include the *why* in the skip reason so a future reader doesn't restore the test.

**6. Hydration timing differs by viewport.**

Pixel-5 mobile takes 2–4× longer than desktop for canvas / WebGL routes to populate live data (sites, missions, satellites). Either bump the timeout to 30 s (`{ timeout: 30_000 }`) or assert on a static-render attribute that doesn't require live data. Don't assume desktop-style 5-second timeouts work on mobile.

---

### GitHub Release ≠ git tag

`git tag vX.Y.Z` + `git push --tags` creates a tag. It does NOT create a GitHub Release. The releases page (`gh release list`) is a separate API entity that surfaces the version on the project's GitHub homepage and feeds release-notes RSS / GitHub notification fan-out.

After tagging, also run:

```bash
gh release create vX.Y.Z --title "vX.Y.Z — short headline" --notes-file /tmp/release-body.md
```

Where the body comes from the matching `## [X.Y.Z]` section in `CHANGELOG.md` (extracted with `awk '/^## \[X\.Y\.Z\]/{flag=1;next} /^## \[/{flag=0} flag' CHANGELOG.md > /tmp/release-body.md`).

**Three ways to publish v0.6.1, only one is the full release:**

| Action | What it does | What it doesn't do |
|---|---|---|
| `git tag v0.6.1` + `git push --tags` | Tag exists; gh sees it; CI deploy chain MAY fire | No GH Release entry; no release notes; no notification |
| `gh release create v0.6.1 …` | Creates the Release entry tied to the tag | Doesn't trigger Pages deploy; doesn't move the tag |
| `gh workflow run "Deploy preview" --ref main` | Manually publishes the live site from current main | Doesn't tag; doesn't create a Release |

All three steps are needed for a complete release: tag + GH Release + deploy. The deploy chain auto-fires from a push-to-main IF the CI + e2e workflows pass; if either is red, use `workflow_dispatch` to force the deploy.

---

### Pre-push hook quirks

- **`validate-data` scopes its PRD/RFC/ADR gating-sentence check to `git ls-files`** (issue #136). Untracked drafts in `docs/prd/` or `docs/rfc/` no longer block `git push`; staged-but-uncommitted files still get gated. If you want a draft to be checked, stage it. If `git` isn't available (CI shallow-clone edge case), the check falls back to the filesystem walk so the gate still enforces on tracked files.
- **`prettier --check` exit code is honoured, but its prose can be filtered.** Some terminal contexts (specifically Claude Code) rewrite Prettier's `[warn] path/to/file.ts` to a reassuring `Prettier: All files formatted correctly` while still returning exit code 1. Trust the exit code, not the prose. When output looks clean but a script exited non-zero, re-run with `/usr/bin/env bash -c '<cmd> 2>&1; echo EXIT=$?'`.

---

## Documentation system

Reading order for any non-trivial task:

1. **`docs/adr/TA.md`** — single-page architecture map. Start here for any task that crosses one file. v2.0 covers every route, subsystem, 3D scene, asset pipeline, contract, and constraint.
2. `docs/adr/` — locked decisions (the why + alternatives).
3. `docs/rfc/` — RFCs in flight (open architectural questions).
4. `docs/prd/` — product specs (the user-value argument + V1 scope).
5. `docs/uxs/` — UX specifications.
6. `docs/guides/i18n-style-guide.md` — per-language translation conventions (binding per ADR-033).
7. `docs/guides/docker-stack.md` — local `docker compose` stack (web nginx + on-demand pipeline runners, RFC-024 / ADR-063-066). For exercising the production-shape artefact locally, running data pipelines without host gdal, or understanding the docker-e2e CI gate.
8. `docs/guides/observability.md` — Sentry (client-side JS errors) + Grafana Cloud Agent (docker logs), both env-var-gated and silent by default, RFC-025 / ADR-067-068. For setting up the operator accounts, populating env vars, verifying silence in local dev, and importing the dashboards.

When code and TA.md / ADRs disagree, one is wrong. Fix the wrong one. Do not tolerate divergence.

---

## What not to do

- Do not hardcode UI strings — use Paraglide-js
- Do not put editorial content in base mission / fleet / site JSON files — use locale overlays (ADR-017, ADR-054)
- Do not fetch data directly — use `src/lib/data.ts`
- Do not add outbound LEARN links without re-running `npm run build-link-provenance` — every link must have a provenance row (ADR-051)
- Do not link to Wikipedia as the *only* source on a non-US entity — the operator's own page must be the first `intro` link (ADR-051)
- Do not run Lambert solver on main thread
- Do not change physics constants without ADR
- Do not design desktop-first
- Do not use `any` in TypeScript without justification
- Do not add npm dependencies without ADR
- Do not use `localStorage` or `sessionStorage`. Cookies are also forbidden for user preferences EXCEPT the single narrowly-scoped `orrery_locale` cookie permitted by ADR-057 (explicit user-set locale override only — auto-detect, Science Lens, mission filters, and any other state stay runtime-only). Any new cookie requires its own ADR.
- Do not use `THREE.CapsuleGeometry` (not in r128)
- Do not use `console.log` in production code
- **NON-NEGOTIABLE — every committed image must end up on `/credits`.** No matter how the image got there (manual download, Wikipedia REST, Open Library API, podcast RSS, YouTube avatar, hand-authored SVG, agency-direct fetch), there has to be a path from the file on disk to a row on `/credits` via `static/data/image-provenance.json`. The same rule applies to LEARN links (must end up on `/library` via `link-provenance.json`) and to source-logos / text fragments (`source-logos.json` / `text-sources.json`). If you add an image and it doesn't appear on `/credits` after `npm run build-image-provenance`, the work is not done — extend the script with a new walker, or register the source in the appropriate map in `scripts/build-image-provenance.ts`. See ADR-046 / ADR-047 / ADR-051. New license short names must land in `scripts/license-allowlist.ts` or be waived in `static/data/license-waivers.json`.
- Do not introduce `waitForTimeout(<magic>)` in Playwright tests — use a deterministic readiness signal (`window.__pickAt`, `data-route-ready`, `data-loading`, `expect(...).toHave...`). Brittle on slow CI. See ADR-056.
- Do not call `console.error` from production code paths the user sees — pipe through a centralised handler instead, so we don't pollute Sentry-style error feeds when added.
- Do not add a fleet entry without bidirectional `fleet_refs` ↔ `linked_missions` / `linked_sites` pointers — the symmetric-link validator in `validate-data.ts` will fail closed. See ADR-052.
- Do not include artist's-impression imagery for vehicles that exist or existed. Planned-only vehicles carry an explicit `artistic-impression: true` waiver flag. See ADR-046, ADR-053.
- Do not generate science / fleet / station / spacecraft SVG diagrams via AI tools — every diagram is hand-authored and the SVG file *is* the committed source. See ADR-035, ADR-053.
- Do not introduce a new 3D model builder ad-hoc — follow the per-mission pattern in `src/lib/earth-satellite-models.ts` (orbiters) or `src/lib/moon-lander-models.ts` (surface) and add it to the BUILDERS dispatch + tests.
- Do not bypass the `flight.cislunar_profile` contract on Moon missions — `/fly` reads it via `cislunar-geometry.ts` to render the Earth-centered second camera. See ADR-058.

---

*Orrery · AGENTS.md · May 2026 · v0.6.0 · paired with [TA.md v2.0](docs/adr/TA.md) — update both when locked decisions change*
