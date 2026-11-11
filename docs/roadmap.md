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
  room is a hand-picked box bounded by IFC walls. The box only picks the elements to judge; each element
  is judged on its own patch, the scan points near its surface wherever they lie (issue #23), not on a crop.
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
    - one door, one element that is OK in the baseline (the east wall `919433`; the floor slab before #23) and one wall where clutter hides it (`979093`; `919433` before #23)
      deleted, as scan masks by geometry (element-class points within BAND), not IFC changes; the room's only
      column has 0 scan points, so it was dropped; with labels all three read "no points" by construction;
    - occlusion control: the hidden wall, and a second wall with more clutter inside the band, deleted and
      present, with the clutter-class points in front removed too (unassigned points stay). Without labels,
      occlusion moves the share within tolerance by up to 7 points; with labels by 0. Neither wall is
      OK in the baseline (the hidden wall is shifted with labels, not confirmed without; the other is not
      confirmed), so the control cannot show occlusion costing an OK; it shows only that a
      deleted wall never reads OK or shifted from its leftover points.
  - Recorded negative result (03b): with labels the moves get the expected verdict, except the 1 cm edge
    case; without labels none does. No wall is OK without labels, and for 3 and 10 cm the one-cluster
    share is 78 % against the 80 % rule (79 % before #23's patches; the counted points rise only at 10 cm).
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
  The gate failed after the tuning week (registration 7 of 9, perturbed model and hand check fail); the
  negative result is written up in [phase-0.5-negative-result.md](phase-0.5-negative-result.md).

## 1. Package and align (weeks 3-5)

Planned 2026-11-09, after the Phase 0.5 negative result. The stage logic the notebooks copy moves into the
package ([#33](https://github.com/Dhruv-Kapri/scan-vs-bim/issues/33)), the registration runs on all 137
PC2Model samples, and the verdict-rule fixes that the negative result deferred are made. Terms (sample,
scaled sample, centroid error, registration success, seen sample, false flag) are in [CONTEXT.md](../CONTEXT.md).

Order of work:

1. Start the detached, resumable download of all 137 samples (about 8.9 GB; the 25 house samples are 7 GB).
   It is the long pole and runs while the rest is done.
2. mypy and annotations ([#34](https://github.com/Dhruv-Kapri/scan-vs-bim/issues/34)).
3. Registration into the package, in two steps: a pure move that leaves 05a's nine rows unchanged; then the
   scaled flag is dropped and scale is fitted on every sample ([ADR 0001](adr/0001-fit-scale-on-every-sample.md)),
   05a and 05c are re-run and their changed numbers recorded.
4. Verdict logic into `scan_vs_bim.compare`, as pure moves split over several tickets: re-run 03a, 03b, 03c
   and 05b give unchanged verdicts.
5. Verdict-rule fixes, each with its acceptance stated before tuning, tuned on 03c's two held-out rooms only
   (never room B, as in #20):
   - the wall side test (#27): a point may take the side away from the room only if the scan shows the
     neighbouring space there;
   - large slabs and coverings (#26): offsets against a plane fitted to the element's own points, its tilt
     reported per element;
   - delete `face_coverage`, whose rule #30 rejected;
   - false flags counted against the baseline verdict ([ADR 0002](adr/0002-false-flags-against-baseline.md)).
6. The registration benchmark: the 37 building samples (25 house, 6 simulated indoor, 6 real indoor) first,
   then the 100 object samples.
7. Room B re-reported: 03a, 03b and 05b re-run once after the fixes. Their gate numbers are reported as
   "after Phase 1", not as a new pass or fail of the Phase 0.5 gate.

The benchmark:

- Pipeline: 05a's, frozen (coarse FPFH + RANSAC + ICP over seeds 0 to 4, the draw with the highest coarse ICP
  fitness, then `refine_plan`), except that scale is fitted on every sample. No further tuning.
- Success: 05a's thresholds (rotation ≤ 2°, centroid error ≤ 5 cm, scale error ≤ 1%), the scale criterion
  now on every sample. Also reported: median and p90 of each error per category, scaled and unscaled rows
  separately, and seed-0 success as context.
- Seen samples (05a's nine gate samples, 05c's tuning samples) are marked; success rates are given over all
  samples and over unseen samples only.
- A detached, resumable script writes per-sample rows to `outputs/`; `docs/phase-1-results.md` holds the
  table, the command and the commit.

- **Done when:** all four hold:
  - the benchmark table for all 137 samples, with the exact command that produced it;
  - #33 complete: each copied helper exists once in the package with tests, the notebooks import it, and the
    pure moves left the numbers unchanged;
  - each rule fix meets its pre-stated acceptance on the held-out rooms;
  - room B re-reported after the fixes.

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
