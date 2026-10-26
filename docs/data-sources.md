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

### INESC TEC CRAS lab: indoor scan with as-built IFC

- Record: <https://zenodo.org/records/7948116>. Paper: <https://www.mdpi.com/2306-5729/8/6/101>.
- **Verified:** CC BY 4.0. 21 terrestrial laser scans, 585M points, 33 labelled classes, in a 4.3 GB
  ASCII file; IFC model, 67 MB.
- The only open real scan + IFC pair found in the survey. Subsample before use.

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
