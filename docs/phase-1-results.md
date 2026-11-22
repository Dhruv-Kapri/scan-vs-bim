# Phase 1 registration benchmark

Command: `uv run python scripts/run_benchmark.py`

Commit(s): b32ab33, df946cc

Samples present: 137 of 137

Cost: 2.9 h summed over the samples' run_s; largest per-sample peak RSS 2.01 GB (veh_002-sketchfab)

Generated from outputs/phase1/registration.csv by `uv run python scripts/write_phase1_results.py`.

Success: rotation error <= 2.0 deg, centroid error <= 0.05 m, relative scale error <= 0.01 (judgement calls, CONTEXT.md "Registration success"). Unseen = neither a Phase 0.5 gate sample nor one of 05c's tuning samples. A model with no triangles left at load (below) counts as a failure; its errors are not measured, so the medians and p90s leave it out.

| group | scale | n | success, all (k/n) | success, unseen only (k/n) | seed 0 success (context) | rot_deg median / p90 | centroid_m median / p90 | scale_err_pct median / p90 |
|---|---|---|---|---|---|---|---|---|
| house | unscaled | 14 | 9/14 (64%) | 7/12 | 7/14 | 0.01617 / 154.9 | 0.001462 / 1.855 | 0.04249 / 8.017 |
| house | scaled | 11 | 7/11 (64%) | 6/9 | 6/11 | 0.01565 / 119.8 | 0.003218 / 4.074 | 0.03902 / 2.16 |
| simulated indoor (indoor_modelling) | unscaled | 2 | 1/2 (50%) | 0/0 | 1/2 | 0.1684 / 0.3019 | 0.2847 / 0.5116 | 3.036 / 5.438 |
| simulated indoor (indoor_modelling) | scaled | 4 | 3/4 (75%) | 2/2 | 2/4 | 0.001173 / 0.2011 | 0.0009575 / 0.1383 | 0.06129 / 1.456 |
| real indoor (ISPRS_indoor_modeling_benchmark) | unscaled | 4 | 2/4 (50%) | 1/2 | 0/4 | 0.1793 / 4.151 | 0.4646 / 1.305 | 3.84 / 7.876 |
| real indoor (ISPRS_indoor_modeling_benchmark) | scaled | 2 | 1/2 (50%) | 0/0 | 1/2 | 0.2292 / 0.2698 | 1.406 / 2.511 | 14.13 / 25.28 |
| furniture | unscaled | 10 | 5/10 (50%) | 5/10 | 3/10 | 0.005983 / 179.9 | 0.1365 / 3.201e+04 | 0.03012 / 6.659 |
| furniture | scaled | 15 | 9/15 (60%) | 8/14 | 6/15 | 0.007449 / 3.213 | 0.005307 / 8.109 | 0.0194 / 12.97 |
| home_decor | unscaled | 13 | 10/13 (77%) | 10/13 | 9/13 | 0.001193 / 49.39 | 0.0007604 / 0.1021 | 0.02746 / 0.0694 |
| home_decor | scaled | 12 | 8/12 (67%) | 8/12 | 8/12 | 0.004367 / 180 | 0.0005049 / 1.731 | 0.02267 / 0.02988 |
| mechanical | unscaled | 13 | 6/13 (46%) | 6/13 | 5/13 | 0.02063 / 178.4 | 0.003386 / 1.243 | 0.03409 / 5.12 |
| mechanical | scaled | 12 | 7/12 (58%) | 7/12 | 6/12 | 0.009419 / 176.4 | 0.002534 / 0.7134 | 0.03134 / 0.06743 |
| vehicle | unscaled | 10 | 1/10 (10%) | 1/10 | 2/10 | 3.505 / 171.1 | 0.2559 / 0.7106 | 9.818 / 26.2 |
| vehicle | scaled | 15 | 8/15 (53%) | 8/15 | 7/15 | 0.09182 / 2.207 | 0.003644 / 0.1806 | 0.1844 / 8.613 |
| building (37) | unscaled | 20 | 12/20 (60%) | 8/14 | 8/20 | 0.02906 / 113.6 | 0.005881 / 1.758 | 0.08105 / 8.163 |
| building (37) | scaled | 17 | 11/17 (65%) | 8/11 | 9/17 | 0.01565 / 101.9 | 0.003218 / 3.302 | 0.05085 / 3.361 |
| objects (100) | unscaled | 46 | 22/46 (48%) | 22/46 | 19/46 | 0.008234 / 178.4 | 0.006826 / 1.51 | 0.03634 / 10.58 |
| objects (100) | scaled | 54 | 32/54 (59%) | 31/53 | 27/54 | 0.007783 / 140.8 | 0.002398 / 2.863 | 0.02934 / 8.051 |
| all | unscaled | 66 | 34/66 (52%) | 30/60 | 27/66 | 0.02063 / 177.2 | 0.006826 / 1.709 | 0.04 / 8.888 |
| all | scaled | 71 | 43/71 (61%) | 39/64 | 36/71 | 0.008224 / 133.2 | 0.002517 / 3.08 | 0.02996 / 7.383 |

## Agreement with the Phase 0.5 gate (05a)

A gate row agrees when its success equals 05a's and the differences are within 0.01 deg, 0.001 m and 0.01 percentage points (judgement calls; registration is seeded, so near-exact is expected).

| sample | benchmark success | 05a success | d rot_deg | d centroid_m | d scale_err_pct | agrees |
|---|---|---|---|---|---|---|
| house_23-sketchfab | True | True | 0 | 2.59e-14 | 7.37e-14 | yes |
| house_13-sketchfab | True | True | 1.8e-10 | 1.39e-14 | 2.22e-14 | yes |
| house_18-sketchfab | True | True | 5.72e-11 | 5.22e-15 | 5.55e-14 | yes |
| indoor_modelling_4-ISPRS_indoor_modelling-UoM | True | True | 0 | 1.41e-14 | 1.49e-14 | yes |
| indoor_modelling_3-ISPRS_indoor_modelling-UVigo | False | False | 0 | 7.55e-15 | 2.22e-14 | yes |
| indoor_modelling_0-ISPRS_indoor_modelling-TUBS1 | False | False | 2.54e-12 | 6.02e-15 | 0 | yes |
| real-indoor_modelling_1-ISPRS_indoor_modelling-TUBS2 | True | True | 2.6e-12 | 1.16e-14 | 1.77e-14 | yes |
| real-indoor_modelling_3-ISPRS_indoor_modelling-UVigo | False | False | 0 | 5.26e-14 | 1.55e-13 | yes |
| real-indoor_modelling_2-ISPRS_indoor_modelling-Fire_Brigade | True | True | 0 | 3.27e-15 | 6.66e-14 | yes |

all agree: yes

## Not scored

Samples whose run raised (scripts/run_benchmark.py logs the error):

none

## Models with non-triangle faces

Open3D's OBJ reader skips faces that are not triangles, without an error, so these models were sampled from their triangles only (05a's loader, kept frozen). The share counts faces, not area.

| sample | faces dropped at load | success |
|---|---|---|
| house_16-sketchfab | 0.0% | True |
| house_17-sketchfab | 2.0% | True |
| veh_013-sketchfab | 30.9% | False |
| house_12-sketchfab | 68.3% | False |
| veh_017-sketchfab | 72.1% | True |
| house_11-sketchfab | 77.6% | True |
| house_18-sketchfab | 82.5% | True |
| house_8-sketchfab | 84.8% | False |
| veh_021-sketchfab | 86.5% | False |
| veh_015-sketchfab | 86.5% | False |
| veh_000-sketchfab | 90.1% | False |
| house_9-sketchfab | 90.3% | False |
| veh_016-sketchfab | 91.8% | False |
| veh_010-sketchfab | 95.1% | True |
| house_20-sketchfab | 96.1% | False |
| house_24-sketchfab | 96.9% | False |
| house_19-sketchfab | 97.3% | False |
| veh_012-sketchfab | 98.0% | False |
| veh_008-sketchfab | 100.0% | False |
