# Image capture instead of a laser scan: evaluation

Surveyed 2026-10-27. Question: could photos or video replace the laser scan in this project, and if so
where does it belong in the [roadmap](roadmap.md)? "Verified" means read on the primary source (record
page, repo README, paper abstract). Everything else is marked unverified. Several pages I could not read
in full; those gaps are listed at the end.

## Short answer

Feasible as a research extension, not as an in-scope phase. The compare step is unchanged if images are
first turned into a point cloud (architecture A). The hard parts are metric scale, textureless walls and
glass, and the fact that I found no open dataset that pairs images, a laser-scan ground truth *and* an
IFC for the same interior. See the [Recommendation](#recommendation).

## 1. Data

| Dataset | Images | Laser/TLS truth | BIM / IFC | Licence and access | Status |
| --- | --- | --- | --- | --- | --- |
| INESC TEC CRAS lab ([Zenodo 7948116](https://zenodo.org/records/7948116)) | **No.** Files are `craslabannotated.zip` (4.3 GB ASCII point cloud with RGB, 21 scans, 585M points) and `craslabbim.ifc` (67.6 MB). Colour is per point, no photo or panorama files listed | Yes (the point cloud itself) | Yes, as-built IFC | CC BY 4.0 | Verified |
| ScanNet++ ([site](https://scannetpp.mlsg.cit.tum.de/scannetpp/), [paper](https://arxiv.org/abs/2308.11417)) | 33 MP DSLR, iPhone RGB-D; 360 degree panoramas added for 956 scenes in Oct 2025 | Yes, laser scan "at sub-millimeter resolution" | None mentioned | "ScanNet++ Terms of Use", application plus personal download token; terms text not read. DUSt3R's README lists ScanNet++ among datasets with non-commercial terms ([naver/dust3r](https://github.com/naver/dust3r)) | Verified except the terms text |
| ETH3D ([datasets](https://www.eth3d.net/datasets)) | High-res multi-view images; indoor-ish scenes such as office, kicker, delivery_area, pipes, relief | Yes, `scan_raw` and `scan_clean` for the training scenes | No | CC BY-NC-SA 4.0 (stated on the [ETH3D home page](https://www.eth3d.net/)) | Verified |
| Tanks and Temples ([download](https://www.tanksandtemples.org/download/)) | Video-derived images | Laser scans for training scenes (Barn, Caterpillar, Church, Courthouse, Ignatius, Meeting room, Truck) | No | Non-commercial research and teaching only, must accept licence page | Verified. Mostly outdoor; Meeting room is the only obvious interior |
| ConSLAM ([repo](https://github.com/mac137/ConSLAM), papers on [Cambridge repository](https://www.repository.cam.ac.uk/handle/1810/340521)) | Yes: synchronised camera images, lidar and IMU from a handheld scanner, five monthly sequences of one construction-site floor (per the paper records) | Yes: TLS ground-truth scans | Separate "ConSLAM BIM and GT Poses" release (IFC and Revit, built from the sequence-2 TLS scan) on TUM mediaTUM | Repo: copyright University of Cambridge, "academic use only" software text, no separate data licence found. Papers: All Rights Reserved. BIM release licence CC BY-NC per a paperswithcode listing only | Dataset contents verified from paper records; BIM release and its licence unverified (mediaTUM page blocked my fetch) |
| Hilti SLAM Challenge 2023 ([page](https://hilti-challenge.com/dataset-2023.html)) | Alphasense cameras (handheld), OAK-D (robot) in rosbags | TLS-derived ground truth map (Trimble X7 per the [2023 paper](https://arxiv.org/html/2404.09765v2) snippet); the dataset page lists 3DoF trajectory files | **No BIM mentioned** | CC BY-NC-SA 3.0 | Verified (page); TLS detail from search snippet |
| SLABIM ([HF](https://huggingface.co/datasets/BobH62/SLABIM), [paper](https://arxiv.org/abs/2502.16856), ICRA 2025, HKUST) | PNG camera frames plus lidar, ROS bags, calibration, ground-truth poses; 232 GB, 12 sessions over four storeys | Not a TLS truth: poses registered to the BIM | **Yes, but as CAD (`.dxf`) and meshes (`.ply`), not IFC** | HF page states no licence; arXiv page links only the paper's licence | Contents verified, licence unverified. The closest image + BIM pairing I found |
| BIMNet ([page](https://thucbims.github.io/bimnet)) | Not stated; built on Matterport3D scans, which need a signed Terms of Use agreement | Point clouds (25 scans, 116.5M points) | Yes, IFC per scan | Own part MIT; access needs a Matterport3D agreement then an email to the authors | Verified from the page. Whether Matterport3D panoramas can be paired with its IFCs is unverified |

Findings:

- **No open dataset found with images, a TLS ground truth and an IFC for the same interior.** The pairs
  that exist are partial: SLABIM (images + BIM as DXF/PLY, no TLS), ConSLAM (images + TLS + a BIM built
  from the TLS, licence unclear), CRAS (TLS + IFC, no images). This is a search result, not proof of
  absence.
- Every image-plus-laser set (ScanNet++, ETH3D, Tanks and Temples) has no BIM, so a per-element verdict
  can only be tested on those with synthetic perturbation, or by fitting planes to the laser scan as
  stand-in "elements".
- The only tidy licence for redistribution-style use is CRAS (CC BY 4.0), and it has no images. The rest
  are non-commercial or gated. The project's rule is "public data with clear licences", so ScanNet++,
  Tanks and Temples, Hilti and ConSLAM would need an explicit exception for research use.

## 2. Two architectures

### A. Images to a point cloud, then the existing pipeline

```
photos / video ─► SfM+MVS or feed-forward model ─► point cloud (arbitrary or metric scale)
                                                          │
                                    existing phases 1-3:  align (FPFH+RANSAC+ICP) → compare → BCF
```

New code: a thin wrapper per reconstruction tool that writes a `.ply`, a scale step (section 3), and a
confidence/density mask so that "thin image coverage" is not read as "missing". Roughly one wrapper, one
scale function, one extra column in the verdict table. The compare code does not change. This is the
cheap option.

Tool options:

| Tool | Type | Code licence | Weights licence | Scale | Apple Silicon |
| --- | --- | --- | --- | --- | --- |
| COLMAP | SfM+MVS | New BSD ([repo](https://github.com/colmap/colmap)) | none | arbitrary | `brew install colmap` is documented ([install](https://colmap.github.io/install.html)). Sparse SfM runs on CPU; **dense reconstruction needs CUDA** ("all COLMAP functionality except the dense reconstruction part" without it, [FAQ](https://colmap.github.io/faq.html)). On a Mac, dense needs external software (e.g. OpenMVS; its CPU support unverified) |
| GLOMAP | global SfM | Not read | none | arbitrary | Unverified. COLMAP README only asks users to cite it |
| DUSt3R | feed-forward pairwise + global alignment | CC BY-NC-SA 4.0 | CC BY-NC-SA 4.0 plus the licences of all training datasets, several non-commercial ([README](https://github.com/naver/dust3r)) | not documented in README | CPU via Docker documented; `--device` selectable; MPS not mentioned. Unverified |
| MASt3R | same family, with matching | CC BY-NC-SA 4.0 | CC BY-NC-SA 4.0 plus training-dataset licences; MapFree called "very restrictive" ([README](https://github.com/naver/mast3r)) | checkpoint name says "metric"; accuracy not reported on the page | MPS not mentioned. Unverified |
| VGGT | feed-forward | Licence text read: no clause on commercial use, but an acceptable-use policy and a Meta research-licence structure ([LICENSE.txt](https://raw.githubusercontent.com/facebookresearch/vggt/main/LICENSE.txt)). README (updated 2025-07-29): code allows commercial use excluding military | Original `VGGT-1B` non-commercial; `VGGT-1B-Commercial` needs an application form ([README](https://github.com/facebookresearch/vggt)) | README makes no metric claim | Official README: CUDA or CPU only. A community MPS port exists (jmanhype/vggt-mps, ~2 stars, README claims only). Unverified |
| MapAnything | feed-forward, optional intrinsics/poses/depth inputs | Apache 2.0 ([README](https://github.com/facebookresearch/map-anything)) | `map-anything` CC BY-NC 4.0; `map-anything-apache` Apache 2.0 | Outputs metric scaling factor; "universal feed-forward metric 3D reconstruction"; accuracy numbers not read | README selects CUDA else CPU; MPS not mentioned. Up to 2000 views "on 140 GB" memory. Unverified on Mac |
| Depth Anything 3 | feed-forward depth + pose | Apache 2.0 ([README](https://github.com/ByteDance-Seed/Depth-Anything-3)) | Mixed: BASE, SMALL, METRIC-LARGE, MONO-LARGE Apache 2.0; NESTED-GIANT-LARGE, GIANT, LARGE CC BY-NC 4.0 | NESTED-GIANT-LARGE outputs metres; METRIC-LARGE needs `focal * net_output / 300` | Examples use CUDA and xformers; MPS not mentioned. Unverified |
| 3D Gaussian splatting (Inria) | optimisation | Licence file not read | n/a | from SfM poses (arbitrary) | Optimiser needs a CUDA GPU, 24 GB VRAM for paper quality ([README](https://github.com/graphdeco-inria/gaussian-splatting)). **Not laptop-feasible** and gives a radiance field, not a clean surface |

Not found for any of these: a timing for 100 to 500 images on an Apple Silicon laptop. VGGT's README says
"under one second" per scene and a May 2026 update says a memory fix allows 2 to 3 times more frames on
the same GPU, both on CUDA hardware. Expect CPU/MPS runs of hundreds of images to be slow or memory
bound; this is unverified and is the first thing the experiment should measure.

### B. Direct image-to-BIM (camera localisation, render-and-compare, per-element visibility)

```
photo ─► camera pose in BIM frame ─► render BIM from that pose ─► compare with photo
                                      (depth / element-ID image)   (edges, segmentation, depth from a model)
```

What it needs: a camera pose against the IFC (manual, from markers, or learned relocalisation), a
renderer for IFC meshes with element IDs, and a per-pixel judgement (segmentation or depth). It replaces
the Align phase with a different problem, and replaces the point-distance Compare with a different one.
That is two new modules and a different evaluation, with essentially no shared code with phases 1 and 2
except the IFC reader. It is a larger and riskier addition.

Evidence it is a live research area, all from search results, none read in full:

- A 2025 arXiv paper aligns SLAM planes to BIM planes to cut AR drift: 52% lower angular error and 60.8%
  lower wall-distance error than manual initial alignment ([arXiv 2504.17693](https://arxiv.org/abs/2504.17693),
  Bikandi-Noya, Shaheer, Bavle, Jevanesan, Voos, Sanchez-Lopez). Verified from the abstract page.
- NeRF with BIM-guided segmentation for progress evaluation, 1% to 2.2% measurement error on concrete
  pouring scenes ([ScienceDirect, Automation in Construction](https://www.sciencedirect.com/science/article/abs/pii/S0926580525000536)).
  Abstract-level, via search snippet.
- A 2026 4D-BIM framework from single site photos using generative reconstruction and scale calibration,
  validated on a masonry mock-up with miniature bricks ([ACM](https://dl.acm.org/doi/10.1145/3795496.3795715)).
  Snippet only.

## 3. Accuracy

What I could verify is thin. I did **not** find a source that evaluates a feed-forward model (VGGT,
MASt3R, MapAnything, DA3) on an interior against TLS at millimetre level.

- Smartphone photogrammetry in four rooms: control-point RMSE about 1.5 cm, versus 15 to 20 cm for
  smartphone LiDAR and 2 mm for the total station (an Iranian study found via search; not read in full,
  unverified). An iPhone LiDAR vs Leica BLK360 study reports paired dimension RMSE 0.182 m
  ([Geodesy and Cartography](https://journals.vilniustech.lt/index.php/GAC/article/view/25678), snippet).
- A 2025 evaluation of DUSt3R/MASt3R/VGGT on aerial photogrammetric blocks says reconstruction works from
  fewer than ten images at up to 518 px, but camera-pose reliability "significantly" declines as image
  count and scene complexity grow ([arXiv 2507.14798](https://arxiv.org/abs/2507.14798); abstract-level
  via snippet, I could not read the PDF text). That matters: a full interior is hundreds of images.
- VGGT's own ETH3D comparison (accuracy, completeness, Chamfer after Umeyama alignment) is reported in the
  VGGT paper ([arXiv 2503.11651](https://arxiv.org/abs/2503.11651)); I did not extract the numbers. Note
  that Umeyama alignment fits scale to the ground truth, so it does not show metric accuracy.
- Photogrammetric clouds against 4D BIM planes: 3 to 5 cm plane deviations, hand-held camera and UAV, 2016
  ([PFG paper](https://lirias.kuleuven.be/3749992) region; snippet, unverified).

**Scale.** A single moving camera gives geometry up to an unknown scale. Ways to fix it:

1. A known dimension or control points in the scene (a scale bar, a measured door width), or by fitting
   to the BIM itself: the project already needs scale estimation for PC2Model, where half the samples are
   rescaled 0.5 to 1.5 ([data-sources.md](data-sources.md), verified there). A global registration that
   solves for similarity (scale, rotation, translation) would serve both. The catch for scan-vs-BIM:
   fitting scale to the BIM bakes the model's errors into the measurement, so a wall built 4 cm off is
   partly absorbed. A scale from an independent measurement (scale bar, known device baseline, depth
   sensor) is cleaner.
2. Metric feed-forward models: MapAnything states metric output and accepts known intrinsics, poses and
   depth; DA3 offers metric variants (README). Their metric accuracy at room scale is **not** established
   by anything I read. Treat as unverified.
3. iPhone depth (ScanNet++ has RGB-D streams), but the supplement describes it as noisy and low
   resolution (search snippet, qualitative).

**Textureless walls and glass.** Textureless white walls are a known weakness of feature-based SfM and
MVS (general knowledge, and the Ljubljana and Iranian studies above did not isolate it). I found no
quantified number. Glass and mirrors break the multi-view consistency assumption in all of the tools
above. For this project the consequence is the same as occlusion: those elements would have to be
labelled "not visible" or "low confidence", never "missing". Feed-forward models tend to hallucinate
smooth planes on blank walls, which is worse for a check that wants to detect absence; unverified, and
testable (section Recommendation).

**Is it good enough for LOA?** The LOA ranges I could find are in a secondary source only (a 2021 Italian
blog quoting USIBD LOA v3.0, 2019; I could not open the spec itself, and v3.1 was released in January
2025):

| LOA | Range (mm) | Source |
| --- | --- | --- |
| LOA10 | 50 to 150 | [shelidon.it](https://www.shelidon.it/bimpill-livello-di-accuratezza-di-un-rilievo/2), unverified against spec |
| LOA20 | 15 to 50 | same |
| LOA30 | 5 to 15 | same |
| LOA40 | 1 to 5 | same |
| LOA50 | 0 to 1 | same |

Against these, centimetre-level image results (about 1.5 cm in the best case I found, 3 to 5 cm for older
drone/hand-held work) sit around LOA20 at best. That is enough to detect a **missing** element or a
gross shift (a wall 5+ cm off), but not the 5 to 15 mm of LOA30 that a tight "shifted" verdict implies.
Also, a point-cloud-vs-scan verdict needs the capture accuracy to be several times better than the
tolerance, which images do not reach at LOA30 or above. Inference from the above, not measured.

## 4. Laptop feasibility and licences

Summary from the table in section 2:

- COLMAP and the classical route are the only tools I can say are installable on a Mac from the pages
  read (Homebrew formula). COLMAP's own dense MVS needs CUDA (verified, FAQ), so the classical route on
  a Mac is COLMAP sparse plus a separate dense tool such as OpenMVS (unverified).
- None of VGGT, MASt3R, DUSt3R, MapAnything, DA3 mention MPS in the READMEs I read. All fall back to CPU
  in their examples. Memory, not speed, is the likely limit on a laptop.
- 3D Gaussian splatting needs CUDA. This puts it under the "cloud GPU, later" rule.
- Licences to watch: DUSt3R and MASt3R are CC BY-NC-SA 4.0 for code and weights, with training-set
  terms on top. VGGT's original checkpoint is non-commercial. MapAnything and DA3 have both Apache and
  non-commercial checkpoints, so choose by checkpoint name. The repo's own code is MIT and public, so
  shipping a non-commercial weight in a pipeline script is a decision to make explicitly; downloading
  weights at runtime is the safer pattern.

## 5. Literature and groups

From search results unless noted. None of it was read in full.

- Golparvar-Fard and colleagues (UIUC): photo-based as-built reconstruction registered to IFC, Bayesian
  progress detection under occlusion. Older baseline (2010s).
- Brilakis group (University of Cambridge): ConSLAM, "Periodically Collected Real-World Construction
  Dataset for SLAM and Progress Monitoring" (Trzeciak et al., ECCV Workshops 2022; JCCE version) and its
  BIM add-on. EU BIM2TWIN funded. Verified from the Cambridge repository records.
- Voos, Sanchez-Lopez (University of Luxembourg): BIM-constrained localisation for AR construction
  monitoring, 2025 (verified, arXiv 2504.17693).
- Shaojie Shen's lab and Huan Yin (HKUST): SLABIM, SLAM + BIM dataset, ICRA 2025 (verified, arXiv 2502.16856).
- Tsinghua group (BIMNet, IFC scan-to-BIM benchmark; authors not read).
- Borrmann (TUM) and Bosche (Edinburgh) are widely known for construction-progress and as-built work, but I did
  not verify any of their 2022 to 2026 image-based papers here. Unverified; do not cite without checking.
- NeRF-with-BIM progress evaluation (Automation in Construction, 2025) and the 2026 MCP-enabled LLM +
  4D BIM progress monitoring paper (ACM), authors not captured.
- Gap I observed, not proven: a search for feed-forward reconstruction (VGGT and similar) on real
  construction or interior sites compared against a BIM found nothing. A June 2026 survey covers the
  feed-forward family ([ScienceDirect](https://www.sciencedirect.com/science/article/pii/S2096579626000203))
  but not BIM checking. If the gap is real, a careful benchmark of feed-forward reconstruction for
  scan-vs-BIM verdicts is a defensible small contribution; it needs a proper literature search before any
  novelty claim goes into a PhD statement.

## Recommendation

**Later extension, not an in-scope phase.** Reasons:

1. No suitable open dataset exists to evaluate it with the project's own constraints (clear licence,
   images + truth + IFC). The data the extension needs is the part the roadmap does not have.
2. Accuracy at best reaches LOA20, and the project's value rests on tolerances taken from LOA. The core
   claim ("shifted at LOA30 tolerances") cannot be made from images on current evidence.
3. The 8-week plan is already full (align, compare, report, show, carbon, write-up) with a hard
   January deadline. Architecture B is two new modules; architecture A is a thin wrapper but adds scale,
   confidence-masking and a dataset-access chase.
4. Laptop constraint: the useful tools (feed-forward models) are CUDA-first with unverified MPS support;
   the one that surely runs (COLMAP) is slow and unverified for dense output.

If it goes in at all, do architecture A, as a post-week-8 extension (listed under "Later" in the roadmap,
next to the learned-registration item), and only after the Compare phase exists, since it reuses that
phase. It would displace nothing in weeks 1 to 8; if tried before then it would take week 7 (Carbon)
first.

### Smallest experiment (about one week, laptop)

Goal: decide whether an image-derived cloud is good enough to feed phases 1 and 2.

- **Data:** two or three ETH3D indoor training scenes with `scan_clean` (e.g. office, kicker; CC BY-NC-SA 4.0, fine for
  non-commercial research but not to redistribute in this repo) as laser truth. If ScanNet++ access is approved in time, one iPhone-plus-laser scene
  adds a second domain. There is no IFC, so build stand-in elements: RANSAC-fit the 6 to 10 largest planes
  in the laser scan, treat them as "elements".
- **Tools:** COLMAP (Homebrew, CPU sparse + whatever dense it can do) and one feed-forward model, MapAnything
  (Apache checkpoint, to keep licences simple) or VGGT, on 50 to 100 images per scene, CPU or MPS. Record
  wall time and peak memory.
- **Pipeline:** image cloud, then the Phase 1 registration with scale estimation (no ground-truth
  transform), then per-plane signed distance to the laser scan.
- **Metrics:**
  1. Median and 90th-percentile cloud-to-laser distance on the stand-in planes, after registration.
  2. Scale error of the recovered similarity transform against truth (from the laser frame).
  3. Verdict test: shift one plane by 5 cm, delete another from the model side; does the pipeline flag
     "shifted" and "missing" on the image cloud as it does on the laser cloud? Report detection rate and
     false positives at LOA20 (15 to 50 mm) and LOA30 (5 to 15 mm) thresholds.
- **Pass (promote to a planned extension):** 90th-percentile plane distance at or below 25 mm on at
  least two scenes, scale error under 2% without ground truth, the 5 cm shift detected and the deleted
  plane flagged on every scene, and each run completes in under 30 minutes on the laptop with the
  chosen tool.
- **Fail (drop it, cite the numbers in the write-up):** 90th-percentile above 50 mm, or the blank-wall
  planes hallucinated (a deleted plane still "found" in the image cloud), or a run needs a CUDA GPU.

## What I could not verify

- USIBD LOA numbers from the spec itself (the spec URLs I tried returned 404; figures above are from a
  2021 blog quoting v3.0). The "95% confidence" basis and any v3.1 changes: unchecked.
- ScanNet++ Terms of Use text; ConSLAM data licence; the ConSLAM BIM release
  contents and licence (mediaTUM blocked the fetch); SLABIM licence; the Gaussian splatting `LICENSE.md`
  text; GLOMAP licence and macOS status.
- Whether any feed-forward tool runs on MPS (none of the READMEs say), and any timing on Apple Silicon.
- Metric accuracy of MASt3R, MapAnything and DA3 at room scale; the ETH3D numbers in the VGGT paper;
  the numeric results in the aerial-block evaluation (PDF unreadable to my fetcher).
- Indoor image-vs-TLS accuracy for textureless walls and glass: no source found.
- Author lists and affiliations for the NeRF+BIM and 2026 4D-BIM papers; whether BIMNet scans pair with
  Matterport3D panoramas; Hilti 2023 TLS and ground-truth accuracy details beyond the search snippet.
