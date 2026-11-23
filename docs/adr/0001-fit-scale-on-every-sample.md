# Fit scale on every sample, without the benchmark's scaled flag

PC2Model scales 71 of its 137 samples, and notebook 05a fitted scale only on the samples the benchmark flags as
scaled: oracle input that a real run would not have. From Phase 1 the registration fits scale on every sample,
and the 1% scale-error criterion applies to every sample, so an unscaled sample that comes out at 1.03 is a
failure. We chose the realistic run over 05a's parity: the headline numbers no longer depend on information
the pipeline could not know.

## Consequences

- 05a's and 05c's numbers change on unscaled samples; the pure move of the registration code proves parity
  first, and the switch is a separate step with its new numbers recorded.
- A real scan in metres has scale 1, so for real projects the scale stages are extra freedom that can only
  hurt. Whether they do is measured on the unscaled samples; if they do, revisit this (for example with a
  user-declared "scan is metric" switch), not by bringing the oracle flag back.

## Revisited 2026-11-23 (#52)

#38 measured the RMS-radius scale start 12.5 % off on both UVigo samples, and the scale stages cannot recover it:
simulated UVigo went from a 2 mm success to a 57 cm / 6.0 % failure, real UVigo from 12 cm to 1.48 m / 8.3 %, and 05a
from 7 to 6 of 9. #39's benchmark: 34 of 66 unscaled samples succeed, and 26 of the 32 unscaled failures end above
1 % scale error.

Decision: `register_sample(..., metric=True)`, a user-declared "scan is metric" switch for real projects (a real
scanner is metric: a fact the user has, not a benchmark oracle). It skips the RMS estimate (start scale 1) and runs
rigid stages only, so the scale is exactly 1. The benchmark stays label-free and runs with `metric=False`; setting it
per sample would be the oracle flag again, so its numbers do not change. With `metric=True` the path is the pre-#38
`scaled=False` one, so 05a's Phase 0.5 rows on the five unscaled gate samples are its measurement: 4 of 5 succeed
(real UVigo fails at 12 cm, as before #38).

Rejected: a multi-start or better scale start. Fitness is not comparable across scales, and choosing one after seeing
the 137-sample results risks tuning on test data.
