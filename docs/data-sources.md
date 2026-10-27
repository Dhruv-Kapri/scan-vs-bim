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

## Carbon factors

Undecided. The licence matters because this repo is public.

| Source | Licence (from search, unverified) | Note |
| --- | --- | --- |
| ICE database (Circular Ecology) | Free educational version; use in software or tools needs a paid licence | Probably not usable in a public tool |
| [EPiC](https://msd.unimelb.edu.au/research/projects/current/environmental-performance-in-construction/epic-database/usage-and-licence-information) (University of Melbourne) | CC BY-NC-ND | Usable non-commercially; don't ship a modified copy |
| ICM database (UNSW) | Listed as open on Research Data Australia | Check the actual licence |
| ÖKOBAUDAT (German federal) | Not checked | Free, with an API, per general knowledge |

Next step: read each licence page and pick one before phase 5.

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
