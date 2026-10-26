# Scan vs BIM

*Does the building match its model? Align a laser scan to its BIM model, flag every element that moved,
went missing or was never built, and put a carbon number on the difference.*

> **Status: planning.** No code yet. This repo holds the plan, the data survey and the research outline;
> the [roadmap](docs/roadmap.md) says what gets built and in what order.

## The problem

A BIM model says what a building *should* be. A laser scan says what it *is*. Checking one against the
other (has the wall been built 4 cm off its grid line, was a slab left out, does the as-built model
still describe the building) is still largely manual work in commercial tools. Two research problems sit
underneath it:

1. **Scan-to-model registration.** Before anything can be compared, the scan has to be placed in the
   model's coordinate system. This is less studied than scan-to-scan registration, which is why ISPRS
   published the [PC2Model benchmark](https://arxiv.org/abs/2604.19596) in 2026.
2. **Per-element deviation.** Once aligned, each BIM element (wall, slab, column, door) needs a verdict:
   built as designed, shifted, or missing, with a measured distance and a confidence.

## What this project builds

```
scan (.e57 / .las)  ─┐
                     ├─► 1. align ──► 2. compare per element ──► 3. report ──► 4. show
BIM model (.ifc)    ─┘     FPFH+RANSAC    distance scan→element      BCF issues     web viewer
                           then ICP       OK / shifted / missing     heatmap        + map
                                                    │
                                                    └──► 5. carbon: embodied carbon of what was
                                                         actually built vs what was designed
```

- **Align:** a classical, reproducible baseline (coarse feature matching, then ICP), scored against the
  ground truth in PC2Model.
- **Compare:** every IFC element is turned into geometry and checked against the scan points near it.
- **Report:** deviations as a colour-coded model and as BCF issues that any BIM tool can open.
- **Show:** a browser viewer, with the building also placed on a map in real-world coordinates (the
  link to city-scale GIS and to the [rooftop solar project](https://github.com/Dhruv-Kapri/Rooftop-Solar-Potential)).
- **Carbon:** quantities of the elements the scan confirms, multiplied by material carbon factors.
  This gives a scan-verified embodied-carbon estimate and the carbon cost of what deviated: the first step
  towards a material passport for reuse. See [the roadmap](docs/roadmap.md#5-carbon).

## Data

All of it public, chosen so the whole pipeline runs on a laptop. Details in
[docs/data-sources.md](docs/data-sources.md).

| Dataset | Use | Licence |
| --- | --- | --- |
| [PC2Model](https://zenodo.org/records/17581812) (ISPRS 2026) | registration accuracy, with ground-truth transforms | CC BY 4.0 |
| [INESC TEC CRAS lab](https://zenodo.org/records/7948116) | real laser scan + its as-built IFC: the end-to-end case study | CC BY 4.0 |

## Stack

Python, [Open3D](https://www.open3d.org/) (point clouds, registration),
[IfcOpenShell](https://ifcopenshell.org/) (IFC read and write, BCF),
[That Open Engine](https://thatopen.com/) (browser IFC viewer), [MapLibre](https://maplibre.org/) (map).
Everything runs on Apple Silicon without a GPU.

## Docs

- [Roadmap](docs/roadmap.md): the phases, what "done" means for each, and the order.
- [Data sources](docs/data-sources.md): datasets, licences, sizes and what is still unverified.
- [Research outline](docs/research-outline.md): the one-page research framing behind the project.

## Licence

Code: MIT. Datasets keep their own licences and are never committed to this repo.
