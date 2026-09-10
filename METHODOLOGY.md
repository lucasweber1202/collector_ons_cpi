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
2. **Monthly bottom-up rate:** for parent `p` and children `i`, the collector
   calculates

   `R_hat(p,t) = sum(w(i,t) * I(i,t)/I(i,t-1)) / sum(w(i,t))`

   and compares it with `I(p,t)/I(p,t-1)`. The configured residual is expressed
   in percentage points and defaults to 0.10 pp.

The bottom-up check is diagnostic by default. Some ONS series involve seasonal
re-referencing, chaining, central-item methods, imputation, or lower-level
components not present in Table 38; these can create legitimate residuals even
when the published data are internally sound. `--strict-validation` is provided
for controlled validation runs, while ordinary ingestion logs the ten worst
exceptions without discarding official observations.

The optional Excel export mirrors the collected levels, official weights,
series/parent map, and every reconciliation result.

