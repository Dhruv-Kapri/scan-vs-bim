# Count false flags against the baseline verdict

The perturbed-model criterion allowed at most 10% of untouched elements to be "falsely flagged" shifted or
missing. In 05b three untouched walls (`Drywall:962532`, `971319`, `976743`) read shifted in every perturbed
run because they already read shifted on the real model, and they may really be displaced. From Phase 1 a
false flag is an untouched element whose verdict changes from its baseline verdict to shifted or missing;
elements already shifted in the baseline leave the denominator and are listed. The perturbed run tests what
the injected change does, not whether the baseline is right; the hand check covers that.

## Considered options

- Keep the rule as written: punishes the logic for walls that may be truly displaced.
- Exclude a baseline-shifted element only if an independent plane fit confirms its displacement: more
  defensible, but it adds a second judging rule whose own errors would need checking.

## Consequences

The Phase 0.5 gate numbers were read under the old rule and are not re-scored; room B's numbers after Phase 1
are reported under this one, labelled as such.
