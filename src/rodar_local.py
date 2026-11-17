"""
rodar_local.py
--------------
Roda o pipeline inteiro na sua máquina, SEM precisar de Databricks.

Por quê? Para qualquer pessoa clonar o repositório e ver o resultado em 1 minuto.
Os arquivos SQL em /sql são escritos em Databricks SQL (a fonte da verdade).
Aqui eu uso o DuckDB (um "mini Databricks" local) e traduzo só 2 funções
que têm nome diferente entre os dois motores.

Fluxo:  data/raw  ->  bronze  ->  silver  ->  gold  ->  data/gold/*.csv  ->  dashboard/index.html

Rode:  python src/rodar_local.py
"""

import json
import re
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
RAW = RAIZ / "data" / "raw"
GOLD_CSV = RAIZ / "data" / "gold"
SQL = RAIZ / "sql"
DASH = RAIZ / "dashboard"

# Mesmo "de-para" de colunas feito no notebook 01 (Delta não aceita espaço e "/" no nome)
RENOMEAR_JIRA = {
    "Issue key": "issue_key", "Issue Type": "issue_type", "Summary": "summary",
    "Status": "status", "Priority": "priority", "Created": "created",
    "Resolved": "resolved", "Component/s": "components", "Labels": "labels",
    "Time Spent": "time_spent",
}


def traduzir_para_duckdb(sql: str) -> str:
    """Databricks SQL -> DuckDB. Só o necessário, nada de mágica."""
    # to_timestamp(col, 'dd/MM/yyyy HH:mm')  ->  strptime(col, '%d/%m/%Y %H:%M')
    sql = re.sub(r"to_timestamp\((.+?), 'dd/MM/yyyy HH:mm'\)", r"strptime(\1, '%d/%m/%Y %H:%M')", sql)
    # unix_timestamp(ts)  ->  epoch(ts)
    sql = sql.replace("unix_timestamp(", "epoch(")
    return sql


def executar_arquivo_sql(con, arquivo: Path):
    """Executa um .sql com vários comandos separados por ';' (igual ao helper do notebook)."""
    texto = traduzir_para_duckdb(arquivo.read_text(encoding="utf-8"))
    for comando in texto.split(";"):
        # ignora pedaços que só têm comentário ou espaço
        if re.sub(r"--.*", "", comando).strip():
            con.execute(comando)
    print(f"  ok  {arquivo.name}")


def main():
    con = duckdb.connect()  # banco em memória: nada para limpar depois

    # ------------------------------------------------------------------ BRONZE
    # Dado bruto, sem regra de negócio. Só padronizo nome de coluna e marco a origem.
    print("BRONZE")
    agora = datetime.now()
    jira = pd.read_csv(RAW / "jira_issues.csv", dtype=str, keep_default_na=False).rename(columns=RENOMEAR_JIRA)
    alertas = pd.read_csv(RAW / "alertas_monitoramento.csv", dtype={"issue_key": str}, keep_default_na=False)
    sistemas = pd.DataFrame(json.loads((RAW / "sistemas.json").read_text(encoding="utf-8")))
    for nome, df in {"jira_issues": jira, "alertas_monitoramento": alertas, "sistemas": sistemas}.items():
        df["_data_ingestao"] = agora
        df["_arquivo_origem"] = nome
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    con.execute("CREATE TABLE bronze.jira_issues AS SELECT * FROM jira")
    con.execute("CREATE TABLE bronze.alertas_monitoramento AS SELECT * FROM alertas")
    con.execute("CREATE TABLE bronze.sistemas AS SELECT * FROM sistemas")
    print(f"  ok  {len(jira)} issues | {len(alertas)} alertas | {len(sistemas)} sistemas")

    # ------------------------------------------------------------ SILVER/GOLD
    print("SILVER / GOLD")
    executar_arquivo_sql(con, SQL / "02_silver.sql")
    executar_arquivo_sql(con, SQL / "03_gold.sql")

    # ---------------------------------------------------- CHECAGENS DE QUALIDADE
    # Se alguma falhar, o pipeline para: dashboard com número errado é pior que dashboard nenhum.
    dup = con.execute("SELECT COUNT(*) - COUNT(DISTINCT issue_key) FROM silver.chamados").fetchone()[0]
    assert dup == 0, "silver.chamados tem issue duplicada"
    sem_data = con.execute("SELECT COUNT(*) FROM silver.chamados WHERE criado_em IS NULL").fetchone()[0]
    assert sem_data == 0, "existe chamado sem data de criação"
    print("  ok  checagens de qualidade")

    # -------------------------------------------- EXPORTA GOLD (Power BI/Tableau)
    GOLD_CSV.mkdir(parents=True, exist_ok=True)
    tabelas = ["chamados_mensal", "kpis_antes_depois", "pareto_recorrentes", "alertas_mensal"]
    dados = {}
    for t in tabelas:
        df = con.execute(f"SELECT * FROM gold.{t}").df()
        df.to_csv(GOLD_CSV / f"{t}.csv", index=False)
        # datas viram texto 'YYYY-MM' para o JavaScript do dashboard
        if "mes_referencia" in df:
            df["mes_referencia"] = pd.to_datetime(df["mes_referencia"]).dt.strftime("%Y-%m")
            df = df.sort_values("mes_referencia")
        dados[t] = df.to_dict(orient="records")

    # --------------------------------------------------------------- DASHBOARD
    # O template HTML tem um marcador; troco pelo JSON da gold. Resultado: 1 arquivo, abre offline.
    template = (DASH / "template.html").read_text(encoding="utf-8")
    html = template.replace("/*__DADOS_GOLD__*/{}", json.dumps(dados, ensure_ascii=False))
    (DASH / "index.html").write_text(html, encoding="utf-8")

    kpi = {r["periodo"]: r for r in dados["kpis_antes_depois"]}
    antes, depois = kpi["Antes (Q1/2025)"], kpi["Depois (Q4/2025)"]
    reducao = 100 * (1 - depois["chamados_mes"] / antes["chamados_mes"])
    print(f"\nChamados/mês: {antes['chamados_mes']:.0f} -> {depois['chamados_mes']:.0f}  (redução de {reducao:.0f}%)")
    print(f"Dashboard gerado em {DASH / 'index.html'}")


if __name__ == "__main__":
    main()
