# Phase 1 registration benchmark

Command: `uv run python scripts/run_benchmark.py`

Commit(s), rows each: df946cc (118), b3824fc (10), 5a7d301 (7), 551f3b3 (2) (per row: the CSV's commit column)

Samples present: 137 of 137

Cost: 4.0 h summed over the samples' run_s; largest per-sample peak RSS 2.01 GB (veh_002-sketchfab)

Generated from outputs/phase1/registration.csv by `uv run python scripts/write_phase1_results.py`.

Success: rotation error <= 2.0 deg, centroid error <= 0.05 m, relative scale error <= 0.01 (judgement calls, CONTEXT.md "Registration success"). Unseen = neither a Phase 0.5 gate sample nor one of 05c's tuning samples. A model with no faces at load would count as a failure; its errors are not measured, so the medians and p90s would leave it out.

| group | scale | n | success, all (k/n) | success, unseen only (k/n) | seed 0 success (context) | rot_deg median / p90 | centroid_m median / p90 | scale_err_pct median / p90 |
|---|---|---|---|---|---|---|---|---|
| house | unscaled | 14 | 10/14 (71%) | 8/12 | 9/14 | 0.004727 / 126 | 0.001178 / 0.4889 | 0.02863 / 6.203 |
| house | scaled | 11 | 9/11 (82%) | 8/9 | 7/11 | 0.005213 / 0.187 | 0.001571 / 0.3498 | 0.02393 / 0.1512 |
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
| vehicle | unscaled | 10 | 2/10 (20%) | 2/10 | 3/10 | 0.3234 / 1.66 | 0.094 / 0.2337 | 5.791 / 11.37 |
| vehicle | scaled | 15 | 9/15 (60%) | 9/15 | 8/15 | 0.01103 / 1.434 | 0.0005474 / 0.2109 | 0.07364 / 9.831 |
| building (37) | unscaled | 20 | 13/20 (65%) | 9/14 | 10/20 | 0.01617 / 23.22 | 0.001831 / 0.913 | 0.03967 / 7.01 |
| building (37) | scaled | 17 | 13/17 (76%) | 10/11 | 10/17 | 0.005213 / 0.2826 | 0.001571 / 0.4892 | 0.02889 / 4.628 |
| objects (100) | unscaled | 46 | 23/46 (50%) | 23/46 | 20/46 | 0.01059 / 149.2 | 0.003828 / 1.472 | 0.03676 / 6.525 |
| objects (100) | scaled | 54 | 33/54 (61%) | 32/53 | 28/54 | 0.007311 / 140.8 | 0.002207 / 2.863 | 0.02934 / 8.498 |
| all | unscaled | 66 | 36/66 (55%) | 32/60 | 30/66 | 0.01059 / 149.2 | 0.003364 / 1.183 | 0.03798 / 7.002 |
| all | scaled | 71 | 46/71 (65%) | 42/64 | 38/71 | 0.006963 / 90 | 0.002138 / 2.356 | 0.02919 / 8.511 |

## Agreement with the Phase 0.5 gate (05a)

A gate row agrees when its success equals 05a's and the differences are within 0.01 deg, 0.001 m and 0.01 percentage points (judgement calls; registration is seeded, so near-exact is expected).

| sample | benchmark success | 05a success | d rot_deg | d centroid_m | d scale_err_pct | agrees |
|---|---|---|---|---|---|---|
| house_23-sketchfab | True | True | 0 | 6.23e-16 | 5.52e-14 | yes |
| house_13-sketchfab | True | True | 0 | 6.59e-15 | 2.22e-14 | yes |
| house_18-sketchfab | True | True | 0 | 1.18e-14 | 2.22e-14 | yes |
| indoor_modelling_4-ISPRS_indoor_modelling-UoM | True | True | 0 | 1.32e-14 | 2.97e-14 | yes |
| indoor_modelling_3-ISPRS_indoor_modelling-UVigo | False | False | 2.17e-12 | 5.22e-15 | 1.78e-13 | yes |
| indoor_modelling_0-ISPRS_indoor_modelling-TUBS1 | False | False | 2.54e-12 | 8.33e-17 | 6.48e-14 | yes |
| real-indoor_modelling_1-ISPRS_indoor_modelling-TUBS2 | True | True | 2.6e-12 | 1.16e-14 | 1.77e-14 | yes |
| real-indoor_modelling_3-ISPRS_indoor_modelling-UVigo | False | False | 0 | 2.13e-14 | 1.07e-14 | yes |
| real-indoor_modelling_2-ISPRS_indoor_modelling-Fire_Brigade | True | True | 0 | 8.95e-15 | 6.66e-14 | yes |

all agree: yes

## Not scored

Samples whose run raised (scripts/run_benchmark.py logs the error):

none

## Models with non-triangle faces

These faces are triangulated at load (`obj_mesh.load_model_mesh`, #53: convex ones as a fan, concave ones split into rings and cut by earcut). Before #53 Open3D's OBJ reader skipped them without an error, so these models were sampled from their triangles only. The share counts faces, not area. Checked once for #53 face by face (`uv run python scripts/check_model_areas.py`): on all 19 models no face's triangles cover less than its outline (a lost face of any size would), the loaded mesh holds every face's triangles (within 1e-6), and on flat faces the triangles exceed the outline by under 1e-6 of the model's area (house_11: 6.5e-8, 0.0002 m2, from a few mm-scale faces whose edges cross, which earcut overlaps). A face that touches itself is measured as the area it covers, so a flap wound backwards counts as surface; a face that is not flat has no single area and is checked only against its outline's projection. veh_010 went from success to failure: before #53 it loaded 0.79 m2 of its 53 m2 model; now all of it loads and the scan sits on it under the true pose, but 35% of the model is unseen by the scan and the scale fit shrinks towards it (a registration limitation, not the loader's).

| sample | non-triangle faces | success before | success now | rot_deg before | rot_deg now | centroid_m before | centroid_m now |
|---|---|---|---|---|---|---|---|
| house_16-sketchfab | 0.0% | True | True | 0.004097 | 0.004465 | 0.0008781 | 0.001019 |
| house_17-sketchfab | 2.0% | True | True | 0.03264 | 0.03123 | 0.001505 | 0.001745 |
| veh_013-sketchfab | 30.9% | False | True | 178.2 | 0.01814 | 0.414 | 0.00131 |
| house_12-sketchfab | 68.3% | False | True | 167.5 | 0.001388 | 4.281 | 0.0003032 |
| veh_017-sketchfab | 72.1% | True | True | 0.008224 | 0.001367 | 0.0008299 | 0.0001503 |
| house_11-sketchfab | 77.6% | True | True | 0.02169 | 0.005213 | 0.001454 | 0.001254 |
| house_18-sketchfab | 82.5% | True | True | 0.02547 | 0.003294 | 0.001419 | 0.0004451 |
| house_8-sketchfab | 84.8% | False | False | 106.7 | 0.06865 | 1.903 | 0.1782 |
| veh_021-sketchfab | 86.5% | False | False | 5.18 | 1.455 | 0.4714 | 0.06571 |
| veh_015-sketchfab | 86.5% | False | True | 2.87 | 0.007389 | 0.1804 | 0.0002705 |
| veh_000-sketchfab | 90.1% | False | False | 169.3 | 0.7514 | 0.6156 | 0.1196 |
| house_9-sketchfab | 90.3% | False | False | 119.8 | 0.187 | 4.074 | 0.3498 |
| veh_016-sketchfab | 91.8% | False | False | 103 | 0.03091 | 1.09 | 0.2081 |
| veh_010-sketchfab | 95.1% | True | False | 0.09182 | 1.658 | 0.01402 | 0.2311 |
| house_20-sketchfab | 96.1% | False | True | 15.93 | 0.004432 | 2.145 | 0.001571 |
| house_24-sketchfab | 96.9% | False | True | 90 | 0.003895 | 1.742 | 0.000445 |
| house_19-sketchfab | 97.3% | False | False | 175.6 | 180 | 1280 | 0.5698 |
| veh_012-sketchfab | 98.0% | False | True | 1.442 | 0.01103 | 0.04459 | 0.0002725 |
| veh_008-sketchfab | 100.0% | False | False | - | 0.05825 | - | 0.001736 |
