# Roadmap

Target: about 8 weeks, part-time, from late October 2026 to mid-December 2026, so the results exist
before the January 2027 PhD deadlines. Each phase ends in something that runs and can be shown; the
next phase does not start until the previous one is done.

## 0. Setup (week 1)

- `uv` Python project, Open3D and IfcOpenShell installed and imported on Apple Silicon.
- Download the INESC CRAS IFC (67 MB) and one PC2Model indoor sample; load both and render them.
- Dev machine limits: 8 GB RAM, about 68 GB free disk. Pull PC2Model samples one by one over HTTP
  ranges and stream-subsample CRAS; see [data-sources.md](data-sources.md). Open3D 0.20 and
  IfcOpenShell 0.9 (with `ifcopenshell.geom`) install and import with Python 3.12 on Apple Silicon
  (checked 2026-10-27); E57 needs a separate reader.
- **Done when:** one script loads a scan and an IFC and shows them in the same window (unaligned).

## 0.5 Explore (weeks 1-2)

Notebooks before code, as in the rooftop project: each one works one stage inline on a small slice,
with rendered outputs committed so it reads on GitHub. The clean version goes into the package after.

| # | Notebook | Slice | Question it answers |
| --- | --- | --- | --- |
| 00 | Pipeline overview | a toy room written as a real IFC (`ifcopenshell.api`), one wall moved 4 cm | the whole chain by hand, with known answers |
| 01 | Data | one CRAS room (subsampled) + its IFC; one PC2Model indoor sample | is the CRAS scan already in the IFC's frame? can the 21 scanner positions be recovered? |
| 02 | Align | PC2Model `real-indoor_modelling_3` (UVigo, unscaled) + one small scaled sample | FPFH+RANSAC+ICP vs ground truth; the scale problem, with one scale estimate tried |
| 03 | Compare | the CRAS room, real and perturbed model | per-element verdicts; occluded vs missing; tolerance |
| 04 | Report + carbon | the CRAS room | IFC properties, BCF export, a small carbon table |
| 05 | Validation | 9 PC2Model samples (3 house, 3 simulated indoor, 3 real indoor; smallest of each, scaled and unscaled); hand check of CRAS verdicts | good enough to formalise? |

Terms (verdict, element, clutter, perturbed model, ...) are defined in [CONTEXT.md](../CONTEXT.md).

- Notebooks are plain `.ipynb` with outputs committed. They import helpers from the `scan_vs_bim`
  package (fetch, loaders); the stage logic stays inline until the stage is formalised.
- No notebook for the web viewer (phase 4); it is JavaScript and goes straight to code.
- Static PNG snapshots (Open3D offscreen rendering), not interactive 3D widgets, so the outputs render on GitHub.
- **CRAS data:** download the zip once, never extract it; stream its single member locally into a
  ~1 cm voxel cache of the whole lab, keeping RGB and scan class. The IFC has no `IfcSpace`, so the
  room is a hand-picked box bounded by IFC walls.
- **CRAS frame:** whatever 01 finds, 03 starts from a recorded transform: always ICP-refine (and report
  the correction); coarse-register with 02's method first if the scan is far off.
- **Compare (03):**
  - Tolerance: USIBD LOA30 (≤ 15 mm at 2σ); quote it from the spec PDF, not secondary sources.
  - Verdicts go to building elements only (walls, slabs, columns, doors, windows, coverings, stairs).
    Furniture counts as clutter.
  - Run 03 both with and without the CRAS scan classes as oracle labels; the gap is what learned
    segmentation would be worth.
  - Missing vs not visible needs scanner positions. CRAS gives none, so 01 tries to recover them from
    the shadow holes on the floor. If that fails, the two merge into **not confirmed**.
  - Known answers come from perturbed copies of the IFC, each change its own perturbed model and run, scored
    in the real model's refined frame (refining against a perturbed model lets moved walls drag the frame by
    13 mm), with the changes listed in a JSON manifest:
    - one wall moved perpendicular to its face by 1 cm (both ways), 3 cm and 10 cm, one IFC per move. The wall
      must be OK in the baseline, one-sided and inside the box; in the CRAS room only `Drywall:973242` is, and
      only with labels. Expected verdict: LOA30 on the true deviation of the wall's plane (1 cm away: OK,
      3 and 10 cm: shifted). 1 cm into the room puts the plane 1 mm inside the 15 mm edge, where the 95 %
      rule on the points cannot say OK (predicted 73.6 %, read 73.5 %): a result about the rule, not a
      failed control;
    - one door, one element that is OK in the baseline (the floor slab) and one wall where clutter hides it
      deleted, as scan masks by geometry (element-class points within BAND), not IFC changes; the room's only
      column has 0 scan points, so it was dropped; with labels all three read "too few points" by construction;
    - occlusion control: the hidden wall, and a second wall with more clutter inside the band, deleted and
      present, with the clutter in front removed too. Occlusion moves the share within tolerance by up to 7
      points and flips no verdict (a deleted wall never reads OK or shifted from its leftover points).
  - Recorded negative result (03b): with labels the moves get the expected verdict, except the 1 cm edge
    case; without labels none does. No wall is OK without labels, and for 3 and 10 cm the counted points
    rise (clutter enters the band) and the one-cluster share falls to 79 % against the 80 % rule.
- **Carbon (04):** ÖKOBAUDAT A1-A3 factors, downloaded at runtime into `data/`. Only the project's own
  mapping (IFC material → dataset UUID) is committed. See [data-sources.md](data-sources.md#carbon-factors).
- **Gate, fixed before 05 runs.** These thresholds are judgement calls, not taken from a standard:
  - Registration success per PC2Model sample, after ICP: rotation error ≤ 2°, translation error ≤ 5 cm,
    and scale error ≤ 1% on scaled samples. At least 6 of the 9 must succeed.
  - Perturbed CRAS model: every injected change beyond tolerance gets the right verdict, and at most 10%
    of untouched elements are falsely flagged shifted or missing.
  - Hand check of 20 random real CRAS elements: at least 80% agree with the verdict.
- **If 05 fails:** at most one week of tuning inside 0.5. If it still fails, write it up as a negative
  result and continue; it motivates the learned registration under Later.
- **Done when:** 00-05 run top to bottom and 05 meets the gate (or the negative result is written up).

## 1. Align (weeks 2-3)

Notebook 02's code moves into the package and runs on all 31 building/indoor samples, then the rest.


- Coarse: voxel downsample, FPFH features, RANSAC global registration (Open3D).
- Fine: point-to-plane ICP.
- The model side: sample the IFC or OBJ surfaces into a point cloud so both sides use the same tools.
- Score on PC2Model with its ground-truth transforms: rotation error, translation error, success rate,
  per category. Start with the building categories (houses, indoor), then run the rest.
- PC2Model applies random scaling to half its samples, so the baseline needs a scale estimate
  (or must report those samples separately). Notebook 02 tries one estimate; decide from its result.
- **Done when:** a reproducible results table, with the exact command that produced it.

## 2. Compare (weeks 3-5)

- For each IFC element: its geometry (IfcOpenShell geometry iterator), the scan points within a
  tolerance band, and the distances between them.
- Verdict per element: **OK** (within tolerance), **shifted** (points cluster at an offset),
  **missing** (too few points), **not visible** (occluded: not scanned is not the same as not built).
- Tolerance values from a standard, not invented. Check the USIBD Level of Accuracy specification,
  which PC2Model also refers to.
- **Done when:** a per-element CSV for the CRAS lab, checked by hand on a sample of elements.

## 3. Report (week 5)

- Write the colour-coded verdict back onto the IFC elements as properties.
- Export one BCF issue per deviating element (IfcOpenShell's BCF module), so it opens in any BIM tool.
- **Done when:** the BCF file opens in a free viewer and each issue points to the right element.

## 4. Show (weeks 6-7)

- Static web page: That Open viewer loading the annotated IFC, coloured by verdict.
- Georeference: write the site location into the IFC (IfcMapConversion) and place the building on a
  MapLibre map, as the rooftop project does for cities. Blocked as written: the CRAS IFC is IFC2X3 and
  its site location is Revit's default ([#2](https://github.com/Dhruv-Kapri/scan-vs-bim/issues/2)).
- **Done when:** a public GitHub Pages link.

## 5. Carbon (week 7)

The sustainability layer: what does the as-built building contain, in carbon terms?

- Quantities per element from IFC geometry (volume, area), mapped from the IFC material to a carbon
  factor (kgCO2e per unit).
- Report: embodied carbon of the elements the scan **confirms**, separately from elements that are
  missing or not visible. The carbon cost of the deviations is the difference.
- Why it matters: a scan-verified inventory of what is in an existing building is the input to
  material passports and component reuse, which design-model numbers alone can't support.
- Carbon factor source: ÖKOBAUDAT, downloaded at runtime (its terms allow only unmodified copies);
  see [data-sources.md](data-sources.md#carbon-factors). Only the material mapping is committed.
- **Done when:** a carbon table for the CRAS lab with every factor's source cited, labelled as an
  estimate (A1-A3 product stage only).

## 6. Write-up (week 8)

- README results: the PC2Model table, the CRAS case study, screenshots, the live link.
- Update the [research outline](research-outline.md) with the measured results.

## Later, not in this scope

- A learned registration step, or point-cloud segmentation (Sonata / Utonia) to tell clutter from
  structure. These need a cloud GPU.
- Scan-to-IFC: generating the model from the scan, then checking it with the Graham bylaw rules.
- An AI agent over the scan and the IFC ("which walls are more than 2 cm off?").
- Multi-epoch construction progress (the Nothing Stands Still dataset; check its licence first).
- Image capture instead of a laser scan: photos turned into a point cloud (COLMAP, MapAnything), then
  phases 1-2 unchanged. Evaluated in [image-capture-evaluation.md](image-capture-evaluation.md); start
  with its one-week ETH3D experiment, which decides whether it is worth building.
