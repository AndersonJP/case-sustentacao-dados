-- =============================================================================
-- Consultas usadas nos visuais do dashboard (Databricks SQL Dashboard,
-- Power BI, QuickSight ou Tableau). Todas leem só da camada GOLD.
-- =============================================================================

-- [Cartões de KPI] Antes x Depois
SELECT * FROM gold.kpis_antes_depois ORDER BY periodo;

-- [Gráfico de barras empilhadas] Volume mensal por categoria
SELECT mes_referencia, categoria, qtd_chamados
FROM gold.chamados_mensal
ORDER BY mes_referencia, categoria;

-- [Linha] MTTR e SLA do mês (todas as categorias)
SELECT
    mes_referencia,
    ROUND(SUM(mttr_horas * qtd_chamados) / SUM(qtd_chamados), 1) AS mttr_horas_ponderado,
    SUM(qtd_chamados)                                            AS qtd_chamados
FROM gold.chamados_mensal
GROUP BY mes_referencia
ORDER BY mes_referencia;

-- [Barras horizontais] Pareto de recorrentes por sistema
SELECT sistema, squad, qtd_antes, qtd_depois, pct_acumulado
FROM gold.pareto_recorrentes
ORDER BY qtd_antes DESC;

-- [Linha] % de alertas resolvidos antes de virar chamado
SELECT mes_referencia, alertas, evitados, pct_evitados
FROM gold.alertas_mensal
ORDER BY mes_referencia;

-- [Exploração] Chamados abertos agora que estão estourando SLA (visão operacional do dia)
SELECT issue_key, sistema, prioridade, criado_em, sla_horas
FROM silver.chamados
WHERE resolvido_em IS NULL
ORDER BY prioridade, criado_em;
