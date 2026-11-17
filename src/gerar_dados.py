"""
gerar_dados.py
--------------
Gera os dados FICTÍCIOS usados no case (nenhum dado real de empresa).

Simula 3 fontes diferentes, como acontece num ambiente bancário de verdade:
  1. data/raw/jira_issues.csv          -> export do Jira (projeto de sustentação)
  2. data/raw/alertas_monitoramento.csv -> alertas da ferramenta de observabilidade
  3. data/raw/sistemas.json             -> cadastro de sistemas / squads (CMDB)

História que os dados contam (ano de 2025):
  - Jan a Mar: time afogado em chamados (~420/mês), metade era pedido de
    extração/relatório manual e dúvida sobre dado.
  - Abr (Fase 1): publicação dos dashboards self-service + dicionário de métricas.
    Pedidos de extração e dúvidas despencam.
  - Jun (Fase 2): análise de Pareto dos incidentes recorrentes -> correção da causa raiz.
  - Jul (Fase 3): alertas proativos de monitoramento ligados ao painel.
  - Out a Dez: ~75 chamados/mês -> redução de ~82%.

Rode:  python src/gerar_dados.py
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42  # semente fixa: qualquer pessoa que rodar gera exatamente os mesmos dados
random.seed(SEED)
rng = np.random.default_rng(SEED)

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# 1) Cadastro de sistemas (fonte 3) - pequeno, por isso em JSON
# ---------------------------------------------------------------------------
SISTEMAS = [
    {"sistema": "Marketplace", "area_negocio": "Canais Digitais", "squad": "Squad Shopping", "criticidade": "Alta"},
    {"sistema": "Pagamentos PIX", "area_negocio": "Pagamentos", "squad": "Squad Pagamentos", "criticidade": "Alta"},
    {"sistema": "Cartões", "area_negocio": "Cartões", "squad": "Squad Cartões", "criticidade": "Alta"},
    {"sistema": "Crédito Pessoal", "area_negocio": "Crédito", "squad": "Squad Crédito", "criticidade": "Alta"},
    {"sistema": "Programa de Fidelidade", "area_negocio": "Relacionamento", "squad": "Squad Fidelidade", "criticidade": "Média"},
    {"sistema": "App Mobile", "area_negocio": "Canais Digitais", "squad": "Squad App", "criticidade": "Alta"},
    {"sistema": "Portal de Relatórios", "area_negocio": "Dados", "squad": "Squad Dados", "criticidade": "Média"},
]
NOMES_SISTEMAS = [s["sistema"] for s in SISTEMAS]

# ---------------------------------------------------------------------------
# 2) Regras de negócio da simulação
# ---------------------------------------------------------------------------
# Volume médio mensal de cada categoria ANTES dos dashboards (Q1/2025)
BASE_MENSAL = {
    "extracao": 190,    # "me manda a planilha de X" -> vira dashboard self-service
    "duvida": 85,       # "esse número está certo?"  -> vira dicionário de métricas
    "recorrente": 85,   # mesmo erro voltando        -> vira correção de causa raiz
    "novo": 40,         # incidente inédito          -> cai pouco (alerta antecipa)
    "melhoria": 20,     # pedido de ajuste           -> cai com backlog priorizado
}

# Multiplicador por mês (jan..dez) = efeito de cada fase do projeto
FATOR_MES = {
    "extracao":   [1, 1, 1, .60, .35, .20, .12, .07, .05, .045, .04, .04],
    "duvida":     [1, 1, 1, .80, .60, .45, .35, .30, .25, .20, .17, .16],
    "recorrente": [1, 1, 1, .97, .92, .80, .55, .35, .25, .20, .18, .17],
    "novo":       [1, 1, 1, 1, 1, 1, .90, .80, .75, .70, .70, .70],
    "melhoria":   [1, 1, 1, 1, .90, .80, .70, .60, .55, .50, .50, .50],
}

# Onde cada categoria costuma acontecer (pesos por sistema, na ordem de NOMES_SISTEMAS)
# Recorrentes concentrados em poucos sistemas -> é isso que o Pareto revela.
PESO_SISTEMA = {
    "extracao":   [3, 2, 2, 3, 3, 1, 4],
    "duvida":     [3, 2, 2, 2, 3, 1, 3],
    "recorrente": [6, 3, 1, 1, 4, 1, 1],
    "novo":       [2, 2, 2, 2, 1, 2, 1],
    "melhoria":   [2, 1, 1, 1, 2, 2, 1],
}

# Como cada categoria aparece no Jira (tipo + labels)
JIRA_TIPO = {
    "extracao": ("Solicitação", "extracao-dados;relatorio"),
    "duvida": ("Solicitação", "duvida-dados"),
    "recorrente": ("Incidente", "recorrente"),
    "novo": ("Incidente", ""),
    "melhoria": ("Melhoria", ""),
}

RESUMOS = {
    "extracao": ["Extração de vendas do {s} por período", "Relatório mensal de transações - {s}",
                 "Planilha de clientes ativos {s}", "Base de pedidos cancelados {s}"],
    "duvida": ["Divergência de valores no relatório do {s}", "Qual a regra do indicador de conversão - {s}?",
               "Número do {s} diferente do fechamento", "Dúvida sobre filtro de período - {s}"],
    "recorrente": ["Timeout na integração do {s}", "Fila de processamento travada - {s}",
                   "Pontos não creditados - {s}", "Erro 500 intermitente no {s}"],
    "novo": ["Falha após deploy no {s}", "Lentidão na tela de consulta - {s}",
             "Erro de certificado na API do {s}", "Job noturno não executou - {s}"],
    "melhoria": ["Novo campo na tela do {s}", "Ajuste de mensagem de erro - {s}",
                 "Incluir filtro por agência no {s}"],
}

# Esforço médio (horas registradas no Jira) por categoria
HORAS_MEDIAS = {"extracao": 3, "duvida": 1.2, "recorrente": 4, "novo": 6, "melhoria": 8}

# Tempo de resolução (horas corridas) por prioridade, antes da melhoria
RESOLUCAO_BASE = {"Alta": 22, "Média": 60, "Baixa": 110}

PRIORIDADE = {
    "extracao": (["Média", "Baixa"], [.5, .5]),
    "duvida": (["Média", "Baixa"], [.4, .6]),
    "recorrente": (["Alta", "Média", "Baixa"], [.4, .5, .1]),
    "novo": (["Alta", "Média", "Baixa"], [.45, .45, .1]),
    "melhoria": (["Média", "Baixa"], [.3, .7]),
}

FIM_PERIODO = datetime(2025, 12, 31, 23, 59)

# ---------------------------------------------------------------------------
# 3) Geração das issues do Jira (fonte 1)
# ---------------------------------------------------------------------------
issues = []
contador = 1000
for mes in range(1, 13):
    inicio_mes = datetime(2025, mes, 1)
    dias_no_mes = (datetime(2025 + mes // 12, mes % 12 + 1, 1) - inicio_mes).days
    # depois dos dashboards o time trabalha menos "apagando incêndio" -> resolve mais rápido
    fator_mttr = 1.0 if mes <= 3 else max(0.55, 1 - 0.06 * (mes - 3))

    for cat, base in BASE_MENSAL.items():
        qtd = rng.poisson(base * FATOR_MES[cat][mes - 1])
        for _ in range(qtd):
            contador += 1
            criado = inicio_mes + timedelta(days=int(rng.integers(0, dias_no_mes)),
                                            hours=int(rng.integers(8, 19)),
                                            minutes=int(rng.integers(0, 60)))
            prio = rng.choice(PRIORIDADE[cat][0], p=PRIORIDADE[cat][1])
            horas_resol = rng.gamma(2.0, RESOLUCAO_BASE[prio] / 2.0) * fator_mttr
            resolvido = criado + timedelta(hours=float(horas_resol))
            sistema = rng.choice(NOMES_SISTEMAS, p=np.array(PESO_SISTEMA[cat]) / sum(PESO_SISTEMA[cat]))

            status = "Concluído"
            if rng.random() < 0.03:
                status = "Cancelado"
            if resolvido > FIM_PERIODO:          # ainda aberto no dia do export
                status, resolvido = "Em andamento", None

            tipo, labels = JIRA_TIPO[cat]
            issues.append({
                "Issue key": f"SUST-{contador}",
                "Issue Type": tipo,
                "Summary": random.choice(RESUMOS[cat]).format(s=sistema),
                "Status": status,
                "Priority": prio,
                "Created": criado.strftime("%d/%m/%Y %H:%M"),       # formato BR, como no export
                "Resolved": resolvido.strftime("%d/%m/%Y %H:%M") if resolvido else "",
                # ~4% sem componente preenchido: problema de qualidade tratado na camada silver
                "Component/s": "" if rng.random() < 0.04 else sistema,
                "Labels": labels,
                "Time Spent": int(rng.gamma(2.0, HORAS_MEDIAS[cat] / 2.0) * 3600),  # Jira grava em segundos
            })

df_jira = pd.DataFrame(issues)
# Simula um problema comum de export: linhas duplicadas (tratado na silver)
df_jira = pd.concat([df_jira, df_jira.sample(25, random_state=SEED)]).sort_values("Issue key")
df_jira.to_csv(RAW / "jira_issues.csv", index=False, encoding="utf-8")

# ---------------------------------------------------------------------------
# 4) Alertas de monitoramento (fonte 2) - existem a partir de jul/2025 (Fase 3)
#    Cada alerta tratado a tempo = um incidente que NÃO virou chamado.
# ---------------------------------------------------------------------------
incidentes = df_jira[df_jira["Issue Type"] == "Incidente"].drop_duplicates("Issue key")
alertas = []
id_alerta = 1
for mes in range(7, 13):
    # % de alertas que acabam virando chamado cai conforme o time aprende a agir antes
    pct_vira_chamado = [0.40, 0.32, 0.25, 0.20, 0.17, 0.15][mes - 7]
    for _ in range(int(rng.integers(45, 60))):
        sistema = rng.choice(NOMES_SISTEMAS)
        disparo = datetime(2025, mes, int(rng.integers(1, 28)), int(rng.integers(0, 24)), int(rng.integers(0, 60)))
        chamado = ""
        if rng.random() < pct_vira_chamado:
            candidatos = incidentes[(incidentes["Component/s"] == sistema) &
                                    (incidentes["Created"].str[3:5] == f"{mes:02d}")]
            if len(candidatos):
                chamado = candidatos.sample(1, random_state=int(rng.integers(0, 10_000)))["Issue key"].iloc[0]
        alertas.append({
            "alerta_id": f"ALR-{id_alerta:05d}",
            "sistema": sistema,
            "severidade": rng.choice(["critical", "warning"], p=[.3, .7]),
            "disparado_em": disparo.isoformat(sep=" "),
            "minutos_ate_tratativa": int(rng.gamma(2, 12)),
            "issue_key": chamado,  # vazio = resolvido antes de virar chamado
        })
        id_alerta += 1

pd.DataFrame(alertas).to_csv(RAW / "alertas_monitoramento.csv", index=False, encoding="utf-8")
(RAW / "sistemas.json").write_text(json.dumps(SISTEMAS, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"jira_issues.csv: {len(df_jira)} linhas | alertas: {len(alertas)} | sistemas: {len(SISTEMAS)}")
