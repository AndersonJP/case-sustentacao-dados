# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Tratamento e integração (camada Silver)
# MAGIC
# MAGIC Executa `sql/02_silver.sql`. O SQL fica num arquivo separado para ser
# MAGIC **a mesma fonte da verdade** aqui no Databricks e no `src/rodar_local.py`.
# MAGIC
# MAGIC O que esta etapa resolve:
# MAGIC 1. Duplicadas do export do Jira
# MAGIC 2. Datas em texto `dd/MM/yyyy` → `timestamp`; segundos → horas
# MAGIC 3. **Categoria de negócio** de cada chamado (extração, dúvida, recorrente, novo, melhoria)
# MAGIC 4. SLA por prioridade
# MAGIC 5. Integração Jira + Alertas + Cadastro de sistemas

# COMMAND ----------

spark.sql("USE CATALOG sustentacao")

def executar_arquivo_sql(caminho):
    """Lê um .sql do repositório (Git folder) e executa cada comando separado por ';'."""
    with open(caminho, encoding="utf-8") as f:
        comandos = [c for c in f.read().split(";") if c.strip() and not all(
            l.strip().startswith("--") or not l.strip() for l in c.splitlines())]
    for comando in comandos:
        spark.sql(comando)
    print(f"{len(comandos)} comandos executados de {caminho}")

executar_arquivo_sql("../sql/02_silver.sql")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Checagens de qualidade
# MAGIC Se falhar, o job para. Dashboard com número errado é pior que dashboard nenhum.

# COMMAND ----------

chamados = spark.table("silver.chamados")
assert chamados.count() == chamados.select("issue_key").distinct().count(), "issue duplicada na silver"
assert chamados.filter("criado_em IS NULL").count() == 0, "chamado sem data de criação"
print("Qualidade ok")

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Primeira pergunta de negócio: do que é feito o volume de sustentação?
# MAGIC SELECT categoria,
# MAGIC        COUNT(*)                                            AS chamados,
# MAGIC        ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)    AS pct
# MAGIC FROM silver.chamados
# MAGIC WHERE mes_referencia < '2025-04-01'
# MAGIC GROUP BY categoria
# MAGIC ORDER BY chamados DESC
# MAGIC -- Resultado: ~65% eram extração de dados e dúvidas -> problema de ACESSO À INFORMAÇÃO, não de sistema.
