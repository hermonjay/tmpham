-- dim_product: one row per product with asset class, label, and bucket
select
    stg_products.product_id,
    stg_products.product_code,
    stg_products.product_name,
    stg_products.isin,
    stg_products.currency,
    stg_products.asset_class,
    case
        stg_products.asset_class
        when 'Saham'
        then 'Equity / Saham'
        when 'Ekuitas'
        then 'Equity / Ekuitas'
        when 'Obligasi'
        then 'Fixed Income / Obligasi'
        when 'Campuran'
        then 'Balanced / Campuran'
        when 'Penyertaan Terbatas'
        then 'Limited / Penyertaan Terbatas'
        when 'Syariah'
        then 'Syariah'
        when 'Terproteksi'
        then 'Protected / Terproteksi'
        when 'Money Market'
        then 'Money Market / Pasar Uang'
        else 'Unknown'
    end as asset_class_label,
    case
        when
            stg_products.asset_class
            in ('Obligasi', 'Terproteksi', 'Penyertaan Terbatas', 'Money Market')
        then 'fixed_income'
        else 'equity_campuran'
    end as asset_class_bucket
from {{ ref('stg_products') }} as stg_products
