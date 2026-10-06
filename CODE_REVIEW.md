# Gridfinity Creator: Code Review & Improvement Report

| | |
|---|---|
| **Repository** | `NoSQLKnowHow/gridfinitycreator` (a fork; upstream appears to be `jeroen94704/gridfinitycreator`) |
| **Reviewed commit** | `d15e26b` (2025-12-02), app version `0.4.5` |
| **Review date** | 2026-10-05 |
| **Scope** | All 81 tracked files: 28 Python files (1,753 lines), 22 HTML/Jinja files (550 lines), Docker/Compose/CI config, docs |
| **Code changes made** | **None.** This file is the only addition. |

---

## 1. Executive summary

**The geometry engine is good. The web application wrapped around it is where the problems are.**

I generated bins across the legal range of every form. The divider bin, solid bin, light bin and baseplate produced valid, single-solid models at exactly the expected dimensions, in about a second each. That's the hard part of this project and it works.

The problems are in everything *around* it. The app trusts its input, has no notion of how expensive a request is, fails silently, and half-implements its headline "Advanced settings" feature. In order of how much I'd worry:

1. **One ordinary request can freeze the whole server.** Six *legitimate, within-the-limits* "max size" requests made the home page take **196 seconds** to load (0.04 s idle). A single 40×40-hole request on the Holey bin takes 100 s and builds a 503 mm bin, even though the UI promises a 6-unit maximum. ([SEC-1](#sec-1), [BUG-1](#bug-1))
2. **Server-side validation doesn't exist.** The only guards are HTML `min`/`max` attributes, which anyone can bypass. A zero, a negative number or a typo gives a bare HTTP 500, or worse, a silently wrong file. ([BUG-2](#bug-2))
3. **When something goes wrong, the user is told nothing.** An expired form token, or any rejected field, just reloads the page on the Home tab. No message is ever rendered. ([BUG-3](#bug-3))
4. **Real output bugs.** The Holey bin without a stacking lip exports as **two disconnected solids** (13 of 13 test cases). Custom grid sizes are only half-supported: the Raaco preset gives a Light bin with undersized square feet and a baseplate that crashes, and any height unit other than 7 mm makes the label tab overshoot the wall. ([BUG-4](#bug-4), [BUG-5](#bug-5))
5. **The documented install steps fail on the first command**, and the debug Compose file doesn't parse. ([OPS-1](#ops-1))
6. **No tests and no CI.** The git history shows users, not tests, finding the geometry regressions. ([OPS-2](#ops-2))

Most of the serious items are small fixes. I've marked the ones where I **tested the fix** myself.

### Scorecard (subjective)

| Area | Grade | One-liner |
|---|---|---|
| Geometry at default grid | **A−** | Valid, exact, fast. One real bug (Holey, no lip). |
| Input validation | **D** | Client-side only. |
| Resilience / abuse resistance | **F** *(public)* / **C** *(private LAN)* | No cost limits, queue, timeout or cache. |
| Error handling & feedback | **D** | Silent failures, bare 500s. |
| Security hygiene | **C−** | No auth to protect, so impact is low, but several bad habits. |
| Front end | **C** | Works on desktop, poor on phones, redundant and external assets. |
| Accessibility | **D** | See [UI-4](#ui-4). |
| Build / deploy | **C−** | Unpinned dependencies, broken docs path. |
| Tests / CI | **F** | None. |
| Maintainability | **C+** | Nice plugin idea, then five copy-pasted `main.py` files. |

### Top-10 priority list

| # | Item | Effort | Ref |
|--:|---|:-:|---|
| 1 | Validate every input server-side (validators + a *cost* cap, not just per-field caps) | S–M | BUG-1, BUG-2 |
| 2 | Limit concurrent generations, add a hard timeout, return 503 when busy | M | SEC-1 |
| 3 | Show validation errors and handle exceptions with a friendly page | S | BUG-3 |
| 4 | Fix the Holey bin (caps + two-solid bug), one-line fix tested | S | BUG-1, BUG-4 |
| 5 | Harden the `gridspec` cookie parsing (home page can be bricked) | S | SEC-2 |
| 6 | Make the README install path work (`DATA_ROOT`, `proxy` network, `/tmpfiles`) | S | OPS-1 |
| 7 | Move `SECRET_KEY` to env; stop binding the debugger to `0.0.0.0` | S | SEC-3, SEC-4 |
| 8 | Add a pytest geometry suite + GitHub Actions | M | OPS-2 |
| 9 | Either finish the custom-grid feature or hide it | M–L | BUG-5 |
| 10 | Drop redundant JS, vendor assets, fix the mobile layout | S–M | UI-1, UI-2 |

*Effort: S ≈ under an hour, M ≈ half a day, L ≈ days.*

---

## 2. How I reviewed this (and what it can't tell you)

Every finding is labelled so you know how much to trust it:

- **[Verified]** I ran it and saw the result.
- **[Code]** From reading the source; I did not execute it.
- **[Inferred]** A reasoned conclusion from verified facts plus documentation or defaults.

**What I did**

1. Read every tracked file.
2. Installed CadQuery 2.8.0 (via `pip`, Python 3.11) and loaded the generators through the app's *own* `load_generators()`.
3. Exercised the generators directly, plus the Flask app via its test client and a real Waitress server.
4. Ran a seeded sweep of 83 configurations across each form's *legal* range (checking for exceptions, invalid shapes and multi-solid results).
5. Drove the UI in headless Chromium on desktop and phone viewports. The CDN assets were served from npm copies of the *same pinned versions*, intercepted in the browser.
6. Tested each recommended fix I'm marking **[Fix verified]** against the original.

**Limits you should know about**

- **Not run in your Docker image.** The Dockerfile installs CadQuery from conda-forge, *unpinned*. I used the pip build. Geometry results may differ by CadQuery version.
- **No reverse proxy.** I did not test behind Traefik or any load balancer.
- **Fork only.** I could only see your fork, so I haven't compared against upstream. Some items may already be fixed or discussed there.
- **No physical prints.** I validated geometry (validity, solid count, bounding boxes, volumes, cross-sections). I did not slice or print anything.
- **Timings are from a 4-core / 16 GB sandbox.** Your server will differ; the *shape* of the numbers (steep growth, starvation) won't.

---

## 3. What's already good

Credit where it's due, since most of this report is complaints:

- **Geometry is correct and exact at the default grid.** E.g. a 6-unit bin with lip measured 46.4 mm (6 × 7 + 4.4); a 2×2×4 bin without lip measured 28.0 mm; all valid, single solid. [Verified]
- **61 of 61 legal-range configs passed** for the divider bin, solid bin, light bin and baseplate: no exceptions, no invalid shapes, no multi-solid results. [Verified]
- **Typical requests are fast:** about 0.5–1.5 s. [Verified]
- **Concurrent generation is consistent.** Six parallel requests returned six byte-count-identical 21.8 MB files. [Verified]
- **No temp-file leaks** after ~20 generation requests, including the concurrent burst and several 500s. [Verified]
- **The plugin-style generator discovery** (drop a folder with a `main.py` into `generators/`) is a neat design.
- **CSRF is on for the generator forms, Bootstrap CSS/JS use SRI, the base image is pinned,** and the in-app help (with pictures) is genuinely helpful.
- The *intent* to cap sizes is there (`MAX_GRID_UNITS`, etc.). It just isn't applied everywhere.

---

## 4. Findings

Severity legend: **Critical** = can take down a public instance with trivial effort · **High** = user-visible wrong results or failures · **Medium** = real risk or maintenance cost · **Low** = polish / latent.

| ID | Title | Severity | Status | Effort |
|---|---|---|---|:-:|
| [SEC-1](#sec-1) | Unbounded generation cost → trivial denial of service | **Critical** (public) | Verified | M |
| [BUG-1](#bug-1) | Holey bin: size caps are defeated | **High** | Verified | S |
| [BUG-2](#bug-2) | No server-side validation | **High** | Verified | S–M |
| [BUG-3](#bug-3) | Failures are silent | **High** | Verified | S |
| [BUG-4](#bug-4) | Holey bin without lip exports two solids | **High** | Verified + fix verified | S |
| [BUG-5](#bug-5) | Custom grid sizes are half-implemented | **High** | Verified | M–L |
| [SEC-2](#sec-2) | `gridspec` cookie can brick the home page | **High** | Verified | S |
| [OPS-1](#ops-1) | Documented install path doesn't work | **High** (self-hosters) | Verified | S |
| [SEC-3](#sec-3) | Hard-coded `SECRET_KEY` in a public repo | Medium | Code | S |
| [SEC-4](#sec-4) | Werkzeug debugger on `0.0.0.0`; debug Compose file won't parse | Medium | Code + Verified | S |
| [SEC-5](#sec-5) | Container hardening, `.dockerignore`, tracked env file | Medium | Verified / Code | S |
| [BUG-6](#bug-6) | Solid bin: wrong checkbox defaults, no help text | Medium | Verified | S |
| [ARCH-1](#arch-1) | App only works via `python gfg_main.py` | Medium | Code + Verified | M |
| [OPS-2](#ops-2) | No tests, no CI | Medium | Verified | M |
| [OPS-3](#ops-3) | Dependencies and image unpinned; junk dependencies | Medium | Verified / Code | S |
| [UI-1](#ui-1) | Mobile layout | Medium | Verified | S–M |
| [UI-2](#ui-2) | Redundant JS, unused jQuery, three external CDNs | Medium | Verified | S |
| [UI-3](#ui-3) | No feedback while generating; double-submit | Medium | Verified | S |
| [UI-4](#ui-4) | Accessibility | Medium | Verified / Computed | M |
| [SEC-6](#sec-6) | No security headers | Low | Verified | S |
| [SEC-7](#sec-7) | Jinja autoescape off + `\|safe` + `inner_render` | Low (latent) | Code | S |
| [SEC-8](#sec-8) | Proxy headers, client-IP logging, privacy | Low | Verified / Inferred | S |
| [BUG-7](#bug-7) | Server won't start without IPv6 | Low | Verified | S |
| [BUG-8](#bug-8) | Exporter failures are silent | Low | Verified | S |
| [BUG-9](#bug-9) | Stale docs, help text and metadata | Low | Code | S |
| [BUG-10](#bug-10) | Cosmetic code/markup bugs | Low | Verified / Code | S |
| [ARCH-2](#arch-2) | Duplicated boilerplate, dead code | Low | Code | M |
| [UI-5](#ui-5) | Page weight and caching | Low | Verified | S |
| [UI-6](#ui-6) | Lost tab state, no deep links | Low | Code | S |
| [OPS-4](#ops-4) | License; the fork's CI pings someone else's site | Low | Code | S |
| [OPS-5](#ops-5) | Logging / observability | Low | Code | S–M |

---

### Critical

<a id="sec-1"></a>
#### SEC-1: Unbounded generation cost → trivial denial of service **[Verified]**

**What.** Every "Generate" click runs CadQuery synchronously inside one of Waitress's 6 threads. There is no cost model, concurrency limit, timeout, queue, rate limit or cache. A request's cost grows steeply with its settings, and nothing bounds it.

**Evidence** (single request, fresh process; 4 cores):

| Request | Result | Time |
|---|---|---|
| Divider bin 2×2×6, 3×3 compartments (typical) | 1 valid solid | **1.0 s** |
| Divider bin **6×6×12, 24×24 compartments**, all options *(within the code's own limits)* | 21.8 MB STL | **37.8 s**, 853 MB peak RSS |
| Holey bin, 8×8 holes | 3×3 units | 1.5 s |
| Holey bin, 16×16 holes | 5×5 units | 4.3 s |
| Holey bin, 24×24 holes | **7×7 units (293 mm)**, over the cap of 6 | 12.5 s |
| Holey bin, **40×40 holes** | **12×12 units (503 mm)** | **100.4 s** |

**Starvation test on the live server:** I fired **six legitimate max-size divider-bin requests** simultaneously, then requested the home page:

- Idle server: `GET /` took **0.04 s**.
- Under load: `GET /` took **196.6 s**.
- The six jobs each took 82–199 s (vs 38 s alone).

That's every worker thread busy and the 7th request, *even a trivial page view*, waiting in line. No exploit was needed; this is just what the form allows. With [BUG-1](#bug-1) a single request can be made far worse (100×100 holes ⇒ a computed 29×29-unit bin, not run).

**Impact.** On a public instance (the README advertises one), a single person with a loop can keep it down. On a private LAN it's an annoyance when two people click at once.

**Fix (in order of value):**
1. **Fix validation first** ([BUG-1](#bug-1), [BUG-2](#bug-2)) and cap *cost*, not just each field. A 6×6 bin with 24×24 compartments is "legal" yet costs 38 s. A simple estimate like `units_x × units_y × compartments_x × compartments_y` (plus a hole-count term for the Holey bin), calibrated from the table above, with a threshold is enough.
2. **Bound concurrency:** a `threading.BoundedSemaphore(2)` around generation, returning `503` with `Retry-After` when no slot frees within a couple of seconds. Cheap routes stay responsive.
3. **Add a hard timeout.** Threads can't be cancelled, so run generation in a worker *process* (`multiprocessing`, or `pebble.ProcessPool` which supports per-task timeouts) and terminate on overrun.
4. **Cache by canonical settings hash.** Identical requests (the default bin, mostly) are extremely common on a public tool and currently recompute from scratch.
5. **Rate-limit per client** (Flask-Limiter, or Traefik's `rateLimit` middleware).
6. Set container `mem_limit` and a size on the tmpfs ([SEC-5](#sec-5)).

---

### High

<a id="bug-1"></a>
#### BUG-1: Holey bin: the size caps are defeated **[Verified]**

**What.** `holeybin_generator.py` computes `sizeUnitsX/Y/Z` from the hole count in `precalculate()`, which runs in `__init__` **before and after** `validate_settings()`:

```python
self.precalculate()        # derives sizeUnits* from numHoles * keepout
self.validate_settings()   # clamps sizeUnits* to MAX_GRID_UNITS / MAX_HEIGHT_UNITS
self.precalculate()        # ...and immediately overwrites the clamped values
```

The clamp is pointless. Also: `numHolesX/Y`, `holeDepth`, `holeSize` and `keepoutDiameter` have **no maximum** at all.

**Evidence:**
```
numHolesX = numHolesY = 100, holeDepth = 1000
→ after "validation": sizeUnitsX=29 sizeUnitsY=29 sizeUnitsZ=144   (caps are 6 / 6 / 12)
```
Real geometry: 24×24 holes produced a 7×7-unit (293.5 mm) bin; 40×40 produced 12×12 (503.5 mm). The in-app help says "maximum is 6 units". Also, `numHolesX=0` → `ZeroDivisionError`.

**Related:** the form's "Width/Length in grid-units" inputs are **ignored server-side**. `precalculate()` overwrites them from the hole count. They exist only as JS-synced readouts, and that JS hard-codes `42`, `1.9` and `0.5`, so with a custom grid the number shown can differ from the bin generated.

**Fix.** Compute the required units, then *reject* with a message if they exceed the maximum ("This hole grid needs 7×7 units; the maximum is 6×6. Reduce the holes or keepout.") instead of silently clamping. Add `NumberRange` validators to every numeric field ([BUG-2](#bug-2)). Drive the JS from the same constants (or render the arithmetic server-side).

---

<a id="bug-2"></a>
#### BUG-2: No server-side validation **[Verified]**

**What.** The forms use `IntegerField(..., widget=NumberInput(min=1, max=6))`. `min`/`max` on the widget are **HTML attributes only**; there are no WTForms validators. Anything that bypasses the browser (curl, a stale tab, an extension, a bored teenager) goes straight to CadQuery. The generators' `validate_settings()` only ever applies `min()` (upper clamp) and never a lower bound.

**Evidence:**

| Input | Result |
|---|---|
| Divider bin `sizeUnitsX=0` | HTTP 500 (`ZeroDivisionError`) |
| Divider bin `compartmentsX=0` | HTTP 500 (`ZeroDivisionError`) |
| Divider bin `sizeUnitsX=-3` | HTTP 500 (`ValueError` in a direct probe with -2) |
| Baseplate `sizeUnitsX=0` | `IndexError` |
| Solid bin `sizeUnitsZ=0` | `Standard_DomainError` |
| Holey bin `numHolesX=0` | `ZeroDivisionError` |
| `magnetHoleDiameter=abc` | HTTP 200, page silently reloads (see [BUG-3](#bug-3)) |
| `magnetHoleDiameter=500` | HTTP 200, returns a **file** with no complaint (I didn't inspect it; a 500 mm "magnet hole" can't be sensible) |
| `gridSizeX=abc` (advanced form) | HTTP 500 |
| `gridSizeX=0` / `1e9` | accepted, saved to cookie |

**Fix [Fix verified].** WTForms' `NumberRange` validator *also* writes the HTML `min`/`max` attributes, so you get one source of truth:

```python
from wtforms.validators import InputRequired, NumberRange

sizeUnitsX = IntegerField(
    "Width",
    validators=[InputRequired(), NumberRange(1, Grid.MAX_GRID_UNITS)],
    widget=NumberInput(), default=2)
magnetHoleDiameter = DecimalField("Magnet-hole diameter",
    validators=[NumberRange(3, 12)], default=6.5, places=2)
```
I tested this: rendering gives `<input max="6" min="1" required ...>` and a posted `0` fails with *"Number must be between 1 and 6."* (which, once [BUG-3](#bug-3) is fixed, the user will actually see). Add cross-field checks in `validate()` (e.g. holes fit, compartments ≤ 4 × units, hole size ≤ keepout).

---

<a id="bug-3"></a>
#### BUG-3: Failures are silent **[Verified]**

**What.** Each generator's `handles()` is `form.id in request.form and form.validate_on_submit()`. When validation fails, control falls through to `render_index(...)`, and the result is the whole page again. `message` is passed to the template but **never rendered**; no template references `errors`, `message` or `flash` (confirmed by grep). Unhandled exceptions become Flask's bare "Internal Server Error" page.

**Evidence.** I simulated a tab left open past `WTF_CSRF_TIME_LIMIT` (default 1 hour). Result: HTTP 200, no download, and the visible text contains none of "expired", "token" or "try again". A rejected `magnetHoleDiameter=abc` likewise returned the page (HTTP 200); since no template renders errors, no message can appear. The Home tab is hard-coded as the active one, so the user lands back on it and sees what looks like "nothing happened".

**Fix.**
- Render `form.errors` (e.g. a Bootstrap alert at the top of the active tab) and re-open that tab.
- Register `@app.errorhandler(Exception)` / `500` / `503` handlers that render a friendly page, log a stack trace and an error ID.
- This app is stateless and anonymous, so consider `WTF_CSRF_TIME_LIMIT = None`: one-hour expiry is pure downside here.

---

<a id="bug-4"></a>
#### BUG-4: Holey bin without a stacking lip exports as two disconnected solids **[Verified, fix verified]**

**What.** With "Stacking lip" unchecked, the model is a `Compound` of **two solids**: the base (z 0–7) and the body (z 7–14), touching but not fused. With the lip on, the final `combine()` happens to fuse them, which hides the bug.

**Evidence.**
- Direct probe: lip OFF → `solids=2` (z=[0,7] and z=[7,14]); lip ON → `solids=1`.
- Sweep: **13 of 13** lip-off Holey configs failed the single-solid check; **0 of 9** lip-on configs did. It is the *only* failure across all 83 configs.
- Some slicers will cope with touching solids and some won't, and a STEP file will contain two bodies.

**Root cause.** In `generate_model()` the base and wall are only `.add()`ed to the stack, then `holey_grid()` cuts and *replaces* `result`. Without a lip nothing remains to trigger the fuse. `stacking_lip()` also returns `None` when disabled and that gets `.add()`ed.

**Fix [Fix verified]:**
```python
result.add(self.outer_wall(plane))
result = result.combine(clean=True)            # fuse base + wall BEFORE cutting the holes
plane = result.faces(">Z").workplane()
result = self.holey_grid(plane)
lip = self.stacking_lip(plane)
if lip is not None:                             # don't push None onto the stack
    result.add(lip)
result = result.combine(clean=True)
```
I tested this against the original on four configs (lip on/off × circle/hex): lip-off goes **2 → 1 solid with identical volume** (e.g. 21,778 mm³ both ways); lip-on output is unchanged.

---

<a id="bug-5"></a>
#### BUG-5: Custom grid sizes ("Advanced settings", the Raaco preset) are half-implemented **[Verified]**

The Advanced settings panel and the Raaco preset (39.5 × 54.5 mm) are offered to every user, but several generators assume the standard grid.

**5a: Height unit ≠ 7 mm: label tab overshoots the wall.** The base is always exactly 7.0 mm because `FLOOR_THICKNESS` (2.25) is a constant and never derived from `HEIGHT_UNITSIZE_MM`. Walls scale with the unit; the base doesn't.
- With a height unit of 8 and 4 units: wall top at **z = 31.0**, label tab top at **z = 32.0**, i.e. the tab sticks **1 mm above the wall**. Total height ≠ 4 × 8. (At 7 mm everything agrees, which is why nobody noticed.)
- **[Code]** The scoop ramp is anchored at `HEIGHT_UNITSIZE_MM` rather than the floor top, so it should be off by the same amount (not measured).
- **[Fix verified]** In `Grid.recalculate()`: `FLOOR_THICKNESS = HEIGHT_UNITSIZE_MM − BASE_BOTTOM_THICKNESS − BASE_TOP_THICKNESS` (= 2.25 at 7 mm). With it, unit=8 gives wall-top = tab-top = 32.0, valid, single solid; unit=7 is unchanged. (Light bin has separate hard-coded `5.25`, `2.25` values that need the same treatment.)

**5b: Light bin on a non-square grid builds square feet.** `lightbin_generator.py` uses the **X** dimension for **both** axes in three places:
- line 40: `rect(BRICK_UNIT_SIZE_X, BRICK_UNIT_SIZE_X)`
- line 50: `box(BRICK_UNIT_SIZE_X-6.7, BRICK_UNIT_SIZE_X-6.7, …)`
- line 76: `box(GRID_UNIT_SIZE_X_MM, GRID_UNIT_SIZE_X_MM, …)`

Measured on a 1×2 Light bin at z = 0.45 mm (inside the floor):

| Grid | Floor patch size | Gap between patches in Y |
|---|---|---|
| Standard 42 × 42 | 36.6 × 36.6 mm | 5.4 mm |
| Raaco 39.5 × 54.5 | **34.1 × 34.1 mm** | **20.4 mm** |

So on Raaco the feet are square on a 54.5 mm pitch: the gap between them in Y is 20.4 mm instead of 5.4 mm, and they no longer fill the grid cell they're meant to sit in. *(Fix: use the Y variants on those lines. Untested.)*

**5c: Baseplate hard-codes 42.** `baseplate_generator.py` has `.rect(42, 42)` for the pocket plus fixed profile points and a magic `fillet(3.999)`.
- Raaco 2×2: **crashes** (`StdFail_NotDone`).
- 45 mm grid, 1×1: "succeeds" with a valid solid, but volume jumps 1,276 → 1,568 mm³, because the pocket is still cut at 42 mm. A 44.5 mm bin will not fit in it. *(The pocket size is from reading the code; the volume change is measured.)*

**Fix options.** (a) Make the grid first-class: derive every constant from `Grid`, use X *and* Y consistently, and add tests on a Raaco-style grid. (b) Until then, hide Advanced settings, or label them "experimental, only the Divider/Solid bins are supported".

*Smaller related issues:* the preset dropdown always shows "Gridfinity" as selected even after you saved Raaco (`selected` is hard-coded); the in-app help always says "42 mm / 7 mm"; and nothing in the UI tells you a non-default grid is active.

---

<a id="sec-2"></a>
#### SEC-2: A bad `gridspec` cookie bricks the home page **[Verified]**

**What.** `index_get()`/`index_post()` do `values = cookie.split(','); float(values[0]) …` with no `try`.

**Evidence** (GET `/`):

| Cookie value | Result |
|---|---|
| `abc` | **HTTP 500** |
| `42,42` (two values) | **HTTP 500** |
| `0,0,0` / `nan,nan,nan` / `-5,42,7` | HTTP 200 (accepted; later generation fails or produces garbage) |

A malformed cookie (from a bug, an old version, a browser extension, a sibling subdomain, or hand-editing) turns the **entire site into a 500** until the user clears cookies. They'll never work out why.

**Also:** the cookie has no `Max-Age` (it's a session cookie, so "saved" settings vanish when the browser closes), no `SameSite`, `Secure` or `HttpOnly`. Posting `gridSizeX=abc` to the Advanced form is a 500 too.

**Fix [sketch, untested]:**
```python
def load_gridspec(raw):
    try:
        x, y, z = (float(v) for v in raw.split(","))
    except (AttributeError, ValueError):
        return None
    ok = all(math.isfinite(v) and lo <= v <= hi
             for v, (lo, hi) in zip((x, y, z), ((10, 200), (10, 200), (2, 50))))
    return (x, y, z) if ok else None        # None → fall back to defaults
...
resp.set_cookie("gridspec", value, max_age=365*86400, samesite="Lax", secure=request.is_secure)
```
Use the same validator for the Advanced form so bad input produces a message, not a 500.

---

<a id="ops-1"></a>
#### OPS-1: The documented install path doesn't work as written **[Verified]**

The README says: clone → `./build.sh` → `./deploy.sh` → browse to `:5000`. What actually happens:

| Step | Problem | Evidence |
|---|---|---|
| `./deploy.sh` | `docker-compose.yml` requires `${DATA_ROOT:?error}`, but the committed `.env.container` doesn't define it (only `GFG_DOMAIN`). | `docker compose --env-file ./.env.container config` → *"required variable DATA_ROOT is missing a value: error"* |
| `./deploy.sh` | The compose file declares an **external network** `proxy` that must already exist. The README never mentions `docker network create proxy`. | **[Code]** |
| `./deploy.sh` / `./debug.sh` | Scripts call the legacy **`docker-compose` v1** binary (end-of-life 2023). Modern hosts ship only `docker compose`. This machine has only the plugin. | Verified here that `docker-compose` isn't installed; yours may differ. |
| `./debug.sh` | `docker-compose.debug.yml` defines `environment:` **twice** → fails to parse under Compose v2+. | `failed to parse … mapping key "environment" already defined at line 9` |
| First generation | The Dockerfile never creates `/tmpfiles`; only the compose `tmpfs:` mount does. The image from `./build.sh` on its own returns 500 on every generation. | Removing `/tmpfiles`: baseplate POST → **HTTP 500** |
| `./build.sh` | Builds an image tagged `cadquery` that `deploy.sh` then ignores (compose rebuilds from `build: ./`). | **[Code]** |
| Warnings | `version: "3.3"` is obsolete (Compose warns). | Verified |

**Fix.** Make the quick start a single copy-pasteable block:
```bash
cp .env.container.template .env.container   # then edit DATA_ROOT
docker network create proxy                  # only if using the Traefik setup
docker compose --env-file .env.container up -d --build
```
Make the `proxy` network optional (use a Compose profile or a separate `docker-compose.traefik.yml` override), `RUN mkdir -p /tmpfiles` in the Dockerfile, de-duplicate `environment:` in the debug file, drop `version:` and `build.sh`, and use `docker compose` (v2) in scripts.

---

### Medium

<a id="sec-3"></a>
#### SEC-3: Hard-coded `SECRET_KEY` in a public repo **[Code]**

`app.config['SECRET_KEY'] = 'hPqPfz!y=moJ!MVO{*tqQO$_Itoo:'` is visible to everyone. It signs the session and CSRF tokens, so anyone can forge them. Today there's no login to protect, so the impact is low, but CSRF is currently the only gate in front of the expensive endpoints, and with the key public that gate is decorative. Secret scanners will also flag it.

**Fix.** `app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)` (fine for a stateless app; document that multi-worker deployments must set it), and consider rotating the old value out of any live deployment.

<a id="sec-4"></a>
#### SEC-4: Debug mode binds the Werkzeug debugger to `0.0.0.0` **[Code + Verified]**

`app.run(debug=True, host='0.0.0.0', …)` plus `docker-compose.debug.yml` publishing `5001:5001` puts the **interactive Werkzeug debugger** on every host interface. It's PIN-protected, but the PIN is not a strong boundary, and the README presents `./debug.sh` as a routine workflow. (The debug Compose file also doesn't parse; see [OPS-1](#ops-1).)

**Fix.** Publish as `127.0.0.1:5001:5001` and bind `host='127.0.0.1'` (or require an explicit opt-in env var to bind wider).

<a id="sec-5"></a>
#### SEC-5: Container hardening, `.dockerignore`, tracked env file **[Verified / Code]**

- **Runs as root.** The Dockerfile has no `USER`. `PUID`/`PGID` in the compose files are LinuxServer.io conventions that nothing in this image reads, so they do nothing. **[Code]**
- **No `.dockerignore`** **[Verified]**, so `COPY . /app` bakes `.git/`, any local logs and **`.env.container`** into the image layers.
- **`.env.container` is tracked in git** **[Verified]** (it holds the author's real domain). Anyone who edits it gets merge conflicts on `git pull`, and anyone who forgets can commit their own values. Ignore it and ship only the `.template`.
- **The tmpfs is unbounded** (defaults to ~50% of RAM) and there's **no `mem_limit`**. The max-size bin took ~290 MB over the ~565 MB import baseline, per concurrent job.

**Fix [sketch].** In the Dockerfile: create a non-root user, `mkdir /tmpfiles`, `HEALTHCHECK`. In compose:
```yaml
user: "1000:1000"
read_only: true
tmpfs: ["/tmpfiles:size=512m,uid=1000", "/tmp"]
mem_limit: 3g
cap_drop: [ALL]
security_opt: ["no-new-privileges:true"]
```
Add `.dockerignore` (`.git`, `logs`, `.env*`, `__pycache__`), `git rm --cached .env.container`, and add it to `.gitignore`.

<a id="bug-6"></a>
#### BUG-6: Solid bin: wrong checkbox defaults and no help text **[Verified]**

- `BooleanField("Magnet removal holes", default="False")`: `"False"` is a **non-empty string, so it's truthy**. The first page load renders **Magnet removal holes and Screw holes as checked** (verified in the rendered HTML), contradicting the evident intent. The divider bin (no `default=`) renders them unchecked.
- The Solid bin form never sets `field.description`, so **all 9 "?" help badges are empty**. Clicking one shows *"There is no extra information available for this field"*. The content already exists in `help_provider.py`.

**Fix.** `default=False`; copy the `__init__` description assignments from the divider/light bin forms. Decide what the *intended* screw-hole default is (the form says False, the `Settings` dataclass says True).

<a id="arch-1"></a>
#### ARCH-1: The app only works via `python gfg_main.py` **[Code + Verified]**

- Generators, logging and the `logger` global are initialised **only inside `if __name__ == "__main__"`**. Under `gunicorn gfg_main:app`, `flask run` or pytest, `generators == []` and `logger is None`. **[Verified]** In that import-time state `GET /` renders an **empty site with only a "Home" tab**; the `None` logger would raise `AttributeError` the first time a generation is logged **[Code]**. That's why `gunicorn` sits in `requirements.txt` yet can't be used, and the front page even claims "Gunicorn (the WSGI server that runs GC)". It's Waitress.
- `load_generators()` swallows per-generator import errors (logs, continues), so a broken generator means the site "starts fine" with a missing tab.
- Import style is inconsistent. Four generators use bare imports (`import classicbin_generator`) that only work because of a `sys.path` hack in the loader; Holey bin imports `holeybin_settings` **and** `generators.holeybin.holeybin_settings`, creating **two module objects** and two distinct `HoleShape` enums **[Verified: both are in `sys.modules`, `a is b` is False]**; it only works because the code compares strings.
- `importlib.util`/`importlib.machinery` are used with only `import importlib`, which works by accident. `exit(1)` uses the `site` builtin.

**Fix.** Use an app factory (`create_app()`) that configures logging and loads generators, make `generators/*` real packages with relative imports, and drop the path hack. Then `waitress`, `gunicorn`, `flask run` and tests all work. Fail startup loudly if a generator can't load.

<a id="ops-2"></a>
#### OPS-2: No tests, no CI **[Verified]**

Zero test files. The only workflow is a daily health ping of the author's production site (pinned by tag, not SHA, and it also runs on forks; see [OPS-4](#ops-4)). The git log is a record of users finding regressions: *"label tab protrudes from the bottom of 1-2 unit light bins" (#32)*, *"missing geometry in light bin" (#21)*, *"holey bin would not apply changes in grid-unit size"*, and two commits repairing a container that broke when CadQuery/conda changed underneath it (`54e24c7`, `f97d9d9`).

**Fix.** A small pytest suite catches most of this report:
- **Geometry (parametrised):** `isValid()`, exactly 1 solid, bounding box = `n × pitch − 0.5`, volume within ±1% of a golden value, across option matrices and **both** the Gridfinity and Raaco grids. (My throwaway fuzz found the Holey two-solid bug with a single `len(shape.Solids()) == 1` assertion.)
- **Web (test client):** malformed cookies, expired CSRF, out-of-range values → expect a clean 400/422 with a visible message, never a 500.
- **CI:** build the image, run the tests *inside it*, `ruff` lint, Dependabot, and pin Actions by SHA.

<a id="ops-3"></a>
#### OPS-3: Dependencies and image unpinned; junk dependencies **[Verified / Code]**

- Everything in `requirements.txt` is `>=`, with `gunicorn` listed **twice**.
- **Never imported anywhere [Verified by grep]:** `bootstrap-flask`, `gunicorn`, `click`, `colorama`. `itsdangerous`, `MarkupSafe`, `Werkzeug`, `Jinja2` are transitive.
- CadQuery comes from conda-forge **unpinned**, with `nlopt` bolted on through *pip into the conda env* as a workaround (`f97d9d9`). That mix is fragile; the history shows two breakages already.
- `libgl1-mesa-glx` was removed in Debian 13, so the build **will likely break** when the miniconda base moves to a trixie-based tag. **[Inferred]**
- **Alternative worth testing:** `pip install cadquery` worked cleanly here on Python 3.11 (~1 GB venv, about ten minutes on this sandbox's connection), so a `python:3.11-slim` + pinned `requirements.txt` (+ `libgl1`/`libglu1-mesa`, which I could not test in your image) would remove conda entirely. At minimum, pin `cadquery=<x.y>` and use an `environment.yml`/lockfile.

<a id="ui-1"></a>
#### UI-1: Mobile layout **[Verified]**

At 375 px wide (screenshot reviewed): the container is `max-width: 70%` → a **263 px** column; the six tabs stack into six rows; the description is squeezed into ~140 px with a thumbnail beside it; settings cards are `col-6` with no breakpoint, so each card is **72 px wide**; and the page overflows horizontally (scrollWidth 387 vs 375).

**Fix.** `container-xl` (or `max-width: min(1100px, 100%)`), `col-12 col-lg-6` for the cards, `col-12 col-md-9` for the description, a scrollable `nav-pills`/`flex-nowrap overflow-auto` tab strip.

<a id="ui-2"></a>
#### UI-2: Redundant JS, unused jQuery, three external CDNs **[Verified]**

- `base.html.j2` loads **`bootstrap.bundle.min.js` (which already contains Popper) *and* `popper.min.js` *and* `bootstrap.min.js`**, plus **unminified jQuery 3.7.0 (285 KB, no SRI)** that nothing uses (no `$(` anywhere). That's ~446 KB of JS to deliver ~81 KB of function: **~366 KB (82%) is dead weight.**
- Visible symptom: clicking "…" once creates **2 offcanvas backdrops** (double-dim overlay). I checked cleanup: both are removed on close, so it's cosmetic.
- The theme CSS `@import`s **Google Fonts** at runtime; combined with jsDelivr and code.jquery.com that's **three third-party hosts**. For a 3D-printing tool people run on workshop LANs, this means an offline self-hosted instance has **no Bootstrap JS, so the tabs don't work at all**, and every visit leaks to Google/CDNs (privacy/GDPR).

**Fix.** Keep only `bootstrap.bundle.min.js`; delete jQuery and the other two scripts. Vendor Bootstrap/Flatly/fonts into `static/` (hashed filenames) and drop the CDNs.

<a id="ui-3"></a>
#### UI-3: No feedback while generating; double-submit **[Verified]**

Generation takes 1–40+ s. The "Generate" button doesn't change or disable during the request (the spinner code in `settings_form.html` is **commented out**). Users will click again, and every click starts another full job. Disable the button and show a spinner on submit, and better, move to an async job with polling ([PROD-2](#prod-2)).

<a id="ui-4"></a>
#### UI-4: Accessibility **[Verified / Computed]**

- The "?" help badges are `<span>`s with a click handler: **not keyboard-focusable** (verified) and no `role`/`aria-label`.
- **0 of 31** `<img>` tags have `alt` text (verified).
- The Y-size label has `for="gridSizeZ"` (copy/paste), and there are **46 duplicate `id="content"`** elements on the page (verified).
- Tab buttons use `href` and lack `role="tab"`/`aria-controls`/`aria-selected`.
- Flatly's link green `#18BC9C` on white is about **2.4:1** contrast (computed by hand from the palette, not measured in the browser), well under WCAG AA's 4.5:1.

**Fix.** Make the badges real `<button type="button" aria-label="Help: Width">`, add alt text, use Bootstrap's documented tab markup, and darken the link colour.

---

### Low

<a id="sec-6"></a>
#### SEC-6: No security headers **[Verified]**
Responses carry no CSP, `X-Frame-Options`/`frame-ancestors`, `X-Content-Type-Options` or `Referrer-Policy`, and advertise `Server: waitress`. Easy via Flask-Talisman or Traefik middleware (a CSP needs the inline scripts moved to static files or given nonces).

<a id="sec-7"></a>
#### SEC-7: Jinja autoescape off + `|safe` + `inner_render` **[Code]**
`render_index()` builds its own `Environment` with **autoescape off**; templates use `|safe` on help/description HTML; and `inner_render` compiles strings as Jinja templates with `Template(value).render(...)` (unsandboxed). Today every one of those inputs is a trusted local file, so **nothing is exploitable now**, but it's a trap: the first time someone echoes a user value (say, to fix [BUG-3](#bug-3)) it's XSS or template injection. It also rebuilds the environment on every request (no template cache), and `FileSystemLoader(["./", os.path.realpath(__file__)])` includes a *file* path and depends on the working directory.

**Fix.** Use Flask's `render_template` with autoescape on (rename `*.html.j2` → `*.html`, or set `app.jinja_env.autoescape = True`), keep `|safe` for vetted static fragments only, and replace `inner_render` with a plain `{% include %}`.

<a id="sec-8"></a>
#### SEC-8: Proxy headers, client-IP logging, privacy **[Verified / Inferred]**
- I sent a forged `X-Forwarded-For` straight to Waitress: it was **ignored** (log shows `127.0.0.1`). **[Verified]** Waitress 3.0.2 defaults `clear_untrusted_proxy_headers = True`, and the app never sets `trusted_proxy`. **[Inferred]** This means a *real* proxy's header (Traefik) is stripped too, so `ProxyFix` does nothing and logs show the proxy's IP, not the client's. (Under the Flask dev server in debug mode, the header *is* honoured and spoofable.) Because `requirements.txt` says `waitress>=2.1.2`, behaviour also differs between 2.x and 3.x.
- The app logs client IP on every generation to a rotating file. If you serve EU users (the compose file uses `Europe/Amsterdam`), consider a retention note or hashing.

**Fix.** `waitress.serve(app, trusted_proxy="<proxy ip>", trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto", "x-forwarded-host"}, …)`, then test behind your proxy.

<a id="bug-7"></a>
#### BUG-7: Server won't start without IPv6 **[Verified]**
`waitress.serve(app, listen='*:5000')` binds IPv4 **and** IPv6. On a kernel with IPv6 disabled it dies at startup with `OSError: [Errno 97] Address family not supported by protocol`. This happened in my sandbox. Use `listen='0.0.0.0:5000'` (add `[::]:5000` only if needed).

<a id="bug-8"></a>
#### BUG-8: Exporter failures are silent **[Verified]**
`cadquery.exporters.export()` to a non-existent directory returns normally and writes **no file**. The app then 500s in `send_file`. The generators never check the file exists (or isn't empty) before sending. Check after export and surface a proper error. Stream via `tempfile`/`BytesIO` so there's no hard-coded `/tmpfiles` ([OPS-1](#ops-1)).

<a id="bug-9"></a>
#### BUG-9: Stale docs, help text and metadata **[Code]**
- `compartment_help.html` says "up to **3** compartments per unit… a 2×2 can have at most 36", but `MAX_COMPARTMENTS_PER_GRID_UNIT = 4` (since commit `b5452cc`) → **64**.
- Front page says Gunicorn runs the app; it's Waitress. "Docker (not FOSS…)": the Docker Engine is open source; Docker Desktop isn't.
- `CITATION.cff` says `version: 0.4.4` and an old commit; `version.py` is `0.4.5`. Footer says ©2024, README says ©2023.
- `holey_keepout_help.html` has a garbled sentence ("…to grab an item. of holes in Width and Length directions specify…").
- Typos: "Onlnie" (front page), "accomodate" (magnet help).
- `size_help.html` hard-codes "42 mm / 7 mm" even when the user changed them.

<a id="bug-10"></a>
#### BUG-10: Cosmetic code and markup bugs **[Verified / Code]**
- Holey bin download name uses a float: `HoleyBin_3x3x5.0.stl` (extra dot).
- Unused imports (`time`, `dataclass`, and `Flask` in every generator `main.py`), plus `from grid_constants import *` in 8 modules (and `gfg_main.py` also imports the module by name).
- `labelRidgeWidth: int = 13` and `dividerThickness: int = 1.5` (annotation says int, value is float).
- `MAX_*: float = 6` constants that are conceptually ints.

<a id="arch-2"></a>
#### ARCH-2: Duplicated boilerplate, dead code **[Code]**
The five `generators/*/main.py` files are ~90% identical (temp-file naming, `send_file`, cleanup hook, `handles()`), and drift: cleanup uses `logger.debug` in some, `print(ex)` in others; some log settings before generating, others after; three contain a dead `get_generator()` that calls `Generator(settings)` with the wrong arity. `Grid` repeats every derived formula in the class body *and* in `recalculate()`; make them `@property`s. Extract a shared `process()` helper and base `Form`/`Generator` classes; generate the download name from one place.

<a id="ui-5"></a>
#### UI-5: Page weight and caching **[Verified]**
The home page is **84 KB of uncompressed HTML** (all five forms plus 46 help fragments inline); the 14 JPEGs total **1.37 MB** and are served with `Cache-Control: no-cache`, so every visit revalidates all of them. Enable compression, convert to WebP, use hashed filenames with long `max-age`, `loading="lazy"`, and load help fragments on demand.

<a id="ui-6"></a>
#### UI-6: Lost tab state, no deep links **[Code]**
After any POST re-render the page resets to the Home tab. All generators live on one URL, so you can't link to "Divider bin" or share a configured bin. Use route-per-generator (`/divider-bin`) or at least `location.hash`.

<a id="ops-4"></a>
#### OPS-4: License; the fork's CI pings someone else's site **[Code]**
- **License.** The code is **CC BY-NC-SA 4.0**. Creative Commons itself advises against CC licenses for software; the NC term is incompatible with the "FOSS" framing on the front page; and the license says nothing about the **STL/STEP files the tool generates** (can people sell prints? share designs?). That's the upstream author's call, but worth clarifying the output's license at least.
- **Fork note.** `.github/workflows/serverstatus.yml` runs daily on **your fork** and hits `https://gridfinity.bouwens.co`: noise for you and (tiny) traffic for someone else. Disable it in the fork or parameterise the URL. `.vscode/tasks.json` is also tracked despite `.gitignore`, and runs `sudo ./deploy.sh`.

<a id="ops-5"></a>
#### OPS-5: Logging / observability **[Code]**
Logging is hard-wired to `/logs/access.log` at DEBUG level, and the `serverFilter` deliberately drops Waitress/Werkzeug logs, so there is **no real access log** (no status codes, no latencies), only "Generating X for IP" lines. You can't see how often 500s happen or how long generations take. Add a request ID, duration and a settings hash to a structured log line, a `/healthz` route (also useful for a container `HEALTHCHECK`), and a metrics endpoint or error tracker.

---

## 5. Product improvements (beyond fixing bugs)

These are the things I think would make people *prefer* this tool. They're suggestions, not defects.

| ID | Idea | Why it matters |
|---|---|---|
| <a id="prod-1"></a>PROD-1 | **3D preview before download** (three.js STL viewer; optionally a low-tessellation preview). | The app's own "Alternatives" list links to a generator "with a nice preview". Previews also cut wasted full-quality generations and server load. |
| <a id="prod-2"></a>PROD-2 | **Async jobs + progress** (POST → job ID → poll/SSE; worker pool with timeouts; cancel button). | Fixes starvation ([SEC-1](#sec-1)), the dead UI during generation ([UI-3](#ui-3)) and gives a natural home for caching. |
| <a id="prod-3"></a>PROD-3 | **Result cache** keyed by a hash of (normalised settings + grid + app/CadQuery version). | Identical requests are common and currently recompute. |
| <a id="prod-4"></a>PROD-4 | **Shareable URLs and remembered settings** (query string or `localStorage`), plus a few named presets. | "Here's the exact bin I use" is the natural way people share Gridfinity configs. |
| <a id="prod-5"></a>PROD-5 | **Fit-to-drawer / fit-to-space:** enter mm, get units + padding (and a baseplate to match). | Consistently a top request for Gridfinity tooling. |
| <a id="prod-6"></a>PROD-6 | **More parameters already hard-coded:** magnet depth (fixed 2.0 mm), wall thickness (1.9) and divider thickness (1.5), label tab width/angle, scoop radius, uneven or custom compartment layouts, baseplate magnet/screw holes. | Users print these for specific hardware; constants in `grid_constants.py` are the natural place to expose them. |
| <a id="prod-7"></a>PROD-7 | **Holey bin: hex size by across-flats.** Today "Size" is corner-to-corner, so a 1/4″ (6.35 mm) bit holder needs hand maths (AF × 1.1547). Add an across-flats option and inch input. | Screw-bit organisers are the main use case in the help text. |
| <a id="prod-8"></a>PROD-8 | **Export options:** STL quality setting (export uses CadQuery's coarse defaults of 0.1 mm / 0.1 rad; the small 0.8–1.6 mm base fillets may show visible faceting; I haven't inspected a mesh) and fix-and-enable 3MF (the help says it's "a little buggy"). | Better surface quality; slicer-friendly format. |
| <a id="prod-9"></a>PROD-9 | **A small JSON API** (`POST /api/v1/<generator>`) with the same validation. | Enables scripting and other front ends; falls out naturally once validation is server-side. |

---

## 6. Suggested roadmap

**Phase 1: "Stop the bleeding" (about 1–2 days)**
- [ ] Validators on every field + cost cap + clear error messages (BUG-1, BUG-2, BUG-3)
- [ ] Concurrency limit + 503 + timeout (SEC-1)
- [ ] Holey `combine()` fix (BUG-4) and Solid bin defaults/help (BUG-6)
- [ ] Defensive cookie parsing (SEC-2)
- [ ] `SECRET_KEY` from env; debug binds to localhost (SEC-3, SEC-4)
- [ ] Working README quick start; Dockerfile `mkdir /tmpfiles`; fix debug compose (OPS-1)
- [ ] `0.0.0.0` bind instead of `*` (BUG-7)

**Phase 2: "Make it safe to change" (about 3–5 days)**
- [ ] Pytest geometry + web suite, GitHub Actions, pinned dependencies/image, Dependabot (OPS-2, OPS-3)
- [ ] App factory + package imports; shared `process()` and base classes (ARCH-1, ARCH-2)
- [ ] Decide on custom grids: finish (BUG-5) or hide
- [ ] Container hardening, `.dockerignore`, untrack `.env.container` (SEC-5)

**Phase 3: "Make it nicer"**
- [ ] Mobile layout, single Bootstrap bundle, vendored assets, accessibility fixes (UI-1…UI-4)
- [ ] Async jobs + cache + preview (PROD-1, PROD-2, PROD-3)
- [ ] Shareable URLs, fit-to-space, more parameters (PROD-4…PROD-7)

---

## 7. Appendix

### A. Quick wins (each ≈ 30 minutes or less)
1. `default=False` on the Solid bin booleans; copy help descriptions in. *(BUG-6)*
2. Holey `combine()` fix (5 lines, tested). *(BUG-4)*
3. `FLOOR_THICKNESS` derived in `Grid.recalculate()` (1 line, tested on the divider bin). *(BUG-5a)*
4. Light bin X→Y on three lines. *(BUG-5b)*
5. Delete jQuery, `popper.min.js` and `bootstrap.min.js` from `base.html.j2`. *(UI-2)*
6. `listen='0.0.0.0:5000'`. *(BUG-7)*
7. `.dockerignore` + `RUN mkdir -p /tmpfiles`. *(SEC-5, OPS-1)*
8. `git rm --cached .env.container` + `.gitignore`. *(SEC-5)*
9. De-duplicate `environment:` in the debug compose file. *(OPS-1)*
10. Fix the stale help text (3 → 4 compartments/unit; Gunicorn → Waitress). *(BUG-9)*
11. Disable `serverstatus.yml` in the fork. *(OPS-4)*
12. `WTF_CSRF_TIME_LIMIT = None`. *(BUG-3)*

### B. Verification log (raw results)

| Probe | Result |
|---|---|
| Baselines at default grid | classic 2×2×6 3×3: 1.0 s, valid, 1 solid, bbox 83.5×83.5×46.4; light 3×2×3: 125.5×83.5×25.4; classic 4-unit no lip: 28.0 |
| Legal-range sweep (seeded, 83 configs: 29 classic, 14 solid, 14 light, 4 baseplate, 22 holey) | 13 problems, **all** Holey bin with lip off ("2 SOLIDS"); 13 of the 13 lip-off configs; 0 of 9 lip-on |
| Divider bin `compartmentsX=0`, `sizeUnitsX=0`, `-2` | `ZeroDivisionError`, `ZeroDivisionError`, `ValueError` |
| Baseplate `sizeUnitsX=0` | `IndexError` |
| Solid bin height 1 / height 0 | OK (valid) / `Standard_DomainError` |
| Holey bin caps (100×100 holes, 1000 mm deep) | units 29×29×144 |
| Height unit 8 (4 units, no lip) | wall top 31.0, label-tab top 32.0 (nominal 32.0) |
| Raaco, Divider bin / Light bin / Baseplate 2×2 | OK footprint / OK footprint but square feet / `StdFail_NotDone` |
| Light bin floor patches, 1×2 | standard 36.6×36.6, gap 5.4 mm · Raaco 34.1×34.1, gap 20.4 mm |
| Cookies: `abc`, `42,42` | HTTP 500 on `GET /` |
| Cookies: `0,0,0`, `nan,nan,nan`, `-5,42,7` | HTTP 200, accepted |
| Advanced form: `abc` / missing / `0` / `1e9` | 500 / 400 / 200 / 200 |
| Expired CSRF token | HTTP 200, no download, no message text |
| Missing `/tmpfiles` | baseplate POST → HTTP 500; exporter returns silently with no file |
| Max-size divider bin (6×6×12, 24×24, all options) | 37.8 s, 853 MB RSS, 21.8 MB output |
| Holey 8 / 16 / 24 / 40 holes per side | 1.5 / 4.3 / 12.5 / 100.4 s; units 3×3 / 5×5 / 7×7 / 12×12 |
| Starvation: 6 concurrent max-size + `GET /` | idle 0.04 s → **196.6 s**; jobs 82–199 s; six 21.8 MB outputs |
| Docker Compose v5.3.1 | prod: `DATA_ROOT` missing error with committed env file, `version` obsolete warning; debug: parse error (duplicate `environment`) |
| Forged `X-Forwarded-For` vs Waitress 3.0.2 | ignored; default `clear_untrusted_proxy_headers = True` |
| `listen='*:PORT'` with no IPv6 | `OSError: [Errno 97]` at startup |
| Browser (Chromium, CDN assets served locally) | offcanvas: 2 backdrops open / 0 after close; help modal works; Solid bin help empty; badge not focusable; Generate button not disabled; phone 375 px: container 263 px, cards 72 px, overflow 387 px |
| Static facts | 0 of 31 `<img>` have `alt`; 46 duplicate `id="content"`; JS 446 KB loaded vs 81 KB needed; images 1.37 MB, `Cache-Control: no-cache`; HTML 84,055 B |
| Import-time app state (`generators=[]`, `logger=None`) | `GET /` → 200 with only the "Home" tab |
| Holey bin module identity | `holeybin_settings` and `generators.holeybin.holeybin_settings` both loaded; different module objects, different `HoleShape` |
| Fix checks | NumberRange → HTML min/max + message ✔ · Holey combine: 2→1 solid, equal volume ✔ · `FLOOR_THICKNESS` derived: unit 8 wall = tab = 32.0 ✔ |

### C. Minimal reproductions

```bash
# Poisoned cookie → 500 on the home page   (SEC-2)
curl -s -o /dev/null -w '%{http_code}\n' -b 'gridspec=abc' http://localhost:5000/
```

```python
# Holey bin caps are defeated   (BUG-1)    — run from the repo root with cadquery installed
import sys, logging; sys.path.insert(0, ".")
import gfg_main, grid_constants
gfg_main.logger = logging.getLogger("GFG")
m = {g.__name__: g for g in gfg_main.load_generators()}["holeybin"]
s = m.settings.Settings(); s.numHolesX = s.numHolesY = 100; s.holeDepth = 1000
m.generator.Generator(s, grid_constants.Grid())
print(s.sizeUnitsX, s.sizeUnitsY, s.sizeUnitsZ)   # → 29 29 144   (caps are 6 / 6 / 12)
```

```python
# Holey bin, lip off → two solids   (BUG-4)
s = m.settings.Settings(); s.addStackingLip = False
shape = m.generator.Generator(s, grid_constants.Grid()).generate_model().val()
print(len(shape.Solids()))                         # → 2  (should be 1)
```

### D. Environment notes
Verification ran on Python 3.11.15, CadQuery 2.8.0, Flask/Flask-WTF/WTForms 3.2.2, Waitress 3.0.2, Chromium via Playwright, Docker Compose v5.3.1. My throwaway test scripts live only in the session scratch area and aren't part of this commit; they're a good seed for the pytest suite in [OPS-2](#ops-2) if you want them turned into one.
