-- Mart: business logic and derived features for ML and analytics.
-- Reads from stg_credit_applications (registered as view by run_model).
-- Never reads the raw Parquet directly — always through the staging layer.
SELECT
    applicant_id,
    defaulted,
    age,
    monthly_income,
    revolving_utilization,
    debt_ratio,
    open_credit_lines,
    dependents,
    income_missing,
    late_30_59_days,
    late_60_89_days,
    late_90_days,

    -- Derived: total payment history burden
    (late_30_59_days + late_60_89_days + late_90_days)  AS total_late_payments,

    -- Derived: binary flag for severe delinquency history
    CASE WHEN late_90_days > 0 THEN 1 ELSE 0 END         AS has_90day_default,

    -- Derived: risk classification for downstream segmentation
    CASE
        WHEN revolving_utilization > 0.9 OR late_90_days > 2 THEN 'HIGH'
        WHEN revolving_utilization > 0.5 OR late_30_59_days > 1 THEN 'MEDIUM'
        ELSE 'LOW'
    END                                                   AS risk_tier,

    loaded_at
FROM stg_credit_applications
