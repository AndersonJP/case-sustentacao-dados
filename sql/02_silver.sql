-- =============================================================================
-- CAMADA SILVER: dado limpo, tipado e integrado (Databricks SQL)
-- -----------------------------------------------------------------------------
-- Entrada : bronze.jira_issues, bronze.alertas_monitoramento, bronze.sistemas
-- Saída   : silver.chamados, silver.alertas
-- O que acontece aqui:
--   1. remove duplicadas do export do Jira (QUALIFY + ROW_NUMBER)
--   2. converte texto em data/hora e segundos em horas
--   3. classifica cada chamado numa CATEGORIA de negócio (a pergunta-chave do case)
--   4. calcula SLA por prioridade
--   5. integra com o cadastro de sistemas (área de negócio, squad, criticidade)
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS silver;

CREATE OR REPLACE TABLE silver.chamados AS
WITH jira_dedup AS (
    -- O export do Jira veio com linhas repetidas. Fico com a versão mais recente de cada issue.
    SELECT *
    FROM bronze.jira_issues
    QUALIFY ROW_NUMBER() OVER (PARTITION BY issue_key ORDER BY _data_ingestao DESC) = 1
),
jira_tipado AS (
    SELECT
        issue_key,
        issue_type                                              AS tipo,
        summary                                                 AS resumo,
        status,
        priority                                                AS prioridade,
        -- Jira exporta data no formato brasileiro (dd/MM/yyyy)
        to_timestamp(created, 'dd/MM/yyyy HH:mm')               AS criado_em,
        to_timestamp(NULLIF(resolved, ''), 'dd/MM/yyyy HH:mm')  AS resolvido_em,
        -- Qualidade de dado: componente vazio vira 'Não informado' em vez de sumir do dashboard
        COALESCE(NULLIF(TRIM(components), ''), 'Não informado') AS sistema,
        COALESCE(labels, '')                                    AS labels,
        CAST(time_spent AS DOUBLE) / 3600                       AS horas_trabalhadas
    FROM jira_dedup
)
SELECT
    j.issue_key,
    j.tipo,
    -- Regra de negócio: tipo + label do Jira => categoria que o gestor entende
    CASE
        WHEN j.labels LIKE '%extracao-dados%' THEN 'Extração / relatório manual'
        WHEN j.labels LIKE '%duvida-dados%'   THEN 'Dúvida sobre dado'
        WHEN j.labels LIKE '%recorrente%'     THEN 'Incidente recorrente'
        WHEN j.tipo = 'Incidente'             THEN 'Incidente novo'
        ELSE 'Melhoria'
    END                                                         AS categoria,
    j.resumo,
    j.status,
    j.prioridade,
    j.sistema,
    COALESCE(s.area_negocio, 'Não informado')                   AS area_negocio,
    COALESCE(s.squad, 'Não informado')                          AS squad,
    s.criticidade,
    j.criado_em,
    j.resolvido_em,
    CAST(date_trunc('MONTH', j.criado_em) AS DATE)              AS mes_referencia,
    ROUND(j.horas_trabalhadas, 2)                               AS horas_trabalhadas,
    -- Tempo de resolução em horas corridas (base do MTTR)
    ROUND((unix_timestamp(j.resolvido_em) - unix_timestamp(j.criado_em)) / 3600, 1) AS horas_resolucao,
    -- SLA acordado com o negócio (horas corridas)
    CASE j.prioridade WHEN 'Alta' THEN 24 WHEN 'Média' THEN 72 ELSE 120 END        AS sla_horas,
    -- Marco do projeto em que o chamado foi aberto (usado nas anotações do dashboard)
    CASE
        WHEN j.criado_em < '2025-04-01' THEN '0 - Antes'
        WHEN j.criado_em < '2025-06-01' THEN '1 - Dashboards self-service'
        WHEN j.criado_em < '2025-07-01' THEN '2 - Causa raiz (Pareto)'
        ELSE                                 '3 - Alertas proativos'
    END                                                         AS fase_projeto
FROM jira_tipado j
LEFT JOIN bronze.sistemas s
       ON j.sistema = s.sistema
WHERE j.status <> 'Cancelado';   -- cancelado não é demanda real de sustentação


CREATE OR REPLACE TABLE silver.alertas AS
SELECT
    a.alerta_id,
    a.sistema,
    s.area_negocio,
    a.severidade,
    CAST(a.disparado_em AS TIMESTAMP)                           AS disparado_em,
    CAST(date_trunc('MONTH', CAST(a.disparado_em AS TIMESTAMP)) AS DATE) AS mes_referencia,
    a.minutos_ate_tratativa,
    NULLIF(a.issue_key, '')                                     AS issue_key,
    -- 1 = alerta virou chamado no Jira / 0 = time resolveu antes do usuário perceber
    CASE WHEN NULLIF(a.issue_key, '') IS NULL THEN 0 ELSE 1 END AS virou_chamado
FROM bronze.alertas_monitoramento a
LEFT JOIN bronze.sistemas s
       ON a.sistema = s.sistema;
