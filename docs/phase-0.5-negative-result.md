# Phase 0.5: the validation gate failed (negative result)

The [roadmap](roadmap.md) fixed a gate before notebook 05 ran, allowed one week of tuning if it failed, and
said to write the result up if it still failed. It did. This page records the gate, what the tuning changed,
why the rest still fails, and what that means for later phases. Issue:
[#21](https://github.com/Dhruv-Kapri/scan-vs-bim/issues/21). Numbers come from the committed notebook outputs
at commit a523be2 (end of Phase 0.5); each is tagged with its notebook or issue. Terms are those of
[CONTEXT.md](../CONTEXT.md). *Room B* is the CRAS room the gate scores; the *held-out rooms* (room A and the
west hall, [03c](../notebooks/03c_tuning_room.ipynb)) are the two rooms #20 tuned on instead. The *own-face
patch* (#20) counts a point only if it lies over its element's own face; the *proxy* is 03c's stand-in for
the hand check on the held-out rooms (per element a truth that does not use the verdict rule); the *sliver
rule* was 03a's rule for elements with little surface in the room box, removed by #23.

## Short answer

Registration now passes (7 of 9 samples, was 4 of 9). The perturbed-model criterion and the hand check fail,
so the **overall gate fails** (05b). The pipeline is not worth formalising as it stands. Most of what is left
is not a registration problem: without oracle labels the verdict logic answers *not confirmed* for 26 of the
35 elements of the CRAS room (03a). That is why the 3 cm and 10 cm moves are missed and why most of the
hand-check draw is *not confirmed*; with oracle labels the moves are right, but the false-flag clause would
then fail (05b).

## 1. The gate, as fixed before 05 ran

Thresholds are from the roadmap and repeated in the first cells of
[05a](../notebooks/05a_registration_gate.ipynb) and [05b](../notebooks/05b_hand_check.ipynb). They are
judgement calls, not taken from a standard.

- Registration, per PC2Model sample, after ICP: rotation error ≤ 2 degrees, translation error ≤ 5 cm, scale
  error ≤ 1% on scaled samples. At least 6 of the 9 samples must succeed.
- Perturbed CRAS model: every injected change beyond tolerance gets the right verdict, and at most 10% of
  untouched elements are falsely flagged shifted or missing.
- Hand check of 20 random CRAS elements: at least 80% agree with the verdict.

Decisions recorded in those first cells before any result (all judgement calls):

- *Translation error* is the centroid error (where the estimate and the ground truth put the scan's centroid),
  not `|dt|`, which is dominated by the lever arm from the scan's origin (05a; #14 comment).
- A sample counts on the draw with the highest ICP fitness among RANSAC seeds 0 to 4, not on seed 0, because
  02 showed RANSAC is a lottery on a real room (05a). Scaled samples start from 02's RMS-radius scale
  estimate; the benchmark's scaled flag is used, which a real run would not have (05a).
- The perturbed criterion is read on the run without oracle labels (the realistic one). "Beyond tolerance" is
  03b's `expected` verdict (LOA30 on the true deviation of the wall's plane), so the two 1 cm moves are
  controls. The false-flag clause is applied per run, and counts *shifted* only: *missing* is unreachable
  because 01 recovered no scanner position in the room (1 of 21, in another room), and CONTEXT.md merges
  *missing* and *not visible* into *not confirmed* (05b). If *not confirmed* counted as *missing*, the clause
  would fail.
- The hand-check draw is `default_rng(0).choice(35, 20)` over 03a's row order, so it does not depend on the
  verdicts. The gate passes only if all three criteria pass (05b).

## 2. Result per criterion, before and after tuning

The tuning week is [#20](https://github.com/Dhruv-Kapri/scan-vs-bim/issues/20). Follow-ups were #23
(per-element patches), #25, #26, #27, #30, #31 and #32. Since the first gate run, only #20 and #23 changed
code that moves a number below; #25 re-judged two hand-check rows, and the rest are diagnoses or small fixes
with no verdict change.

| Criterion | Threshold | First gate run, after #17 and #18 (#14, #15; 05b at a18aa3b) | After #23, before #20's re-run of 05a | Now (a523be2; 05a, 03b, 05b) |
| --- | --- | --- | --- | --- |
| Registration | ≥ 6 of 9 | 4 of 9, FAIL | 4 of 9, FAIL | **7 of 9, PASS** |
| Perturbed model, changes beyond tolerance right (no labels) | all | 3 of 5, FAIL | 3 of 5, FAIL | 3 of 5, **FAIL** |
| Perturbed model, untouched flagged shifted, worst run | ≤ 10% | 1 of 34 = 2.9%, ok | 3 of 34 = 8.8%, ok | 3 of 34 = 8.8%, ok (narrowly) |
| Hand check | ≥ 80% | 15 of 20 = 75%, FAIL | 14 of 20 = 70%, FAIL | 14 of 20 = 70%, **FAIL** |
| **Overall** | all three | FAIL | FAIL | **FAIL** |

Sources: #15 and #20 comments (first run), 05b "Answer" table (the last two columns). Notes on how each number
moved:

- **Registration** moved with #20's refinement only (05a "Answer").
- **Beyond-tolerance changes** stayed 3 of 5 throughout: the three deleted elements are right, the 3 cm and 10
  cm moves read *not confirmed*, not *shifted* (05b section 5). With oracle labels all 5 are right (context
  only). Before 03b's redesign (#18) the counts were 3 of 6 changes right and 1 of 29 flagged (#15 comment).
- **False flags** rose from 2.9% to 8.8% with #23, not #20: the element patches made `Drywall:971319` and
  `Drywall:976743` shifted without labels, joining `Drywall:962532`. No perturbation adds a flag (03b
  "Answer"). With labels the worst run is now 4 of 34 = 11.8%, so the labelled run, which passed before #23,
  would fail the clause (03b, 05b section 5; context, not the criterion).
- **Hand check** history, exactly:
  - first judgement of the 20 close-ups (#15): 15 of 20 agree (75%). The draw's verdicts were 17 *not
    confirmed*, 3 OK, 0 *shifted*; the population's were 29, 5 and 1;
  - after #23 (5846d48): 14 of 20 (70%). The draw is now 16 / 4 / 0, population 26 / 6 / 3. The ceiling
    covering `...1429616` went from *not confirmed* (sliver rule) to OK on its whole patch, and the author had
    judged it *not confirmed* on a strip, so that row flipped to a disagreement;
  - after #20's own-face patch: 14 of 20, no verdict moved (05b "Answer");
  - after #25 (3ef05d3): the author re-judged rows 3 and 4 on the whole-patch close-ups, both OK. Row 3 now
    agrees, row 4 now disagrees. Still 14 of 20 = 70%, below the 16 of 20 needed.

## 3. What failed and why

### 3.1 Registration: scale estimate and centroid error (05a, 05c, 02)

Before tuning 4 of 9 succeeded. Rotation was within 2 degrees on all nine. All four scaled samples failed the
1% scale criterion: 02's RMS-radius estimate was 1.5, 3.9, 5.3 and 7.4% off (05a). 02 had already shown the
estimate's weak point: on `fur_010` it was 2.20% off, and on UVigo, whose true scale is 1, it gave 0.874
(12.62% off), because clutter and area outside the model change the RMS radius without any change of scale
(02).

The centroid criterion was the second cause. ICP ran only at the coarse voxel, 0.18 to 0.44 m (0.008 of the
model's diagonal), against a 5 cm threshold, so only 5 of 9 centroids were within 5 cm (05a).

#20 added scale-fitting ICP stages and finer rigid stages (`scan_vs_bim.register`), chosen on four usable held-out
samples in [05c](../notebooks/05c_registration_tuning.ipynb), not on the nine. On 05a: scale errors of 3.9,
1.5 and 7.4% went to 0.02, 0.01 and 0.20%, and seven of nine centroids are within 2.6 cm. Two samples still
fail (05a):

- `indoor_modelling_0` (TUBS1, scale 0.69): the estimate was 5.3% off and is 2.04% off after the scale stages;
  centroid error 19.7 cm, against a coarse voxel of 0.351 m. Residual 2.2 cm against 0.1 cm under the ground
  truth, so ICP stopped in a local minimum. The start error is beyond the 2.2 to 3.6% that 05c tested.
- `real-indoor_modelling_3` (UVigo, scale 1): centroid error 12.3 cm (voxel 0.394 m), rotation 0.23 degrees.
  The residual under the estimate (3.0 cm) is lower than under the ground truth (4.2 cm), so a finer ICP
  cannot reach it; the centroid criterion may be at its limit on cluttered real scans.

Limits that remain (05a, 05c): the margin is one sample; seed 0 alone gives 4 of 9 (2 before), so the
ICP-fitness pick still matters; and the scale stages cannot recover from a large start error. 05c's real GM
sample, 26.7% off, ended 28.1% off and no candidate passed it.

### 3.2 03a leans to *not confirmed* (#17, #18, 03a)

Without oracle labels the room's 35 elements read 6 OK, 3 shifted, 26 *not confirmed* (03a "Answer"; 5 / 1 /
29 before #23). No wall is OK without labels. Of the 26, 23 are "inconsistent offsets" and 3 "too few points",
and many are near misses of the 95% line: at 80% instead of 95% the OK count would be 14 (03a).

The causes found in #17 and 03a: walls scanned from both sides, where 40 to 50% of the points of the two
biggest walls lie one wall thickness behind the room-facing face; and clutter in front. The wall side test and
junction margin removed the back-of-wall points (44% and 40% of the band points of `Drywall:961571` and
`Drywall:973242`) and let `Drywall:973242` reach OK, but only with labels: 98% with, 79% without. The 21% gap
is clutter-class or unassigned points in front of the wall, and no label-free rule tried reached 95% without
also making a wall OK that an independent plane fit says is not clean (03a). 03a calls the gap between 79% and
98% the measured value of segmentation for a wall in this room.

### 3.3 The perturbed-model criterion and the shifted-only reading (03b, 05b)

The one wall that qualifies for the moves, `Drywall:973242`, is not OK without labels (78.6% within 15 mm), so
neither 1 cm move can stay OK. For the 3 cm and 10 cm moves one cluster holds 78.0% of its points against the
80% rule (80.5% before #23). The offsets follow the injected move to within 1 mm (+9.9, -10.0, -29.9, -99.3 mm
for +10, -10, -30, -100); the verdict does not. So the first clause fails on the logic's label-free verdict,
not on measurement.

The false-flag clause passes only because of the shifted-only reading. Per run, 3 of 34 untouched elements are
shifted (`Drywall:962532`, `971319`, `976743`), all shifted on the real model already. Read *not confirmed* as
*missing* and 198 of 238 untouched rows, pooled over the runs, would be flagged (177 are *not confirmed*, 21
shifted; 05b section 5). The clause also counts walls that are really displaced as false flags; 05b keeps the
rule as written.

The evidence is thin: the five changes beyond tolerance are two moves of one wall and three deleted elements.

### 3.4 The hand check: mostly *not confirmed* draws (05b)

The first draw had 17 *not confirmed*, 3 OK and 0 *shifted* (16 / 4 / 0 now). *Not confirmed* is also the
default verdict of the logic, so agreement mostly measures whether it is a fair description. All disagreements
go one way: 03a says *not confirmed* where the author saw an answer. Now six: OK for elements 2 and 4
(coverings), 6 and 8 (walls) and 15 (a window), *shifted* for element 5 (a double door, narrow leaf 2 and 6 cm
off the model face). Of the 4 OK verdicts all 4 were confirmed; of the 16 *not confirmed*, 10 were.

The room's only *shifted* element in the first run, `Drywall:962532`, was not drawn. Now there are three
*shifted* walls and none is drawn, so the hand check cannot say whether a *shifted* verdict is right.

## 4. Owner-decided findings from the follow-ups

Owner decision (2026-11-04, on #26, #27, #30 and #32): Phase 0.5 records the cause and a decision only; any
rule change waits for Phase 2, when the verdict logic moves into `scan_vs_bim.compare`
([#33](https://github.com/Dhruv-Kapri/scan-vs-bim/issues/33)), because #20 was the one tuning week. No verdict
changed in the work below.

**#30: label-free *shifted* on walls with little surface** ([03c](../notebooks/03c_tuning_room.ipynb), section
8b). Since #23 there is no sliver rule, so three short walls of the west hall tuning room (`Drywall:981948`,
`964467`, `963112`, 20, 10 and 8% of their surface in the room box) read *shifted* without labels (-21, +74,
+91 mm; 85, 90 and 88% of the points within 15 mm of the median), and not with labels. Cause confirmed: the
clusters (9,627, 11,633 and 17,215 points) are flat sheets of scan, 89 to 100% in the scan class unassigned,
0% clutter class, 0 to 3% inside the box, over the middle of each wall face. They are not a fold: 0 to 2% lie
within 15 mm of either face plane. With labels they read *not confirmed* only because that area is not
annotated. A coverage rule (a label-free *shifted* needs its cluster to cover at least `MIN_COVER` of the
wall's face) was tested on both held-out rooms and **rejected**: the three walls cover 0.43, 0.44 and 0.62 of
their faces and a wall the proxy calls *shifted* covers 0.56. 0.50 removes two and keeps `963112`; removing it
needs more than 0.62 and loses the proxy-shifted wall. Room A adds no evidence. **The rule is kept.** Whether
the three walls are really displaced stays open: nothing in 03c confirms or refutes it, which needs a look at
the scan.

**#32: deep coverings** (03a "Answer"; 03c). The own face of a slab or covering stays its faces across z.
`Forros 1` (`...1537527`, a 0.5 m deep dropped ceiling band) loses 53,708 of its 161,318 counted points as
past the edge of those faces, and its share within 15 mm rises from 59% to 88.6%: still *not confirmed*. It is
the only slab or covering deeper than 15 cm in room B and the two held-out rooms (the next is a stair landing
at 0.246 m in none of them), so a rule for deep side faces could only be tuned on room B, which #20 forbids.
At most about 1.3% of the dropped points lie within 15 mm, so the band would not be confirmed either way.
**The rule is kept.**

**#27: `Drywall:9713` and `Drywall:9790` are not folds** (03a, section 4). Nearest-face offsets of +62.9 mm
and +48.6 mm (+64.5 and +49.3 without labels) are the true sizes. With labels the points that decided their
own side read +126 and +151 mm (p50), which looked like a fold. But floor and ceiling points run up to the
scanned plane (none west of x = 1.201 m; 3,514 floor and 6,226 ceiling points where a wall body 162 mm away
would stand for `Drywall:9713`, 1,348 and 3,247 for `Drywall:9790`), and the door leaves (35 mm) sit inside
the 100 mm west of the plane. The +126 and +151 mm points come from the free-space side test reading clutter
in front plus unscanned space behind as "seen from behind". That alone makes `Drywall:9790` *not confirmed*
without labels: 75.0% of its points near the median, 87.7% when those points are measured against the east
face (a diagnostic, not a rule). **Decision: no partition rule.** Fix the side test in Phase 2 (#33): a point
may take the side away from the room only if the scan shows the neighbouring space there, tested on the
held-out rooms. Measured on these two walls only; their thickness and west face are not confirmed, and the
flaw applies to any wall whose other side is unscanned (03a).

**#26: the floor ramp** ([03d](../notebooks/03d_floor_ramp.ipynb)). The floor slab is *not confirmed* (84.3%
of 2,826,028 points within 15 mm with labels; 99.2% inside room B, 80.5% outside; 03a). Over 282 cells of 1 m
the floor and ceiling ramp together: floor gradient (+1.21, -0.82) mm/m, ceiling (+1.15, -1.28) mm/m, room
height (-0.06 [-0.83, +0.77], -0.46 [-0.75, -0.20]) mm/m. So the ramp is **mostly a tilt of about 0.1 degrees
shared by floor and ceiling**, which cannot be told from a frame tilt or a building out of level; the
remainder is in y. A floor-only slope is **not supported building-wide**, and the x result depends on which
ceiling sheets enter the cells (with the 23 west sheets, 10 to 13 cm below their room's covering, given to the
2.80 m level instead, room height gx is -1.49 [-3.16, +0.20]; 03d); it is **indicated in x in two rooms**
(-1.40 and -1.51 mm/m, 46 and 33 cells), not established. Setup drift is **not supported**: floor and ceiling
residuals are uncorrelated (r = +0.10 [-0.08, +0.34]). The slab verdict is unchanged in 0.5.

## 5. What it motivates

- **Scale-aware or learned registration** (roadmap, Later). A scale estimate from the registration itself
  fixed three of four scaled gate samples, but it starts from a coverage-sensitive estimate, so a scan that
  covers more than the model (05c's real GM, 26.7% off; TUBS1, 5.3%) still fails, and the RANSAC step stays a
  lottery (UVigo: 2 of 5 seeds at the chosen voxel size, 02). Scale-invariant features, or a learned global
  step, would attack that directly. The scale problem comes from PC2Model's scaling; a real scan in metres has
  scale 1.
- **Scanner positions or normals for walls scanned from both sides** (#17). Without them the side test has to
  infer the side from free space, which is what failed in #27. Scanner positions would also make *missing* and
  *not visible* separable; today both are *not confirmed*.
- **Segmentation** (roadmap, Later). With labels, 5 of 5 changes are right and 8 elements are OK; without, 3
  of 5 and 6 (03a, 05b).
- **Phase 2 inherits** (#33): moving the verdict logic into `compare`; the side-test fix (#27); a level and
  tilt step or a local plane for large horizontal elements (#26); adopting or deleting the rejected
  `face_coverage` (#30); whether to count a displaced wall as a false flag (05b).

## 6. Limits of this result

- The thresholds are judgement calls. The hand-check line needs 16 of 20; the result is 14.
- One room, and moves on one wall (03b). The hand check is by the author, who also wrote the logic, on 20 of
  the room's 35 elements (57%), 16 of them *not confirmed*.
- Only #20's registration refinement and own-face patch were tuned on held-out data. The wall side test,
  junction margin and element patches (#17, #23) were developed on room B, which the gate also scores. The
  own-face patch moved no verdict there, so it shows no harm, not benefit.
- The 18 hand-check judgements kept after #23 were made on close-ups cut to the room box; rows 3 and 4 were
  re-judged after the gate was known to fail (05b).
- Registration: nine samples, one run each, the scale flag taken from the benchmark, refinement chosen on four
  usable held-out samples (05a, 05c).
