-- Staging: faithful to the source, only cleaned and renamed.
-- No business logic here — that belongs in the mart.
-- Columns with hyphens require double-quoting in DuckDB.
SELECT
    ROW_NUMBER() OVER ()                              AS applicant_id,
    SeriousDlqin2yrs                                  AS defaulted,
    RevolvingUtilizationOfUnsecuredLines              AS revolving_utilization,
    age,
    DebtRatio                                         AS debt_ratio,
    MonthlyIncome                                     AS monthly_income,
    NumberOfOpenCreditLinesAndLoans                   AS open_credit_lines,
    NumberOfTimes90DaysLate                           AS late_90_days,
    "NumberOfTime30-59DaysPastDueNotWorse"            AS late_30_59_days,
    "NumberOfTime60-89DaysPastDueNotWorse"            AS late_60_89_days,
    NumberOfDependents                                AS dependents,
    income_missing,
    NOW()                                             AS loaded_at
FROM 'data/staging/credit_applications.parquet'
WHERE age BETWEEN 18 AND 100
  AND monthly_income >= 0
QUALIFY ROW_NUMBER() OVER (PARTITION BY age, monthly_income, debt_ratio ORDER BY 1) = 1
