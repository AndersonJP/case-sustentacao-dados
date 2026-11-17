-- =============================================================================
-- CAMADA GOLD: tabelas prontas para o dashboard (Databricks SQL)
-- -----------------------------------------------------------------------------
-- Cada tabela responde UMA pergunta de negócio:
--   gold.chamados_mensal     -> como o volume evoluiu mês a mês, por categoria?
--   gold.kpis_antes_depois   -> quanto melhorou do Q1 para o Q4? (o "-82%")
--   gold.pareto_recorrentes  -> onde estão os incidentes que se repetem?
--   gold.alertas_mensal      -> quantos problemas o monitoramento evitou?
-- Power BI / QuickSight / Tableau conectam direto nessas tabelas.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS gold;

-- 1) Série mensal por categoria ------------------------------------------------
CREATE OR REPLACE TABLE gold.chamados_mensal AS
SELECT
    mes_referencia,
    categoria,
    COUNT(*)                                                    AS qtd_chamados,
    ROUND(SUM(horas_trabalhadas), 1)                            AS horas_trabalhadas,
    ROUND(AVG(horas_resolucao), 1)                              AS mttr_horas,
    ROUND(100.0 * SUM(CASE WHEN horas_resolucao <= sla_horas THEN 1 ELSE 0 END)
          / NULLIF(SUM(CASE WHEN resolvido_em IS NOT NULL THEN 1 ELSE 0 END), 0), 1) AS pct_dentro_sla
FROM silver.chamados
GROUP BY mes_referencia, categoria;


-- 2) KPIs Antes (Q1) x Depois (Q4) ---------------------------------------------
--    Comparo médias mensais de trimestres fechados para não ser enganado por sazonalidade de um mês só.
CREATE OR REPLACE TABLE gold.kpis_antes_depois AS
WITH periodos AS (
    SELECT
        CASE
            WHEN mes_referencia BETWEEN '2025-01-01' AND '2025-03-01' THEN 'Antes (Q1/2025)'
            WHEN mes_referencia BETWEEN '2025-10-01' AND '2025-12-01' THEN 'Depois (Q4/2025)'
        END AS periodo,
        *
    FROM silver.chamados
)
SELECT
    periodo,
    ROUND(COUNT(*) / 3.0, 0)                                    AS chamados_mes,
    ROUND(SUM(horas_trabalhadas) / 3.0, 0)                      AS horas_mes,
    ROUND(AVG(horas_resolucao), 1)                              AS mttr_horas,
    ROUND(100.0 * SUM(CASE WHEN horas_resolucao <= sla_horas THEN 1 ELSE 0 END)
          / NULLIF(SUM(CASE WHEN resolvido_em IS NOT NULL THEN 1 ELSE 0 END), 0), 1) AS pct_dentro_sla,
    ROUND(100.0 * SUM(CASE WHEN categoria IN ('Extração / relatório manual', 'Dúvida sobre dado') THEN 1 ELSE 0 END)
          / COUNT(*), 1)                                        AS pct_resolvivel_por_dashboard
FROM periodos
WHERE periodo IS NOT NULL
GROUP BY periodo;


-- 3) Pareto dos incidentes recorrentes no período "Antes" -----------------------
--    Foi esta tabela que mostrou que poucos sistemas concentravam a maior parte do problema.
CREATE OR REPLACE TABLE gold.pareto_recorrentes AS
WITH base AS (
    SELECT
        sistema,
        squad,
        SUM(CASE WHEN mes_referencia <  '2025-04-01' THEN 1 ELSE 0 END) AS qtd_antes,
        SUM(CASE WHEN mes_referencia >= '2025-10-01' THEN 1 ELSE 0 END) AS qtd_depois
    FROM silver.chamados
    WHERE categoria = 'Incidente recorrente'
    GROUP BY sistema, squad
)
SELECT
    sistema,
    squad,
    qtd_antes,
    qtd_depois,
    -- Window function: % acumulado, ordenado do sistema que mais gera recorrência para o que menos gera
    ROUND(100.0 * SUM(qtd_antes) OVER (ORDER BY qtd_antes DESC, sistema
                                       ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
          / SUM(qtd_antes) OVER (), 1)                          AS pct_acumulado
FROM base;


-- 4) Efeito dos alertas proativos ----------------------------------------------
CREATE OR REPLACE TABLE gold.alertas_mensal AS
SELECT
    mes_referencia,
    COUNT(*)                                                    AS alertas,
    SUM(virou_chamado)                                          AS viraram_chamado,
    COUNT(*) - SUM(virou_chamado)                               AS evitados,
    ROUND(100.0 * (COUNT(*) - SUM(virou_chamado)) / COUNT(*), 1) AS pct_evitados,
    ROUND(AVG(minutos_ate_tratativa), 0)                        AS minutos_medios_tratativa
FROM silver.alertas
GROUP BY mes_referencia;
