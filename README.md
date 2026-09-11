# TRELICA_APP

**Otimização Dimensional de Treliças Planas 2D**  
PIBIC — UNESC | Programa de Iniciação Científica

> Desenvolvido por **Gustavo Azocar** com colaboração de Emily e assistência de Claude (Anthropic).  
> Orientação: Msc. Eng Augusto Warmiling — UNESC — Engenharia Civil.

---

## Sobre o projeto

Aplicação desktop para análise, dimensionamento e otimização de treliças planas 2D,
com verificação normativa segundo a **NBR 8800:2024** e **NBR 16239:2013** (perfis CHS).

O fluxo de trabalho vai do lançamento geométrico até o snap discreto em catálogo comercial
(perfis tubulares circulares Vallourec), passando por FEA, SLSQP e verificação de UC por barra.

---

## Funcionalidades

| Etapa | Descrição |
|-------|-----------|
| **1. Nós** | Coordenadas X, Y em tabela editável |
| **2. Barras + Seções** | Conectividade, seções (cm² / GPa) e agrupamento por descrição |
| **3. Apoios** | Condições de contorno: pino, rolete X, rolete Y |
| **4. Croqui** | Visualização geométrica com numeração |
| **5. Estaticidade** | Verificação `m + r = 2n` (isostática / lábil / hiperestática) |
| **6. Carregamento** | Carga distribuída q (N/m) → forças nodais automáticas |
| **7. Estrutura completa** | Croqui com cargas e apoios |
| **8. Dimensionar** | FEA + UC por barra (NBR 8800 / NBR 16239) |
| **9. Otimizar** | Minimização de volume (SLSQP) com restrições UC ≤ 1,0 |
| **10. Resultados** | Reabre log e CSVs da última otimização |
| **11. Snap Discreto** | Mapeia barras otimizadas para perfis CHS do catálogo Vallourec |

**Recursos adicionais**
- Catálogo de 142 perfis CHS Vallourec (visualizável na interface, filtrável por diâmetro)
- Configurações de norma: curva de flambagem, coeficientes γ, material (A36 / A572 / API 5L)
- Exportação de relatório PDF (tabelas + gráficos)
- Salvar / abrir projetos em `.trelica` (JSON)

---

## Estrutura do repositório

```
TRELICA_APP/
├── truss_engine.py          # Motor FEA + otimizador SLSQP
├── truss_norma.py           # Verificação NBR 8800 / NBR 16239
├── truss_input.py           # Conversão DataFrame → TrelicaInput
├── truss_catalogo.py        # Catálogo CHS + snap discreto
├── truss_gui.py             # Interface gráfica tkinter
├── catalogo_chs_vallourec.csv  # 142 perfis CHS (Vallourec)
├── requirements.json        # Dependências do projeto
├── modelos/
│   └── tesoura_PIBIC.trelica   # Treliça de referência do artigo PIBIC
└── CHANGELOG.md
```

---

## Requisitos

- Python ≥ 3.10
- Dependências (instaladas automaticamente no primeiro run):

| Pacote | Versão mínima | Uso |
|--------|--------------|-----|
| numpy | 1.24 | Álgebra linear (FEA) |
| scipy | 1.10 | Otimizador SLSQP |
| matplotlib | 3.7 | Visualização gráfica |
| pandas | 2.0 | Tabelas de dados |
| tksheet | 7.0 | Tabelas editáveis na GUI |

> O app verifica as dependências no startup e oferece instalação automática via pip.

---

## Como executar

```bash
python truss_gui.py
```

Para abrir diretamente a treliça de referência do PIBIC:
**Arquivo → Abrir Projeto** → `modelos/tesoura_PIBIC.trelica`

---

## Fluxo típico

```
Nós → Barras/Seções → Apoios → Carregamento
       → Dimensionar → Otimizar → Snap Discreto → Relatório PDF
```

---

## Versionamento

Veja [CHANGELOG.md](CHANGELOG.md) para o histórico completo de versões.  
Versão atual: **v0.9.10**

---

## Licença

Uso acadêmico — PIBIC/UNESC.
