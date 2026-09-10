# UK CPI collection and bottom-up methodology

The collector uses ONS detailed reference Table 38 for CPI index levels and
Annex A Table W1 for official basket weights. It intentionally stores levels
(2015=100), not derived monthly or annual percentage changes.

## Coverage and identifiers

Table 38 currently contains 173 monthly series from January 1988: 122 series in
the publishable COICOP hierarchy and 51 ONS analytical aggregates. IDs encode
the measure, family, hierarchy node, native ONS CDID, and official name, for
example `CPI_COICOP_D01_D7BU_FOOD_AND_NON_ALCOHOLIC_BEVERAGES`.

## Weight regimes

W1 publishes weights in parts per 1,000. From 2017 onward, the ONS uses two
annual regimes above consumption-segment level:

- the December-reference weights apply to January;
- the January-reference weights apply from February through December.

The collector expands each source regime to its applicable reference months and
stores the published absolute weights unchanged in original_weights. Pre-2017 annual weights apply
to all twelve months of their year.

## Hierarchy

The structured node token reconstructs the immediate hierarchy without a
hand-written series map:

`ALL -> division (Dxx) -> group (Gxxx) -> class (Cxxxx)`.

Analytical `ALT` aggregates are stored but excluded from COICOP bottom-up checks
because they are overlapping cuts rather than a single additive tree.

## Checks performed on every run

1. **Weight additivity:** immediate-child absolute weights must sum to the
   parent weight. The default absolute tolerance is 0.01 parts per 1,000.
2. **Monthly bottom-up rate:** ONS aggregates with a Laspeyres-type index
   against an annual January price reference and chains the series in December.
   Reconstructing a parent price relative therefore requires price-updating the
   child weights to that reference month. For parent `p` and children `i`:

   ```text
   ref(t)     = January of year(t), except January itself, which chains on
                December of year(t-1)
   phi(i,t)   = w(i,t) * I(i,t-1)/I(i,ref) /
                sum_j w(j,t) * I(j,t-1)/I(j,ref)
   R_hat(p,t) = sum_i phi(i,t) * I(i,t)/I(i,t-1)
   ```

   `R_hat(p,t)` is compared with `I(p,t)/I(p,t-1)`. The configured residual is
   expressed in percentage points and defaults to 0.10 pp.

   The `I(i,ref)` term is not optional. Dropping it is equivalent to assuming
   every child shares one January index level. Table 38 publishes 2015=100
   levels that are never re-referenced to January, so omitting the term biases
   the residual progressively within each year: on a synthetic two-child parent
   built by the ONS rule (weights 400/600, one child rising 3% per month, one
   flat) the omission produces -0.0213 pp in March, -0.0860 pp in June and
   -0.1078 pp in July, breaching the 0.10 pp tolerance on perfectly consistent
   data.

All three checks (basket sums, official-basket reconstruction and direct
operational-share reconstruction) are mandatory before persistence. The current
full W1 window produces 8,251 bottom-up checks across 37 parents, with maximum
absolute residual 0.0019795967 pp. Table 38 publishes three-decimal levels.
The default 0.10 pp tolerance is a conservative historical configuration, not
a claim that published rounding is 0.10 pp. Tightening it requires review of
historical regimes and a separately agreed error budget.

The exact source basket is retained in original_weights. Operational phi weights
are persisted in weights, with 1.0 for standalone roots. The operational
validation applies stored shares directly, without normalization or another
price update. Weights are only derived where required price-reference indices
exist. Extraction includes the preceding December to validate January links.

The optional Excel export contains Time Series, Weights, Original Weights,
Series Map, Original Weight Map and Validation. It is an in-memory validation
snapshot, not a database vintage export.

See [COMPLIANCE.md](COMPLIANCE.md) for approved UK-local schema exceptions,
the deterministic classification aliases, complete weight-only source coverage,
upgrade safety and the remaining consumption-segment and deployment gates.
