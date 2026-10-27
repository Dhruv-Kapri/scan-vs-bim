# Roadmap

Target: about 8 weeks, part-time, from late October 2026 to mid-December 2026, so the results exist
before the January 2027 PhD deadlines. Each phase ends in something that runs and can be shown; the
next phase does not start until the previous one is done.

## 0. Setup (week 1)

- `uv` Python project, Open3D and IfcOpenShell installed and imported on Apple Silicon.
- Download the INESC CRAS IFC (67 MB) and one PC2Model indoor sample; load both and render them.
- **Done when:** one script loads a scan and an IFC and shows them in the same window (unaligned).

## 1. Align (weeks 1-3)

- Coarse: voxel downsample, FPFH features, RANSAC global registration (Open3D).
- Fine: point-to-plane ICP.
- The model side: sample the IFC or OBJ surfaces into a point cloud so both sides use the same tools.
- Score on PC2Model with its ground-truth transforms: rotation error, translation error, success rate,
  per category. Start with the building categories (houses, indoor), then run the rest.
- PC2Model applies random scaling to half its samples, so the baseline needs a scale estimate
  (or must report those samples separately). Decide after the first run.
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
  MapLibre map, as the rooftop project does for cities.
- **Done when:** a public GitHub Pages link.

## 5. Carbon (week 7)

The sustainability layer: what does the as-built building contain, in carbon terms?

- Quantities per element from IFC geometry (volume, area), mapped from the IFC material to a carbon
  factor (kgCO2e per unit).
- Report: embodied carbon of the elements the scan **confirms**, separately from elements that are
  missing or not visible. The carbon cost of the deviations is the difference.
- Why it matters: a scan-verified inventory of what is in an existing building is the input to
  material passports and component reuse, which design-model numbers alone can't support.
- Carbon factor source: see [data-sources.md](data-sources.md#carbon-factors). The licence decides
  whether factors can be shipped in the repo or must be downloaded by the user.
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
