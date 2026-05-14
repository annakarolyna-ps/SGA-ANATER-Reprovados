# 🔍 SGA ANATER — Verificador Automático de Relatórios Reprovados

Automação web desenvolvida em Python para verificar execuções reprovadas no sistema SGA da ANATER, eliminando horas de trabalho manual repetitivo.

---

## 📌 Sobre o Projeto

A coordenadora do contrato precisa verificar periodicamente quais execuções de relatórios foram reprovadas pelo gestor no SGA. O processo manual exige navegar por múltiplos níveis do sistema — Painel Extensionista → Metas → Municípios → UFPAs → Execuções — clicando em cada balão vermelho para ler o motivo da reprovação.

Com 4 metas, dezenas de municípios e centenas de UFPAs, essa verificação consumia horas de trabalho a cada ciclo. Esta automação realiza o mesmo processo em minutos.

---

## ⚙️ O Que o Script Faz

O script executa automaticamente todo o fluxo de navegação no SGA:

| Etapa | Ação executada automaticamente |
|-------|-------------------------------|
| 1. Login | Autentica no SGA com CPF e senha fornecidos pelo usuário |
| 2. Navegação | Acessa o Painel Extensionista e abre as Metas Pactuadas |
| 3. Filtro | Filtra metas de Atendimento Individual de Ater |
| 4. Seleção | Usuário escolhe interativamente quais metas e cidades processar |
| 5. Municípios | Identifica todos os municípios com reprovações na meta selecionada |
| 6. UFPAs | Lista as propriedades rurais com relatórios reprovados por cidade |
| 7. Execuções | Entra em cada UFPA e localiza os registros com balão vermelho |
| 8. Motivo | Clica em cada balão e extrai o texto completo da reprovação |
| 9. Exportação | Exibe tabela no terminal e salva CSV automaticamente após cada cidade |

---

## ✨ Funcionalidades Principais

- **Menu interativo** — Escolha quais metas e cidades processar. É possível voltar ao menu a qualquer momento sem reiniciar o script.
- **Motivo completo** — Clica em cada balão vermelho e lê o texto completo do motivo de reprovação informado pelo gestor.
- **Proprietária correta** — Identifica automaticamente o responsável pela UFPA buscando quem tem 'Sim' na coluna Responsável.
- **Código da UFPA** — Extrai o código numérico da UFPA diretamente da ficha de dados do sistema.
- **CSV para Excel** — Salvo com ponto-e-vírgula (padrão Brasil). Gravado após cada cidade. Tolerante a arquivo aberto no Excel — salva com sufixo de hora se necessário.
- **Resistência a falhas** — Trata timeouts, modais abertos, menus recolhidos e lentidão do servidor.
- **Relatório final** — Ao encerrar, exibe tabela consolidada com todos os registros coletados na sessão.

---

## 📊 Dados Coletados por Execução Reprovada

| Campo | Descrição | Exemplo |
|-------|-----------|---------|
| Meta | Código da meta pactuada | 16560 |
| Cód. Execução | Identificador único da execução | 737004 |
| Cód. UFPA | Código da propriedade rural | 131567 |
| Nome UFPA | Nome da propriedade | Sítio São Miguel |
| Proprietária | Responsável (Sim na tabela de integrantes) | Maria Luiza Ribeiro |
| Data Execução | Data de execução do relatório | 11/11/2025 |
| Cidade | Município da propriedade | Cidade Ocidental |
| Motivo | Texto completo da reprovação do gestor | A data não condiz... |

---

## 📈 Análise de Execuções

### Execução — 05/05/2026

| META | QTD. REPROVADOS | TEMPO |
|------|-----------------|-------|
| 16560 | 90 | 38min 35seg |
| 16565 | 39 | 19min 19seg |
| 16558 | 9 | 4min 24seg |
| 16751 | 13 | 6min 43seg |
| **Total** | **151** | **68min 21seg** |

### Execução — 06/05/2026

| META | QTD. REPROVADOS | TEMPO |
|------|-----------------|-------|
| 16560 | 91 | 40min 30seg |
| 16565 | 39 | 20min 24seg |
| 16558 | 12 | 5min 28seg |
| 16751 | 14 | 7min 29seg |
| **Total** | **156** | **73min 11seg** |

> ⚠️ O computador utilizado estava sendo usado para outras atividades durante a execução, ou seja, não estava usando seu desempenho máximo em apenas uma tarefa.

---

## 🛠️ Tecnologias Utilizadas

- Python 3.x
- [Playwright](https://playwright.dev/python/) — automação web assíncrona
- asyncio — execução assíncrona
- csv — exportação de dados

---

## 📁 Estrutura do Projeto

```
SGA-ANATER-Reprovados/
│
├── src/
│   └── sga_reprovados.py     # Script principal
└── README.md                 # Documentação
```

---

## 👩‍💻 Autora

**Anna Karolyna P. Santos**  
Graduanda em Ciência da Computação — UFU  
Estagiária no Instituto Rede Terra  

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Anna%20Santos-blue?style=flat&logo=linkedin)](https://www.linkedin.com/in/annakarolynaps)
[![GitHub](https://img.shields.io/badge/GitHub-annakarolyna--ps-black?style=flat&logo=github)](https://github.com/annakarolyna-ps)
