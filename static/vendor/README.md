# Third-party assets, served from this folder

The page used to load these from four third-party hosts (jsDelivr, cdnjs, code.jquery.com and
Google Fonts). That sent every visitor's address to those hosts and broke the tabs, the preview
and the fonts on a machine without internet access, such as a workshop LAN. They are served from
here now, at the same versions as before.

| File | What | Version | Licence | Source |
|---|---|---|---|---|
| `bootswatch/flatly.min.css` | Bootstrap CSS, Flatly theme | Bootswatch 5.3.2 | MIT | npm `bootswatch@5.3.2`, `dist/flatly/bootstrap.min.css`, **modified** (below) |
| `bootstrap/bootstrap.bundle.min.js` | Bootstrap JavaScript with Popper | Bootstrap 5.3.2 | MIT | npm `bootstrap@5.3.2`, `dist/js/bootstrap.bundle.min.js`, unmodified |
| `three/three.min.js` | three.js, for the 3D preview | r128 | MIT | npm `three@0.128.0`, `build/three.min.js`, unmodified |
| `fonts/*.woff2`, `fonts/fonts.css` | Inter and Space Grotesk, variable weight, latin and latin-ext | 5.3.0 | SIL OFL 1.1 | npm `@fontsource-variable/inter`, `@fontsource-variable/space-grotesk` (`fonts.css` is ours) |

The licence texts are in `licenses/`. jQuery is gone: nothing used it.

## Checked against what the page loaded before

- `bootstrap.bundle.min.js` and the original Flatly file match the SRI hashes that `base.html.j2`
  pinned (`sha384-C6RzsynM9kWDrMNeT87bh95OGNyZPhcTNXj1NW7RuBCsyN/o0jlpcV8Qyq46cDfL` and
  `sha256-JbXZMBEeXZolOq78p+ASw+5YCEXPUmNmKmIMYeGDTe0=`).
- `three.min.js` has the same SHA-256 as the file served by
  `cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js`
  (`9274bbcec8d96168626c732b5d31c775aa8cfb7eaa0599bec0c175908a2c1ce2`).

## The one modified file

`bootswatch/flatly.min.css` is the npm file (sha256
`25b5d930111e5d9a253aaefca7e012c3ee580845cf5263662a620c61e1834ded`) with two things removed:

- its `@import url(https://fonts.googleapis.com/css2?family=Lato...)`. Flatly asks Google for
  Lato, which `theme.css` never uses (the page is set in Inter and Space Grotesk);
- the trailing `/*# sourceMappingURL=... */` comment, which pointed at a file that is not here.

## Integrity

`checksums.sha256` lists every file here. `tests/test_assets.py` checks it, so a vendored file
cannot be edited, or replaced, unnoticed. After a deliberate update, regenerate it from this
folder with `find . -type f ! -name checksums.sha256 ! -name README.md | sort | sed "s|^\./||" | xargs sha256sum > checksums.sha256`.

## Updating

Fetch the new version from npm (`npm pack bootstrap@x.y.z`, and so on), copy the file over,
repeat the Flatly edit above, update the table and the checksums, and look at the page.
Nothing here is built from source.
