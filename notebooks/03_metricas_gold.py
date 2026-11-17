# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Métricas e indicadores (camada Gold)
# MAGIC
# MAGIC Executa `sql/03_gold.sql` e gera as tabelas que o dashboard consome.
# MAGIC Cada tabela responde **uma** pergunta de negócio:
# MAGIC
# MAGIC | Tabela | Pergunta |
# MAGIC |---|---|
# MAGIC | `gold.chamados_mensal` | Como o volume evoluiu mês a mês, por categoria? |
# MAGIC | `gold.kpis_antes_depois` | Quanto melhorou do Q1 para o Q4? |
# MAGIC | `gold.pareto_recorrentes` | Onde estão os incidentes que se repetem? |
# MAGIC | `gold.alertas_mensal` | Quantos problemas o monitoramento evitou? |

# COMMAND ----------

spark.sql("USE CATALOG sustentacao")

def executar_arquivo_sql(caminho):
    """Mesmo helper do notebook 02."""
    with open(caminho, encoding="utf-8") as f:
        comandos = [c for c in f.read().split(";") if c.strip() and not all(
            l.strip().startswith("--") or not l.strip() for l in c.splitlines())]
    for comando in comandos:
        spark.sql(comando)
    print(f"{len(comandos)} comandos executados de {caminho}")

executar_arquivo_sql("../sql/03_gold.sql")

# COMMAND ----------

# MAGIC %md
# MAGIC ### O resultado em uma tabela

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT * FROM gold.kpis_antes_depois ORDER BY periodo

# COMMAND ----------

kpi = {r["periodo"]: r for r in spark.table("gold.kpis_antes_depois").collect()}
antes, depois = kpi["Antes (Q1/2025)"], kpi["Depois (Q4/2025)"]

reducao = 100 * (1 - depois["chamados_mes"] / antes["chamados_mes"])
horas_liberadas = antes["horas_mes"] - depois["horas_mes"]

print(f"Chamados/mês: {antes['chamados_mes']:.0f} -> {depois['chamados_mes']:.0f}  (-{reducao:.0f}%)")
print(f"Horas de sustentação liberadas por mês: {horas_liberadas:.0f} h (~{horas_liberadas/160:.1f} pessoas em tempo integral)")
print(f"MTTR: {antes['mttr_horas']} h -> {depois['mttr_horas']} h | SLA: {antes['pct_dentro_sla']}% -> {depois['pct_dentro_sla']}%")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Pareto: onde atacar a causa raiz
# MAGIC Poucos sistemas concentravam a maioria dos incidentes recorrentes.
# MAGIC Foi essa visão que priorizou o backlog de correções com os POs.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT sistema, squad, qtd_antes, qtd_depois, pct_acumulado
# MAGIC FROM gold.pareto_recorrentes
# MAGIC ORDER BY qtd_antes DESC

# COMMAND ----------

# MAGIC %md
# MAGIC ### Próximo passo
# MAGIC As tabelas `gold.*` ficam disponíveis no **SQL Warehouse**. Dali:
# MAGIC - **Databricks SQL Dashboard** com as consultas de `sql/04_consultas_dashboard.sql`
# MAGIC - **Power BI** (conector Azure Databricks), **QuickSight** ou **Tableau** apontando para o mesmo warehouse
# MAGIC - Este notebook pode ser agendado como **Job** diário (01 → 02 → 03)
