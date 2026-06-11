# Asset classification rules

## Why deterministic

Every product maps to exactly one asset-class bucket through a
deterministic chain of `CASE WHEN` predicates. No ML, no manual
overrides, no per-row exceptions. This means:

* dbt tests can fail the pipeline when a product is unclassifiable.
* A new product entering `raw.cis_products` either maps cleanly or
  breaks the build — silent misallocation is impossible.
* Re-runs produce identical results (idempotent at the cell level).

## Buckets

The KPI brief asks for two buckets only:

| Bucket           | Includes (Indonesian)                                |
|------------------|------------------------------------------------------|
| `equity_campuran`| Saham (Equity), Campuran (Mixed/Balanced)            |
| `fixed_income`   | Pendapatan Tetap (Fixed Income), Pasar Uang (Money Market), Sukuk |

Money Market (`pasar uang`) is grouped with Fixed Income because for
agent scorecards it behaves like short-duration fixed income. If the
business later wants to break it out, add a third bucket and update
the asset-allocation reconciliation test.

## Precedence

The classifier runs two passes (see `macros/classify_asset.sql`):

1. **Curated `fund_type` wins.** If the source carries a curated
   `fund_type` code, it is trusted over the name. Recognised codes:
   * Equity/Campuran bucket: `saham`, `campuran`, `equity`, `mixed`
   * Fixed Income bucket: `pendapatan_tetap`, `fixed_income`,
     `fixedincome`, `pasar_uang`, `money_market`, `money market`,
     `sukuk`, `bond`
2. **Name keyword scan** (case-insensitive, `SIMILAR TO` regex):
   * `%(saham|equity|stock)%`               → equity_campuran
   * `%(campuran|mixed|balanced)%`          → equity_campuran
   * `%(pendapatan tetap|fixed income|fixedincome|obligasi|bond|sukuk)%`
                                            → fixed_income
   * `%(pasar uang|money market|money_market|pasaruang)%`
                                            → fixed_income
   * Anything else                          → `unknown`

Order matters. A hypothetical product "Reksa Dana Saham Campuran"
matches `saham` first and is treated as equity. This is intentional:
saham funds are governed by OJK rules to hold ≥80% equity, whereas
campuran funds hold ≤79% — when in doubt, the higher-equity bucket
wins.

## Where it is invoked

| Model / Test                                   | Purpose                                                |
|------------------------------------------------|--------------------------------------------------------|
| `stg_products`                                 | Adds `asset_class` column                              |
| `dim_product`                                  | Forwards `asset_class` + adds human label              |
| `fct_agent_monthly_kpis`                       | Joins via `dim_product`, splits AUM by `asset_class`   |
| `tests/singular/no_unknown_asset_class.sql`    | Hard-fails on any `unknown`                            |
| `tests/singular/asset_allocation_reconciles.sql`| Hard-fails if buckets don't sum to total              |

## Catalogue (current `raw.cis_products`)

| id | product_name                                     | fund_type        | asset_class      |
|----|--------------------------------------------------|------------------|------------------|
|  1 | Reksa Dana Saham BNI Stable Growth              | saham            | equity_campuran  |
|  2 | Reksa Dana Pendapatan Tetap Mandiri Premium     | pendapatan_tetap | fixed_income     |
|  3 | Syailendra Campuran Berimbang                   | campuran         | equity_campuran  |
|  4 | Reksa Dana Pasar Uang BCA Likuid                | pasar_uang       | fixed_income     |
|  5 | Sucorinvest Equity Fund Saham                   | saham            | equity_campuran  |
|  6 | Trimegah Pendapatan Tetap Berkah                | pendapanan_tetap | fixed_income     |
|  7 | Ashmore Campuran Progresif                      | campuran         | equity_campuran  |
|  8 | CIMB Niaga Likuid Pasar Uang                    | pasar_uang       | fixed_income     |
|  9 | Manulife Saham Andalan                          | saham            | equity_campuran  |
| 10 | BRIngin Pendapatan Tetap Stabil                | pendapatan_tetap | fixed_income     |

**Bucket mix:** 5 equity/campuran, 5 fixed income → balanced catalogue
that lets the Equity-vs-FI KPI split actually discriminate.

## Adding a new product

1. Insert into `raw.cis_products` with `product_name`, `fund_type`,
   `product_code`, `isin`, `currency`.
2. If `fund_type` is one of the recognised codes, no further action.
3. Otherwise, ensure the product_name matches a keyword. If not,
   add the keyword to `macros/classify_asset.sql` and bump the
   package version.
4. Run `dbt test -s stg_products` — `no_unknown_asset_class` will
   fail if the new product is not classified.
