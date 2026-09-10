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
stores the published absolute weights unchanged. Pre-2017 annual weights apply
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

The bottom-up check is diagnostic by default. Measured against the current
published workbook (173 series, 37 reconcilable parents, 4,218 parent-months
from 2017 onward), the price-updated formula reconciles every check: the median
absolute residual is 0.0003 pp and the maximum is 0.0015 pp, which is the
rounding granularity of the one-decimal published index levels. No parent-month
breaches the 0.10 pp tolerance. Residuals materially above that level indicate a
parsing, hierarchy or weight-matching defect rather than ONS methodology.
`--strict-validation` is provided for controlled validation runs, while ordinary
ingestion logs the ten worst exceptions without discarding official
observations.

The optional Excel export mirrors the collected levels, official weights,
series/parent map, and every reconciliation result.

