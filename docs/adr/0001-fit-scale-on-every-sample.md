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
