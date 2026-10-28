# Data sources

Surveyed 2026-10-25. "Verified" means read on the dataset's own record page; everything else is
marked unverified and must be checked before use.

## Used

### PC2Model: ISPRS benchmark on point cloud to model registration

- Record: <https://zenodo.org/records/17581812> (DOI 10.5281/zenodo.17581812, v1, 2025-11-11).
  Paper: Maboudi et al., ISPRS Archives XLIX-B2-2026, <https://arxiv.org/abs/2604.19596>.
- **Verified:** CC BY 4.0. One file, `PC2Model_v1.4.zip`, 10.2 GB. 137 samples, each a model (`.obj`),
  a transformed point cloud (`.e57`) and the ground-truth transform (`.txt`).
- Contents: 125 simulated samples (25 each of mechanical objects, furniture, home décor, houses,
  vehicles), 6 simulated indoor spaces, 6 real indoor spaces. Simulated scans come from Helios++
  configured as a Leica P40, with noise, mixed pixels, occlusion and density changes.
- Transforms: any rotation, translation up to 5x the cloud extent, and on half the samples a scale of
  0.5 to 1.5.
- Not a building dataset overall: 31 of 137 samples are houses or indoor spaces. Report those
  categories separately.
- Unverified: the metrics the authors use, and whether an evaluation server will open.
- **Verified 2026-10-27 (access):** Zenodo serves HTTP range requests (206) on the zip, so single
  samples can be pulled without the 10.2 GB download, e.g. with `remotezip`. Each sample is a folder
  of model `.obj`, scan `.e57` and transform `.txt`, 115 MB to 1.6 GB (`house_19` is the largest). Layout:
  `PC2Model_v1.4/house/house_N-sketchfab/` (25), `indoor_modelling/indoor_modelling_N-ISPRS_indoor_modelling-<site>/`
  (6) and `ISPRS_indoor_modeling_benchmark/real-indoor_modelling_N-.../` (6). Probably simulated and real
  respectively, going by the folder names; unverified.
- Open3D 0.20 cannot read `.e57`; a separate reader is needed. **Verified 2026-10-27:** `pye57` 0.4.19
  installs from a wheel on Apple Silicon (Python 3.12) and reads
  `real-indoor_modelling_3-ISPRS_indoor_modelling-UVigo` (1 scan with pose, 9.5M points, XYZ only: no
  colour or intensity).
- **Verified 2026-10-27 (download):** Zenodo throughput varied from 0.15 to 1 MB/s, with occasional HTTP
  504s, and one long streamed `remotezip` read died after 267 KB. `scripts/fetch_data.py` therefore uses
  chunked, retried, resumable range requests (`remotezip` only reads the central directory).

### INESC TEC CRAS lab: indoor scan with as-built IFC

- Record: <https://zenodo.org/records/7948116>. Paper: <https://www.mdpi.com/2306-5729/8/6/101>.
- **Verified:** CC BY 4.0. 21 terrestrial laser scans, 585M points, 33 labelled classes, in a 4.3 GB
  ASCII file; IFC model, 67 MB.
- The only open real scan + IFC pair found in the survey. Subsample before use.
- Files: `craslabannotated.zip` (4.27 GB) and `craslabbim.ifc` (67.6 MB); no photos (verified via the
  Zenodo API). Unzipped, 585M ASCII points are likely 25-30 GB (estimate), more than the dev laptop can
  hold in memory (8 GB RAM, about 68 GB free disk on 2026-10-27). Stream the zip member and subsample
  on the fly; don't extract it.
- **Verified 2026-10-27 (zip, via range reads):** one member, `CRASLAB_annotated.asc`, deflate, zip64,
  26,752,658,348 bytes uncompressed (4,267,281,165 compressed); it can be streamed sequentially (the
  local header has 0xFFFFFFFF sizes, so the central directory gives the real ones). Line 1 is the header
  `//X Y Z R G B Intensity Classification` (tab-separated), line 2 the point count `584701977`, then rows
  such as `6.5185 15.7385 1.5075 164 174 193 0.201 0.000`. XYZ in metres, RGB 0-255, class as a float.
  No scan-id column.
- **Verified (Zenodo description):** the 21 scans were registered in Leica Cyclone Register 360 (3 mm
  mean error) and delivered as one merged cloud. No scanner positions in the zip or the record. 33 scan
  classes: 0 unassigned, 1 ceiling, 2 floor, 3 wall, 4 door, 5 window, 6 desk, 7 chair, 8 cabinet,
  9 mobile cabinet, 10 shelf, 11 vents, 12 water tank, 13 bin, 14 box, 15 board, 16 computer, 17 screen,
  18 printer, 19 vest, 20 switch, 21 paper dispenser, 22 alcohol dispenser, 23 cable, 24 phone, 25 robot,
  26 water kettle, 27 stairs, 28 ladder, 29 oil heater, 30 divider, 31 hanger, 32 fan, 33 water dispenser.
- **Verified 2026-10-27 (IFC, read with IfcOpenShell):**
  - IFC2X3, metres. Counts: 61 IfcWallStandardCase, 44 IfcWindow, 10 IfcColumn, 7 IfcCovering,
    6 IfcDoor, 5 IfcSlab, 1 IfcStair (2 flights), 1 proxy, 66 IfcFurnishingElement, 54 openings.
  - No IfcSpace, so no rooms in the model.
  - IfcSite "Default" with Revit's default latitude/longitude (near Brasília), so there is no real
    georeference ([#2](https://github.com/Dhruv-Kapri/scan-vs-bim/issues/2)).
  - Element bounding box about x -9.9..8.3, y -4.5..20.0, z -1.2..3.0 m.
- Unverified: whether the scan is in the IFC's coordinate frame (the scan coordinates fall inside the
  IFC's bounding box, which suggests it is), and whether the IFC was modelled from this scan. The MDPI
  paper returned 403 to automated reads; read it in a browser. Notebook 01 checks the frame.

## Standards

### USIBD Level of Accuracy (LOA) Specification

- **Verified 2026-10-28 (spec PDF, downloaded by hand from the USIBD store at $0.00; the site returns
  403 to automated reads):** v3.1, Guide C120 "USIBD_LOA3.1_SpecGuide-2025.pdf", plus the Framework
  template C220 (`.xlsm`). Kept locally in gitignored `data/reference/`, not committed.
- **Verified 2026-10-28 (Guide C120, LOA table and the paragraph after it):** bands as upper/lower
  range, "*Specified at the 95% Confidence level": LOA10 15 cm-5 cm, LOA20 5 cm-15 mm, LOA30 15 mm-5 mm,
  LOA40 5 mm-1 mm, LOA50 1 mm-0. "The numbers represented in the LOA ranges relate to standard deviation
  of 2 Sigma." LOA10's 15 cm upper range dates from v3.0 (corrects the earlier "> 5 cm" from secondary
  sources). A result better than the specified band "is presumed also to be acceptable". Bands apply to
  both Measured Accuracy (the measurements) and Represented Accuracy (data "processed into some other
  form such as line work or a model").
- Reading of the bands (2026-10-28): LOA30 as a pass/fail tolerance is ≤ 15 mm at 2σ, and a
  scan-vs-model deviation is checked against Represented Accuracy. The project uses LOA30 as its
  tolerance.
- **Verified 2026-10-28 (licence, Guide C120 and v3.1 release notes):** © 2025 USIBD, under Creative
  Commons Attribution-NonCommercial-NoDerivatives 4.0 International. "Modifications to the LOA
  Framework may be made ... if they are licensed to do so by the USIBD"; only LOA10-LOA50 may be called
  USIBD LOAs. Licensing questions: communications@usibd.org.
- Reading of the licence (2026-10-28), not confirmed with USIBD: quoting the band values with
  attribution (USIBD LOA Specification v3.1, Guide C120) is fine; don't commit the PDF or a modified
  copy. NonCommercial binds copies of the document, so a commercial use of this project would need the
  values cited, not the PDF shipped; ask USIBD if that ever matters.
- PC2Model's "LOA" is a different thing: `LOA_mean`/`LOA_median` are registration residuals
  (point-to-model distances; the paper cites Ersöz and Bosché 2026), not USIBD bands. Read from the
  arXiv PDF; see [CONTEXT.md](../CONTEXT.md).

## Carbon factors

**Chosen (2026-10-27): ÖKOBAUDAT, downloaded at runtime.** The repo commits only its own mapping
(IFC material → ÖKOBAUDAT dataset UUID), never the factors or a filtered copy. Licences checked
2026-10-27:

| Source | Licence | Verdict |
| --- | --- | --- |
| [ÖKOBAUDAT](https://www.oekobaudat.de/en/guidance/data-users.html) (German federal) | **Verified:** use is "free of charge and without any restrictions"; unmodified copies may be redistributed if the source is named. No named open licence | Chosen. Download at runtime: a subset or modified copy is not clearly allowed. CSV and ILCD/EPD XML downloads plus a soda4LCA API (**verified**); size and coverage unverified |
| [ICE](https://circularecology.com/embodied-carbon-footprint-database.html) (Circular Ecology) | **Verified:** proprietary; the free Educational V5.0 (June 2026) excludes use in tools or software | Not usable |
| ICM database (UNSW) | CC BY 4.0, unverified (search snippet; the record page blocked automated reads) | Fallback if committable values are ever needed; Australian, 2014-15 data |
| [EPiC](https://msd.unimelb.edu.au/research/projects/current/environmental-performance-in-construction/epic-database/usage-and-licence-information) (University of Melbourne) | CC BY-NC-ND, unverified (page blocked) | No modified copies; Australian |
| EC3 (Building Transparency) | API terms of service, unverified | No caching or redistribution on the free tier |

- **Verified 2026-10-28 (ÖKOBAUDAT terms, read from the
  [data-users page](https://www.oekobaudat.de/en/guidance/data-users.html) and the
  [manual](https://www.oekobaudat.de/fileadmin/downloads/2021-06-28_OEBD-Manual.pdf) §3.4.2, same
  wording):** "The BMWSB provides the ÖKOBAUDAT data free of charge and without any restrictions. They
  are primarily intended for performing life cycle assessment of buildings." and "The free distribution
  of unmodified data is permitted, provided that the source is named." Data owners stay responsible
  for values; BMWSB/BBSR take no liability. "ÖKOBAUDAT is not designed for performing life cycle
  assessment of building products." The page gives a service-interface base URL for software tools,
  `https://www.oekobaudat.de/OEKOBAU.DAT/resource`.
- Reading of those terms (2026-10-28): runtime download into gitignored `data/` is use, which is
  unrestricted, and redistributes nothing. The committed IFC-material → dataset-UUID mapping holds
  identifiers, not data values. Both appear allowed; not confirmed with BBSR. Name ÖKOBAUDAT as the
  source wherever factors are shown.
  Committing factor values or a filtered/modified copy stays out, since only unmodified data may be
  passed on.

## Considered, not used now

| Dataset | Why not now |
| --- | --- |
| [Building3D](https://building3d.ucalgary.ca/) (Tallinn roofs) | Roof reconstruction, a different project; CC BY-NC-SA |
| [3DBAG](https://3dbag.nl/en/download) + AHN lidar | Roof reconstruction (same); open |
| Nothing Stands Still | Multi-epoch construction scans; licence unverified (a mirror says CC BY-NC-SA) |
| Cloud2BIM ([paper](https://arxiv.org/abs/2503.11498), [code](https://github.com/VaclavNezerka/Cloud2BIM/releases/tag/v1.02)) | A scan-to-IFC pipeline, not data; relevant to the later scan-to-IFC scope |
| ScanNet++, Matterport3D, Structured3D, ARKitScenes | Access forms and non-commercial terms; no BIM pairing |
| S3DIS | Segmentation benchmark, no BIM pairing |
| India | No open building-scale lidar or CityGML found |
