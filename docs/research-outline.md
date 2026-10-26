# Research outline: scan-verified building models

*One page. Updated as results come in; numbers appear here only once measured.*

## Question

How reliably can a laser scan of an existing building be aligned to its BIM model and turned into a
per-element verdict (built as designed, shifted, missing, not observed), and what does that verdict
change about what we know of the building's embodied carbon?

## Why it matters

- BIM models drift from what is built. Facility management, renovation, and reuse of building
  components all need a model that matches the building, with evidence for each element.
- Registration of a scan to a *model* is less studied than registration of scan to scan. The
  ISPRS PC2Model benchmark (Maboudi et al., 2026) was published to close that gap; open, reproducible
  baselines on it are still scarce.
- Embodied-carbon estimates and material passports are usually computed from design models. A
  scan-verified inventory says which of those quantities are confirmed by observation.

## Approach

1. **Registration baseline.** Classical global registration (FPFH + RANSAC) refined by ICP, with
   explicit handling of PC2Model's scale changes. Reported per category against ground truth.
2. **Element-level comparison.** IFC element geometry against nearby scan points, with tolerances
   taken from a published accuracy specification (USIBD LOA), and occlusion kept separate from absence.
3. **Outputs that tools can use.** Verdicts written into the IFC and exported as BCF issues.
4. **Carbon.** Element quantities times cited carbon factors, split into confirmed and unconfirmed.

## Evaluation

- Registration: rotation and translation error, and success rate, per PC2Model category.
- Comparison: verdicts checked by hand on a sample of elements in the INESC TEC CRAS lab scan.
- Carbon: an estimate with stated scope (A1-A3) and sources, not a validated LCA.

## Where it could go next

- Learned registration and segmentation (separating clutter from structure).
- Generating the model from the scan (scan-to-BIM), then automated rule checking of the result.
- Repeated scans over time: construction progress and change detection.

## Results

None yet.
