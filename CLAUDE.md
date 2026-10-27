# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Phase 0 (setup) done. The repo holds the plan (`README.md`), the phased plan with "done when" criteria
(`docs/roadmap.md`), the dataset survey (`docs/data-sources.md`) and the research framing
(`docs/research-outline.md`). Read the roadmap before starting any work; record new commands here.

## Commands

```sh
uv sync                                   # Python 3.12 venv: Open3D 0.20, IfcOpenShell 0.9, pye57, pytest
uv run pytest                             # tests
uv run python scripts/fetch_data.py       # CRAS IFC + PC2Model real-indoor_modelling_3 (UVigo) into data/;
                                          # resumable, idempotent; ~5-10 min at Zenodo speeds
uv run python scripts/show_unaligned.py   # scan + IFC in one Open3D window, unaligned; writes
                                          # docs/images/stage0-unaligned{,-scan,-ifc}.png (overview + close-ups;
                                          # --no-interactive: PNGs only)
```

- `src/scan_vs_bim/fetch.py`: chunked, retried, resumable HTTP range downloads and single-member zip
  extraction (Zenodo is slow and returns 504s; a long `remotezip` stream died).
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
- **PC2Model** (10.2 GB zip): don't download whole. Zenodo serves HTTP range requests, so pull single
  samples (chunked, retried ranges; see `scripts/fetch_data.py`). Half its samples are randomly scaled
  0.5–1.5, so registration needs a scale estimate or must report those separately. Report the 31
  house/indoor samples separately.
- **INESC CRAS** (4.3 GB zip, ~585M ASCII points, likely 25–30 GB unzipped): stream the zip member and
  subsample on the fly; never extract.
- Open3D cannot read `.e57`; use `pye57` (works on Apple Silicon).
- Tolerances must come from a standard (USIBD Level of Accuracy), not be invented.
- Carbon factor source is undecided and licence-gated (repo is public); see `docs/data-sources.md`.

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
