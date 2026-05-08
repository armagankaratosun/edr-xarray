# edr-xarray: Generic OGC EDR 1.1 xarray Backend

## TL;DR

> **Quick Summary**: Build a Python package `edr-xarray` that registers an xarray backend (`engine="edr"`) lazily exposing OGC API - Environmental Data Retrieval (EDR) 1.1 compliant servers as `xarray.Dataset` objects. v1 supports `/cubes` queries consuming CoverageJSON only. Designed to be subclassed by downstream packages (e.g. future `xarray-firecube`).
>
> **Deliverables**:
> - PyPI-publishable package `edr-xarray` (module name `edr_xarray`)
> - `engine="edr"` registered via `xarray.backends` entry point
> - Lazy fetch through `EdrBackendArray._raw_indexing_method` translating xarray slice keys → EDR cube subset queries
> - Dask integration via `encoding["preferred_chunks"]`; pickle-safe via `__getstate__/__setstate__`
> - Documented subclass hooks (`_build_cube_url`, `_negotiate_output_format`, `_parse_collection_metadata`, `_parse_coveragejson`, `_translate_indexer`, `_request`, `_discover_axes`)
> - TDD test suite using `pytest-httpserver`; opt-in live integration test against firecube
> - README with usage examples; CI workflow running ruff + mypy + pytest
>
> **Estimated Effort**: Large
> **Parallel Execution**: YES — 6 waves
> **Critical Path**: T1 → T9 → T11 → T12 → T13 → T14 → T15-T19 → F1-F4

---

## Context

### Original Request
User wants to write a custom xarray backend for OGC API - EDR. Primary interest: the `/cubes` endpoint to expose remote data cubes (Zarr or otherwise) as `xarray.Dataset`. Reference points provided: (a) the EDR Swagger spec, (b) xarray's "How to add new backend" docs, (c) tensogram-xarray as an existing implementation, and (d) a local EDR-compliant server `firecube-backend` for testing.

User explicitly clarified mid-interview: **the package must be EDR-spec generic**. firecube-specific quirks (`refresh` parameter, `/cube/series` extension, "single-instance only" collection-level cube) belong in a future separate `xarray-firecube` package that **subclasses** this one. firecube is the test target, not the platform.

### Interview Summary

**Key Discussions** (decisions made via the Question tool):
- v1 query types: **/cubes only** — position/area/trajectory/etc. deferred to future versions.
- v1 response format: **CoverageJSON only** — GeoJSON / NetCDF passthrough deferred.
- User-facing URL: **collection URL is the identifier** (`https://server/collections/{id}`), with optional `instance="..."` kwarg for `/instances/{instId}` path.
- Lazy strategy: **lazy fetch on `.compute()`/`.values`** — `open_dataset` returns metadata only.
- Dask: **yes via `preferred_chunks`** — pickle-safe via `__getstate__`/`__setstate__` dropping session.
- Auth: **inject pre-configured `httpx.Client`** via `session=` kwarg (one mechanism covers all auth styles).
- Extensibility: **explicit named hook methods** on `EdrDataStore` for subclasses.
- Tests: **TDD with `pytest-httpserver`** mock + opt-in live firecube smoke test.
- Tooling: **uv + Python ≥ 3.11 + httpx + ruff + mypy + Apache-2.0**.
- Coord discovery: **configurable via `discovery=` kwarg** (default `"probe"`, with `"metadata_only"` and `"strict"` modes).
- Vertical (`z`): **basic support** — accept scalar `z=500` and range `z=lo/hi`; reject exotic forms (`R14/.../...`, multi-level lists).

**Research Findings**:
- **firecube** (the live test target) advertises CoverageJSON for Zarr cubes, runs FastAPI on `:8000`, sample collection `msg_frm` with instance `f024`. No auth required.
- **tensogram-xarray pattern** maps almost 1:1: `BackendEntrypoint` → `DataStore` (orchestrator with shared HTTP session) → `BackendArray` (lazy fetch via `_raw_indexing_method`) → `LazilyIndexedArray` → `Variable` → `Dataset` + `set_close()`.
- **xarray contract**: `BackendEntrypoint.open_dataset()` mandatory; `IndexingSupport.BASIC` is the right level for EDR (slice + int only); `encoding["preferred_chunks"]` is how Dask integration happens; entry point goes in `pyproject.toml [project.entry-points."xarray.backends"]`.
- **EDR spec**: cube endpoint must be discovered from `data_queries.cube.link.href`; `parameter_names` lists variables with unit (UCUM URI), observedProperty (NERC URI), and measurementType. CoverageJSON `range.{axisNames, shape, values}` maps directly to numpy.

### Metis Review

Metis identified 10 critical gaps and recommended specific guardrails. All resolved:

| Gap | Resolution |
|---|---|
| Cube endpoint discovery rule | **MUST use `data_queries.cube.link.href`**; if missing, raise `EdrMetadataError`. No fallback to `<collection>/cube`. |
| `parameter_names=None` policy | **Expose all advertised parameters** (ergonomic, spec-reliable). |
| BBOX convention | **User input always `(lon_min, lat_min, lon_max, lat_max)`** in CRS84 axis order; backend handles server CRS translation. |
| `/conformance` check | **No automatic check** (trust collection metadata; subclass can add via `_check_conformance` hook later). |
| Squeeze singleton dims | **No** — preserve dimensions always. |
| CoverageJSON support | **Only `domainType="Grid"` with flat `range.values`**. Reject TiledNdArray, PointSeries, Trajectory, VerticalProfile with `EdrUnsupportedFeatureError`. |
| Datetime parsing | **Accept ISO 8601 string only** (instant or `start/end`). Reject `../end`, `start/..`, date-only, naive — pass through after light validation. |
| Antimeridian bbox | **Reject in v1** with clear error. |
| z support | **Basic only** — scalar or `lo/hi` range. Reject `R14/.../...` and multi-level lists. |
| Coord discovery | **Configurable** via `discovery=` kwarg (`"probe"` default). |
| Custom exceptions | **Hierarchy**: `EdrXarrayError` (base) → `EdrServerError`, `EdrUnsupportedFeatureError`, `EdrMetadataError`, `EdrCoverageJsonError`, `EdrConformanceError`. |
| Session lifecycle | **Owned** internal session: closed on `ds.close()`. **Injected** session: never closed by us. Track via `_owns_session: bool` flag. |
| HTTP errors | Wrap into `EdrServerError`, preserve original via `raise ... from exc`. Never swallow. |

---

## Work Objectives

### Core Objective
Deliver a working, tested, documented Python package `edr-xarray` that provides a generic `engine="edr"` xarray backend for OGC EDR 1.1 servers. The backend must be lazy, Dask-friendly, pickle-safe, and explicitly subclassable so downstream server-specific packages can extend behavior cleanly.

### Concrete Deliverables
1. **Repository layout** with `pyproject.toml`, `LICENSE` (Apache-2.0), `README.md`, `.gitignore`, `.python-version`, `src/edr_xarray/`, `tests/`.
2. **Source modules** under `src/edr_xarray/`:
   - `__init__.py` — public exports (`EdrBackendEntrypoint`, `EdrDataStore`, `EdrBackendArray`, exceptions)
   - `errors.py` — exception hierarchy
   - `coveragejson.py` — typed parser for CoverageJSON Grid responses
   - `metadata.py` — typed parser for EDR collection metadata
   - `query.py` — query parameter encoders (bbox, datetime, z, parameter-name) + validators
   - `indexer.py` — translate xarray ExplicitIndexer key → EDR query params
   - `transport.py` — `httpx.Client` wrapper with error mapping + session ownership
   - `discovery.py` — coord-axis discovery strategies (probe, metadata_only, strict)
   - `builder.py` — build `xr.Variable` and `Coordinates` from parsed metadata + axes
   - `array.py` — `EdrBackendArray(BackendArray)` with `__getitem__` + pickle support
   - `store.py` — `EdrDataStore` orchestrator with documented subclass hooks
   - `backend.py` — `EdrBackendEntrypoint(BackendEntrypoint)`
3. **Test suite** under `tests/`:
   - `conftest.py` — `pytest-httpserver` fixture, sample CoverageJSON & metadata loaders
   - per-module unit tests
   - `test_integration_full_flow.py` — end-to-end open + lazy-fetch + index
   - `test_lazy_semantics.py` — verify metadata-only on open, cube fetch only on access
   - `test_pickle_dask.py` — `__getstate__/__setstate__` round-trip + Dask compute
   - `test_subclass_extensibility.py` — verify each documented hook is overridable
   - `test_live_firecube.py` — opt-in `@pytest.mark.live` against firecube
   - `tests/data/` — fixture JSON files
4. **CI** at `.github/workflows/ci.yml` running ruff + mypy + pytest on Python 3.11/3.12.
5. **Documentation**:
   - `README.md` with installation, basic usage, subclassing example, supported feature matrix.
   - Module docstrings on every public class/function.

### Definition of Done
- [ ] `uv build` produces a wheel.
- [ ] `uv run pytest` passes (≥ 95% coverage on `src/edr_xarray/`).
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests` clean.
- [ ] `uv run mypy --strict src/edr_xarray` clean.
- [ ] `uv run python -c "import xarray as xr; assert 'edr' in xr.backends.list_engines(); print('ok')"` prints `ok`.
- [ ] Demo end-to-end script works against running firecube on `localhost:8000` (opt-in).
- [ ] Every Final Verification F1-F4 verdict = APPROVE.

### Must Have
- `engine="edr"` registered and discoverable.
- `xr.open_dataset(collection_url, engine="edr", ...)` returns a Dataset whose `.values`/`.compute()` actually fetches data via EDR `/cube` queries.
- Cube endpoint URL discovered from `data_queries.cube.link.href` (never assumed).
- All documented subclass hooks (`_build_cube_url`, `_negotiate_output_format`, `_parse_collection_metadata`, `_parse_coveragejson`, `_translate_indexer`, `_request`, `_discover_axes`) overridable by subclasses and verified by tests.
- CoverageJSON `axisNames` honored (no silent transposition).
- `null` in CoverageJSON values → NaN when `mask_and_scale=True`.
- `instance=` kwarg supported when collection advertises instances.
- `bbox`, `datetime`, `parameter_names`, `crs`, `z`, `session`, `discovery` kwargs supported.
- Custom exception hierarchy with `raise ... from exc` for HTTP errors.
- Session ownership rule enforced.
- `__getstate__/__setstate__` on `EdrBackendArray` drops session for pickle safety.
- `encoding["preferred_chunks"]` set on every Variable for Dask integration.
- TDD: every implementation task has a failing test written first, then minimal code to pass.
- Agent-Executed QA Scenarios on every task with concrete commands, expected outputs, and evidence files.

### Must NOT Have (Guardrails)

**Spec-fidelity guardrails (from user direction & Metis):**
- ❌ NO firecube-specific behavior in `edr-xarray` source. No `refresh`, `/cube/series`, hardcoded `localhost:8000`, single-instance assumption.
- ❌ NO assumption that `<collection_url>/cube` is the cube URL — always read from metadata.
- ❌ NO non-cube query types (position/area/radius/trajectory/corridor/items/locations).
- ❌ NO non-CoverageJSON parsing (GeoJSON/NetCDF/Zarr/CSV/etc.).
- ❌ NO TiledNdArray / non-Grid CoverageJSON domain types.
- ❌ NO automatic `/conformance` check on open.
- ❌ NO antimeridian-crossing bbox handling.
- ❌ NO exotic z grammar (`R14/.../...`, multi-level lists).

**Lazy-semantics guardrails (Metis):**
- ❌ NO cube data fetch during `open_dataset` (only metadata + at most one probe per `discovery="probe"` mode).
- ❌ NO eager materialization of arrays in `__init__`; data MUST flow through `_raw_indexing_method`.
- ❌ NO swallowing `httpx` exceptions — wrap into `EdrServerError` with `raise ... from exc`.

**AI-slop guardrails:**
- ❌ NO broad `except Exception: pass` blocks anywhere.
- ❌ NO generic variable names (`data`, `result`, `item`, `temp`, `obj`) where domain names exist (`coverage`, `metadata`, `axes`, `parameter_id`).
- ❌ NO premature abstraction (no utility classes/decorators with only one call site).
- ❌ NO commented-out code, no excessive defensive `try/except`, no `# type: ignore` without explanation.
- ❌ NO `as Any` / `cast(Any, ...)` without typed reasoning.
- ❌ NO over-documentation (one-line docstrings restating function name).
- ❌ NO `print()` calls in source (use `logging.getLogger(__name__)`).
- ❌ NO dependencies beyond {`xarray`, `numpy`, `httpx`}; dev deps {`pytest`, `pytest-httpserver`, `pytest-cov`, `ruff`, `mypy`} only.

**Scope-creep guardrails:**
- ❌ NO async client (sync httpx only in v1).
- ❌ NO retry/backoff logic.
- ❌ NO caching layer (memory or disk).
- ❌ NO CLI / FastAPI proxy / discovery utilities.
- ❌ NO write/export functionality.
- ❌ NO custom xarray `Index` subclasses (use default).

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed via Bash/curl/Python REPL.
> Acceptance criteria requiring "user manually tests/confirms" are FORBIDDEN.

### Test Decision
- **Infrastructure exists**: NO (greenfield) — set up in T1.
- **Automated tests**: YES (TDD).
- **Framework**: `pytest` + `pytest-httpserver` + `pytest-cov`.
- **TDD cycle**: Each implementation task follows RED (failing test) → GREEN (minimal impl) → REFACTOR.
- **Coverage floor**: ≥ 95% on `src/edr_xarray/`.

### QA Policy
Every task MUST include agent-executed QA scenarios. Evidence saved to `.sisyphus/evidence/task-{N}-{slug}.{ext}`.

- **Library/Module tasks**: Bash + Python REPL — `uv run python -c "import ...; assert ..."`. Evidence = stdout transcript.
- **HTTP/transport tasks**: `pytest-httpserver` mock spun up in test, plus optional `curl` probes against firecube. Evidence = pytest output + request log.
- **Integration tasks**: Full open → index → fetch flow against `pytest-httpserver`. Evidence = pytest output + recorded HTTP requests.
- **Live firecube tests**: Marked `@pytest.mark.live`; only run if `EDR_LIVE_URL` env var set. Evidence = pytest output OR skip message.

### Scenario Specificity Requirements
- **Selectors / endpoints**: Exact URL paths and query params (`GET /collections/test_collection/cube?bbox=10,40,11,41&parameter-name=temperature&datetime=2025-01-01T00:00:00Z&f=CoverageJSON`).
- **Test data**: Concrete fixture filenames (`tests/data/cov_grid_3x3.json`).
- **Assertions**: Exact values (`np.array_equal(actual, np.array([[1.0, 2.0], [3.0, 4.0]]))`, not "verify it works").
- **Failure modes**: Every task must have ≥ 1 negative scenario (malformed input → specific exception).

---

## Execution Strategy

### Parallel Execution Waves

> Maximize throughput by grouping independent tasks into parallel waves. Each wave completes before the next begins.

```
Wave 1 (Foundation — 7 tasks parallel, no inter-deps):
├── T1: Project scaffolding (pyproject + ruff/mypy/pytest config + LICENSE + README skeleton + entry-point string + .gitignore + uv setup)
├── T2: Exception hierarchy (errors.py + tests)
├── T3: CoverageJSON parser (coveragejson.py + tests)
├── T4: Metadata parser (metadata.py + tests)
├── T5: Query encoders (query.py + tests)
├── T6: Test infrastructure (conftest.py + sample fixture JSON files)
└── T7: CI workflow (.github/workflows/ci.yml)

Wave 2 (Core modules — 4 tasks parallel, depend on Wave 1):
├── T8: Indexer translation (indexer.py + tests) — depends on T5
├── T9: HTTP transport (transport.py + tests) — depends on T2
├── T10: Coord discovery (discovery.py + tests) — depends on T3, T4
└── T11: Variable/Coords builder (builder.py + tests) — depends on T3, T4

Wave 3 (Integration core — 2 tasks parallel, depend on Wave 2):
├── T12: BackendArray (array.py + tests) — depends on T8, T9, T3
└── T13: DataStore (store.py + tests) — depends on T9, T10, T11, T4

Wave 4 (Public API — 1 task, depends on Wave 3):
└── T14: BackendEntrypoint + entry-point verification + first integration smoke test (backend.py + tests) — depends on T12, T13, T1

Wave 5 (E2E + docs — 5 tasks parallel, depend on Wave 4):
├── T15: Full integration test suite (test_integration_full_flow.py)
├── T16: Lazy semantics test (test_lazy_semantics.py)
├── T17: Pickle/Dask test (test_pickle_dask.py)
├── T18: Subclass extensibility test (test_subclass_extensibility.py)
└── T19: README usage examples + live firecube smoke test (README.md + test_live_firecube.py)

Wave FINAL (4 review agents in PARALLEL — present results, get explicit user okay):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality review (unspecified-high)
├── F3: Real manual QA (unspecified-high)
└── F4: Scope fidelity check (deep)
→ Present consolidated results → user okay → mark complete

Critical Path: T1 → T9 → T11 → T12 → T13 → T14 → T15 → F1-F4 → user okay
Max Concurrent: 7 (Wave 1)
```

> **Note on narrow Waves 3-4**: These are intentionally narrow. `BackendArray` and `DataStore` form a tightly-coupled core (with shared concerns around session, indexer, parsing); splitting further would create artificial partial states. `BackendEntrypoint` is naturally a thin glue layer over them.

### Dependency Matrix

| Task | Depends on | Blocks |
|---|---|---|
| T1 | — | T7, T14, T15-T19 |
| T2 | — | T9, T13 |
| T3 | — | T10, T11, T12 |
| T4 | — | T10, T11, T13 |
| T5 | — | T8 |
| T6 | — | T9-T19 (test infra) |
| T7 | T1 | — |
| T8 | T5 | T12 |
| T9 | T2, T6 | T12, T13 |
| T10 | T3, T4 | T13 |
| T11 | T3, T4 | T13 |
| T12 | T3, T8, T9 | T14 |
| T13 | T2, T4, T9, T10, T11 | T14 |
| T14 | T1, T12, T13 | T15-T19 |
| T15 | T6, T14 | F1-F4 |
| T16 | T6, T14 | F1-F4 |
| T17 | T6, T12, T14 | F1-F4 |
| T18 | T6, T13 | F1-F4 |
| T19 | T14 | F1-F4 |
| F1-F4 | T15-T19 | user okay |

### Agent Dispatch Summary

| Wave | Tasks | Agent profiles |
|---|---|---|
| 1 | 7 | T1 → `quick`; T2 → `quick`; T3 → `unspecified-high`; T4 → `unspecified-high`; T5 → `quick`; T6 → `quick`; T7 → `quick` |
| 2 | 4 | T8 → `unspecified-high`; T9 → `unspecified-high`; T10 → `deep`; T11 → `deep` |
| 3 | 2 | T12 → `deep`; T13 → `deep` |
| 4 | 1 | T14 → `deep` |
| 5 | 5 | T15 → `unspecified-high`; T16 → `unspecified-high`; T17 → `unspecified-high`; T18 → `unspecified-high`; T19 → `writing` |
| FINAL | 4 | F1 → `oracle`; F2 → `unspecified-high`; F3 → `unspecified-high`; F4 → `deep` |

---

## TODOs

- [ ] 1. **Project scaffolding (uv + ruff + mypy + pytest + LICENSE + entry point)**

  **What to do**:
  - Create `pyproject.toml` with project metadata: name `edr-xarray`, version `0.1.0`, requires-python `>=3.11`, license `Apache-2.0`, authors placeholder.
  - Runtime deps (pinned to floor): `xarray>=2024.6.0`, `numpy>=1.24`, `httpx>=0.25`.
  - Dev deps: `pytest>=8`, `pytest-httpserver>=1.0`, `pytest-cov>=5`, `ruff>=0.6`, `mypy>=1.10`.
  - `[project.entry-points."xarray.backends"]` with `edr = "edr_xarray.backend:EdrBackendEntrypoint"`. (Class is created later in T14; this string is committed in T1.)
  - `[tool.ruff]` config: line-length 100, target-version py311, select=["E","F","W","I","B","UP","RUF","ANN","D","SIM","TID"], ignore=["D100","D104","D203","D213","ANN101","ANN102"]. `[tool.ruff.format]` quote-style="double".
  - `[tool.mypy]` config: strict=true, python_version="3.11", warn_unused_ignores=true, no_implicit_optional=true, disallow_any_generics=true.
  - `[tool.pytest.ini_options]` config: testpaths=["tests"], markers=["live: opt-in tests against live EDR server (requires EDR_LIVE_URL env)"], filterwarnings=["error"].
  - `[tool.coverage.run]` source=["src/edr_xarray"], branch=true.
  - `[tool.hatch.build.targets.wheel]` packages=["src/edr_xarray"]. Use hatchling as build backend.
  - Create `LICENSE` file with full Apache-2.0 license text.
  - Create `.gitignore` excluding `.venv/`, `__pycache__/`, `*.pyc`, `dist/`, `.pytest_cache/`, `.coverage`, `.mypy_cache/`, `.ruff_cache/`, `.sisyphus/evidence/` (preserve plans + drafts).
  - Create `.python-version` containing `3.11`.
  - Create `src/edr_xarray/__init__.py` with `__version__ = "0.1.0"` and a `# Public API will be re-exported in T14` comment placeholder. (Don't put real exports yet — those classes don't exist.)
  - Create `src/edr_xarray/py.typed` empty marker.
  - Create `README.md` with project title, one-paragraph summary, "Status: alpha", placeholder Installation and Usage sections (filled in T19). NO emojis.
  - Initialize git repo: `git init && git add -A && git commit -m "chore: scaffold uv project with ruff/mypy/pytest and Apache-2.0 license"`.
  - Run `uv lock` then `uv sync` to materialize venv and lockfile.
  - Create `.sisyphus/evidence/` directory: `mkdir -p .sisyphus/evidence` (used by every downstream task to capture QA scenario evidence; the directory itself is `.gitignore`d so won't be committed).

  **Must NOT do**:
  - ❌ NO source modules besides `__init__.py`/`py.typed` — they belong in their own tasks.
  - ❌ NO test files yet (T6 owns test infrastructure).
  - ❌ NO CI workflow yet (T7 owns it).
  - ❌ NO emojis anywhere.
  - ❌ NO commented-out config items.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Mechanical scaffolding from a clear template; no architectural reasoning needed.
  - **Skills**: [`git-master`]
    - `git-master`: Initial commit message style and atomic commit hygiene.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T2-T7)
  - **Blocks**: T7, T14, T15-T19 (test commands depend on uv config)
  - **Blocked By**: None — foundation task

  **References**:

  *Pattern References* (existing code to follow):
  - `~/Desktop/projects/eumetsat/firecube/firecube-backend/pyproject.toml` — uv-managed Python project structure to mirror; copy the `[tool.ruff]`/`[tool.pytest]` style.

  *External References*:
  - https://docs.astral.sh/uv/concepts/projects/ — uv project layout
  - https://docs.astral.sh/ruff/configuration/ — ruff config schema
  - https://hatch.pypa.io/latest/config/build/#hatchling — hatchling wheel target syntax
  - https://www.apache.org/licenses/LICENSE-2.0.txt — exact Apache-2.0 license text
  - https://docs.xarray.dev/en/latest/internals/how-to-add-new-backend.html — xarray entry-point string format

  *WHY Each Reference Matters*:
  - firecube `pyproject.toml`: Same toolchain (uv) — match the dev-dep spec style (e.g. `[tool.uv] dev-dependencies = [...]`) so it feels consistent in the same workspace.
  - Apache-2.0 license URL: Use the verbatim text — partial copies cause license-checker failures.
  - xarray docs: The exact entry-point key MUST be `xarray.backends` (not `xarray_backends` or similar), or registration fails silently.

  **Acceptance Criteria**:

  *TDD (this task is config-only — no unit tests, but verification is mandatory)*:
  - [ ] `uv sync` exits 0 and creates `.venv/`.
  - [ ] `uv build --wheel` exits 0 and produces `dist/edr_xarray-0.1.0-py3-none-any.whl`.
  - [ ] `uv run python -c "import edr_xarray; print(edr_xarray.__version__)"` prints `0.1.0`.
  - [ ] `uv run ruff check src` exits 0 (no source files yet ⇒ vacuously passes).
  - [ ] `uv run mypy --strict src/edr_xarray` exits 0.
  - [ ] `git log --oneline | head -1` shows the scaffolding commit.

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Fresh sync produces working venv (and bootstraps .sisyphus/evidence/ for all later tasks)
    Tool: Bash
    Preconditions: empty repo with pyproject.toml, no .venv/
    Steps:
      1. cd /home/armagan/Desktop/projects/opensource/edr-xarray
      2. rm -rf .venv uv.lock dist
      3. mkdir -p .sisyphus/evidence  # bootstraps evidence dir for ALL downstream tasks
      4. test -d .sisyphus/evidence
      5. uv sync 2>&1 | tee .sisyphus/evidence/task-1-uv-sync.log
      6. test -d .venv
      7. uv run python --version 2>&1 | tee .sisyphus/evidence/task-1-python-version.log
    Expected Result:
      - .sisyphus/evidence/ exists (no error)
      - uv sync exit code 0
      - .venv/ exists
      - python --version output starts with "Python 3.11"
    Failure Indicators:
      - uv error about missing dependency
      - python version != 3.11.x
      - .sisyphus/evidence/ does not exist after step 3
    Evidence: .sisyphus/evidence/task-1-uv-sync.log, task-1-python-version.log

  Scenario: Wheel build succeeds with correct metadata
    Tool: Bash
    Preconditions: clean .venv from previous scenario
    Steps:
      1. uv build --wheel 2>&1 | tee .sisyphus/evidence/task-1-uv-build.log
      2. ls dist/ | tee .sisyphus/evidence/task-1-dist-ls.log
      3. uv run python -c "import edr_xarray; assert edr_xarray.__version__ == '0.1.0'; print('version-ok')" | tee .sisyphus/evidence/task-1-version.log
    Expected Result:
      - exit 0
      - dist/edr_xarray-0.1.0-py3-none-any.whl exists
      - prints "version-ok"
    Evidence: .sisyphus/evidence/task-1-uv-build.log, task-1-dist-ls.log, task-1-version.log

  Scenario: Entry point string is registered (negative test — class not yet created)
    Tool: Bash
    Preconditions: T1 scaffold exists; T14 not yet run
    Steps:
      1. uv run python -c "from importlib.metadata import entry_points; eps = entry_points(group='xarray.backends'); print([(ep.name, ep.value) for ep in eps])" 2>&1 | tee .sisyphus/evidence/task-1-entry-points.log
    Expected Result:
      - Output includes ('edr', 'edr_xarray.backend:EdrBackendEntrypoint')
      - (Note: importing the class itself will fail until T14 — that's expected)
    Evidence: .sisyphus/evidence/task-1-entry-points.log
  ```

  **Commit**: YES
  - Message: `chore: scaffold uv project with ruff/mypy/pytest and Apache-2.0 license`
  - Files: `pyproject.toml`, `LICENSE`, `.gitignore`, `.python-version`, `README.md`, `src/edr_xarray/__init__.py`, `src/edr_xarray/py.typed`, `uv.lock`
  - Pre-commit: `uv sync && uv build --wheel`

- [x] 2. **Exception hierarchy (`errors.py`)**

  **What to do**:
  - Create `src/edr_xarray/errors.py` with the exception hierarchy:
    - `EdrXarrayError(Exception)` — base for all package errors.
    - `EdrServerError(EdrXarrayError)` — HTTP-level failures (4xx, 5xx, network). Constructor: `(message: str, *, status_code: int | None = None, url: str | None = None)`. Attributes accessible as `.status_code`, `.url`. `__str__` includes both if present.
    - `EdrMetadataError(EdrXarrayError)` — collection metadata is missing required fields (e.g., no `data_queries.cube.link.href`).
    - `EdrCoverageJsonError(EdrXarrayError)` — CoverageJSON response malformed or unparseable.
    - `EdrUnsupportedFeatureError(EdrXarrayError)` — feature requested but not in v1 scope (non-Grid domain, antimeridian bbox, exotic z grammar, non-CoverageJSON format, etc.).
    - `EdrConformanceError(EdrXarrayError)` — server doesn't claim required conformance class (reserved for future use; documented but not raised in v1).
  - Each class gets a one-line docstring describing the intent.
  - `__all__` defined for clean re-exports.
  - Create `tests/test_errors.py` BEFORE implementing — RED phase:
    - Test base class is `Exception`.
    - Test each subclass `isinstance` of `EdrXarrayError`.
    - Test `EdrServerError("foo", status_code=404, url="http://x").status_code == 404` and `.url == "http://x"`.
    - Test `EdrServerError("foo")` works with all-optional kwargs.
    - Test `str(EdrServerError("not found", status_code=404, url="http://x/cube"))` contains "404", "http://x/cube", and "not found".
    - Test `raise ... from exc` chain preserves `__cause__`: `try: raise ValueError("x") except ValueError as e: try: raise EdrServerError("y") from e except EdrServerError as e2: assert e2.__cause__ is the ValueError`.

  **Must NOT do**:
  - ❌ NO logic in `__init__` beyond storing fields.
  - ❌ NO custom `__repr__` or fancy string formatting helpers.
  - ❌ NO module-level constants (status code dictionaries, etc.).
  - ❌ NO emojis in messages.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Mechanical class hierarchy creation with simple tests; no architectural decisions.
  - **Skills**: []
    - No skills needed; pattern is well-defined.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T3-T7)
  - **Blocks**: T9, T13 (HTTP error mapping uses these)
  - **Blocked By**: None

  **References**:

  *Pattern References*:
  - Standard Python exception hierarchy idiom — see `httpx` source: `httpx/_exceptions.py` for hierarchy with constructor kwargs.

  *External References*:
  - https://docs.python.org/3/tutorial/errors.html#user-defined-exceptions — conventional way to define exception hierarchy.

  *WHY Each Reference Matters*:
  - `httpx._exceptions`: Confirms the pattern of optional kwargs (status_code, url) stored as attributes, accessible by callers. We mirror this style.

  **Acceptance Criteria**:

  *TDD*:
  - [ ] `tests/test_errors.py` written FIRST and runs: `uv run pytest tests/test_errors.py` → all tests fail (no impl yet).
  - [ ] After implementing `errors.py`: `uv run pytest tests/test_errors.py -v` → all pass.
  - [ ] `uv run ruff check src/edr_xarray/errors.py tests/test_errors.py` clean.
  - [ ] `uv run mypy --strict src/edr_xarray/errors.py` clean.

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Exception hierarchy verifiable from REPL
    Tool: Bash (Python REPL)
    Preconditions: T2 implemented and committed
    Steps:
      1. uv run python -c "
         from edr_xarray.errors import (
             EdrXarrayError, EdrServerError, EdrMetadataError,
             EdrCoverageJsonError, EdrUnsupportedFeatureError, EdrConformanceError
         )
         assert issubclass(EdrServerError, EdrXarrayError)
         assert issubclass(EdrMetadataError, EdrXarrayError)
         assert issubclass(EdrCoverageJsonError, EdrXarrayError)
         assert issubclass(EdrUnsupportedFeatureError, EdrXarrayError)
         assert issubclass(EdrConformanceError, EdrXarrayError)
         e = EdrServerError('boom', status_code=503, url='http://srv/cube')
         assert e.status_code == 503 and e.url == 'http://srv/cube'
         assert '503' in str(e) and 'http://srv/cube' in str(e)
         print('hierarchy-ok')
         " 2>&1 | tee .sisyphus/evidence/task-2-hierarchy.log
    Expected Result: prints "hierarchy-ok", exit 0.
    Evidence: .sisyphus/evidence/task-2-hierarchy.log

  Scenario: raise...from preserves __cause__ (failure chaining)
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         from edr_xarray.errors import EdrServerError
         try:
             try:
                 raise ConnectionError('upstream down')
             except ConnectionError as exc:
                 raise EdrServerError('cube fetch failed', status_code=None, url='http://srv') from exc
         except EdrServerError as e2:
             assert isinstance(e2.__cause__, ConnectionError)
             assert str(e2.__cause__) == 'upstream down'
             print('cause-chain-ok')
         " 2>&1 | tee .sisyphus/evidence/task-2-cause-chain.log
    Expected Result: prints "cause-chain-ok", exit 0.
    Evidence: .sisyphus/evidence/task-2-cause-chain.log

  Scenario: Pytest suite passes
    Tool: Bash
    Steps:
      1. uv run pytest tests/test_errors.py -v 2>&1 | tee .sisyphus/evidence/task-2-pytest.log
    Expected Result: pytest reports all tests PASSED, exit 0, ≥6 tests.
    Evidence: .sisyphus/evidence/task-2-pytest.log
  ```

  **Commit**: YES
  - Message: `feat(errors): add EdrXarrayError hierarchy`
  - Files: `src/edr_xarray/errors.py`, `tests/test_errors.py`
  - Pre-commit: `uv run pytest tests/test_errors.py && uv run ruff check src/edr_xarray/errors.py tests/test_errors.py && uv run mypy --strict src/edr_xarray/errors.py`

- [x] 3. **CoverageJSON parser (`coveragejson.py`)**

  **What to do**:
  - Create `src/edr_xarray/coveragejson.py` with typed dataclasses and pure-function parsers:
    - `@dataclass(frozen=True) class Axis`: `name: str`, `values: np.ndarray` (1-D float64 or datetime64[ns]).
    - `@dataclass(frozen=True) class CoverageData`: `axes: dict[str, Axis]` (ordered insertion = canonical order), `axis_names: tuple[str, ...]`, `shape: tuple[int, ...]`, `parameters: dict[str, ParameterDef]`, `ranges: dict[str, np.ndarray]` (already reshaped to `shape`).
    - `@dataclass(frozen=True) class ParameterDef`: `name: str`, `unit: str | None`, `standard_name: str | None` (from `observedProperty.id`), `long_name: str | None` (from `observedProperty.label.en`), `cell_methods: str | None` (from `measurementType.method`).
  - Implement `parse_coverage(payload: dict) -> CoverageData` per the EDR/CoverageJSON spec:
    - Verify `payload["type"] == "Coverage"` and `payload["domain"]["domainType"] == "Grid"`. Otherwise raise `EdrUnsupportedFeatureError(f"only Grid domainType supported, got {dt}")`.
    - Parse `domain.axes` — each entry can be `{"values": [...]}` (explicit) or `{"start", "stop", "num"}` (regular interval). For regular interval, materialize `np.linspace(start, stop, num)`. Time axes (`t`) values are ISO strings → parse to `datetime64[ns]`.
    - For each parameter in `payload["parameters"]`: extract unit (from `unit.symbol.value`), standard_name (`observedProperty.id`), long_name (`observedProperty.label.en`), cell_methods (`measurementType.method`).
    - For each range in `payload["ranges"]`:
      - Verify `type == "NdArray"` (reject `TiledNdArray` with `EdrUnsupportedFeatureError`).
      - Read `axisNames`, `shape`, `dataType`, `values` (flat list).
      - Replace JSON `null` with `np.nan` if `dataType in {"float", "double"}`. If integer dtype contains `null`, raise `EdrCoverageJsonError`.
      - Reshape to `tuple(shape)` — verify `len(values) == prod(shape)`, else raise `EdrCoverageJsonError(f"value count {len(values)} does not match shape product {prod(shape)}")`.
      - Convert to `np.asarray(...)` with appropriate dtype.
    - Determine canonical `axis_names: tuple[str, ...]` from the FIRST range's `axisNames`. Verify all ranges share the same `axisNames` (else raise `EdrCoverageJsonError`).
    - Verify `shape` matches the lengths of axes referenced by `axis_names`.
  - All functions are pure: no I/O, no logging, no global state.
  - Write `tests/test_coveragejson.py` first (TDD RED):
    - Happy path: 3D Grid with explicit axes, single parameter, no nulls.
    - axisNames respected: input has `axisNames=["t","y","x"]` → output `axis_names=("t","y","x")` and `shape` matches axes lengths in that order.
    - Regular axis: `{"start":0,"stop":4,"num":5}` → np.array([0,1,2,3,4]).
    - Time axis: ISO strings → datetime64[ns].
    - Null handling: `[1.0, null, 3.0]` with `dataType="float"` → array containing `np.nan` at index 1.
    - Multi-parameter: two ranges sharing axisNames → both parsed, shape consistent.
    - Reject non-Grid: `domainType="PointSeries"` → `EdrUnsupportedFeatureError`.
    - Reject TiledNdArray: range with `type="TiledNdArray"` → `EdrUnsupportedFeatureError`.
    - Reject inconsistent axis: one range has different `axisNames` → `EdrCoverageJsonError`.
    - Reject mismatched value count: `shape=[2,2]` but `values=[1,2,3]` → `EdrCoverageJsonError`.
    - Reject null in integer range: `dataType="integer", values=[1, null]` → `EdrCoverageJsonError`.

  **Must NOT do**:
  - ❌ NO HTTP I/O — module is pure.
  - ❌ NO support for non-Grid domain types in v1.
  - ❌ NO TiledNdArray handling.
  - ❌ NO automatic transpose to a "preferred" axis order — preserve `axisNames` exactly. The transposition (if any) happens later in builder/array.
  - ❌ NO `try: ... except: pass` — every exception flows.
  - ❌ NO use of `pandas` (we only need `numpy.datetime64`).

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Non-trivial parsing logic with several edge cases and TDD discipline; benefits from careful code-quality attention.
  - **Skills**: []
    - No specific skill needed; clear spec.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1-T2, T4-T7)
  - **Blocks**: T10 (discovery), T11 (builder), T12 (array)
  - **Blocked By**: None — depends only on Python stdlib + numpy

  **References**:

  *Pattern References*:
  - tensogram-xarray `src/tensogram_xarray/coords.py` and `mapping.py` — typed structures for axis/dim resolution. Adapt the immutable `@dataclass(frozen=True)` style for our `Axis`/`CoverageData`.

  *API/Type References*:
  - https://covjson.org/spec/ — CoverageJSON 1.0 spec. Specifically sections "Coverage objects", "Domain objects", "NdArray objects", "Range objects".
  - EDR spec annex on CoverageJSON: https://docs.ogc.org/is/19-086r6/19-086r6.html#toc54

  *External References*:
  - numpy datetime64 docs: https://numpy.org/doc/stable/reference/arrays.datetime.html — for ISO string → datetime64[ns] conversion via `np.datetime64(s)`.

  *WHY Each Reference Matters*:
  - covjson.org/spec: Authoritative. Don't hardcode assumptions about field presence — check exactly what the spec mandates as required vs optional.
  - EDR spec annex: Confirms which CoverageJSON subset EDR servers can return; we restrict to Grid + NdArray for v1.
  - tensogram-xarray immutable dataclass pattern: Frozen dataclasses prevent later mutation surprises in the builder/array stages.

  **Acceptance Criteria**:

  *TDD*:
  - [ ] `tests/test_coveragejson.py` written first; running it → all fail (no impl).
  - [ ] After `coveragejson.py` implemented: `uv run pytest tests/test_coveragejson.py -v` → all pass (≥10 tests).
  - [ ] `uv run ruff check src/edr_xarray/coveragejson.py tests/test_coveragejson.py` clean.
  - [ ] `uv run mypy --strict src/edr_xarray/coveragejson.py` clean.
  - [ ] `uv run pytest --cov=src/edr_xarray/coveragejson tests/test_coveragejson.py` → coverage ≥ 95%.

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Parse 3D Grid with axisNames in non-canonical order
    Tool: Bash (Python REPL)
    Preconditions: T3 implemented
    Steps:
      1. uv run python -c "
         import json, numpy as np
         from edr_xarray.coveragejson import parse_coverage
         payload = {
             'type': 'Coverage',
             'domain': {
                 'type': 'Domain', 'domainType': 'Grid',
                 'axes': {
                     'x': {'start': 10.0, 'stop': 11.0, 'num': 2},
                     'y': {'start': 40.0, 'stop': 41.0, 'num': 2},
                     't': {'values': ['2025-01-01T00:00:00Z']},
                 },
                 'referencing': []
             },
             'parameters': {
                 'temperature': {
                     'type': 'Parameter',
                     'unit': {'symbol': {'value': 'K', 'type': 'http://www.opengis.net/def/uom/UCUM/'}},
                     'observedProperty': {'id': 'http://vocab.nerc.ac.uk/standard_name/air_temperature/', 'label': {'en': 'Air temperature'}}
                 }
             },
             'ranges': {
                 'temperature': {
                     'type': 'NdArray', 'dataType': 'float',
                     'axisNames': ['t', 'y', 'x'],
                     'shape': [1, 2, 2],
                     'values': [273.15, 274.15, 275.15, 276.15]
                 }
             }
         }
         cov = parse_coverage(payload)
         assert cov.axis_names == ('t', 'y', 'x'), cov.axis_names
         assert cov.shape == (1, 2, 2), cov.shape
         arr = cov.ranges['temperature']
         assert arr.shape == (1, 2, 2)
         assert np.allclose(arr, [[[273.15, 274.15], [275.15, 276.15]]])
         pdef = cov.parameters['temperature']
         assert pdef.unit == 'K', pdef.unit
         assert pdef.standard_name == 'http://vocab.nerc.ac.uk/standard_name/air_temperature/'
         assert pdef.long_name == 'Air temperature'
         print('parse-grid-ok')
         " 2>&1 | tee .sisyphus/evidence/task-3-grid-parse.log
    Expected Result: prints "parse-grid-ok", exit 0.
    Evidence: .sisyphus/evidence/task-3-grid-parse.log

  Scenario: Null values become NaN for float dtype
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         import numpy as np
         from edr_xarray.coveragejson import parse_coverage
         payload = {
             'type': 'Coverage',
             'domain': {'type':'Domain','domainType':'Grid',
                'axes': {'x': {'values':[0.0,1.0]}}, 'referencing': []},
             'parameters': {'p': {'type':'Parameter','observedProperty': {'id':'p','label':{'en':'p'}}}},
             'ranges': {'p': {'type':'NdArray','dataType':'float','axisNames':['x'],'shape':[2],'values':[1.0, None]}}
         }
         cov = parse_coverage(payload)
         arr = cov.ranges['p']
         assert arr.shape == (2,)
         assert arr[0] == 1.0
         assert np.isnan(arr[1])
         print('null-nan-ok')
         " 2>&1 | tee .sisyphus/evidence/task-3-null.log
    Expected Result: prints "null-nan-ok", exit 0.
    Evidence: .sisyphus/evidence/task-3-null.log

  Scenario: Reject non-Grid domain type (negative)
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         from edr_xarray.coveragejson import parse_coverage
         from edr_xarray.errors import EdrUnsupportedFeatureError
         payload = {
             'type':'Coverage',
             'domain':{'type':'Domain','domainType':'PointSeries','axes':{},'referencing':[]},
             'parameters': {}, 'ranges': {}
         }
         try:
             parse_coverage(payload)
             print('FAIL: should have raised')
         except EdrUnsupportedFeatureError as e:
             assert 'PointSeries' in str(e) or 'Grid' in str(e)
             print('reject-non-grid-ok')
         " 2>&1 | tee .sisyphus/evidence/task-3-reject-non-grid.log
    Expected Result: prints "reject-non-grid-ok", exit 0.
    Evidence: .sisyphus/evidence/task-3-reject-non-grid.log

  Scenario: Pytest suite passes with coverage
    Tool: Bash
    Steps:
      1. uv run pytest tests/test_coveragejson.py -v --cov=src/edr_xarray/coveragejson --cov-report=term 2>&1 | tee .sisyphus/evidence/task-3-pytest.log
    Expected Result: ≥10 tests PASSED, coverage ≥ 95%, exit 0.
    Evidence: .sisyphus/evidence/task-3-pytest.log
  ```

  **Commit**: YES
  - Message: `feat(coveragejson): parse Grid CoverageJSON responses with null→nan`
  - Files: `src/edr_xarray/coveragejson.py`, `tests/test_coveragejson.py`
  - Pre-commit: `uv run pytest tests/test_coveragejson.py && uv run ruff check src tests && uv run mypy --strict src/edr_xarray/coveragejson.py`

- [x] 4. **EDR collection metadata parser (`metadata.py`)**

  **What to do**:
  - Create `src/edr_xarray/metadata.py` with frozen dataclasses + a pure parser:
    - `class SpatialExtent`: `bbox: tuple[float, float, float, float]`, `crs: str | None`. Reject (raise `EdrMetadataError`) if `extent.spatial.bbox` contains multiple bboxes (length > 1) — log a one-liner and pick first only if explicitly enabled (NOT in v1).
    - `class TemporalExtent`: `interval: tuple[str, str]`, `values: tuple[str, ...] | None` (raw ISO strings preserved; conversion to datetime64 happens in builder).
    - `class VerticalExtent`: `interval: tuple[float, float]`, `values: tuple[float, ...] | None`, `vrs: str | None`.
    - `class ParameterDefinition`: `id: str`, `unit: str | None`, `standard_name: str | None`, `long_name: str | None`, `cell_methods: str | None` (these are duplicated from coveragejson.ParameterDef, but the source-of-truth is metadata; coveragejson values may be sparser).
    - `class CubeLink`: `href: str`, `output_formats: tuple[str, ...]`, `default_output_format: str | None`, `crs_options: tuple[str, ...]`.
    - `class CollectionMetadata`: `id: str`, `title: str | None`, `description: str | None`, `spatial: SpatialExtent`, `temporal: TemporalExtent | None`, `vertical: VerticalExtent | None`, `crs_options: tuple[str, ...]`, `parameters: dict[str, ParameterDefinition]`, `cube_link: CubeLink`, `instances_link: str | None`.
  - Implement `parse_collection_metadata(payload: dict) -> CollectionMetadata`:
    - Required fields: `id`, `extent.spatial.bbox`, `parameter_names`, `data_queries.cube.link.href`. Missing any → `EdrMetadataError(f"required field {x} missing in collection metadata")`.
    - `data_queries.cube.link.href` is the canonical cube URL — store as-is. Don't normalize relative URLs in this layer; transport will handle joining.
    - `data_queries.cube.link.variables.output_formats` → `cube_link.output_formats`. If absent, fall back to top-level `output_formats`. If neither contains `"CoverageJSON"` (case-insensitive), set `cube_link.output_formats=()` (empty) and let store layer raise `EdrUnsupportedFeatureError` later when negotiating.
    - `data_queries.cube.link.variables.default_output_format` → `cube_link.default_output_format`.
    - `data_queries.cube.link.variables.crs_details` (list of `{crs, wkt}` objects) → `cube_link.crs_options` = tuple of `crs` values (e.g. `("CRS84","EPSG:4326")`).
    - `data_queries.instances` (if present) → `instances_link` (the instances list URL).
    - Each parameter under `parameter_names`: extract `unit.symbol.value` → unit; `observedProperty.id` → standard_name; `observedProperty.label.en` → long_name; `measurementType.method` → cell_methods.
    - `extent.spatial.bbox` is `[[x1,y1,x2,y2]]` — take `[0]`.
    - `extent.temporal.interval` is `[[start,end]]` — take `[0]`.
    - `extent.temporal.values` (optional) preserved as tuple of strings.
    - `extent.vertical` parallel handling.
  - Function `cube_url(metadata: CollectionMetadata, instance: str | None, base_url: str) -> str`:
    - If `instance` is None: returns `metadata.cube_link.href` (joined with `base_url` if relative).
    - If `instance` provided: replaces `/collections/{id}` segment with `/collections/{id}/instances/{instance}` in the cube href, OR (preferred) fetches `instances` link to verify and obtain instance-specific cube href. **For v1, simpler approach**: derive instance cube URL by string-replacing `/cube` after pattern `/collections/<id>` with `/instances/<instance>/cube`. If pattern doesn't match, raise `EdrMetadataError("cannot resolve instance cube URL — non-standard URL shape; subclass _build_cube_url to override")`.
  - Tests written first (`tests/test_metadata.py`):
    - Happy path: minimal valid metadata (id, bbox, temporal interval, one parameter, cube link) → dataclass populated.
    - Full path: rich metadata with values arrays, multiple parameters, CRS list → all fields populated.
    - Cube link variables.crs_details list → `cube_link.crs_options` tuple of crs strings.
    - Missing `id` → `EdrMetadataError("required field id ...")`.
    - Missing `data_queries.cube.link.href` → `EdrMetadataError(... cube link ...)`.
    - Missing `extent.spatial.bbox` → `EdrMetadataError`.
    - Missing `parameter_names` → `EdrMetadataError`.
    - Multiple bboxes in extent → `EdrMetadataError("multiple disjoint bboxes not supported")`.
    - `cube_url(meta, instance=None, base_url="http://srv")` returns canonical href.
    - `cube_url(meta, instance="f024", base_url="http://srv")` returns instance-prefixed URL when shape is standard.
    - `cube_url(meta, instance="f024", ...)` with non-standard cube href → raises `EdrMetadataError`.
    - Parameter with no `observedProperty` → `standard_name=None, long_name=None`.
    - Parameter with `unit` but no `symbol.value` → `unit=None`.

  **Must NOT do**:
  - ❌ NO HTTP I/O — pure parser.
  - ❌ NO assumption that the cube URL is `<collection_url>/cube`. Always read `data_queries.cube.link.href`.
  - ❌ NO downloading instance metadata in this layer (store layer can do that if needed).
  - ❌ NO silent defaults for required fields — raise.
  - ❌ NO regex tricks on URLs that depend on firecube's specific shape.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Spec-driven parser with many optional fields and several edge cases.
  - **Skills**: []
    - Clear spec, no skills needed.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1-T3, T5-T7)
  - **Blocks**: T10 (discovery), T11 (builder), T13 (store)
  - **Blocked By**: None

  **References**:

  *Pattern References*:
  - `~/Desktop/projects/eumetsat/firecube/firecube-backend/firecube_backend/edr/metadata.py` — example of how an EDR server emits collection metadata. Use this as a real-world fixture when designing the parser.

  *API/Type References*:
  - https://docs.ogc.org/is/19-086r6/19-086r6.html#requirements_class_collection — EDR Collection metadata schema.
  - http://schemas.opengis.net/ogcapi/edr/1.0/openapi/schemas/ — JSON schemas for `extent`, `parameter-name-object`, `data-query-link`.

  *External References*:
  - CoverageJSON spec on `unit`, `observedProperty`, `measurementType`: https://covjson.org/spec/#parameters

  *WHY Each Reference Matters*:
  - firecube's `metadata.py`: Real implementation that emits the exact JSON our parser needs to consume. Mirror its field names so we test against realistic shapes.
  - EDR spec: Authoritative on which fields are required vs optional. Our parser must NOT silently default required fields — it must raise.

  **Acceptance Criteria**:

  *TDD*:
  - [ ] Tests written first; running → fail.
  - [ ] After impl: `uv run pytest tests/test_metadata.py -v` → ≥12 tests pass.
  - [ ] `uv run ruff check src/edr_xarray/metadata.py tests/test_metadata.py` clean.
  - [ ] `uv run mypy --strict src/edr_xarray/metadata.py` clean.
  - [ ] `uv run pytest --cov=src/edr_xarray/metadata tests/test_metadata.py` → coverage ≥ 95%.

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Parse rich firecube-style metadata
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         from edr_xarray.metadata import parse_collection_metadata, cube_url
         payload = {
             'id': 'msg_frm', 'title': 'MSG FRM',
             'extent': {
                 'spatial': {'bbox': [[10.0,40.0,11.0,41.0]], 'crs': 'http://www.opengis.net/def/crs/OGC/1.3/CRS84'},
                 'temporal': {'interval': [['2025-01-01T00:00:00Z','2025-01-01T00:00:00Z']],
                              'values': ['2025-01-01T00:00:00Z']}
             },
             'crs': ['http://www.opengis.net/def/crs/OGC/1.3/CRS84'],
             'output_formats': ['CoverageJSON','GeoJSON'],
             'parameter_names': {
                 'FWI': {'type':'Parameter','unit':{'symbol':{'value':'-'}},
                         'observedProperty':{'id':'FWI','label':{'en':'Fire Weather Index'}}}
             },
             'data_queries': {
                 'cube': {'link': {
                     'href':'http://srv/collections/msg_frm/cube',
                     'rel':'data','type':'application/prs.coverage+json',
                     'variables':{'output_formats':['CoverageJSON','GeoJSON'],
                                  'default_output_format':'CoverageJSON',
                                  'crs_details':[{'crs':'CRS84','wkt':'...'}]}
                 }},
                 'instances': {'link': {'href':'http://srv/collections/msg_frm/instances'}}
             }
         }
         meta = parse_collection_metadata(payload)
         assert meta.id == 'msg_frm'
         assert meta.spatial.bbox == (10.0,40.0,11.0,41.0), meta.spatial.bbox
         assert meta.temporal.interval == ('2025-01-01T00:00:00Z','2025-01-01T00:00:00Z')
         assert 'FWI' in meta.parameters
         assert meta.parameters['FWI'].long_name == 'Fire Weather Index'
         assert meta.cube_link.href == 'http://srv/collections/msg_frm/cube'
         assert 'CoverageJSON' in meta.cube_link.output_formats
         assert meta.cube_link.crs_options == ('CRS84',)
         assert meta.instances_link == 'http://srv/collections/msg_frm/instances'
         assert cube_url(meta, instance=None, base_url='http://srv') == 'http://srv/collections/msg_frm/cube'
         assert cube_url(meta, instance='f024', base_url='http://srv') == 'http://srv/collections/msg_frm/instances/f024/cube'
         print('metadata-parse-ok')
         " 2>&1 | tee .sisyphus/evidence/task-4-metadata-parse.log
    Expected Result: prints "metadata-parse-ok", exit 0.
    Evidence: .sisyphus/evidence/task-4-metadata-parse.log

  Scenario: Reject metadata missing cube link (negative)
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         from edr_xarray.metadata import parse_collection_metadata
         from edr_xarray.errors import EdrMetadataError
         payload = {
             'id':'x', 'extent':{'spatial':{'bbox':[[0,0,1,1]]}},
             'parameter_names':{'p':{'type':'Parameter','observedProperty':{'id':'p','label':{'en':'p'}}}},
             'data_queries': {}
         }
         try:
             parse_collection_metadata(payload)
             print('FAIL: should have raised')
         except EdrMetadataError as e:
             assert 'cube' in str(e).lower()
             print('reject-no-cube-ok')
         " 2>&1 | tee .sisyphus/evidence/task-4-reject-no-cube.log
    Expected Result: prints "reject-no-cube-ok", exit 0.
    Evidence: .sisyphus/evidence/task-4-reject-no-cube.log

  Scenario: Reject multiple disjoint bboxes (negative — Metis identified)
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         from edr_xarray.metadata import parse_collection_metadata
         from edr_xarray.errors import EdrMetadataError
         payload = {
             'id':'x',
             'extent':{'spatial':{'bbox':[[0,0,1,1],[10,10,11,11]]}},
             'parameter_names':{'p':{'type':'Parameter','observedProperty':{'id':'p','label':{'en':'p'}}}},
             'data_queries':{'cube':{'link':{'href':'http://srv/cube','variables':{'output_formats':['CoverageJSON']}}}}
         }
         try:
             parse_collection_metadata(payload)
             print('FAIL: should have raised')
         except EdrMetadataError as e:
             assert 'bbox' in str(e).lower() or 'disjoint' in str(e).lower() or 'multiple' in str(e).lower()
             print('reject-multibbox-ok')
         " 2>&1 | tee .sisyphus/evidence/task-4-reject-multibbox.log
    Expected Result: prints "reject-multibbox-ok", exit 0.
    Evidence: .sisyphus/evidence/task-4-reject-multibbox.log

  Scenario: Pytest suite passes
    Tool: Bash
    Steps:
      1. uv run pytest tests/test_metadata.py -v --cov=src/edr_xarray/metadata 2>&1 | tee .sisyphus/evidence/task-4-pytest.log
    Expected Result: ≥12 tests PASSED, coverage ≥ 95%.
    Evidence: .sisyphus/evidence/task-4-pytest.log
  ```

  **Commit**: YES
  - Message: `feat(metadata): parse EDR collection metadata and resolve cube link`
  - Files: `src/edr_xarray/metadata.py`, `tests/test_metadata.py`
  - Pre-commit: `uv run pytest tests/test_metadata.py && uv run ruff check src/edr_xarray/metadata.py tests/test_metadata.py && uv run mypy --strict src/edr_xarray/metadata.py`

- [x] 5. **Query parameter encoders & validators (`query.py`)**

  **What to do**:
  - Create `src/edr_xarray/query.py` with pure functions:
    - `encode_bbox(bbox: tuple[float, float, float, float]) -> str`:
      - Validates tuple of 4 floats.
      - Validates `lon_min < lon_max` (raise `EdrUnsupportedFeatureError("antimeridian-crossing bbox not supported in v1")` if not).
      - Validates `lat_min < lat_max` (raise `ValueError`).
      - Validates lon ∈ [-180, 180], lat ∈ [-90, 90] (raise `ValueError` with concrete message).
      - Returns `f"{lon_min},{lat_min},{lon_max},{lat_max}"`.
    - `encode_datetime(dt: str | None) -> str | None`:
      - If None, return None.
      - Accept either ISO instant (`"2025-01-01T00:00:00Z"`) or interval `"start/end"`. Reject `..` open intervals (`EdrUnsupportedFeatureError("open datetime intervals (../...) not supported in v1")`).
      - Light validation via `datetime.datetime.fromisoformat` after stripping trailing `Z` (or use `re.match` for the `\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?` shape) — reject malformed with `ValueError("datetime must be ISO 8601 instant or interval")`.
      - Pass through as-is once validated.
    - `encode_z(z: float | str | None) -> str | None`:
      - None → None.
      - Single float/int → `str(z)` (e.g. `500` → `"500"`).
      - String containing single `/` (e.g. `"1000/300"`) → validate each side parses as float, return as-is.
      - Reject any string containing `R` prefix (repeat syntax) with `EdrUnsupportedFeatureError("z repeat syntax (R...) not supported in v1")`.
      - Reject any string containing `,` (multi-level list) with `EdrUnsupportedFeatureError("z multi-level lists not supported in v1")`.
    - `encode_parameter_names(names: list[str] | None) -> str | None`:
      - None → None.
      - List → comma-joined.
      - Empty list → `ValueError("parameter_names must be None or non-empty list")`.
    - `encode_crs(crs: str | None, allowed: tuple[str, ...]) -> str | None`:
      - None → None.
      - If `crs not in allowed` → `EdrUnsupportedFeatureError(f"crs {crs} not in collection's advertised list {allowed}")`.
      - Pass through.
    - `negotiate_format(advertised: tuple[str, ...]) -> str`:
      - Returns `"CoverageJSON"` if `"CoverageJSON"` in advertised (case-insensitive match against canonical name).
      - Else raises `EdrUnsupportedFeatureError(f"server does not advertise CoverageJSON; advertised={advertised}")`.
  - Tests written first (`tests/test_query.py`):
    - `encode_bbox` happy: `(10.0,40.0,11.0,41.0)` → `"10.0,40.0,11.0,41.0"`.
    - `encode_bbox` antimeridian: `(170, 0, -170, 1)` → `EdrUnsupportedFeatureError`.
    - `encode_bbox` invalid lat: `(0, 100, 1, 101)` → `ValueError`.
    - `encode_bbox` non-tuple: `[10,40,11,41]` (list) accepted (test that we coerce or accept iterable).
    - `encode_datetime` instant: `"2025-01-01T00:00:00Z"` → same.
    - `encode_datetime` interval: `"2025-01-01T00:00:00Z/2025-01-02T00:00:00Z"` → same.
    - `encode_datetime` open: `"../2025-01-02T00:00:00Z"` → `EdrUnsupportedFeatureError`.
    - `encode_datetime` malformed: `"yesterday"` → `ValueError`.
    - `encode_z` scalar: `500` → `"500"`, `500.5` → `"500.5"`.
    - `encode_z` range: `"1000/300"` → `"1000/300"`.
    - `encode_z` repeat: `"R14/1000/-50"` → `EdrUnsupportedFeatureError`.
    - `encode_z` list: `"500,400,300"` → `EdrUnsupportedFeatureError`.
    - `encode_parameter_names` happy: `["temp","wind"]` → `"temp,wind"`.
    - `encode_parameter_names` None → None.
    - `encode_parameter_names` empty: `[]` → `ValueError`.
    - `encode_crs` allowed: `"CRS84"` in `("CRS84","EPSG:4326")` → `"CRS84"`.
    - `encode_crs` not allowed: `"EPSG:3857"` not in allowed → `EdrUnsupportedFeatureError`.
    - `negotiate_format` happy: `("CoverageJSON","GeoJSON")` → `"CoverageJSON"`.
    - `negotiate_format` case-insensitive: `("coveragejson",)` → `"CoverageJSON"`.
    - `negotiate_format` no match: `("GeoJSON",)` → `EdrUnsupportedFeatureError`.

  **Must NOT do**:
  - ❌ NO HTTP calls.
  - ❌ NO support for antimeridian, repeat z grammar, multi-level z lists.
  - ❌ NO automatic CRS conversion.
  - ❌ NO clever bbox normalization (e.g., wrapping longitudes mod 360).

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Pure functions with simple validators; mechanical.
  - **Skills**: []
    - None needed.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1-T4, T6-T7)
  - **Blocks**: T8 (indexer uses these encoders)
  - **Blocked By**: None

  **References**:

  *API/Type References*:
  - EDR cube query parameters: https://docs.ogc.org/is/19-086r6/19-086r6.html#req_edr_rc-cube — bbox/datetime/z/parameter-name/crs/f shapes.

  *External References*:
  - https://en.wikipedia.org/wiki/ISO_8601 — datetime format reference.

  *WHY Each Reference Matters*:
  - EDR spec: Defines the exact wire format. Don't invent variants — match the spec strings.

  **Acceptance Criteria**:

  *TDD*:
  - [ ] Tests first, fail.
  - [ ] After impl: `uv run pytest tests/test_query.py -v` → ≥18 tests pass.
  - [ ] `uv run ruff check src/edr_xarray/query.py tests/test_query.py` clean.
  - [ ] `uv run mypy --strict src/edr_xarray/query.py` clean.
  - [ ] Coverage ≥ 95%.

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Encode bbox/datetime/z happy path
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         from edr_xarray.query import encode_bbox, encode_datetime, encode_z, encode_parameter_names, negotiate_format
         assert encode_bbox((10.0,40.0,11.0,41.0)) == '10.0,40.0,11.0,41.0'
         assert encode_datetime('2025-01-01T00:00:00Z') == '2025-01-01T00:00:00Z'
         assert encode_datetime('2025-01-01T00:00:00Z/2025-01-02T00:00:00Z') == '2025-01-01T00:00:00Z/2025-01-02T00:00:00Z'
         assert encode_z(500) == '500'
         assert encode_z('1000/300') == '1000/300'
         assert encode_parameter_names(['t','w']) == 't,w'
         assert negotiate_format(('CoverageJSON','GeoJSON')) == 'CoverageJSON'
         print('encode-happy-ok')
         " 2>&1 | tee .sisyphus/evidence/task-5-happy.log
    Expected Result: prints "encode-happy-ok".
    Evidence: .sisyphus/evidence/task-5-happy.log

  Scenario: Reject antimeridian bbox (negative)
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         from edr_xarray.query import encode_bbox
         from edr_xarray.errors import EdrUnsupportedFeatureError
         try:
             encode_bbox((170.0, 0.0, -170.0, 1.0))
             print('FAIL: should have raised')
         except EdrUnsupportedFeatureError as e:
             assert 'antimeridian' in str(e).lower()
             print('reject-antimeridian-ok')
         " 2>&1 | tee .sisyphus/evidence/task-5-antimeridian.log
    Expected Result: prints "reject-antimeridian-ok".
    Evidence: .sisyphus/evidence/task-5-antimeridian.log

  Scenario: Reject z repeat grammar (negative)
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         from edr_xarray.query import encode_z
         from edr_xarray.errors import EdrUnsupportedFeatureError
         try:
             encode_z('R14/1000/-50')
             print('FAIL')
         except EdrUnsupportedFeatureError as e:
             assert 'repeat' in str(e).lower() or 'R' in str(e)
             print('reject-z-repeat-ok')
         " 2>&1 | tee .sisyphus/evidence/task-5-z-repeat.log
    Expected Result: prints "reject-z-repeat-ok".
    Evidence: .sisyphus/evidence/task-5-z-repeat.log

  Scenario: Pytest suite
    Tool: Bash
    Steps:
      1. uv run pytest tests/test_query.py -v --cov=src/edr_xarray/query 2>&1 | tee .sisyphus/evidence/task-5-pytest.log
    Expected Result: ≥18 tests pass, coverage ≥ 95%.
    Evidence: .sisyphus/evidence/task-5-pytest.log
  ```

  **Commit**: YES
  - Message: `feat(query): encode bbox, datetime, z, and parameter-name query params`
  - Files: `src/edr_xarray/query.py`, `tests/test_query.py`
  - Pre-commit: `uv run pytest tests/test_query.py && uv run ruff check src tests && uv run mypy --strict src/edr_xarray/query.py`

- [x] 6. **Test infrastructure & fixtures (`tests/conftest.py` + `tests/data/*.json`)**

  **What to do**:
  - Create `tests/__init__.py` (empty).
  - Create `tests/conftest.py` exposing pytest fixtures:
    - `httpserver` (provided by pytest-httpserver — just ensure plugin loaded).
    - `sample_cov_grid_3d(request)`: returns a CoverageJSON dict for a 3D Grid (t=1, y=2, x=2) with one parameter `temperature` and concrete values `[[273.15, 274.15], [275.15, 276.15]]`. Fixture parameterizable by adding null at a position.
    - `sample_cov_grid_4d`: 4D Grid (t=1, z=3, y=2, x=2) with z values [1000.0, 850.0, 500.0].
    - `sample_collection_metadata(httpserver)`: returns a dict matching firecube's metadata shape; the cube link's `href` uses `httpserver.url_for("/collections/test/cube")` so the mock server can claim that URL.
    - `sample_metadata_with_instances(httpserver)`: collection metadata that advertises an `instances` link.
    - `register_metadata_endpoint(httpserver, collection_id, payload)`: helper that registers a GET route returning the metadata.
    - `register_cube_endpoint(httpserver, collection_id, payload, status=200)`: helper that registers a GET route returning CoverageJSON (or an error payload at given status).
    - `request_log(httpserver)`: helper that returns the list of request URLs/queries the test server received during a test (for asserting laziness).
  - Create `tests/data/cov_grid_3d.json` — verbatim happy-path 3D CoverageJSON.
  - Create `tests/data/cov_grid_4d.json` — 4D with z axis.
  - Create `tests/data/cov_grid_with_nulls.json` — 3D with one null value.
  - Create `tests/data/collection_metadata_basic.json` — minimal valid metadata.
  - Create `tests/data/collection_metadata_with_instances.json` — metadata with `instances` link.
  - Create `tests/data/cov_pointseries.json` — a CoverageJSON with `domainType=PointSeries` for negative tests.
  - Create `tests/data/cov_tiled.json` — CoverageJSON with `range.type=TiledNdArray` for negative tests.
  - Each JSON fixture is loadable via `json.loads(Path("tests/data/<name>.json").read_text())`.
  - Create `tests/__init__.py` (empty marker).
  - Verify pytest-httpserver discovery: a smoke test in `tests/test_conftest_smoke.py` that registers a route and asserts a request roundtrips. (Delete or move into integration tests after Wave 5.)

  **Must NOT do**:
  - ❌ NO actual EDR backend code in test fixtures (don't import edr_xarray modules — fixtures are inputs only).
  - ❌ NO live HTTP — pytest-httpserver only.
  - ❌ NO hardcoded localhost URLs (use `httpserver.url_for(...)`).

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Test scaffolding and JSON fixture authoring.
  - **Skills**: []
    - None needed.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1-T5, T7)
  - **Blocks**: T9-T19 (every test downstream uses fixtures)
  - **Blocked By**: None

  **References**:

  *Pattern References*:
  - tensogram-xarray `tests/conftest.py` — fixtures for synthetic data and remote-server mocks.
  - `~/Desktop/projects/eumetsat/firecube/firecube-backend/tests/compliance/conftest.py` — examples of CoverageJSON shape that real firecube emits.
  - `~/Desktop/projects/eumetsat/firecube/firecube-backend/firecube_backend/edr/encoders.py` — server's CoverageJSON encoder; gives us reference shapes to mirror in test fixtures.

  *External References*:
  - https://pytest-httpserver.readthedocs.io/en/latest/howto.html — pytest-httpserver usage patterns.

  *WHY Each Reference Matters*:
  - firecube's encoder: Real-world CoverageJSON shape from a working server. Our fixtures must match this so end-to-end tests pass against the real server too.
  - pytest-httpserver howto: We use `expect_request().respond_with_json()` and `httpserver.url_for()` in fixtures.

  **Acceptance Criteria**:

  *TDD*:
  - [ ] Smoke test runs: `uv run pytest tests/test_conftest_smoke.py -v` → passes.
  - [ ] All fixture JSON files load with `json.loads(...)` (no syntax errors).
  - [ ] `uv run ruff check tests` clean.

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: All fixture JSONs are valid
    Tool: Bash
    Steps:
      1. uv run python -c "
         import json, glob, sys
         files = sorted(glob.glob('tests/data/*.json'))
         assert len(files) >= 5, f'expected >=5 fixtures, got {files}'
         for f in files:
             with open(f) as fp:
                 data = json.load(fp)
             assert isinstance(data, dict)
             print(f'ok: {f}')
         print('all-fixtures-valid')
         " 2>&1 | tee .sisyphus/evidence/task-6-fixtures.log
    Expected Result: prints "all-fixtures-valid", exit 0.
    Evidence: .sisyphus/evidence/task-6-fixtures.log

  Scenario: pytest-httpserver fixture works
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_conftest_smoke.py -v 2>&1 | tee .sisyphus/evidence/task-6-smoke.log
    Expected Result: ≥1 test PASSED, exit 0.
    Evidence: .sisyphus/evidence/task-6-smoke.log

  Scenario: Conftest exposes named fixtures
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest --fixtures tests/ 2>&1 | tee .sisyphus/evidence/task-6-fixtures-list.log
      2. grep -E '(sample_cov_grid_3d|sample_collection_metadata|register_metadata_endpoint|register_cube_endpoint)' .sisyphus/evidence/task-6-fixtures-list.log
    Expected Result: grep finds all 4 fixture names; exit 0.
    Evidence: .sisyphus/evidence/task-6-fixtures-list.log
  ```

  **Commit**: YES
  - Message: `test: add pytest-httpserver fixtures and sample EDR JSON data`
  - Files: `tests/__init__.py`, `tests/conftest.py`, `tests/test_conftest_smoke.py`, `tests/data/*.json`
  - Pre-commit: `uv run pytest tests/test_conftest_smoke.py && uv run ruff check tests`

- [x] 7. **CI workflow (`.github/workflows/ci.yml`)**

  **What to do**:
  - Create `.github/workflows/ci.yml` with one job `lint-typecheck-test`:
    - Triggers: `push` and `pull_request` on all branches.
    - Matrix: Python `3.11`, `3.12`.
    - Runner: `ubuntu-latest`.
    - Steps:
      1. `actions/checkout@v4`
      2. Install uv via `astral-sh/setup-uv@v3` with `enable-cache: true`.
      3. `uv sync --frozen --all-extras --dev`
      4. `uv run ruff check src tests`
      5. `uv run ruff format --check src tests`
      6. `uv run mypy --strict src/edr_xarray`
      7. `uv run pytest --cov=src/edr_xarray --cov-fail-under=95 -v -m "not live"`
    - Concurrency group `${{ github.workflow }}-${{ github.ref }}` with `cancel-in-progress: true`.
  - Add `.github/dependabot.yml` for weekly Python and Actions updates.
  - Create `CONTRIBUTING.md` skeleton with one paragraph: "Run `uv sync && uv run pytest` before opening a PR."

  **Must NOT do**:
  - ❌ NO live tests in CI (mark with `-m "not live"`).
  - ❌ NO secrets/tokens in CI yet.
  - ❌ NO matrix for OSes (Linux only for v1).
  - ❌ NO publish-to-PyPI workflow (out of scope for v1).

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Standard CI YAML; trivial.
  - **Skills**: []
    - None.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1-T6)
  - **Blocks**: None (CI is meta — runs separately).
  - **Blocked By**: T1 (uses pyproject test commands)

  **References**:

  *External References*:
  - https://docs.astral.sh/uv/guides/integration/github/ — recommended GitHub Actions integration with uv.
  - https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions — workflow syntax.

  *WHY Each Reference Matters*:
  - astral-sh/setup-uv: Official action — handles caching properly so CI is fast.

  **Acceptance Criteria**:

  *Local-equivalent verification (CI itself can't run without GitHub):*
  - [ ] `uv run ruff check src tests && uv run ruff format --check src tests` clean.
  - [ ] `uv run mypy --strict src/edr_xarray` clean (vacuous if only T1's `__init__.py`).
  - [ ] `uv run pytest -v -m "not live"` exits 0 (passes Wave 1 tests).
  - [ ] CI workflow file present, non-empty, and references the four QA commands (verified by grep — no PyYAML required).
  - [ ] Workflow file references `astral-sh/setup-uv` action and the four QA commands (`ruff check`, `ruff format`, `mypy`, `pytest`).

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: CI YAML file present and references required steps (dependency-free)
    Tool: Bash
    Preconditions: .github/workflows/ci.yml exists
    Steps:
      1. test -f .github/workflows/ci.yml || { echo "MISSING: .github/workflows/ci.yml"; exit 1; }
      2. test -s .github/workflows/ci.yml || { echo "EMPTY: .github/workflows/ci.yml"; exit 1; }
      3. for needle in "ruff check" "ruff format" "mypy" "pytest" "astral-sh/setup-uv"; do
           grep -q "$needle" .github/workflows/ci.yml || { echo "MISSING needle: $needle"; exit 1; }
         done
      4. echo "ci-yaml-ok" | tee .sisyphus/evidence/task-7-ci-yaml.log
    Expected Result: prints "ci-yaml-ok", exit 0.
    Failure Indicators: any "MISSING" output, non-zero exit.
    Evidence: .sisyphus/evidence/task-7-ci-yaml.log

  Scenario: CI commands all run cleanly locally
    Tool: Bash
    Steps:
      1. uv run ruff check src tests 2>&1 | tee .sisyphus/evidence/task-7-ruff.log
      2. uv run ruff format --check src tests 2>&1 | tee -a .sisyphus/evidence/task-7-ruff.log
      3. uv run mypy --strict src/edr_xarray 2>&1 | tee .sisyphus/evidence/task-7-mypy.log
      4. uv run pytest -v -m "not live" 2>&1 | tee .sisyphus/evidence/task-7-pytest.log
    Expected Result: all four commands exit 0.
    Evidence: .sisyphus/evidence/task-7-ruff.log, task-7-mypy.log, task-7-pytest.log
  ```

  **Commit**: YES
  - Message: `ci: add ruff+mypy+pytest GitHub Actions workflow`
  - Files: `.github/workflows/ci.yml`, `.github/dependabot.yml`, `CONTRIBUTING.md`
  - Pre-commit: `test -f .github/workflows/ci.yml && grep -q "ruff check" .github/workflows/ci.yml && grep -q "pytest" .github/workflows/ci.yml`

- [x] 8. **Indexer translation (`indexer.py`)**

  **What to do**:
  - Create `src/edr_xarray/indexer.py` with a pure translator from xarray's basic indexer key to EDR cube subset query parameters.
  - Define dataclass `AxisInfo`: `name: str` (e.g. `"x"`, `"y"`, `"z"`, `"t"`), `values: np.ndarray`, `kind: Literal["x","y","z","t"]`.
  - Function `translate_indexer(key: tuple[Union[int, slice], ...], axes: tuple[AxisInfo, ...], collection_bbox: tuple[float, float, float, float] | None = None) -> dict[str, str]`:
    - `key` length must equal `len(axes)`. Else `ValueError(f"indexer length {len(key)} does not match dimensionality {len(axes)}")`.
    - For each `(idx, axis)` pair:
      - If `axis.kind == "x"` and idx is `slice`: compute `lon_min/lon_max` from `axis.values[idx]`. Combine with `y` slice into bbox.
      - If `axis.kind == "y"` and idx is `slice`: compute `lat_min/lat_max` from `axis.values[idx]`.
      - If `axis.kind == "x"` or `"y"` and idx is `int`: collapse to a single coord — bbox becomes `(v, v', v, v')` for tiny epsilon (or repeat the same value; servers may vary). Document this behavior.
      - If `axis.kind == "z"`: int → `z=str(value)`; slice → `z=f"{lo}/{hi}"` from `axis.values[lo_idx]/axis.values[hi_idx_inclusive]`.
      - If `axis.kind == "t"`: int → `datetime=str(value)` (axis values are ISO strings or datetime64 — convert to ISO via `np.datetime_as_string(...)`); slice → `datetime=f"{start_iso}/{end_iso}"`.
    - Returns dict like `{"bbox": "10.0,40.0,11.0,41.0", "datetime": "2025-01-01T00:00:00Z/2025-01-02T00:00:00Z", "z": "1000/300"}` — only including keys whose corresponding axis is in `axes` AND whose key isn't a full slice that would mean "no subset" (in which case omit to let server return full extent).
    - Uses `encode_bbox`, `encode_datetime`, `encode_z` from `query.py`.
  - Function `slice_extent(values: np.ndarray, idx: int | slice) -> tuple[Any, Any]`:
    - For int `i`: returns `(values[i], values[i])`.
    - For slice: handles `start/stop/step` semantics; preserves inclusive end (slice stop is exclusive, but EDR ranges are inclusive — adjust by `idx.stop - 1` if step=1).
    - Negative indices supported (Python convention).
  - Tests written first:
    - 3D (t, y, x) full slice → query has neither bbox nor datetime override (full extent).
    - 3D (t, y, x) with `slice(0, 1)` for x and `slice(None)` for y — bbox is just x-narrow, y-full.
    - 4D (t, z, y, x) with int z=2, full t/y/x → `z=str(axis.values[2])`.
    - Time slice `[1:3]` on time axis with values `[t0, t1, t2, t3]` → `datetime="t1/t2"`.
    - Time int `0` → `datetime=str(axis.values[0])`.
    - Mismatched key length → `ValueError`.
    - Negative slice indices: `slice(-1, None)` on a 3-element axis → take the last element.
    - X int collapse: `int` on x-axis → bbox uses `(v, y_lo, v, y_hi)` (point-or-tiny-bbox).

  **Must NOT do**:
  - ❌ NO HTTP calls.
  - ❌ NO assumption that all axes are present (some collections may be 2D — just lat/lon — handle 2/3/4D uniformly).
  - ❌ NO assumption about axis ORDER (the caller passes `axes` in the order matching `key`).
  - ❌ NO support for fancy indexing (numpy arrays as indexer values) — that's `IndexingSupport.OUTER` territory; v1 stays at BASIC.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Subtle slicing semantics (Python exclusive vs EDR inclusive ranges, negative indices, full-slice detection) require careful TDD.
  - **Skills**: []
    - None needed.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T9, T10, T11)
  - **Blocks**: T12 (BackendArray uses this translator)
  - **Blocked By**: T5 (encoders)

  **References**:

  *Pattern References*:
  - tensogram-xarray `src/tensogram_xarray/array.py:_nd_slice_to_flat_ranges` — analogous "slice → range list" decomposition for byte ranges. Same conceptual problem (slice math), different output form.

  *API/Type References*:
  - xarray's `BasicIndexer` and `OuterIndexer` types: `xarray/core/indexing.py:BasicIndexer` — confirms the key tuple shape we'll receive.

  *External References*:
  - https://numpy.org/doc/stable/reference/arrays.indexing.html — basic slicing semantics.

  *WHY Each Reference Matters*:
  - tensogram's slice decomposition: Validates the approach of iterating axis-by-axis and aggregating into a flat output. The math (negative indices, step handling) is the trickiest part — copy their unit tests.

  **Acceptance Criteria**:

  *TDD*:
  - [ ] Tests first; running → fail.
  - [ ] After impl: `uv run pytest tests/test_indexer.py -v` → ≥10 tests pass.
  - [ ] `uv run mypy --strict src/edr_xarray/indexer.py` clean.
  - [ ] Coverage ≥ 95%.

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: 3D full slice produces no subset overrides
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         import numpy as np
         from edr_xarray.indexer import translate_indexer, AxisInfo
         axes = (
             AxisInfo(name='time', values=np.array(['2025-01-01T00:00:00','2025-01-02T00:00:00'], dtype='datetime64[ns]'), kind='t'),
             AxisInfo(name='y', values=np.array([40.0,41.0]), kind='y'),
             AxisInfo(name='x', values=np.array([10.0,11.0]), kind='x'),
         )
         q = translate_indexer((slice(None), slice(None), slice(None)), axes)
         # full slices ⇒ no narrowing query params
         assert 'bbox' not in q or q['bbox'] == '10.0,40.0,11.0,41.0', q
         print('full-slice-ok', q)
         " 2>&1 | tee .sisyphus/evidence/task-8-full-slice.log
    Expected Result: prints "full-slice-ok ...", exit 0.
    Evidence: .sisyphus/evidence/task-8-full-slice.log

  Scenario: Subset slice produces narrowed bbox + datetime
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         import numpy as np
         from edr_xarray.indexer import translate_indexer, AxisInfo
         axes = (
             AxisInfo(name='time', values=np.array(['2025-01-01T00:00:00','2025-01-02T00:00:00','2025-01-03T00:00:00'], dtype='datetime64[ns]'), kind='t'),
             AxisInfo(name='y', values=np.array([40.0,41.0,42.0]), kind='y'),
             AxisInfo(name='x', values=np.array([10.0,11.0,12.0]), kind='x'),
         )
         q = translate_indexer((slice(0,2), slice(0,2), slice(1,3)), axes)
         assert q['bbox'] == '11.0,40.0,12.0,41.0', q
         assert q['datetime'].startswith('2025-01-01') and 'T' in q['datetime'] and '/' in q['datetime'], q
         print('subset-slice-ok', q)
         " 2>&1 | tee .sisyphus/evidence/task-8-subset.log
    Expected Result: prints "subset-slice-ok ...", exit 0.
    Evidence: .sisyphus/evidence/task-8-subset.log

  Scenario: 4D with z scalar index
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         import numpy as np
         from edr_xarray.indexer import translate_indexer, AxisInfo
         axes = (
             AxisInfo(name='time', values=np.array(['2025-01-01T00:00:00'], dtype='datetime64[ns]'), kind='t'),
             AxisInfo(name='z',    values=np.array([1000.0, 850.0, 500.0]), kind='z'),
             AxisInfo(name='y',    values=np.array([40.0, 41.0]), kind='y'),
             AxisInfo(name='x',    values=np.array([10.0, 11.0]), kind='x'),
         )
         q = translate_indexer((0, 1, slice(None), slice(None)), axes)
         assert q.get('z') == '850.0', q
         print('z-int-ok', q)
         " 2>&1 | tee .sisyphus/evidence/task-8-z.log
    Expected Result: prints "z-int-ok ...".
    Evidence: .sisyphus/evidence/task-8-z.log

  Scenario: Pytest suite
    Tool: Bash
    Steps:
      1. uv run pytest tests/test_indexer.py -v --cov=src/edr_xarray/indexer 2>&1 | tee .sisyphus/evidence/task-8-pytest.log
    Expected Result: ≥10 tests pass, coverage ≥ 95%.
    Evidence: .sisyphus/evidence/task-8-pytest.log
  ```

  **Commit**: YES
  - Message: `feat(indexer): translate xarray ExplicitIndexer to EDR query params`
  - Files: `src/edr_xarray/indexer.py`, `tests/test_indexer.py`
  - Pre-commit: `uv run pytest tests/test_indexer.py && uv run ruff check src tests && uv run mypy --strict src/edr_xarray/indexer.py`

- [x] 9. **HTTP transport with error mapping & session ownership (`transport.py`)**

  **What to do**:
  - Create `src/edr_xarray/transport.py` with a small wrapper around `httpx.Client` enforcing error mapping, session ownership, and pickle safety.
  - Class `Transport`:
    - `__init__(self, *, session: httpx.Client | None = None, timeout: float = 30.0)`. If `session` provided: `self._session = session`, `self._owns = False`. Else: `self._session = httpx.Client(timeout=timeout)`, `self._owns = True`.
    - `request(self, method: str, url: str, *, params: Mapping[str, str] | None = None, headers: Mapping[str, str] | None = None) -> httpx.Response`:
      - Calls `self._session.request(method, url, params=params, headers=headers)`.
      - Wraps `httpx.RequestError` → `EdrServerError(f"network error: {exc}", url=url) from exc`.
      - On non-2xx response: parse `application/problem+json` body if present (extract `detail` field as message) and raise `EdrServerError(message, status_code=response.status_code, url=str(response.request.url))` from the underlying `httpx.HTTPStatusError`. Use `response.raise_for_status()` to trigger.
      - Returns the raw `httpx.Response` on success — caller does `.json()` or other parsing.
      - This is the LOW-LEVEL hook that `EdrDataStore._request` delegates to. Subclasses overriding `_request` see this Response shape.
    - `get_json(self, url: str, params: Mapping[str, str] | None = None, headers: Mapping[str, str] | None = None) -> dict`:
      - Convenience wrapper: `response = self.request("GET", url, params=params, headers=headers); return response.json()`.
      - JSON parse error → `EdrServerError("non-JSON response", url=url) from exc`.
      - Used by tests directly, but production code paths flow through `request(...)` so subclasses can intercept Response objects.
    - `close(self) -> None`: only closes `self._session` if `self._owns`. Idempotent.
    - `__enter__/__exit__` for context-manager support (calls `close`).
    - `__getstate__(self) -> dict`: returns dict with `session=None`, `_owns=False` (drop session).
    - `__setstate__(self, state: dict) -> None`: restore state with default fresh httpx.Client (but `_owns=False` because the original owner was elsewhere; safer to set `_owns=True` when reconstructing — DOCUMENT this behavior in docstring).

      **Decision**: On unpickle, create a fresh client and set `_owns=True`. Tests verify pickle round-trip works without leaking the original client.
  - Tests written first:
    - Owned session: `Transport()` then `t.close()` — internal client is closed. `Transport()` then `__exit__` — internal client closed.
    - Injected session: `Transport(session=external_client)` then `t.close()` — external client NOT closed.
    - `request("GET", url)` returns `httpx.Response` on 200; caller can `.json()`, `.headers`, `.status_code`.
    - 200 happy: pytest-httpserver returns `{"x": 1}` → `t.get_json(url)` returns `{"x": 1}`; `t.request("GET", url).json()` returns `{"x": 1}`.
    - 404 via `request(...)` → `EdrServerError(status_code=404, url=...)`.
    - 500 with problem-details body via `request(...)` → `EdrServerError` with detail message.
    - 200 but invalid JSON via `get_json(...)` → `EdrServerError("non-JSON response", ...)`.
    - Network error (server unreachable) via `request(...)` → `EdrServerError`, `__cause__` is `httpx.ConnectError` (or RequestError).
    - Pickle round-trip: `pickle.dumps(t); t2 = pickle.loads(blob); assert t2 is not t and t2._session is not t._session`.
    - Headers passed through: register an httpserver expectation for `Authorization: Bearer XYZ` header → `t.request("GET", url, headers={"Authorization": "Bearer XYZ"})` succeeds.

  **Must NOT do**:
  - ❌ NO retry logic.
  - ❌ NO async client (sync only in v1).
  - ❌ NO logging of response bodies (could leak credentials).
  - ❌ NO connection pooling tuning (httpx defaults).
  - ❌ NO closing of injected session in any case (including __exit__).

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Several edge cases (ownership flag, problem-details, pickle), warrants extra rigor.
  - **Skills**: []
    - None needed.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T8, T10, T11)
  - **Blocks**: T12 (array uses transport), T13 (store uses transport)
  - **Blocked By**: T2 (errors)

  **References**:

  *Pattern References*:
  - tensogram-xarray `array.py.__getstate__/__setstate__` — pattern for dropping non-pickleable session state. Adapt to httpx.

  *API/Type References*:
  - https://www.python-httpx.org/api/#client — `httpx.Client` API. Specifically `raise_for_status()`, `request.url`, `RequestError`.
  - RFC 7807 Problem Details: https://www.rfc-editor.org/rfc/rfc7807 — body shape we may receive on errors.

  *External References*:
  - https://pytest-httpserver.readthedocs.io/en/latest/howto.html#handle-requests-using-handlers — how to register response patterns including 4xx/5xx in tests.

  *WHY Each Reference Matters*:
  - httpx Client API: Need to know `raise_for_status` semantics — it throws `HTTPStatusError`, NOT `RequestError`. Our wrapper must catch both base classes.
  - RFC 7807: firecube's error responses use this content type; our error mapping should extract the `detail` field for clearer messages.

  **Acceptance Criteria**:

  *TDD*:
  - [ ] Tests first → fail.
  - [ ] Implementation → all pass.
  - [ ] `uv run mypy --strict src/edr_xarray/transport.py` clean.
  - [ ] Coverage ≥ 95%.

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Owned session is closed on Transport.close()
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         from edr_xarray.transport import Transport
         t = Transport()
         assert t._owns is True
         assert not t._session.is_closed
         t.close()
         assert t._session.is_closed
         t.close()  # idempotent
         print('owned-close-ok')
         " 2>&1 | tee .sisyphus/evidence/task-9-owned-close.log
    Expected Result: prints "owned-close-ok", exit 0.
    Evidence: .sisyphus/evidence/task-9-owned-close.log

  Scenario: Injected session is NOT closed
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         import httpx
         from edr_xarray.transport import Transport
         external = httpx.Client()
         t = Transport(session=external)
         assert t._owns is False
         t.close()
         assert not external.is_closed, 'injected session must not be closed'
         external.close()
         print('injected-not-closed-ok')
         " 2>&1 | tee .sisyphus/evidence/task-9-injected.log
    Expected Result: prints "injected-not-closed-ok".
    Evidence: .sisyphus/evidence/task-9-injected.log

  Scenario: 404 raises EdrServerError with status code and URL
    Tool: Bash (pytest with httpserver fixture)
    Steps:
      1. uv run pytest tests/test_transport.py::test_404_maps_to_edr_server_error -v 2>&1 | tee .sisyphus/evidence/task-9-404.log
    Expected Result: test passes; assertion checks status_code=404 and url present in exception.
    Evidence: .sisyphus/evidence/task-9-404.log

  Scenario: Pickle round-trip preserves transport state
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         import pickle
         from edr_xarray.transport import Transport
         t = Transport()
         blob = pickle.dumps(t)
         t2 = pickle.loads(blob)
         assert t2 is not t
         assert t2._session is not t._session
         t.close(); t2.close()
         print('pickle-ok')
         " 2>&1 | tee .sisyphus/evidence/task-9-pickle.log
    Expected Result: prints "pickle-ok".
    Evidence: .sisyphus/evidence/task-9-pickle.log

  Scenario: Pytest suite
    Tool: Bash
    Steps:
      1. uv run pytest tests/test_transport.py -v --cov=src/edr_xarray/transport 2>&1 | tee .sisyphus/evidence/task-9-pytest.log
    Expected Result: ≥8 tests pass, coverage ≥ 95%.
    Evidence: .sisyphus/evidence/task-9-pytest.log
  ```

  **Commit**: YES
  - Message: `feat(transport): wrap httpx.Client with error mapping and session ownership`
  - Files: `src/edr_xarray/transport.py`, `tests/test_transport.py`
  - Pre-commit: `uv run pytest tests/test_transport.py && uv run ruff check src tests && uv run mypy --strict src/edr_xarray/transport.py`

- [x] 10. **Coord discovery strategies (`discovery.py`)**

  **What to do**:
  - Create `src/edr_xarray/discovery.py` with three discovery strategies callable as functions returning `tuple[AxisInfo, ...]` (or raising).
  - Define `Literal["probe","metadata_only","strict"]` type alias `DiscoveryMode`.
  - Define `RequestCallable = Callable[..., httpx.Response]` — the type of the request hook the store exposes.
  - Function `discover_axes(metadata: CollectionMetadata, *, mode: DiscoveryMode, request_callable: RequestCallable, cube_url: str, instance: str | None) -> tuple[AxisInfo, ...]`:
    - **Important**: `request_callable` is passed in (NOT a Transport). This allows the store to pass `self._request` so the probe flows through subclass-overridable hooks. In tests, you can pass any callable matching `(method, url, *, params=None, headers=None) -> httpx.Response`.
    - **`mode="metadata_only"`**:
      - Time axis from `metadata.temporal.values` if present (datetime64 array). Else `(start, end)` 2-element array.
      - Vertical axis from `metadata.vertical.values` if present. Else from `(start, end)` 2-element array if `vertical.interval` present.
      - Spatial axes: from `metadata.spatial.bbox` use `(lon_min, lon_max)` 2-element x-axis and `(lat_min, lat_max)` 2-element y-axis. Coords are bounding values only — sufficient to define `dims` but no resolution.
      - **MUST NOT call `request_callable`.**
    - **`mode="strict"`**:
      - REQUIRES `metadata.temporal.values` (full timestamp list) AND collection metadata to advertise spatial coord arrays via a custom extension field `extent.spatial.values_x`/`values_y` (proposed convention). If absent, raise `EdrMetadataError("strict mode requires explicit coordinate values in metadata; got only bbox")`.
      - **MUST NOT call `request_callable`.**
    - **`mode="probe"`** (default):
      - Calls `response = request_callable("GET", cube_url, params={"bbox": encode_bbox(metadata.spatial.bbox), "datetime": encode_datetime(metadata.temporal.interval[0]), "parameter-name": list(metadata.parameters.keys())[0], "f": "CoverageJSON"})`.
      - `payload = response.json()` (JSON parse → `EdrCoverageJsonError`).
      - Note: probe uses minimum spatial extent (full bbox) with single first instant — server returns CoverageJSON with axes describing the FULL grid (same axes shape regardless of single-time vs multi-time queries).
      - Parse the response with `parse_coverage(...)`.
      - Construct AxisInfo from `cov.axes` honoring `cov.axis_names` order. Time axis values from `metadata.temporal.values` if available (richer than single-instant from probe), else from probe's t axis.
      - Returns the tuple in the same order as `cov.axis_names`.
  - Function `axis_kind(name: str) -> Literal["x","y","z","t"]`:
    - Maps EDR axis name conventions: `"x"|"lon"|"longitude"` → `"x"`; `"y"|"lat"|"latitude"` → `"y"`; `"z"|"level"|"pressure"|"height"|"depth"` → `"z"`; `"t"|"time"` → `"t"`. Case-insensitive.
    - Unknown name → `EdrCoverageJsonError(f"axis name {name} could not be classified as x/y/z/t")`.
  - Tests written first (use a `MagicMock` `request_callable` — no real Transport needed):
    - **probe mode**: pass a `request_callable` that returns a fake `httpx.Response` (use `httpx.Response(200, json=cov_grid_3d_payload)`) → assert axes returned with correct names, values, kinds.
    - **probe mode**: probe response with 4D (z axis present) → axes include z.
    - **probe mode**: `request_callable` raises `EdrServerError` → propagated as-is.
    - **probe mode**: probe response with non-Grid → `EdrUnsupportedFeatureError` (propagated from coveragejson parser).
    - **probe mode**: assert `request_callable` called exactly ONCE with expected positional args (`"GET"`, `cube_url`) and expected `params=` dict.
    - **metadata_only mode**: metadata with `temporal.values` and bbox → returns 3 axes; spatial axes have 2 values each (bbox endpoints). `request_callable` NOT called (assert call_count == 0).
    - **metadata_only mode**: metadata without `temporal.values` → spatial+temporal axes from intervals (2 elements each). `request_callable` NOT called.
    - **strict mode** without enriched metadata → `EdrMetadataError`. `request_callable` NOT called.
    - **strict mode** with hypothetical enriched metadata (test fixture defines `extent.spatial.values_x = [10.0, 10.5, 11.0]`) → returns full coord arrays.
    - `axis_kind`: cases for `"x"`, `"longitude"`, `"LON"`, `"y"`, `"latitude"`, `"z"`, `"pressure"`, `"t"`, `"time"`. Unknown → raises.

  **Must NOT do**:
  - ❌ NO probe in `metadata_only` or `strict` modes — they must NOT call transport.
  - ❌ NO arbitrary multiple cube probes; one probe maximum in `probe` mode.
  - ❌ NO assumption about which axes appear (could be 2D, 3D, 4D — handle all three).
  - ❌ NO blocking on temporal.values to be a long list — single-element is allowed.

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Multiple strategies with different correctness invariants; needs careful reasoning about laziness contract.
  - **Skills**: []
    - None needed.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T8, T9, T11)
  - **Blocks**: T13 (store uses discovery)
  - **Blocked By**: T3 (coveragejson — for parse_coverage), T4 (metadata — for CollectionMetadata type). Does NOT depend on T9 directly: takes a `request_callable` argument typed as `Callable[..., httpx.Response]`, decoupling it from the Transport class.

  **References**:

  *Pattern References*:
  - tensogram-xarray `src/tensogram_xarray/coords.py:detect_coords` — pattern for detecting which objects are coords vs data via name. We adapt similar name-detection in `axis_kind`.

  *API/Type References*:
  - EDR axis name conventions: https://docs.ogc.org/is/19-086r6/19-086r6.html#req_edr_rc-cube — common axis labels (`x`, `y`, `z`, `t`).
  - CoverageJSON axis spec: https://covjson.org/spec/#axes-objects

  *WHY Each Reference Matters*:
  - tensogram's name detection: Provides a known-good list of axis name aliases (lat/longitude/etc.) — copy and extend.
  - EDR + CoverageJSON specs: Authoritative on which axis names are conventional.

  **Acceptance Criteria**:

  *TDD*:
  - [ ] Tests first → fail.
  - [ ] After impl: ≥10 tests pass.
  - [ ] mypy strict clean.
  - [ ] Coverage ≥ 95%.

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Probe mode discovers axes via single HTTP call
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_discovery.py::test_probe_mode_returns_axes_from_single_http_call -v 2>&1 | tee .sisyphus/evidence/task-10-probe.log
    Expected Result: test passes; assertion checks axes returned AND request count == 1.
    Evidence: .sisyphus/evidence/task-10-probe.log

  Scenario: metadata_only mode does NOT call transport
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_discovery.py::test_metadata_only_does_not_call_transport -v 2>&1 | tee .sisyphus/evidence/task-10-md-only.log
    Expected Result: test passes; assertion checks request count == 0.
    Evidence: .sisyphus/evidence/task-10-md-only.log

  Scenario: strict mode raises when metadata insufficient
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_discovery.py::test_strict_mode_raises_when_no_explicit_coord_values -v 2>&1 | tee .sisyphus/evidence/task-10-strict.log
    Expected Result: test passes; raises EdrMetadataError.
    Evidence: .sisyphus/evidence/task-10-strict.log

  Scenario: axis_kind classifies common names + rejects unknown
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         from edr_xarray.discovery import axis_kind
         from edr_xarray.errors import EdrCoverageJsonError
         for name, kind in [('x','x'),('lon','x'),('LONGITUDE','x'),('y','y'),('lat','y'),('z','z'),('pressure','z'),('t','t'),('time','t')]:
             assert axis_kind(name) == kind, f'{name} -> {axis_kind(name)} != {kind}'
         try:
             axis_kind('foo')
             print('FAIL')
         except EdrCoverageJsonError:
             pass
         print('axis-kind-ok')
         " 2>&1 | tee .sisyphus/evidence/task-10-axis-kind.log
    Expected Result: prints "axis-kind-ok".
    Evidence: .sisyphus/evidence/task-10-axis-kind.log

  Scenario: Pytest suite
    Tool: Bash
    Steps:
      1. uv run pytest tests/test_discovery.py -v --cov=src/edr_xarray/discovery 2>&1 | tee .sisyphus/evidence/task-10-pytest.log
    Expected Result: ≥10 tests pass, coverage ≥ 95%.
    Evidence: .sisyphus/evidence/task-10-pytest.log
  ```

  **Commit**: YES
  - Message: `feat(discovery): add probe/metadata_only/strict coord discovery strategies`
  - Files: `src/edr_xarray/discovery.py`, `tests/test_discovery.py`
  - Pre-commit: `uv run pytest tests/test_discovery.py && uv run ruff check src tests && uv run mypy --strict src/edr_xarray/discovery.py`

- [x] 11. **Variable & Coordinates builder (`builder.py`)**

  **What to do**:
  - Create `src/edr_xarray/builder.py` that, given parsed metadata + discovered axes + a function that produces a per-parameter `BackendArray`, assembles `dict[str, xr.Variable]` for both data variables and coordinate variables, plus a global `attrs` dict.
  - Function `build_coord_variables(axes: tuple[AxisInfo, ...], metadata: CollectionMetadata) -> dict[str, xr.Variable]`:
    - For each axis, create `xr.Variable(dims=(name,), data=axis.values, attrs={...})`.
    - Coord attrs:
      - x: `{"axis": "X", "long_name": "longitude", "units": "degrees_east", "standard_name": "longitude"}` (when `axis.kind=="x"`).
      - y: `{"axis": "Y", "long_name": "latitude", "units": "degrees_north", "standard_name": "latitude"}`.
      - z: `{"axis": "Z", "long_name": "vertical", "units": metadata.vertical.vrs or ""}`.
      - t: `{"axis": "T", "long_name": "time", "standard_name": "time"}` — units omitted (xarray decodes from datetime64 dtype).
  - Function `build_data_variables(metadata: CollectionMetadata, axes: tuple[AxisInfo, ...], make_backend_array: Callable[[str, tuple[int, ...]], BackendArray]) -> dict[str, xr.Variable]`:
    - For each parameter in `metadata.parameters`:
      - Compute `shape = tuple(len(a.values) for a in axes)` (default — ALL parameters share the same axes; v1 assumption).
      - Compute `dims = tuple(a.name for a in axes)`.
      - Build attrs: `{"units": p.unit, "standard_name": p.standard_name, "long_name": p.long_name, "cell_methods": p.cell_methods}` — drop None values.
      - Create `backend_array = make_backend_array(parameter_id, shape)`.
      - Wrap: `data = xr.core.indexing.LazilyIndexedArray(backend_array)`.
      - Set `encoding["preferred_chunks"]` heuristically: if any axis is time and has ≥4 timesteps, set `{"time": 1}`; else `{}` (single chunk).
      - Build `xr.Variable(dims=dims, data=data, attrs=attrs, encoding=encoding)`.
    - Returns dict `{parameter_id: variable}`.
  - Function `build_global_attrs(metadata: CollectionMetadata) -> dict[str, Any]`:
    - Returns CF-conventional global attrs:
      - `title` from metadata.title.
      - `summary` from metadata.description.
      - `Conventions = "CF-1.10"`.
      - `keywords` from metadata.title (best-effort).
      - `institution` not set (would be added later via metadata extension).
    - Drop None values.
  - Tests written first:
    - 3D coords: x/y/t axes → 3 coord variables with correct attrs (longitude/latitude/time).
    - 4D coords: x/y/z/t → z coord has axis="Z".
    - Data variable shape matches axis lengths.
    - Data variable attrs include units, standard_name, long_name when present in metadata.
    - Data variable encoding[preferred_chunks] set when time has ≥4 steps.
    - Data variable encoding empty when time has <4 steps.
    - Global attrs include title and summary; None values dropped.
    - Lazy: BackendArray's `__getitem__` is NOT called during build (assert via mock that records calls).

  **Must NOT do**:
  - ❌ NO calling backend_array.__getitem__ during build (preserves laziness).
  - ❌ NO assumption that all variables share the same axes — but in v1 we DO assume this. Document the assumption clearly; future enhancement can per-parameter axes.
  - ❌ NO computing CF unit conversions — pass through unit strings as-is.

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Multi-step assembly involving xarray internals (Variable, encoding, LazilyIndexedArray) — careful TDD needed.
  - **Skills**: []
    - None needed.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T8, T9, T10)
  - **Blocks**: T13 (store uses builder)
  - **Blocked By**: T3 (coveragejson), T4 (metadata)

  **References**:

  *Pattern References*:
  - tensogram-xarray `src/tensogram_xarray/store.py:build_dataset` — assembling dict of Variables with LazilyIndexedArray. Same pattern adapted to EDR.
  - xarray `xarray/backends/store.py:open_dataset` — how a builtin backend constructs Coordinates and Dataset. Lines 20-73 are the canonical pattern.

  *API/Type References*:
  - `xarray.core.indexing.LazilyIndexedArray` — constructor signature.
  - `xarray.Variable(dims, data, attrs, encoding)` — constructor.
  - `xarray.Coordinates(coord_vars, indexes={})` — Coordinates constructor for empty-indexes mode.

  *External References*:
  - CF Conventions 1.10: https://cfconventions.org/Data/cf-conventions/cf-conventions-1.10/cf-conventions.html — reference for `standard_name`, `axis`, `long_name`, `units`.

  *WHY Each Reference Matters*:
  - xarray store.py: The canonical builtin backend assembly logic. We're not reimplementing — we're paralleling its structure.
  - CF Conventions: Standard attrs that downstream tools (like cartopy plotting) expect. Setting them right makes the Dataset useful out of the box.

  **Acceptance Criteria**:

  *TDD*:
  - [ ] Tests first → fail.
  - [ ] Coverage ≥ 95%; ≥10 tests.
  - [ ] mypy strict clean.

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Builder produces a Dataset-ready dict without fetching data
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         import numpy as np, xarray as xr
         from edr_xarray.builder import build_coord_variables, build_data_variables, build_global_attrs
         from edr_xarray.discovery import AxisInfo
         from edr_xarray.metadata import CollectionMetadata, SpatialExtent, TemporalExtent, ParameterDefinition, CubeLink
         class FakeArray:
             call_count = 0
             def __init__(self, name, shape):
                 self.shape = shape; self.dtype = np.float64; self.name = name
             def __getitem__(self, key):
                 FakeArray.call_count += 1
                 return np.zeros(self.shape, dtype=self.dtype)
         meta = CollectionMetadata(
             id='c', title='t', description='d',
             spatial=SpatialExtent(bbox=(10.,40.,11.,41.), crs=None),
             temporal=TemporalExtent(interval=('2025-01-01T00:00:00Z','2025-01-01T00:00:00Z'), values=('2025-01-01T00:00:00Z',)),
             vertical=None, crs_options=('CRS84',),
             parameters={'temp': ParameterDefinition(id='temp', unit='K', standard_name='air_temperature', long_name='Air Temperature', cell_methods=None)},
             cube_link=CubeLink(href='http://srv/cube', output_formats=('CoverageJSON',), default_output_format='CoverageJSON', crs_options=('CRS84',)),
             instances_link=None,
         )
         axes = (
             AxisInfo(name='time', values=np.array(['2025-01-01T00:00:00'], dtype='datetime64[ns]'), kind='t'),
             AxisInfo(name='y', values=np.array([40.0,41.0]), kind='y'),
             AxisInfo(name='x', values=np.array([10.0,11.0]), kind='x'),
         )
         coords = build_coord_variables(axes, meta)
         data_vars = build_data_variables(meta, axes, lambda n, s: FakeArray(n, s))
         attrs = build_global_attrs(meta)
         ds = xr.Dataset(data_vars, coords=xr.Coordinates(coords, indexes={}), attrs=attrs)
         assert FakeArray.call_count == 0, f'lazy violated: __getitem__ called {FakeArray.call_count} times'
         assert ds['temp'].dims == ('time','y','x'), ds['temp'].dims
         assert ds['temp'].attrs['units'] == 'K'
         assert ds.coords['x'].attrs['axis'] == 'X'
         print('builder-lazy-ok', dict(ds.dims), list(ds.data_vars))
         " 2>&1 | tee .sisyphus/evidence/task-11-builder.log
    Expected Result: prints "builder-lazy-ok ...", exit 0.
    Evidence: .sisyphus/evidence/task-11-builder.log

  Scenario: preferred_chunks set when time axis is long
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         import numpy as np
         from edr_xarray.builder import build_data_variables
         from edr_xarray.discovery import AxisInfo
         from edr_xarray.metadata import CollectionMetadata, SpatialExtent, TemporalExtent, ParameterDefinition, CubeLink
         class FakeArray:
             def __init__(self, n, s): self.shape=s; self.dtype=np.float64
             def __getitem__(self, k): return np.zeros(self.shape)
         meta = CollectionMetadata(id='c', title=None, description=None,
             spatial=SpatialExtent(bbox=(0.,0.,1.,1.), crs=None),
             temporal=TemporalExtent(interval=('2025-01-01','2025-01-05'), values=tuple(f'2025-01-0{i}T00:00:00Z' for i in range(1,6))),
             vertical=None, crs_options=(),
             parameters={'p': ParameterDefinition(id='p', unit=None, standard_name=None, long_name=None, cell_methods=None)},
             cube_link=CubeLink(href='', output_formats=(), default_output_format=None, crs_options=()),
             instances_link=None)
         axes = (
             AxisInfo(name='time', values=np.array([f'2025-01-0{i}T00:00:00' for i in range(1,6)], dtype='datetime64[ns]'), kind='t'),
             AxisInfo(name='y', values=np.array([0.0,1.0]), kind='y'),
             AxisInfo(name='x', values=np.array([0.0,1.0]), kind='x'),
         )
         dv = build_data_variables(meta, axes, lambda n, s: FakeArray(n, s))
         assert dv['p'].encoding.get('preferred_chunks') == {'time': 1}, dv['p'].encoding
         print('preferred-chunks-ok')
         " 2>&1 | tee .sisyphus/evidence/task-11-chunks.log
    Expected Result: prints "preferred-chunks-ok".
    Evidence: .sisyphus/evidence/task-11-chunks.log

  Scenario: Pytest suite
    Tool: Bash
    Steps:
      1. uv run pytest tests/test_builder.py -v --cov=src/edr_xarray/builder 2>&1 | tee .sisyphus/evidence/task-11-pytest.log
    Expected Result: ≥10 tests pass, coverage ≥ 95%.
    Evidence: .sisyphus/evidence/task-11-pytest.log
  ```

  **Commit**: YES
  - Message: `feat(builder): construct xr.Variable and Coordinates from EDR metadata`
  - Files: `src/edr_xarray/builder.py`, `tests/test_builder.py`
  - Pre-commit: `uv run pytest tests/test_builder.py && uv run ruff check src tests && uv run mypy --strict src/edr_xarray/builder.py`

- [x] 12. **EdrBackendArray with lazy `__getitem__` + pickle support (`array.py`)**

  **What to do**:
  - Create `src/edr_xarray/array.py` with `EdrBackendArray(BackendArray)` from xarray. Crucially, **all cube fetches MUST flow through the store's documented hooks** (`_request`, `_translate_indexer`, `_parse_coveragejson`) so subclasses overriding hooks see every cube call. The BackendArray holds a back-reference to the store.
  - Constructor signature:
    - `__init__(self, *, store: EdrDataStore, cube_url: str, parameter_id: str, axes: tuple[AxisInfo, ...], shape: tuple[int, ...], dtype: np.dtype, extra_query_params: Mapping[str, str] | None = None) -> None`.
    - `__slots__ = ("_store", "_cube_url", "_parameter_id", "_axes", "_shape", "_dtype", "_extra_query_params")`.
  - `@property shape -> tuple[int, ...]`: returns `self._shape`.
  - `@property dtype -> np.dtype`: returns `self._dtype`.
  - `__getitem__(self, key: indexing.ExplicitIndexer) -> np.ndarray`:
    - `return indexing.explicit_indexing_adapter(key, self.shape, indexing.IndexingSupport.BASIC, self._raw_indexing_method)`.
  - `_raw_indexing_method(self, key: tuple) -> np.ndarray`:
    1. `query_params = dict(self._store._translate_indexer(key, self._axes))` — **routes through hook** so subclasses can customize slicing semantics.
    2. Merge with `self._extra_query_params` (extra wins for static keys like `f`, `crs`).
    3. Always include `parameter-name=self._parameter_id` and `f=CoverageJSON` (unless extra overrides `f`).
    4. `response = self._store._request("GET", self._cube_url, params=query_params)` — **routes through hook** so subclasses can inject auth headers / sign requests / etc. Returns `httpx.Response`.
    5. `payload = response.json()` — JSON parse error → wrap into `EdrCoverageJsonError(...)`.
    6. `cov = self._store._parse_coveragejson(payload)` — **routes through hook** so subclasses can handle server-specific CoverageJSON extensions.
    7. `arr = cov.ranges[self._parameter_id]` — KeyError → `EdrCoverageJsonError(f"server returned no range for parameter {self._parameter_id}")`.
    8. **Axis order**: if `cov.axis_names` differs from `tuple(a.name for a in self._axes)`, compute permutation and `arr = np.transpose(arr, axes=permutation)`. Honors CoverageJSON `axisNames`.
    9. **Shape validation**: compute `expected_shape` from `key` applied to `self._shape` (using stdlib `numpy.s_` slicing on a placeholder); if `arr.shape != expected_shape`, raise `EdrCoverageJsonError(f"server returned shape {arr.shape}, expected {expected_shape}")`.
    10. Return `arr`.
  - `__getstate__(self) -> dict[str, Any]`: returns a dict containing every slot value. The `_store` reference IS preserved (its own `__getstate__` drops the unpickleable session), so the array remains functional after unpickling on a Dask worker — it will hit the EDR server via a freshly-created Transport.
  - `__setstate__(self, state: dict[str, Any]) -> None`: restores all slots from `state` directly. No special handling — the store has already handled session reconstruction via its own `__setstate__`.

  - Tests written first (`tests/test_array.py`):
    - `EdrBackendArray.shape/dtype` accessible without calling __getitem__.
    - `__getitem__` with full-slice key fetches CoverageJSON via store hooks; returns ndarray of expected shape + values.
    - **Hook routing**: instantiate a real EdrDataStore subclass that wraps each hook in `unittest.mock.MagicMock(wraps=original)`. Trigger `arr[BasicIndexer((slice(None),)*ndim)]`. Assert `_translate_indexer.called`, `_request.called`, `_parse_coveragejson.called` — proving cube fetches route through hooks.
    - `__getitem__` with subset slice (e.g., `(slice(0,1), slice(None), slice(None))`) issues query with bbox/datetime narrowed (verified via httpserver request log).
    - `__getitem__` with int key on time axis returns a 2D array (time dim collapsed).
    - Axis transposition: mock CoverageJSON with `axisNames=["x","y","t"]` while `_axes=(t,y,x)` → returned array is transposed to `(t,y,x)` order; values verifiable.
    - Error path: server returns 500 → `EdrServerError` propagates (raised by Transport, surfaced through `_request` hook).
    - Error path: server returns CoverageJSON with shape mismatch → `EdrCoverageJsonError`.
    - Error path: server returns CoverageJSON missing requested parameter range → `EdrCoverageJsonError`.
    - Pickle: `pickle.dumps(arr); arr2 = pickle.loads(blob)` — `arr2._store` is restored; `arr2._store._transport` has a fresh httpx.Client; `arr2.shape == arr.shape`; `arr2[BasicIndexer((slice(None),)*ndim)]` works against the same mock URL.
    - `IndexingSupport.BASIC` enforced: vectorized indexing (numpy array as key) is decomposed by xarray's adapter — verify by exercising `arr[indexing.OuterIndexer((np.array([0,1]),))]` and confirming it works through the adapter.
    - LazilyIndexedArray wrapping: `arr_lazy = LazilyIndexedArray(arr); arr_lazy.shape == arr.shape; arr_lazy[BasicIndexer((slice(None),)*ndim)]` triggers fetch.

  **Must NOT do**:
  - ❌ NO eager fetch in `__init__`.
  - ❌ NO support for vectorized indexing (rely on adapter for decomposition).
  - ❌ NO retry on transient errors.
  - ❌ NO local caching of fetched arrays — every `__getitem__` issues a new request (lazy from xarray's perspective; xarray itself caches via LazilyIndexedArray's IndexCallable).
  - ❌ NO use of `np.copy` after parse — `parse_coverage` already returns owned arrays.
  - ❌ NO calling module-level `translate_indexer`, `parse_coverage`, or `Transport.request/get_json` directly. Cube fetches MUST flow through `self._store._translate_indexer`, `self._store._request`, `self._store._parse_coveragejson` — that's the subclass extension contract.

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Core lazy-fetch logic with multiple interacting concerns (indexing, transposition, pickle, hook plumbing, error mapping). High-stakes correctness.
  - **Skills**: []
    - None needed.

  **Parallelization**:
  - **Can Run In Parallel**: YES (with caveat — see below)
  - **Parallel Group**: Wave 3 (with T13)
  - **Blocks**: T14 (entrypoint constructs arrays via store)
  - **Blocked By**: T3 (coveragejson types), T8 (indexer functions used by store hooks), T9 (transport — Response shape).
  - **Coupling note**: T12 and T13 reference each other (BackendArray takes store back-ref; store constructs BackendArrays). To enable parallel execution: T12 imports `EdrDataStore` only under `if TYPE_CHECKING:` (forward reference). At runtime the store is duck-typed (any object exposing `_translate_indexer`, `_request`, `_parse_coveragejson`). T12's tests construct a `unittest.mock.MagicMock` with those three methods — no dependency on T13's concrete class. T13's tests use T12's concrete `EdrBackendArray` class (so T13 should be scheduled to start after T12 has produced the class file, even though both are nominally "Wave 3").

  **References**:

  *Pattern References*:
  - tensogram-xarray `src/tensogram_xarray/array.py:TensogramBackendArray.__getitem__` and `_raw_indexing_method` — direct template. Same shape, different transport.
  - xarray `xarray/backends/zarr.py:ZarrArrayWrapper.__getitem__` (lines around `explicit_indexing_adapter` call) — confirms our use of `IndexingSupport.BASIC`.

  *API/Type References*:
  - `xarray.core.indexing.explicit_indexing_adapter(key, shape, support, raw_method)` — required signature.
  - `xarray.core.indexing.IndexingSupport.BASIC` — slice + int only.
  - `xarray.backends.BackendArray` — abstract base.
  - `numpy.transpose(arr, axes=permutation)` — for axis reorder.

  *Test References*:
  - tensogram-xarray `tests/test_array.py` — assertion patterns for lazy fetch and pickle.

  *WHY Each Reference Matters*:
  - tensogram's BackendArray: This is the closest-to-1:1 architectural match. Their tests confirm laziness + pickle + slicing math; we mirror.
  - xarray Zarr backend: Built-in baseline — confirms our use of IndexingSupport.BASIC is appropriate for a remote-array backend.

  **Acceptance Criteria**:

  *TDD*:
  - [ ] Tests first → fail.
  - [ ] After impl: ≥12 tests pass.
  - [ ] mypy strict clean.
  - [ ] Coverage ≥ 95%.

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Construction does NOT trigger HTTP
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_array.py::test_construction_does_not_trigger_http -v 2>&1 | tee .sisyphus/evidence/task-12-no-http-on-init.log
    Expected Result: test passes; assertion checks request count == 0 after constructor.
    Evidence: .sisyphus/evidence/task-12-no-http-on-init.log

  Scenario: __getitem__ triggers ONE HTTP fetch with translated query
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_array.py::test_getitem_subset_triggers_one_http_fetch -v 2>&1 | tee .sisyphus/evidence/task-12-getitem.log
    Expected Result: test passes; assertion checks: request count == 1; URL path matches cube_url; query params include bbox + datetime + parameter-name + f=CoverageJSON.
    Evidence: .sisyphus/evidence/task-12-getitem.log

  Scenario: Axis transposition honors CoverageJSON axisNames
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_array.py::test_axis_transposition -v 2>&1 | tee .sisyphus/evidence/task-12-transpose.log
    Expected Result: test passes; CoverageJSON returned with axisNames=["x","y","t"] but BackendArray declared axes (t,y,x); values transposed correctly.
    Evidence: .sisyphus/evidence/task-12-transpose.log

  Scenario: Pickle round-trip preserves array fetch capability
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_array.py::test_pickle_roundtrip -v 2>&1 | tee .sisyphus/evidence/task-12-pickle.log
    Expected Result: test passes; restored array can perform __getitem__ against the same mock.
    Evidence: .sisyphus/evidence/task-12-pickle.log

  Scenario: Pytest suite
    Tool: Bash
    Steps:
      1. uv run pytest tests/test_array.py -v --cov=src/edr_xarray/array 2>&1 | tee .sisyphus/evidence/task-12-pytest.log
    Expected Result: ≥12 tests pass, coverage ≥ 95%.
    Evidence: .sisyphus/evidence/task-12-pytest.log
  ```

  **Commit**: YES
  - Message: `feat(array): EdrBackendArray with lazy __getitem__ and pickle support`
  - Files: `src/edr_xarray/array.py`, `tests/test_array.py`
  - Pre-commit: `uv run pytest tests/test_array.py && uv run ruff check src tests && uv run mypy --strict src/edr_xarray/array.py`

- [x] 13. **EdrDataStore orchestrator with documented subclass hooks (`store.py`)**

  **What to do**:
  - Create `src/edr_xarray/store.py` with `EdrDataStore` class. NOT an xarray `AbstractDataStore` subclass — it's our own orchestrator.
  - Constructor: `__init__(self, *, collection_url: str, instance: str | None = None, parameter_names: list[str] | None = None, bbox: tuple[float, float, float, float] | None = None, datetime: str | None = None, crs: str | None = None, z: float | str | None = None, session: httpx.Client | None = None, discovery: DiscoveryMode = "probe", timeout: float = 30.0)`.
  - Stores all args; constructs `self._transport = Transport(session=session, timeout=timeout)`.
  - Method `build_dataset(self) -> xr.Dataset`:
    1. `response = self._request("GET", self.collection_url)` — uses hook; returns `httpx.Response`. Subclasses overriding `_request` see this Response (can inject headers, sign requests, etc.).
    2. `metadata_payload = response.json()` (JSON parse error → `EdrMetadataError("collection metadata is not valid JSON", url=self.collection_url) from exc`).
    3. `self._metadata = self._parse_collection_metadata(metadata_payload)`.
    4. `selected_format = self._negotiate_output_format(self._metadata.cube_link.output_formats)`.
    5. `self._cube_url = self._build_cube_url(self.collection_url, self.instance)`.
    6. `validated_crs = encode_crs(self.crs, self._metadata.cube_link.crs_options or self._metadata.crs_options)`.
    7. `axes = self._discover_axes(self._metadata)` — for `discovery="probe"` mode, this internally calls `self._request(...)` for the probe so subclasses see that fetch too.
    8. `extra = {"f": selected_format}` (+ `crs` if validated; + `z` if `self.z` provided via `encode_z`; + `datetime` if `self.datetime` via `encode_datetime`; + `bbox` if `self.bbox` via `encode_bbox`).
       Note: when user provides bbox/datetime/z explicitly at open time, those become STATIC subset filters applied to ALL fetches (further narrowed by indexing slices). The translator merges static + dynamic.
    9. `make_array = lambda parameter_id, shape: EdrBackendArray(store=self, cube_url=self._cube_url, parameter_id=parameter_id, axes=axes, shape=shape, dtype=np.float64, extra_query_params=extra)`. **Note**: array gets a back-reference to the store so `EdrBackendArray._raw_indexing_method` can call `self._store._translate_indexer/_request/_parse_coveragejson` — making cube fetches subject to subclass hook overrides.
    10. Filter parameters: if `self.parameter_names` is None → use all `self._metadata.parameters`; else filter to user list. If user lists an unknown param → `EdrMetadataError`.
    11. `data_vars = build_data_variables(filtered_metadata, axes, make_array)`.
    12. `coord_vars = build_coord_variables(axes, self._metadata)`.
    13. `attrs = build_global_attrs(self._metadata)`.
    14. `ds = xr.Dataset(data_vars, coords=xr.Coordinates(coord_vars, indexes={}), attrs=attrs)`.
    15. `ds.set_close(self.close)`.
    16. Return `ds`.
  - **Documented subclass hooks** (each is an instance method that subclasses can override):
    - `_request(self, method: str, url: str, *, params: Mapping[str, str] | None = None, headers: Mapping[str, str] | None = None) -> httpx.Response`: low-level HTTP. Default: `return self._transport.request(method, url, params=params, headers=headers)`. Override for custom auth signing, request shaping, server-specific retry. **Returns httpx.Response so subclasses can introspect status/headers.**
    - `_parse_collection_metadata(self, payload: dict) -> CollectionMetadata`: default delegates to `parse_collection_metadata(payload)`. Override to handle server-specific metadata extensions (e.g. firecube's `refresh` or extra fields).
    - `_negotiate_output_format(self, advertised: tuple[str, ...]) -> str`: default delegates to `negotiate_format(advertised)`. Override to prefer alternative formats (e.g. NetCDF when advertised in a future version).
    - `_build_cube_url(self, collection_url: str, instance: str | None) -> str`: default uses `cube_url(self._metadata, instance, base_url=collection_url)`. Override for non-standard instance URL shapes.
    - `_parse_coveragejson(self, payload: dict) -> CoverageData`: default delegates to `parse_coverage(payload)`. Override to handle server-specific CoverageJSON extensions.
    - `_translate_indexer(self, key: tuple, axes: tuple[AxisInfo, ...]) -> dict[str, str]`: default delegates to `translate_indexer(key, axes)`. Override for custom slicing semantics.
    - `_discover_axes(self, metadata: CollectionMetadata) -> tuple[AxisInfo, ...]`: default calls `discover_axes(metadata, mode=self.discovery, request_callable=self._request, cube_url=self._cube_url, instance=self.instance)`. **Note**: for probe mode, the underlying `discover_axes` function takes a `request_callable` parameter (a bound method) so the probe request also flows through `_request`. This means subclass overrides of `_request` (auth, headers, signing) automatically apply to the probe too. Override `_discover_axes` itself only for server-specific axis discovery beyond probe-customization.
  - Method `close(self) -> None`: closes `self._transport`. Idempotent.

  - **Pickle support**: `__getstate__` returns dict of all attrs except `_transport`. `__setstate__` restores attrs and creates a fresh `Transport()` (default-owned, default timeout). Subclasses with extra state should override and call super.
  - Tests written first (`tests/test_store.py`):
    - Happy path: register metadata + cube probe + cube subset endpoints; `EdrDataStore(...).build_dataset()` returns Dataset with expected dims/coords/data_vars.
    - `discovery="metadata_only"`: build_dataset triggers exactly ONE HTTP request (metadata only).
    - `discovery="probe"`: build_dataset triggers exactly TWO HTTP requests (metadata + probe).
    - Instance kwarg: `instance="f024"` produces requests against `/instances/f024/cube` URL.
    - parameter_names filter: only listed params appear as data_vars.
    - parameter_names with unknown name → `EdrMetadataError`.
    - Server returns metadata without CoverageJSON in advertised → `EdrUnsupportedFeatureError` from negotiate_format.
    - bbox kwarg passed at open propagates to subsequent cube fetches as static filter (visible in request log of mock).
    - `crs` kwarg with value not in `crs_options` → `EdrUnsupportedFeatureError`.
    - `z` kwarg with repeat syntax → `EdrUnsupportedFeatureError`.
    - close: closes owned transport; injected session not closed.
    - Subclass hook test (CRITICAL): a subclass `class MyStore(EdrDataStore): _build_cube_url = unittest.mock.Mock(return_value="http://other-host/cube")` — verify the mock is called and the cube URL used in fetches is the mocked one.
    - All hooks discoverable: `dir(EdrDataStore)` includes all 7 hook names.

  **Must NOT do**:
  - ❌ NO calling `__getitem__` on backend arrays during `build_dataset` (laziness).
  - ❌ NO firecube-specific assumptions in default hooks.
  - ❌ NO automatic conformance checking.
  - ❌ NO bypassing `_request`/`_parse_*` hooks — always go through them so subclasses can intercept.
  - ❌ NO storing the full metadata payload as a Dataset attr (could be huge); store only the parsed fields.

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Largest orchestration task. Many interacting hooks, careful TDD around override correctness, integration of all Wave-2 modules.
  - **Skills**: []
    - None needed.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with T12)
  - **Blocks**: T14 (entrypoint instantiates store)
  - **Blocked By**: T2 (errors), T4 (metadata), T9 (transport), T10 (discovery), T11 (builder)

  **References**:

  *Pattern References*:
  - tensogram-xarray `src/tensogram_xarray/store.py:TensogramDataStore` — class structure (orchestrator, `build_dataset`, `_open_file`, `close`).
  - xarray `xarray/backends/store.py:StoreBackendEntrypoint.open_dataset` (lines 20-73) — the canonical assembly flow.

  *API/Type References*:
  - `xr.Coordinates(coord_vars, indexes={})` — explicitly empty indexes (xarray creates default ones lazily).
  - `xr.Dataset.set_close(callable)` — callback fired when Dataset is closed.

  *Test References*:
  - tensogram-xarray `tests/test_backend.py` and `tests/test_remote.py` — patterns for testing orchestration logic and HTTP-mock-based integration tests respectively.

  *WHY Each Reference Matters*:
  - tensogram store.py: Direct template for the orchestrator pattern. We replicate the build sequence.
  - xarray store.py: Confirms `Coordinates(coord_vars, indexes={})` is the correct way to attach coords without forcing index creation.

  **Acceptance Criteria**:

  *TDD*:
  - [ ] Tests first → fail.
  - [ ] After impl: ≥15 tests pass.
  - [ ] mypy strict clean.
  - [ ] Coverage ≥ 95%.

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: build_dataset with discovery="probe" issues exactly 2 HTTP requests
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_store.py::test_probe_mode_two_requests -v 2>&1 | tee .sisyphus/evidence/task-13-probe-2req.log
    Expected Result: test passes; mock httpserver request log has exactly 2 entries: [metadata URL, cube probe URL].
    Evidence: .sisyphus/evidence/task-13-probe-2req.log

  Scenario: Subclass hook _build_cube_url is invoked
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_store.py::test_subclass_overrides_build_cube_url -v 2>&1 | tee .sisyphus/evidence/task-13-hook.log
    Expected Result: test passes; subclass's mocked _build_cube_url returns custom URL; that URL is used in subsequent fetches.
    Evidence: .sisyphus/evidence/task-13-hook.log

  Scenario: parameter_names filter
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_store.py::test_parameter_names_filter -v 2>&1 | tee .sisyphus/evidence/task-13-param-filter.log
    Expected Result: test passes; ds has only requested parameters as data_vars.
    Evidence: .sisyphus/evidence/task-13-param-filter.log

  Scenario: Unsupported CoverageJSON not advertised → error
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_store.py::test_no_coveragejson_advertised_raises -v 2>&1 | tee .sisyphus/evidence/task-13-no-cov.log
    Expected Result: test passes; raises EdrUnsupportedFeatureError mentioning CoverageJSON.
    Evidence: .sisyphus/evidence/task-13-no-cov.log

  Scenario: Pytest suite
    Tool: Bash
    Steps:
      1. uv run pytest tests/test_store.py -v --cov=src/edr_xarray/store 2>&1 | tee .sisyphus/evidence/task-13-pytest.log
    Expected Result: ≥15 tests pass, coverage ≥ 95%.
    Evidence: .sisyphus/evidence/task-13-pytest.log
  ```

  **Commit**: YES
  - Message: `feat(store): EdrDataStore orchestrator with documented subclass hooks`
  - Files: `src/edr_xarray/store.py`, `tests/test_store.py`
  - Pre-commit: `uv run pytest tests/test_store.py && uv run ruff check src tests && uv run mypy --strict src/edr_xarray/store.py`

- [x] 14. **EdrBackendEntrypoint registered as `engine="edr"` (`backend.py`)**

  **What to do**:
  - Create `src/edr_xarray/backend.py` with `EdrBackendEntrypoint(xarray.backends.BackendEntrypoint)`:
    - Class attributes:
      - `description: ClassVar[str] = "Lazy xarray backend for OGC API - Environmental Data Retrieval (EDR) /cubes endpoint"`
      - `url: ClassVar[str] = "https://github.com/<placeholder>/edr-xarray"` (TODO comment for real URL after publishing)
      - `open_dataset_parameters: ClassVar[tuple[str, ...]] = ("filename_or_obj", "drop_variables", "instance", "parameter_names", "bbox", "datetime", "crs", "z", "session", "discovery", "timeout")`
    - `def open_dataset(self, filename_or_obj, *, drop_variables=None, mask_and_scale=True, decode_times=True, decode_coords=True, use_cftime=None, decode_timedelta=None, concat_characters=True, instance=None, parameter_names=None, bbox=None, datetime=None, crs=None, z=None, session=None, discovery="probe", timeout=30.0) -> xr.Dataset`:
      - Validate `filename_or_obj` is a `str` URL containing `/collections/`. Else raise `ValueError("EDR backend requires a string URL pointing to /collections/{id}")`.
      - Construct `EdrDataStore(collection_url=filename_or_obj, instance=instance, parameter_names=parameter_names, bbox=bbox, datetime=datetime, crs=crs, z=z, session=session, discovery=discovery, timeout=timeout)`.
      - Call `ds = store.build_dataset()`.
      - Apply standard CF decoders if requested via `xarray.conventions.decode_cf_variables(...)` — but we mostly let xarray handle this on the user's side via `xr.decode_cf(ds, mask_and_scale=mask_and_scale, decode_times=decode_times, decode_coords=decode_coords, ...)` if any are True. Pass them through.
      - If `drop_variables` is non-empty: `ds = ds.drop_vars(drop_variables)`.
      - Return `ds`.
    - `def guess_can_open(self, filename_or_obj) -> bool`:
      - Returns False if not str.
      - Returns True if URL contains `/collections/` AND does NOT contain `/items` or `/wmts` (avoid false positives for OGC API Features / Tiles URLs that share the `/collections/` segment).
      - Otherwise False.
  - Update `src/edr_xarray/__init__.py` to re-export public API:
    ```python
    from edr_xarray.array import EdrBackendArray
    from edr_xarray.backend import EdrBackendEntrypoint
    from edr_xarray.errors import (
        EdrConformanceError,
        EdrCoverageJsonError,
        EdrMetadataError,
        EdrServerError,
        EdrUnsupportedFeatureError,
        EdrXarrayError,
    )
    from edr_xarray.store import EdrDataStore

    __version__ = "0.1.0"
    __all__ = [
        "EdrBackendEntrypoint", "EdrDataStore", "EdrBackendArray",
        "EdrXarrayError", "EdrServerError", "EdrMetadataError",
        "EdrCoverageJsonError", "EdrUnsupportedFeatureError", "EdrConformanceError",
        "__version__",
    ]
    ```
  - Tests written first (`tests/test_backend.py`):
    - `xr.backends.list_engines()` includes `"edr"` (entry-point active).
    - Engine class loads: `xr.backends.get_engine("edr")` returns `EdrBackendEntrypoint`.
    - `xr.open_dataset(metadata_url, engine="edr", parameter_names=["temp"])` against `pytest-httpserver` returns Dataset with `data_vars={"temp"}`.
    - `guess_can_open("http://srv/collections/foo")` → True.
    - `guess_can_open("http://srv/collections/foo/items")` → False.
    - `guess_can_open("http://srv/api")` → False.
    - `guess_can_open(123)` → False.
    - `guess_can_open(None)` → False.
    - `instance="f024"` propagates to fetched URLs.
    - `drop_variables=["temp"]` removes the variable.
    - Auto-engine detection: `xr.open_dataset(metadata_url)` (no `engine=` kwarg) — xarray probes engines via `guess_can_open`; ours should be selected. Assert resulting Dataset has expected data_vars.
    - Bad URL: `xr.open_dataset("http://example.com/api", engine="edr")` (no `/collections/`) → `ValueError`.

  **Must NOT do**:
  - ❌ NO touching the entry-point string in pyproject.toml — it was set in T1.
  - ❌ NO eager fetch in `open_dataset` beyond what `EdrDataStore.build_dataset` does.
  - ❌ NO automatic engine detection priority hacking — let xarray's standard mechanism work.
  - ❌ NO swallowing of underlying exceptions — let them propagate.

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Public API surface; integrates everything. Errors here are user-visible.
  - **Skills**: []
    - None needed.

  **Parallelization**:
  - **Can Run In Parallel**: NO (single task in Wave 4)
  - **Parallel Group**: Wave 4
  - **Blocks**: T15-T19 (all E2E tests use the entrypoint)
  - **Blocked By**: T1 (entry-point string), T12 (array), T13 (store)

  **References**:

  *Pattern References*:
  - tensogram-xarray `src/tensogram_xarray/backend.py:TensogramBackendEntrypoint` — direct template.
  - xarray `xarray/backends/zarr.py:ZarrBackendEntrypoint` — built-in reference.
  - xarray `xarray/backends/pydap_.py:PydapBackendEntrypoint.guess_can_open` — pattern for URL-based detection.

  *API/Type References*:
  - `xarray.backends.BackendEntrypoint` abstract — required `open_dataset` method, optional `guess_can_open`, `description`, `url`, `open_dataset_parameters`.
  - `xarray.backends.list_engines() -> dict[str, BackendEntrypoint]`.

  *External References*:
  - https://docs.xarray.dev/en/latest/internals/how-to-add-new-backend.html — registration walkthrough.

  *WHY Each Reference Matters*:
  - tensogram backend.py: Same `description`/`url`/`open_dataset_parameters` style we mirror.
  - pydap guess_can_open: URL pattern matching technique adapted to EDR's `/collections/` segment.

  **Acceptance Criteria**:

  *TDD*:
  - [ ] Tests first; running → fail (engine not registered until impl complete).
  - [ ] After impl: ≥10 tests pass.
  - [ ] mypy strict clean.
  - [ ] Coverage ≥ 95%.
  - [ ] `uv run python -c "import xarray as xr; assert 'edr' in xr.backends.list_engines(); print('ok')"` prints `ok`.

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Engine registered and discoverable
    Tool: Bash (Python REPL)
    Steps:
      1. uv run python -c "
         import xarray as xr
         engines = xr.backends.list_engines()
         assert 'edr' in engines, f'engines: {sorted(engines)}'
         from edr_xarray.backend import EdrBackendEntrypoint
         assert isinstance(engines['edr'], EdrBackendEntrypoint)
         print('engine-registered-ok')
         " 2>&1 | tee .sisyphus/evidence/task-14-engine-registered.log
    Expected Result: prints "engine-registered-ok", exit 0.
    Evidence: .sisyphus/evidence/task-14-engine-registered.log

  Scenario: Auto-engine detection via guess_can_open
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_backend.py::test_auto_engine_detection -v 2>&1 | tee .sisyphus/evidence/task-14-auto.log
    Expected Result: test passes; xr.open_dataset(url) without engine= picks "edr".
    Evidence: .sisyphus/evidence/task-14-auto.log

  Scenario: open_dataset returns lazy Dataset
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_backend.py::test_open_dataset_returns_lazy_dataset -v 2>&1 | tee .sisyphus/evidence/task-14-open.log
    Expected Result: test passes; ds has expected data_vars/dims/coords; no cube fetches yet (only metadata + probe).
    Evidence: .sisyphus/evidence/task-14-open.log

  Scenario: Pytest suite
    Tool: Bash
    Steps:
      1. uv run pytest tests/test_backend.py -v --cov=src/edr_xarray/backend 2>&1 | tee .sisyphus/evidence/task-14-pytest.log
    Expected Result: ≥10 tests pass, coverage ≥ 95%.
    Evidence: .sisyphus/evidence/task-14-pytest.log
  ```

  **Commit**: YES
  - Message: `feat(backend): EdrBackendEntrypoint registered as engine="edr"`
  - Files: `src/edr_xarray/backend.py`, `src/edr_xarray/__init__.py`, `tests/test_backend.py`
  - Pre-commit: `uv run pytest tests/test_backend.py && uv run ruff check src tests && uv run mypy --strict src/edr_xarray`

- [x] 15. **Full integration test (`tests/test_integration_full_flow.py`)**

  **What to do**:
  - Create `tests/test_integration_full_flow.py` exercising the complete flow against `pytest-httpserver`:
    - Test `test_open_dataset_then_select_then_compute_full_flow`:
      1. Register metadata endpoint at `/collections/test_coll` returning fixture metadata.
      2. Register cube endpoint at `/collections/test_coll/cube` returning `cov_grid_3d.json`.
      3. `ds = xr.open_dataset(httpserver.url_for("/collections/test_coll"), engine="edr", parameter_names=["temp"])`.
      4. Assert `set(ds.data_vars) == {"temp"}`.
      5. Assert `ds.dims == {"time": 1, "y": 2, "x": 2}`.
      6. Assert `ds.coords["x"].attrs["axis"] == "X"`.
      7. Assert `ds["temp"].attrs["units"]` matches metadata's parameter unit.
      8. `arr = ds["temp"].sel(x=10.0).values` — triggers fetch.
      9. Assert request log has metadata + probe + 1 cube subset request.
      10. Assert `arr.shape == (1, 2)` (sel collapsed x).
      11. Verify request URL contains `bbox=10.0,40.0,10.0,41.0` (or appropriate degenerate bbox).
    - Test `test_4d_cube_with_z`:
      1. Register `/collections/wx` metadata + 4D cube fixture.
      2. `ds = xr.open_dataset(url, engine="edr", parameter_names=["temperature"])`.
      3. Assert `ds["temperature"].dims` includes `z`.
      4. `arr = ds["temperature"].isel(z=1).values`.
      5. Assert request URL contains `z=850.0` (or whatever level index 1 maps to).
    - Test `test_instance_kwarg_routes_through_instance_url`:
      1. Register metadata that advertises instances.
      2. `ds = xr.open_dataset(url, engine="edr", instance="f024", parameter_names=["temp"])`.
      3. `ds["temp"].values` — triggers fetch.
      4. Assert the cube request URL includes `/instances/f024/cube`.
    - Test `test_open_with_drop_variables`:
      1. Metadata with two parameters.
      2. `ds = xr.open_dataset(url, engine="edr", drop_variables=["humidity"])`.
      3. Assert only the remaining parameter is in `ds.data_vars`.
    - Test `test_session_injection`:
      1. Create external `httpx.Client(headers={"X-Test": "yes"})`.
      2. Register httpserver expectation that requires `X-Test: yes` header.
      3. `xr.open_dataset(url, engine="edr", session=client, parameter_names=["temp"])` succeeds.
      4. Verify external client is NOT closed when Dataset is closed.

  **Must NOT do**:
  - ❌ NO live HTTP calls (everything via pytest-httpserver).
  - ❌ NO assumption about firecube specifics.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Multiple end-to-end scenarios with rich assertions.
  - **Skills**: []
    - None needed.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with T16-T19)
  - **Blocks**: F1-F4 (verification depends on these tests)
  - **Blocked By**: T6 (fixtures), T14 (entrypoint)

  **References**:

  *Pattern References*:
  - tensogram-xarray `tests/test_remote.py` — patterns for full-flow integration tests with mock servers.
  - `tests/conftest.py` from T6 — fixtures used here.

  *External References*:
  - https://pytest-httpserver.readthedocs.io/en/latest/howto.html#expect-request — assertion patterns for request-log checks.

  *WHY Each Reference Matters*:
  - tensogram test_remote.py: Confirms how to assert request count and URL patterns with stdlib HTTP mocks. We use pytest-httpserver but the pattern is the same.

  **Acceptance Criteria**:
  - [ ] ≥5 integration tests pass.
  - [ ] Coverage of `src/edr_xarray/` increases to ≥ 95% overall (if not already).

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Full happy-path open→select→compute
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_integration_full_flow.py::test_open_dataset_then_select_then_compute_full_flow -v 2>&1 | tee .sisyphus/evidence/task-15-full-flow.log
    Expected Result: passes; assertions verify dims, coords, fetch URL, value shape.
    Evidence: .sisyphus/evidence/task-15-full-flow.log

  Scenario: Instance kwarg routing
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_integration_full_flow.py::test_instance_kwarg_routes_through_instance_url -v 2>&1 | tee .sisyphus/evidence/task-15-instance.log
    Expected Result: passes; cube fetch URL contains `/instances/f024/cube`.
    Evidence: .sisyphus/evidence/task-15-instance.log

  Scenario: Pytest suite
    Tool: Bash
    Steps:
      1. uv run pytest tests/test_integration_full_flow.py -v 2>&1 | tee .sisyphus/evidence/task-15-pytest.log
    Expected Result: ≥5 tests pass.
    Evidence: .sisyphus/evidence/task-15-pytest.log
  ```

  **Commit**: YES
  - Message: `test: full open→index→fetch integration flow`
  - Files: `tests/test_integration_full_flow.py`
  - Pre-commit: `uv run pytest tests/test_integration_full_flow.py && uv run ruff check tests`

- [x] 16. **Lazy semantics test (`tests/test_lazy_semantics.py`)**

  **What to do**:
  - Create `tests/test_lazy_semantics.py` proving that `open_dataset` does NOT fetch cube data:
    - Test `test_open_dataset_metadata_only_with_metadata_only_discovery`:
      1. Register metadata endpoint with values arrays present.
      2. Register cube endpoint with a request handler that fails the test if invoked.
      3. `ds = xr.open_dataset(url, engine="edr", parameter_names=["temp"], discovery="metadata_only")`.
      4. Assert `ds.dims` populated correctly.
      5. Assert request log shows ONLY the metadata URL was hit (cube endpoint never called).
    - Test `test_open_dataset_with_probe_does_one_metadata_one_probe`:
      1. Register metadata + cube endpoints.
      2. `ds = xr.open_dataset(url, engine="edr", parameter_names=["temp"], discovery="probe")`.
      3. Assert request log has exactly 2 entries: metadata, then cube probe.
      4. Assert NO further cube requests.
    - Test `test_compute_triggers_cube_fetch`:
      1. Same as above for setup.
      2. `_ = ds["temp"].values`.
      3. Assert request log now has 3 entries (metadata, probe, fetch).
    - Test `test_repeated_compute_triggers_repeated_fetch`:
      1. Same setup.
      2. `_ = ds["temp"].values; _ = ds["temp"].values`.
      3. Assert request log has 4 entries (metadata, probe, fetch1, fetch2). Confirms NO local caching beyond xarray's per-call decoding.
    - Test `test_isel_subset_translates_to_narrow_query`:
      1. Same setup.
      2. `_ = ds["temp"].isel(x=slice(0, 1)).values`.
      3. Assert the most recent cube request has narrower bbox than the probe.

  **Must NOT do**:
  - ❌ NO assumptions about caching that would mask the laziness check.
  - ❌ NO firecube assumptions.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Critical correctness invariant; needs precise request-counting assertions.
  - **Skills**: []
    - None needed.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with T15, T17, T18, T19)
  - **Blocks**: F1-F4
  - **Blocked By**: T6, T14

  **References**:

  *Pattern References*:
  - tensogram-xarray `tests/test_remote.py` — uses `httpserver.log` for request counting.

  *WHY Each Reference Matters*:
  - tensogram's request-log assertions are the precise idiom we mirror.

  **Acceptance Criteria**:
  - [ ] ≥5 lazy-semantics tests pass.
  - [ ] No `XFAIL` or skipped tests in this file.

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: open_dataset (probe mode) issues exactly 2 HTTP requests
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_lazy_semantics.py::test_open_dataset_with_probe_does_one_metadata_one_probe -v 2>&1 | tee .sisyphus/evidence/task-16-lazy-probe.log
    Expected Result: passes.
    Evidence: .sisyphus/evidence/task-16-lazy-probe.log

  Scenario: open_dataset (metadata_only mode) issues exactly 1 HTTP request
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_lazy_semantics.py::test_open_dataset_metadata_only_with_metadata_only_discovery -v 2>&1 | tee .sisyphus/evidence/task-16-lazy-md-only.log
    Expected Result: passes.
    Evidence: .sisyphus/evidence/task-16-lazy-md-only.log

  Scenario: .values triggers exactly one additional fetch
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_lazy_semantics.py::test_compute_triggers_cube_fetch -v 2>&1 | tee .sisyphus/evidence/task-16-compute.log
    Expected Result: passes.
    Evidence: .sisyphus/evidence/task-16-compute.log

  Scenario: Pytest suite
    Tool: Bash
    Steps:
      1. uv run pytest tests/test_lazy_semantics.py -v 2>&1 | tee .sisyphus/evidence/task-16-pytest.log
    Expected Result: ≥5 tests pass.
    Evidence: .sisyphus/evidence/task-16-pytest.log
  ```

  **Commit**: YES
  - Message: `test: verify lazy semantics — metadata-only on open, cube fetch on access`
  - Files: `tests/test_lazy_semantics.py`
  - Pre-commit: `uv run pytest tests/test_lazy_semantics.py`

- [x] 17. **Pickle round-trip + Dask compatibility test (`tests/test_pickle_dask.py`)**

  **What to do**:
  - Create `tests/test_pickle_dask.py` (skip Dask tests gracefully if Dask not installed):
    - Test `test_pickle_dataset_roundtrip`:
      1. Open Dataset via `xr.open_dataset(url, engine="edr", parameter_names=["temp"])`.
      2. `blob = pickle.dumps(ds)`.
      3. `ds2 = pickle.loads(blob)`.
      4. `arr = ds2["temp"].values` — succeeds. The underlying `EdrBackendArray._store` was preserved through pickle; the store's `__setstate__` created a fresh `Transport` so the fetch goes through a new httpx.Client.
      5. Assert `arr.shape == ds["temp"].shape`.
    - Test `test_pickle_lazy_array_roundtrip`:
      1. Open Dataset, get `arr = ds["temp"].variable.data` (this is the LazilyIndexedArray wrapping EdrBackendArray).
      2. Pickle/unpickle.
      3. Confirm restored data has same shape and dtype; underlying `EdrBackendArray._store` is restored with a fresh Transport.
      4. Restored array can perform `arr2[BasicIndexer((slice(None),)*ndim)]` against the same mock URL.
    - Test `test_dask_compute_via_chunks` (skip if dask not installed):
      1. `import dask`. If ImportError → `pytest.skip("dask not installed")`.
      2. Open Dataset with `chunks={"time": 1}`.
      3. Assert `ds["temp"].data` is a `dask.array.Array`.
      4. `_ = ds["temp"].compute()` — runs without errors; one (or more, if dask schedules multiple workers) cube request issued.
      5. Verify result shape matches expected.
    - Test `test_dask_pickling_for_distributed`:
      1. Open Dataset with chunks; `arr_dask = ds["temp"].data`.
      2. Pickle the dask array's underlying graph element.
      3. Unpickle; confirm value resolution works.

  **Must NOT do**:
  - ❌ NO requiring Dask to be installed (skip cleanly).
  - ❌ NO actual distributed cluster — just pickle round-trip.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Pickle/Dask correctness depends on careful __getstate__/__setstate__ semantics.
  - **Skills**: []
    - None needed.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with T15, T16, T18, T19)
  - **Blocks**: F1-F4
  - **Blocked By**: T6, T12, T14

  **References**:

  *Pattern References*:
  - tensogram-xarray `tests/test_array.py` — pickle test patterns.
  - xarray `xarray/tests/test_dask.py` — patterns for chunked-Dataset testing.

  *External References*:
  - https://docs.xarray.dev/en/latest/user-guide/dask.html — chunks integration with backends.

  *WHY Each Reference Matters*:
  - tensogram's pickle tests are the closest analogue. We adapt them to httpx-backed transport.

  **Acceptance Criteria**:
  - [ ] ≥4 tests pass (with dask test possibly skipped if dask absent).
  - [ ] Coverage maintained ≥ 95%.

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Pickle Dataset roundtrip preserves fetch capability
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_pickle_dask.py::test_pickle_dataset_roundtrip -v 2>&1 | tee .sisyphus/evidence/task-17-pickle.log
    Expected Result: passes.
    Evidence: .sisyphus/evidence/task-17-pickle.log

  Scenario: Dask compute with chunks (skip if dask absent)
    Tool: Bash (pytest)
    Steps:
      1. uv pip install dask 2>&1 | tee .sisyphus/evidence/task-17-dask-install.log
      2. uv run pytest tests/test_pickle_dask.py::test_dask_compute_via_chunks -v 2>&1 | tee .sisyphus/evidence/task-17-dask.log
    Expected Result: pytest passes.
    Evidence: .sisyphus/evidence/task-17-dask.log

  Scenario: Pytest suite
    Tool: Bash
    Steps:
      1. uv run pytest tests/test_pickle_dask.py -v 2>&1 | tee .sisyphus/evidence/task-17-pytest.log
    Expected Result: ≥4 tests pass or skip.
    Evidence: .sisyphus/evidence/task-17-pytest.log
  ```

  **Commit**: YES
  - Message: `test: pickle round-trip and Dask compute compatibility`
  - Files: `tests/test_pickle_dask.py`
  - Pre-commit: `uv run pytest tests/test_pickle_dask.py`

- [x] 18. **Subclass extensibility test (`tests/test_subclass_extensibility.py`)**

  **What to do**:
  - Create `tests/test_subclass_extensibility.py` proving each documented hook on `EdrDataStore` is overridable. This test is the contract for downstream packages like `xarray-firecube`.
  - For each hook (`_request`, `_parse_collection_metadata`, `_negotiate_output_format`, `_build_cube_url`, `_parse_coveragejson`, `_translate_indexer`, `_discover_axes`):
    - Define a minimal subclass of `EdrDataStore` overriding ONLY that hook.
    - Verify the override is invoked by tracking calls (e.g., via `unittest.mock.MagicMock` wrapped around the original or a recording wrapper).
    - Verify the override's effect propagates correctly (e.g., `_build_cube_url` returning `"http://different/cube"` causes subsequent fetches to use that URL).
  - Test `test_subclass_can_override_request_for_custom_auth`:
    1. Define `class AuthStore(EdrDataStore)` overriding `_request(self, method, url, *, params=None, headers=None) -> httpx.Response` to merge in `{"X-Api-Key": "secret"}` before delegating to `super()._request(...)`.
    2. Register httpserver expectation requiring `X-Api-Key: secret` header on metadata + cube endpoints.
    3. Construct `AuthStore(...)` and call `build_dataset()`.
    4. Trigger a cube fetch via `ds["temp"].values`.
    5. Assert all three requests (metadata, probe, cube fetch) carried the header — verifies that `_request` is the single chokepoint for cube-side traffic too.
  - Test `test_subclass_can_override_parse_metadata_for_extensions`:
    1. Define subclass overriding `_parse_collection_metadata(self, payload: dict) -> CollectionMetadata` to wrap super and store a custom field `extra_metadata` on `self`.
    2. Call `build_dataset()` and assert `store.extra_metadata` populated. (Note: stored on store, not Dataset — Dataset attrs would also work; pick one and document.)
  - Test `test_subclass_can_override_build_cube_url_for_nonstandard_routing`:
    1. Define subclass that returns `"http://other-host/cubes/v2"` regardless of inputs.
    2. Trigger a cube fetch and verify the request URL via httpserver request log matches the override.
  - Test `test_subclass_can_override_translate_indexer_to_inject_static_filters`:
    1. Define subclass overriding `_translate_indexer(key, axes) -> dict` to add `{"refresh": "true"}` to every translation result.
    2. Trigger `ds["temp"].values` and verify the cube request URL contains `refresh=true`.
  - Test `test_subclass_can_override_parse_coveragejson_for_extensions`:
    1. Define subclass overriding `_parse_coveragejson(payload) -> CoverageData` to delegate to super and then strip out a server-specific extension field.
    2. Verify the override is called during cube fetches.
  - Test `test_subclass_hooks_are_documented_in_class_docstring`:
    1. Inspect `EdrDataStore.__doc__` — assert it lists each hook name with at least a one-line description.
    2. Use this as a DOCUMENTATION CONTRACT — if a future change removes a hook from docstring, this test catches it.
  - Test `test_all_hooks_have_default_implementations`:
    1. For each documented hook name (the 7), assert `hasattr(EdrDataStore, hook_name)` and the attribute is callable.
  - Test `test_xarray_firecube_minimal_demo`:
    1. Define a TINY illustrative subclass `class FakeFirecubeStore(EdrDataStore)` that overrides `_build_cube_url` to append `?refresh=true` and `_translate_indexer` to add a `min-value=0.0` static query.
    2. NOTE: this is a TEST FIXTURE only — it MUST live in tests/, NEVER in src/.
    3. Verify the subclass works end-to-end against pytest-httpserver.

  **Must NOT do**:
  - ❌ NO firecube-specific code in `src/edr_xarray/` — the demo subclass lives ONLY in tests/.
  - ❌ NO use of monkeypatching for hook tests — use real subclassing.
  - ❌ NO assumption that subclass hooks need underscores forever; the documentation contract is what matters.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Verifies the extensibility contract; defines the subclass surface for downstream packages.
  - **Skills**: []
    - None needed.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with T15-T17, T19)
  - **Blocks**: F1-F4
  - **Blocked By**: T6, T13

  **References**:

  *Pattern References*:
  - The store hooks defined in T13 — must directly mirror.
  - tensogram-xarray `tests/test_backend.py` — patterns for entrypoint subclassing tests.

  *External References*:
  - https://docs.python.org/3/library/unittest.mock.html#unittest.mock.MagicMock — for tracking method calls.

  *WHY Each Reference Matters*:
  - tensogram tests: Confirm the `class CustomBackend(BackendEntrypoint): ...` pattern; we use the same on our store.

  **Acceptance Criteria**:
  - [ ] ≥7 subclassing tests pass.
  - [ ] EdrDataStore docstring lists all 7 hooks with at least a one-line description each.

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Subclass override of _build_cube_url is invoked
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_subclass_extensibility.py::test_subclass_can_override_build_cube_url_for_nonstandard_routing -v 2>&1 | tee .sisyphus/evidence/task-18-build-url.log
    Expected Result: passes.
    Evidence: .sisyphus/evidence/task-18-build-url.log

  Scenario: Subclass override of _request adds auth header
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_subclass_extensibility.py::test_subclass_can_override_request_for_custom_auth -v 2>&1 | tee .sisyphus/evidence/task-18-auth.log
    Expected Result: passes.
    Evidence: .sisyphus/evidence/task-18-auth.log

  Scenario: Hook documentation contract enforced
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/test_subclass_extensibility.py::test_subclass_hooks_are_documented_in_class_docstring -v 2>&1 | tee .sisyphus/evidence/task-18-docs.log
    Expected Result: passes; docstring includes all 7 hook names.
    Evidence: .sisyphus/evidence/task-18-docs.log

  Scenario: Pytest suite
    Tool: Bash
    Steps:
      1. uv run pytest tests/test_subclass_extensibility.py -v 2>&1 | tee .sisyphus/evidence/task-18-pytest.log
    Expected Result: ≥7 tests pass.
    Evidence: .sisyphus/evidence/task-18-pytest.log
  ```

  **Commit**: YES
  - Message: `test: verify subclass extensibility hooks are invoked`
  - Files: `tests/test_subclass_extensibility.py`
  - Pre-commit: `uv run pytest tests/test_subclass_extensibility.py`

- [x] 19. **README usage examples + opt-in live firecube smoke test (`README.md`, `tests/test_live_firecube.py`)**

  **What to do**:
  - Rewrite `README.md` (replacing T1's skeleton) with concrete sections:
    - **Title**: "edr-xarray"
    - **Status**: alpha (v0.1.0)
    - **Overview**: 2-3 sentences explaining what it does.
    - **Installation**: `uv add edr-xarray` and `pip install edr-xarray` snippets.
    - **Usage**:
      ```python
      import xarray as xr

      # Open an EDR collection (probe mode discovers axes; one extra HTTP call on open)
      ds = xr.open_dataset(
          "https://edr.example.com/collections/temperature_2m",
          engine="edr",
          parameter_names=["t2m"],
          bbox=(-3.5, 50.2, -2.1, 51.0),
          datetime="2023-01-01T00:00:00Z/2023-01-07T00:00:00Z",
      )

      # Inspect (lazy)
      print(ds.dims)            # {'time': 168, 'y': 50, 'x': 50}
      print(ds.data_vars)       # {'t2m': <DataArray ...>}

      # Slice and compute (issues subset cube query)
      sub = ds["t2m"].sel(x=slice(-3.0, -2.5)).load()
      ```
    - **Lazy semantics**: explanation that `open_dataset` does only metadata + (in `probe` mode) one tiny probe; data flows on `.values`/`.compute()`.
    - **Authentication**: example with `httpx.Client(headers={...})` injected via `session=`.
    - **Discovery modes**: explain `probe` (default), `metadata_only`, `strict`.
    - **Vertical (`z`)**: example with 4D cube and `z=850` kwarg.
    - **Dask**: example with `chunks={"time": 1}` and `.compute()`.
    - **Subclassing**: a code block showing how to subclass `EdrDataStore` to override `_request` for an API key, and pointing to test_subclass_extensibility.py for full hook list.
    - **Limitations** (what's NOT supported in v1):
      - Only `/cubes` queries (no position/area/trajectory/etc.).
      - Only CoverageJSON responses (Grid domain, flat NdArray).
      - Only CRS84 axis order for `bbox` input.
      - No antimeridian-crossing bbox.
      - No exotic z grammar (`R14/.../...`, multi-level lists).
      - No retry / cache / async client.
    - **Development**: `uv sync && uv run pytest`.
    - **License**: Apache-2.0.
    - NO emojis anywhere.
  - Create `tests/test_live_firecube.py` (opt-in, marked `@pytest.mark.live`):
    - Skip-fixture: `@pytest.fixture` that reads `EDR_LIVE_URL` env var (default `http://localhost:8000`); does a `httpx.get(url + "/conformance", timeout=2)` and skips with a clear message if unreachable.
    - Test `test_live_firecube_open_msg_frm`:
      1. `ds = xr.open_dataset(f"{base_url}/collections/msg_frm", engine="edr", instance="f024")`.
      2. Assert `ds.dims` non-empty.
      3. Assert at least one parameter in `ds.data_vars`.
      4. `_ = ds[<first var>].values` — completes without error.
    - Test `test_live_firecube_subset_query`:
      1. Same open.
      2. Subset via `ds[<var>].sel(...)` against firecube's actual extent.
      3. Verify shape is smaller than full extent.
    - **Configurable**: tests use `EDR_LIVE_URL` env var so users can point at their own server.
    - **Documented in README**: how to run live tests.

  **Must NOT do**:
  - ❌ NO emojis in README.
  - ❌ NO marketing language ("blazing fast", "production-ready").
  - ❌ NO hardcoded firecube collection IDs that don't exist by default — use `MSG_FRM` only because user confirmed it as their test collection.
  - ❌ NO live tests that fail loudly when firecube is absent — must skip cleanly.

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: README is documentation work; clear writing matters more than coding.
  - **Skills**: []
    - None needed.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with T15-T18)
  - **Blocks**: F1-F4
  - **Blocked By**: T14

  **References**:

  *Pattern References*:
  - tensogram-xarray repo-level README at `python/tensogram-xarray/README.md` (the package's own README inside the monorepo) — concise, code-example-driven structure to mirror.
  - xarray docs main: https://docs.xarray.dev/en/stable/ — usage example layout.

  *External References*:
  - https://docs.xarray.dev/en/latest/user-guide/io.html#opendap-and-grib-files — example backend documentation tone.

  *WHY Each Reference Matters*:
  - tensogram README tone: Realistic, no overselling. Same approach for ours.

  **Acceptance Criteria**:
  - [ ] README.md exists with all sections listed above.
  - [ ] All code blocks in README.md are syntactically valid Python (parsed via `ast.parse` in a verification script).
  - [ ] Live test file exists; running without `EDR_LIVE_URL` set or with unreachable server → tests skipped.
  - [ ] Running with reachable firecube → tests pass (validated manually if firecube is available).

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: README code blocks parse as valid Python
    Tool: Bash
    Steps:
      1. uv run python -c "
         import re, ast, pathlib
         text = pathlib.Path('README.md').read_text()
         blocks = re.findall(r'\`\`\`python\n(.*?)\n\`\`\`', text, re.DOTALL)
         assert len(blocks) >= 3, f'expected >=3 python blocks, got {len(blocks)}'
         for i, b in enumerate(blocks):
             try:
                 ast.parse(b)
             except SyntaxError as e:
                 print(f'block {i} invalid: {e}')
                 raise
         print(f'all {len(blocks)} python blocks parse-ok')
         " 2>&1 | tee .sisyphus/evidence/task-19-readme-parse.log
    Expected Result: prints "all N python blocks parse-ok".
    Evidence: .sisyphus/evidence/task-19-readme-parse.log

  Scenario: Live firecube test skips cleanly when server unreachable
    Tool: Bash (pytest)
    Steps:
      1. unset EDR_LIVE_URL
      2. uv run pytest tests/test_live_firecube.py -v -m live 2>&1 | tee .sisyphus/evidence/task-19-skip.log
    Expected Result: tests SKIPPED (not failed); skip reason mentions "EDR server unreachable" or similar.
    Evidence: .sisyphus/evidence/task-19-skip.log

  Scenario: Live firecube test runs against firecube if reachable (BEST EFFORT — depends on firecube being up)
    Tool: Bash (pytest)
    Steps:
      1. EDR_LIVE_URL=http://localhost:8000 uv run pytest tests/test_live_firecube.py -v -m live 2>&1 | tee .sisyphus/evidence/task-19-live.log
      2. RESULT=$?
    Expected Result:
      - If firecube on :8000 reachable → pytest passes (1+ tests pass).
      - If firecube unreachable → tests skipped cleanly with informative message.
      - Either way, evidence file shows the outcome.
    Evidence: .sisyphus/evidence/task-19-live.log

  Scenario: README has all required sections
    Tool: Bash
    Steps:
      1. uv run python -c "
         import pathlib
         text = pathlib.Path('README.md').read_text()
         for h in ['# edr-xarray', 'Installation', 'Usage', 'Authentication', 'Discovery', 'Subclassing', 'Limitations', 'License']:
             assert h in text, f'README missing section: {h}'
         print('readme-sections-ok')
         " 2>&1 | tee .sisyphus/evidence/task-19-sections.log
    Expected Result: prints "readme-sections-ok".
    Evidence: .sisyphus/evidence/task-19-sections.log
  ```

  **Commit**: YES
  - Message: `docs: README usage examples + opt-in live firecube smoke test`
  - Files: `README.md`, `tests/test_live_firecube.py`
  - Pre-commit: `uv run pytest tests/test_live_firecube.py -m "live or not live"`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
>
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback → fix → re-run → present again → wait for okay.

- [ ] F1. **Plan Compliance Audit** — `oracle`

  Read `.sisyphus/plans/edr-xarray-backend.md` end-to-end. For each "Must Have": verify implementation exists (read file, run command, parse import). For each "Must NOT Have": grep `src/edr_xarray/` ONLY (NOT `tests/`, `docs/`, `README.md`, or fixtures — those legitimately mention forbidden strings in negative-test contexts, error messages, advertised-but-unsupported lists, and feature-matrix docs).

  **Forbidden-pattern grep rules** (each scoped to `src/edr_xarray/` only via `grep -r --include='*.py' <pattern> src/edr_xarray/`):
  - `localhost` (test target only — must NOT appear in source)
  - `firecube` (case-insensitive)
  - `\\?refresh=` or `&refresh=` (firecube-specific query param)
  - `cube/series` (firecube-specific endpoint)
  - non-cube query verbs in URL strings: `/position`, `/radius`, `/area`, `/trajectory`, `/corridor`, `/items`, `/locations` (specifically inside string literals — confirm via context check on each match)
  - `application/geo\\+json`, `application/x-netcdf` (non-CoverageJSON media types)
  - `"TiledNdArray"`, `"PointSeries"`, `"Trajectory"`, `"VerticalProfile"` (non-Grid CoverageJSON domain types — the rejection-message strings are EXEMPT, so the auditor must inspect context: a literal `"TiledNdArray"` used in an error message like `f"only Grid supported, got {dt}"` is OK; a hardcoded fixture/sample-output containing it is NOT)
  - `<collection.*?>/cube` regex (assumed URL pattern — the cube URL must come from `data_queries.cube.link.href`, never assembled this way)
  - `except Exception:` (broad catch)
  - `# type: ignore` without an explanatory comment on the same line (allowed only with justification e.g. `# type: ignore[<code>]  # reason: ...`)
  - `print\\(` (logging.getLogger required)
  - ` as any`, ` as Any`, `cast\\(Any` (typing escape hatches)

  **README.md and tests/** are EXEMPT from the above grep — they may legitimately mention these strings in:
  - Feature matrix tables ("Not supported: GeoJSON, NetCDF passthrough...")
  - Negative test fixtures (e.g. `tests/data/cov_pointseries.json`, `tests/data/cov_tiled.json`)
  - Negative test bodies (`pytest.raises(EdrUnsupportedFeatureError, match="PointSeries")`)
  - Error message regression checks
  - Live firecube test (`tests/test_live_firecube.py` — uses `localhost` only via `EDR_LIVE_URL` env default)

  Check evidence files exist in `.sisyphus/evidence/`. Compare each deliverable against plan.

  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | Evidence [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`

  Run `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy --strict src/edr_xarray && uv run pytest --cov=src/edr_xarray --cov-fail-under=95`. Review all changed files for: `as any`/`@ts-ignore`/Python `# type: ignore`, empty/swallowing `except`, `print()` in src, commented-out code, unused imports, generic variable names, premature abstractions (utilities with one call site), excessive defensive coding. Verify Apache-2.0 LICENSE present. Verify entry point in pyproject correctly points to existing class.

  Output: `Ruff [PASS/FAIL] | Format [PASS/FAIL] | Mypy [PASS/FAIL] | Pytest [N pass/N fail] | Coverage [N%] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`

  Start from clean state (`uv sync --refresh`). Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Specifically: (a) `import edr_xarray` succeeds; (b) `xr.backends.list_engines()` includes `"edr"`; (c) given a `pytest-httpserver` returning sample collection metadata + cube CoverageJSON, `xr.open_dataset(server_url + "/collections/test", engine="edr", parameter_names=["temp"], bbox=(10,40,11,41), datetime="2025-01-01T00:00:00Z")` returns a Dataset with the expected `data_vars`, `dims`, `coords`; (d) `ds["temp"].values` triggers exactly one cube HTTP request to the advertised cube URL; (e) `ds["temp"].sel(x=...).values` triggers a subset cube request; (f) pickling and unpickling `ds["temp"].variable.data` survives a round trip; (g) live test against firecube on `:8000` (if reachable) opens `msg_frm` collection with `instance="f024"`. Save evidence to `.sisyphus/evidence/final-qa/`.

  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | Live Firecube [PASS/SKIP] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`

  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance per task. Detect cross-task contamination: Task N touching Task M's files. Flag unaccounted changes (files not assigned to any task). Verify package boundary discipline: no firecube-specific symbols in `src/edr_xarray/`; firecube assumptions only in `tests/test_live_firecube.py` and that test gracefully skips.

  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | Boundary discipline [CLEAN/N leaks] | VERDICT`

---

## Commit Strategy

One commit per task, conventional-commits style. Commits within a wave can be independent; commits across waves must respect dependency order. Pre-commit gate: `uv run ruff check && uv run ruff format --check && uv run mypy --strict src/edr_xarray && uv run pytest tests/<task-tests>`.

| Task | Commit message |
|---|---|
| T1 | `chore: scaffold uv project with ruff/mypy/pytest and Apache-2.0 license` |
| T2 | `feat(errors): add EdrXarrayError hierarchy` |
| T3 | `feat(coveragejson): parse Grid CoverageJSON responses with null→nan` |
| T4 | `feat(metadata): parse EDR collection metadata and resolve cube link` |
| T5 | `feat(query): encode bbox, datetime, z, and parameter-name query params` |
| T6 | `test: add pytest-httpserver fixtures and sample EDR JSON data` |
| T7 | `ci: add ruff+mypy+pytest GitHub Actions workflow` |
| T8 | `feat(indexer): translate xarray ExplicitIndexer to EDR query params` |
| T9 | `feat(transport): wrap httpx.Client with error mapping and session ownership` |
| T10 | `feat(discovery): add probe/metadata_only/strict coord discovery strategies` |
| T11 | `feat(builder): construct xr.Variable and Coordinates from EDR metadata` |
| T12 | `feat(array): EdrBackendArray with lazy __getitem__ and pickle support` |
| T13 | `feat(store): EdrDataStore orchestrator with documented subclass hooks` |
| T14 | `feat(backend): EdrBackendEntrypoint registered as engine="edr"` |
| T15 | `test: full open→index→fetch integration flow` |
| T16 | `test: verify lazy semantics — metadata-only on open, cube fetch on access` |
| T17 | `test: pickle round-trip and Dask compute compatibility` |
| T18 | `test: verify subclass extensibility hooks are invoked` |
| T19 | `docs: README usage examples + opt-in live firecube smoke test` |

---

## Success Criteria

### Verification Commands
```bash
# Install
uv sync

# Lint+format clean
uv run ruff check src tests
uv run ruff format --check src tests

# Type checking clean
uv run mypy --strict src/edr_xarray

# Tests pass with ≥95% coverage
uv run pytest --cov=src/edr_xarray --cov-fail-under=95

# Engine registered
uv run python -c "import xarray as xr; assert 'edr' in xr.backends.list_engines(); print('ok')"
# Expected: ok

# Build wheel
uv build
# Expected: dist/edr_xarray-0.1.0-py3-none-any.whl

# Live firecube smoke (only if firecube on :8000)
EDR_LIVE_URL=http://localhost:8000 uv run pytest tests/test_live_firecube.py -v -m live
```

### Final Checklist
- [ ] All "Must Have" items verified present.
- [ ] All "Must NOT Have" items verified absent (grep clean).
- [ ] All TODO tasks completed.
- [ ] All Final Verification F1-F4 → APPROVE.
- [ ] User explicitly okays the work.
