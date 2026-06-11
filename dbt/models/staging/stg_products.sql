-- stg_products: product master from raw.cis_products with derived asset_class
--
-- asset_class is the raw Indonesian fund-type label extracted from
-- the product name via keyword matching. Bucketing into
-- equity_campuran / fixed_income happens downstream in dim_product.
select
    cast(id as bigint) as product_id,
    cast(hpfid as varchar) as product_code,
    cast(name as varchar) as product_name,
    cast(sid as varchar) as isin,
    'IDR'::varchar as currency,
    case
        when lower(name) ilike '%saham%'
        then 'Saham'
        when lower(name) ilike '%ekuitas%'
        then 'Ekuitas'
        when lower(name) ilike '%obligasi%' or lower(name) ilike '%bond%'
        then 'Obligasi'
        when lower(name) ilike '%campuran%'
        then 'Campuran'
        when lower(name) ilike '%penyertaan terbatas%'
        then 'Penyertaan Terbatas'
        when lower(name) ilike '%syariah%'
        then 'Syariah'
        when lower(name) ilike '%terproteksi%'
        then 'Terproteksi'
        when lower(name) ilike '%pasar uang%' or lower(name) ilike '%money market%'
        then 'Money Market'
        else 'Unknown'
    end as asset_class,
    current_timestamp as created_at,
    current_timestamp as updated_at
from {{ source('raw', 'cis_products') }}
