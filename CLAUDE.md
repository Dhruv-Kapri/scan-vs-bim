# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Phase 0 (setup) done. The repo holds the plan (`README.md`), the phased plan with "done when" criteria
(`docs/roadmap.md`), the dataset survey (`docs/data-sources.md`) and the research framing
(`docs/research-outline.md`). Read the roadmap before starting any work; record new commands here.

## Commands

```sh
uv sync                                   # Python 3.12 venv: Open3D 0.20, IfcOpenShell 0.9, pye57; dev: pytest,
                                          # jupyter/ipykernel, nbclient, matplotlib, scipy
uv run pytest                             # tests
uv run python scripts/fetch_data.py       # CRAS IFC + CRAS scan zip (4.27 GB, never extracted; measured 2026-10-28:
                                          # 0.1-0.5 MB/s on one connection, ~3.5 h) + PC2Model real-indoor_modelling_3 (UVigo) into
                                          # data/; resumable, idempotent
uv run python scripts/build_cras_cache.py # stream the CRAS zip into data/cras/cras_voxel_1cm.npz (first point per
                                          # 1 cm voxel; xyz/rgb/cls + meta; idempotent; --zip/--out/--voxel)
uv run python scripts/find_scaled_sample.py # reads only PC2Model's 137 transform files (cached in data/pc2model/
                                          # transforms/), writes outputs/pc2model_scales.csv, fetches the smallest
                                          # scaled sample; --no-fetch to list only
uv run jupyter nbconvert --to notebook --execute --inplace notebooks/02_align.ipynb
                                          # notebook 02 (UVigo + fur_010; ~2 min, <1 GB RSS; needs fetch_data.py and
                                          # find_scaled_sample.py first)
uv run python scripts/show_unaligned.py   # scan + IFC in one Open3D window, unaligned; writes
                                          # docs/images/stage0-unaligned{,-scan,-ifc}.png (overview + close-ups;
                                          # --no-interactive: PNGs only)
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=3000 notebooks/01_data.ipynb
                                          # re-run notebook 01 in place (needs the CRAS cache + IFC; ~5-6 min, peak
                                          # RSS under 3 GB); rewrites notebooks/01_cras_slice.json (read by 03/04)
uv run jupyter nbconvert --to notebook --execute --inplace --ClearMetadataPreprocessor.enabled=True \
  notebooks/00_pipeline_overview.ipynb    # notebook 00 (toy room, no downloaded data); the flag drops timing
                                          # metadata so re-runs give no diff
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=1800 notebooks/03a_compare.ipynb
                                          # notebook 03a (CRAS room, per-element verdicts with and without oracle
                                          # labels; ~1.5 min, peak RSS 1.1 GB; needs the CRAS cache + IFC and
                                          # notebooks/01_cras_slice.json; writes outputs/03a/)
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=1800 notebooks/03b_perturbed.ipynb
                                          # notebook 03b (03a's verdicts on a perturbed copy of the CRAS model: three
                                          # walls moved 1/3/10 cm in an IFC copy, door/column/wall masked in the scan;
                                          # ~2-3 min, peak RSS 1.8 GB; needs the same inputs as 03a; writes
                                          # outputs/03b/: perturbed IFC, manifest.json, scores_*.csv, figure)
uv run jupyter nbconvert --to notebook --execute --inplace --ClearMetadataPreprocessor.enabled=True \
  notebooks/04a_report.ipynb              # notebook 04a (03a's no-labels verdicts as a ScanVsBim_Verdict pset in an IFC
                                          # copy, plus a BCF 2.1 file with one issue per non-OK element; ~10 s; needs
                                          # the CRAS IFC and outputs/03a/*.csv from 03a; writes outputs/04a/)
```

- `src/scan_vs_bim/load.py`: E57 loader (seeded subsample, poses applied) and IFC loaders (per-element meshes
  with GlobalId + class in world coordinates, or one merged mesh; `only_guids=` tessellates just those
  elements, 17 s instead of minutes for the 35 room elements (measured 2026-10-28); it cannot be combined with
  `exclude=`). `tests/run_notebook.py`: `run_notebook(path)`
  executes a notebook top to bottom for tests (nbclient; raises on any cell error).
- `src/scan_vs_bim/fetch.py`: chunked, retried, resumable HTTP range downloads and single-member zip
  extraction (Zenodo is slow and returns 504s; a long `remotezip` stream died).
- `src/scan_vs_bim/cras_cache.py`: streams the 26.8 GB ASCII zip member in 64 MB blocks (never extracted
  or loaded whole), keeps the first point per voxel; xyz float32, rgb/class uint8, intensity dropped.
  Measured 2026-10-28 on the real member (8 GB Apple Silicon): 584,701,977 points read (= declared),
  20,404,814 kept at 1 cm, 5.3 min, max RSS 1.22 GB, cache 326 MB; extent x 0.01..18.32, y -4.18..20.27,
  z -2.07..3.25 m. Memory is ~0.75 GB fixed (64 MB blocks) + ~29 MB per million occupied voxels (synthetic).
  A run whose point count differs from the header's raises and writes no cache. Run it detached:
  `mkdir -p outputs/jobs; nohup sh -c 'uv run python scripts/build_cras_cache.py; echo "exit=$?" > outputs/jobs/cras-cache.status' > outputs/jobs/cras-cache.log 2>&1 &`
  then poll the `.log` and `.status` files.
- E57 reader: `pye57` 0.4.19 works on Apple Silicon. Measured 2026-10-27: `show_unaligned.py` peaks
  under 2 GB RSS; the CRAS IFC tessellation (~1.2M triangles) takes about 90 s.

## What gets built

Pipeline: scan (`.e57`/`.las`) + BIM (`.ifc`) → **align** (FPFH+RANSAC, then point-to-plane ICP) →
**compare** per IFC element (OK / shifted / missing / not visible) → **report** (verdicts as IFC
properties + BCF issues) → **show** (That Open viewer + MapLibre) → **carbon** (embodied carbon of
scan-confirmed elements). Python with Open3D and IfcOpenShell; the viewer is JavaScript.

- Phases are strictly ordered: the next phase does not start until the previous one's "done when" is met.
- Phase 0.5 is notebook-first: notebooks `00`–`05` each work one stage on a small slice, with rendered
  outputs committed as **static PNGs** (not interactive 3D widgets) so they render on GitHub. Clean code
  moves into the package afterwards. The web viewer skips notebooks.
- Tooling: a `uv` Python project, Python 3.12, Open3D 0.20, IfcOpenShell 0.9 (`ifcopenshell.geom`).

## Constraints that shape the code

- **Dev machine: Apple Silicon, 8 GB RAM, ~68 GB free disk, no GPU.** Everything must run on it.
- **Never commit data.** `data/`, `outputs/` and point-cloud/zip extensions are gitignored; datasets
  keep their own licences.
- **PC2Model** (10.2 GB zip): don't download whole. Zenodo serves HTTP range requests, so pull single samples
  (chunked, retried ranges; see `scripts/fetch_data.py`). 71 of 137 samples are scaled (0.69–1.98 measured;
  the record says 0.5–1.5), so registration needs a scale estimate or must report those separately. Report the
  31 house/indoor samples separately.
- **INESC CRAS** (4.3 GB zip, ~585M ASCII points, likely 25–30 GB unzipped): stream the zip member and
  subsample on the fly; never extract.
- Open3D cannot read `.e57`; use `pye57` (works on Apple Silicon).
- Tolerances must come from a standard: USIBD LOA30 (≤ 15 mm at 2σ), not invented. PC2Model's `LOA_mean`
  is a registration residual, not a USIBD band (see `CONTEXT.md`).
- Carbon factors: ÖKOBAUDAT, downloaded at runtime into `data/`; commit only the IFC-material → UUID
  mapping, never factor values (its terms allow only unmodified copies). See `docs/data-sources.md`.

## Docs conventions

- In `docs/data-sources.md`, facts are marked **Verified** (with date, read from the source) or
  unverified. Keep that distinction when adding or changing facts.
- `docs/reference/*.pdf` are reading lists with their HTML sources in `docs/reference/src/`; edit the HTML.

## Agent skills

### Issue tracker

Issues live in GitHub Issues for Dhruv-Kapri/scan-vs-bim (via `gh`). See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root (created lazily). See `docs/agents/domain.md`.
