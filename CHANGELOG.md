# Changelog — PIBIC: Otimização de Treliças Planas 2D
## UNESC — Programa de Iniciação Científica
### Equipe: Augusto Wanderlind · Emily (colaboradora) · Claude (assistente IA)

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).  
Versionamento: `MAJOR.MINOR.PATCH`  
— MAJOR: mudança de arquitetura ou objetivo do projeto  
— MINOR: nova funcionalidade ou módulo  
— PATCH: correção de bug ou melhoria pontual

---

## [0.9.1] — 2026-04-27

### Adicionado
- **`truss_canvas.py` — modo `'deformada'`**: nova vista de forma deformada da estrutura
  - Ghost cinza tracejado (posição original) + barras azuis sólidas (posição deformada)
  - Setas laranja tracejadas do nó original ao nó deformado (exibidas quando deslocamento é visível na escala atual)
  - Anotação no topo: `δ_max = X.XXXX mm | amplificação ×N`
  - Slider vertical `tk.Scale` embutido via `create_window()` na lateral direita do canvas (escala 1 → max(auto×5, 500))
  - Escala inicial auto-calculada: δ_max visual ≈ 15 % do vão da estrutura (legível por padrão sem ajuste manual)
  - Zero custo computacional — reutiliza os deslocamentos já calculados pelo FEA
- **`truss_gui.py` — `_show_canvas_2v(paineis)`**: layout vertical com 2 TrussCanvas empilhados (peso igual, títulos individuais)
- **`truss_gui.py` — `cmd_dimensionar()`**: passa a exibir layout 2v com **Esforços Axiais** (topo) + **Forma Deformada** (base) automaticamente após o dimensionamento

### Alterado
- Slider de amplificação: `orient='vertical'`, posicionado na lateral direita (`anchor='e'`), label compacta `'× amp.'`
- Botão `'↳ Deformada'` removido do painel esquerdo — a deformada agora aparece automaticamente no resultado do dimensionamento

---

## [0.9.0] — 2026-04-27

### Adicionado
- **`truss_canvas.py`** — novo módulo de renderização interativa (substituiu matplotlib nas vistas estruturais):
  - `TrussCanvas(tk.Canvas)` — widget com zoom (roda), pan (arrastar), tooltip por hover e popup por duplo clique (janela 1050×700 px)
  - Ícone `⤢` no canto inferior direito sinaliza o popup ao usuário
  - **Modo `croqui`**: barras coloridas por grupo de seção (`_PALETA_SECOES`, 10 cores), espessura proporcional à área; legenda lateral com swatch + valor em cm²; comprimentos de barra em label perpendicular à barra; grid X/Y (labels Y apenas no 1.º e último nível)
  - **Modo `completa`**: croqui + setas de força laranja (cauda→nó), labels em kN com anti-sobreposição perpendicular
  - **Modo `esforcos`**: barras coloridas por N axial (azul = tração / vermelho = compressão), espessura proporcional; apoios; reações verdes (cauda fora da estrutura, ponta no nó) com label bold; colorbar com gradiente + labels de valor e legenda "tração / compressão"
  - `_secoes_info()` — retorna `(unique_areas, {area → cor})` sem ambiguidade de float
  - `_draw_expand_hint()` — ícone discreto sempre visível no canto do canvas

- **`truss_gui.py`** — integração TrussCanvas e fluxo snap:
  - `_show_canvas(modo, dados, resultado)` — substitui `_show_matplotlib` nas etapas 4, 7 e 8
  - `_show_canvas_comparativo(paineis)` — grade 2×2 de TrussCanvas com título por célula; células com `weight=1` para distribuição igual de espaço
  - Botão **"✔ Aceitar e Dimensionar com Snap"** no rodapé da janela de snap discreto: executa `analise_fea` + `verificar_barras` com `dados_discretos`; fecha a janela e exibe comparativo 2×2 **Otimizado Contínuo vs Snap Discreto** (esforços + croqui de cada)
  - `_aceitar_snap(resultado_snap, win)` — handler do botão acima; resultado armazenado em `self._res_fea_snap`

### Alterado
- **Colorbar de esforços** — labels aprimorados: valor em kN bold + "tração" (itálico azul) no topo; "compressão" (itálico vermelho) + valor na base; ambos com âncora correta (`nw` / `sw`)
- **Convenção de cor confirmada**: N > 0 = tração → azul; N < 0 = compressão → vermelho (convenção NBR padrão: extensão positiva)
- **Apoios** reduzidos para `t = span × 0.025` (eram `0.05`) — não invadem a geometria
- **Reações** — seta com `arrow=tk.LAST`, cauda fora da estrutura; label posicionado na cauda com `anchor='n'`, fonte 11 pt
- **Grid Y** — labels apenas no 1.º e último nível quando há mais de 2 níveis distintos (evita aglutinação)

### Corrigido
- **`truss_engine.py`** — erro NumPy ≥ 1.25 *"only 0-dimensional arrays can be converted"*: `W = float((desloc.T @ K_orig @ desloc).item())`
- **`truss_engine.py` — `analise_fea()`** — passa a retornar chave `'reacoes'` (array `[no, Rx, Ry]`) calculada via `r_vec = np.asarray(K_orig @ desloc − F).ravel()`; permite exibição das reações no canvas sem nova chamada FEA
- **Tooltip barra** — label "Tração / Compressão" corrigido para N ≥ 0 = Tração (alinhado à convenção do engine)

### Pendências resolvidas nesta versão
- [x] ~~Gráficos interativos (canvas nativo tkinter com zoom/pan/tooltip)~~
- [x] ~~Comparativo visual inicial × otimizado com canvas~~
- [x] ~~Dimensionamento com perfis do snap discreto e comparativo visual~~

---

## [0.8.0] — 2026-04-20

### Adicionado
- **`truss_catalogo.py`** — novo módulo de catálogo e snap discreto:
  - `carregar_catalogo(caminho=None)` — carrega `catalogo_chs_vallourec.csv` e
    adiciona colunas SI (`A_m2`, `r_m`, `I_m4`); ordenado por área crescente
  - `snap_discreto(dados, grupos, param_norma, catalogo, max_iter)` — Fase A:
    mapeia cada grupo de barras ao menor perfil do catálogo com UC ≤ 1,0;
    re-executa FEA a cada avanço de perfil usando `r_cm` real do catálogo
    (não a fórmula analítica `C_r·√A`); retorna dados discretos, perfis,
    UC por barra, massa total, iterações e barras sem grupo
  - `_uc_barra()` — taxa de utilização interna com `r` do catálogo
- **`catalogo_chs_vallourec.csv`** — 142 perfis CHS Vallourec extraídos do
  catálogo PDF; separador `;`; diâmetros 33,4–355,6 mm; colunas:
  `designacao, d_mm, t_mm, m_kg_m, A_cm2, I_cm4, r_cm, W_cm3, Z_cm3, J_cm4, Wt_cm3, U_m2m`
- **`truss_input.py` — `extrair_grupos(df_barras)`** — extrai agrupamento
  `{nome_grupo: [índices_barra]}` a partir da coluna `descricao` existente
  (sem nova coluna); barras sem descrição recebem snap individual
- **`truss_gui.py`** — botão **11 Snap Discreto**: executa `extrair_grupos` +
  `snap_discreto` e abre janela com 2 abas (Perfis por Grupo / UC por Barra
  com tags verde/vermelho)
- **`truss_gui.py` — `_abrir_catalogo_perfis()`** — Toplevel com Treeview dos
  142 perfis, filtrável por diâmetro via Combobox
- **`truss_gui.py`** — botão **Ver Catálogo de Perfis** no cabeçalho da aba
  Seções (canto direito), via parâmetro `btn_top_extra` em `_show_two_sheets()`

### Alterado
- **`truss_input.py`** — unidades do usuário trocadas de m²/Pa para **cm²/GPa**:
  - `dataframes_vazios()`: colunas `area_m2 → area_cm2`, `E_Pa → E_GPa`
  - `dataframes_para_trelica()`: converte internamente `area_cm2 × 1e-4 → m²`
    e `E_GPa × 1e9 → Pa` antes de passar ao engine
  - `exemplo_rev02()`: valores de seção atualizados (`0.000115 m² → 1.15 cm²`,
    `200e9 Pa → 200.0 GPa`)
- **`truss_gui.py`** — título da aba Seções, colunas de `salvar_secoes()` e
  texto de ajuda atualizados para `area_cm2 / E_GPa`
- **`truss_gui.py` — `cmd_abrir_projeto()`** — migração de compatibilidade:
  arquivos `.trelica` antigos com `area_m2`/`E_Pa` são convertidos
  automaticamente para `area_cm2`/`E_GPa` ao carregar

### Organização
- Todos os arquivos do app consolidados em `TRELICA_APP/`; cópias soltas
  `truss_catalogo.py`, `truss_gui.py`, `truss_input.py` removidas de `02.CODIGOS`

---

## [0.7.3] — 2026-04-19

### Corrigido
- **`truss_gui.py`** — barra de status sumia após dimensionar:
  `_frm_status` agora é packed ANTES de `root` (lado bottom deve ser reservado
  antes do frame com `expand=True` absorver o espaço restante)

### Alterado
- **`truss_gui.py`** — painel esquerdo alargado: `width=230 → 280`, `_BTN_W=28 → 32`
- **`truss_gui.py`** — log de otimização: fundo claro (`#f5f5f5`) em vez de terminal escuro

### Adicionado
- **`truss_gui.py`** — botão **10  Resultados**: reabre a janela de log/CSV da última
  otimização sem precisar re-executar; armazena `_dados_otim_ini` como referência

---

## [0.7.2] — 2026-04-19

### Corrigido
- **`truss_gui.py`** — TclError `invalid command name .!progressbar`:
  - `frm_status` agora salvo como `self._frm_status` (evita GC prematuro)
  - `_progress_stop()` com guard `winfo_exists()` + try/except

### Adicionado
- **`truss_engine.py` — `otimizar()`**: parâmetro `callback_iter(n, vol_m3, compliance)`
  chamado ao final de cada iteração SLSQP
- **`truss_gui.py`** — painel de log no painel esquerdo (abaixo dos botões):
  - `tk.Text` estilo terminal (fundo escuro) com 8 linhas
  - Exibe: "▶ Otimizador iniciado", nº de barras, volume inicial, separador
  - Atualiza a cada iteração: `Iter N | Vol X cm³ | C Y`
  - Ao final: "✓ Concluído" ou "~ Concluído (⚠ msg scipy)"
  - Métodos `_log_append()` e `_log_clear()`
- **`truss_gui.py`** — barra de status inferior atualizada a cada iteração:
  "Otimizando — iteração N | Volume: X cm³"

---

## [0.7.1] — 2026-04-19

### Adicionado
- **`truss_gui.py`** — botão 9 Otimizar agora roda em thread separada:
  - `ttk.Progressbar` indeterminado aparece na barra de status durante o cálculo
  - GUI permanece responsiva enquanto o SLSQP roda em background
  - Métodos auxiliares `_progress_start()`, `_progress_stop()`, `_otim_concluido()`, `_otim_erro()`
- **`truss_gui.py` — Log da Otimização**:
  - Botão **Exportar Iterações (CSV)** — salva iter, volume_cm³, compliance_J, var_vol_%
  - Botão **Exportar Áreas (CSV)** — salva barra, área_ini, área_oti, variação_%

### Alterado
- Barra de status refeita como `ttk.Frame` para acomodar label + progressbar lado a lado

---

## [0.7.0] — 2026-04-19

### Corrigido
- **`truss_gui.py` — botão 9 Otimizar Estrutura**:
  - Formulação corrigida: `objetivo='volume'` + `usar_restricoes_norma=True`
    (restrições UC ≤ 1,0 por barra — NBR 8800/16239)
  - Removida restrição `restricao_volume_max` (redundante ao minimizar volume
    e impedia convergência com restrições estruturais)
  - Messagebox reescrito: exibe volume inicial/otimizado/variação (%) e massa
    estimada (kg), além de compliance e status de convergência
  - Barra de status atualizada com métricas de volume
  - Texto de ajuda corrigido: "minimiza volume de aço (UC ≤ 1,0, NBR 8800)"
  - Relatório PDF: título da página 4 alterado para mostrar variação de volume

### Adicionado
- **`truss_engine.py` — `otimizar()`**:
  - Callback por iteração: captura volume, compliance e f_obj a cada passo
  - Retorna chave `'historico'` (lista de dicts com iter/volume_m3/compliance/f_obj)
  - Tolerância e maxiter explícitos: `options={'ftol': 1e-9, 'maxiter': 500}`
- **`truss_gui.py` — `_mostrar_log_otimizacao()`**:
  - Janela Toplevel com 2 abas: *Iterações* (tabela iter × volume × compliance × Δvol%)
    e *Áreas por Barra* (tabela comparativa área inicial × otimizada × variação%)

---

## [0.6.0] — 2026-03-31

### Adicionado
- **`truss_gui.py`** — botão **Configurações** (janela modal com 3 abas):
  - *Norma*: dropdown de normas aplicáveis (NBR 8800:2024 + NBR 16239:2013);
    curva de flambagem a/b/c/d; coeficientes γa1, γa2, k_flambagem
  - *Material*: fy, fu, E com presets para A36, A572 Gr.50 e API 5L X52
  - *Seção*: tipo CHS / SHS / sólida circular; relação β = t/D
  - Valores aplicados são persistidos em `self._param_norma` (ParamNorma)

### Alterado
- **`truss_gui.py` — botão 8 Dimensionar Estrutura**:
  - Executa `verificar_barras()` após FEA usando `self._param_norma`
  - Figura expandida para 3 painéis: croqui · esforços axiais · UC por barra
  - Gráfico de barras com código de cores: verde (<0,8) · laranja (0,8–1,0) · vermelho (>1,0)
  - Messagebox exibe: UC global, barras reprovadas, parâmetros da norma e alertas de esbeltez
  - Resultado `norma` armazenado em `self.resultado_inicial['norma']`

### Resolvido
- Pendência "Integrar `truss_norma` no botão Dimensionar Estrutura" — concluído

---

## [0.5.0] — 2026-03-31

### Adicionado
- **`truss_norma.py`** — módulo independente de verificação normativa:
  - `ParamNorma` (dataclass): parâmetros de material, seção e coeficientes  
    (fy, fu, E, γa1, γa2, k_flambagem, curva de flambagem, tipo_secao, β_t/D)
  - `Nt_Rd()` — resistência à tração: `Ag·fy / γa1`  
    (NBR 8800:2024 Seção 5.2, Eq. 5.1a)
  - `Nc_Rd()` — resistência à compressão com flambagem global: `χ·Ag·fy / γa1`  
    (NBR 8800:2024 Seção 5.3, Eq. 5.7–5.9 + NBR 16239:2013)
  - Curvas de flambagem a/b/c/d com fator de imperfeição europeu (Tabela 5.1)
  - `C_r` analítico para CHS, SHS e barra sólida circular (`r = C_r·√A`)
  - `verificar_barras()` — UC por barra + alertas kL/r > 200
  - `constraints_norma()` — gera lista de constraints scipy para o otimizador
- **`requirements.json`** — manifesto de dependências do projeto com versões mínimas
- **`truss_gui.py`** — verificação automática de dependências no startup:
  - Lê `requirements.json` antes de qualquer import externo
  - Dialog tkinter pergunta se deseja instalar pacotes ausentes via pip
  - `sys.exit(1)` se instalação cancelada ou falhou

### Alterado
- **`truss_engine.py`** — motor de otimização atualizado:
  - `ConfigOtimizacao.objetivo`: `'volume'` (padrão) ou `'compliance'`
  - `ConfigOtimizacao.usar_restricoes_norma`: ativa constraints NBR por barra
  - `ConfigOtimizacao.param_norma`: injeta `ParamNorma` personalizado
  - `otimizar()` retorna chave `'norma'` com verificação quando ativado
  - Import de `truss_norma` adicionado

---

## [0.4.0] — 2026-03-31

### Adicionado
- **`truss_gui.py`** — botão **Ajuda** com janela `Toplevel` e 3 abas:
  - *Fluxo de Trabalho*: passos ①–⑨ explicados para usuário leigo
  - *Seções Transversais*: conversão de unidades e orientações
  - *Salvar / Abrir*: descrição de cada função de arquivo
- **`truss_gui.py`** — salvar/abrir projeto em formato `.trelica` (JSON):
  - `cmd_salvar_projeto()` — serializa os 5 DataFrames
  - `cmd_abrir_projeto()` — desserializa e atualiza indicadores ○/✓
- **`truss_gui.py`** — geração de relatório PDF (`cmd_gerar_relatorio()`):
  - Pág. 1: tabelas de nós, barras, seções, apoios e forças
  - Pág. 2: croqui geométrico + estrutura completa com cargas
  - Pág. 3: diagrama de esforços axiais + tabela N por barra (se dimensionado)
  - Pág. 4: comparativo inicial × otimizado (se otimização executada)
- **`tesoura_PIBIC.trelica`** — arquivo de projeto pré-configurado com a treliça
  do artigo PIBIC (22 nós, 41 barras, dados iniciais do notebook REV04)

### Alterado
- **Botão 4 — Visualizar Croqui**: exibe somente geometria (`mostrar_forcas=False`)
- **`truss_engine.py` — símbolos de apoio** redesenhados:
  - Pino (rx+ry): triângulo + linha de base + hachura de solo
  - Rolete Y (só ry): triângulo ↓ + linha de contato + 3 rodinhas + solo
  - Rolete X (só rx): triângulo ← + linha de contato + 3 rodinhas + parede

---

## [0.3.0] — 2026-03-31

### Adicionado
- **`truss_gui.py`** — interface tkinter completa com 9 etapas:
  1. Inserir Coordenadas (tksheet editável)
  2. Inserir Barras + Seções (dois sheets empilhados)
  3. Informar Apoios
  4. Visualizar Croqui
  5. Verificar Estaticidade (`m + r = 2n`)
  6. Inserir Carregamento distribuído (conversão automática para forças nodais)
  7. Visualizar Estrutura Completa
  8. Dimensionar Estrutura (FEA + benchmark)
  9. Otimizar Estrutura (SLSQP)
- Indicadores de etapa ○ / ✓ na área de botões
- Barra de status descritiva
- Distribuição automática de carga: q (N/m) → forças nodais por comprimento tributário
- `cmd_verificar_estaticidade()`: isostática / lábil / hiperestática com grau

### Adicionado
- **`truss_input.py`** — camada de conversão DataFrame → TrelicaInput:
  - `dataframes_vazios()` — retorna os 5 DataFrames com colunas corretas
  - `dataframes_para_trelica()` — valida e converte para `TrelicaInput`

---

## [0.2.0] — 2026-03-31

### Adicionado
- **`truss_engine.py`** — motor genérico de análise e otimização:
  - `TrelicaInput` (dataclass): nós, conectividade, áreas, E, forças, apoios
  - `analise_fea()` — MEF para treliças planas 2D; retorna compliance, volume,
    deslocamentos e forças internas
  - `plotar_trelica()` — visualização matplotlib com:
    - Colormap de esforços axiais (azul = tração, vermelho = compressão)
    - Símbolos de apoio, setas de força, numeração de nós e elementos
    - Marcações de coordenadas X no eixo e labels `y=valor` ao lado dos nós
  - `ConfigOtimizacao` (dataclass): bounds, restrições de volume, método
  - `otimizar()` — wrapper scipy.optimize.minimize (SLSQP)
  - `TrelicaInput.volume_total()`, `.copia_com_areas()`, `.copia_com_nos()`

---

## [0.1.0] — 2026-03-31 *(baseline — backup 2026.03.31)*

### Estado inicial (notebooks REV01 e REV02)
- `PIBIC_TRELICA_REV01.ipynb` — implementação inicial da análise FEA hardcoded
- `PIBIC_TRELICA_REV02.ipynb` — expansão das variáveis de projeto (7 variáveis);
  bug conhecido: `bounds` com 4 elementos vs. `x0` com 7 (Emily responsável)
- Treliça: 22 nós, 41 barras (Pratt inclinada), vão 12,5 m, banzo inclinado 5 %
- Otimização: compliance como objetivo (a ser trocado para volume)
- Restrições: placeholder `tensoes` sem implementação (a ser feito)

---

## Pendências conhecidas / próximas versões

- [ ] **Tooltip na deformada**: no modo `'deformada'`, o hit-test deve checar contra as posições **deformadas** dos nós (atualmente checa a posição original); ao hover exibir: nó, δx, δy (mm) e δ_total = √(δx²+δy²) mm; implementação: `_hit_test()` recebe `nos_def` quando modo é `'deformada'`
- [ ] Validar cálculos do `truss_norma.py` contra exemplos manuais da NBR (notebook `VALIDACAO_truss_norma.ipynb` criado — aguarda execução)
- [ ] Implementar restrição de deslocamento nodal máximo no otimizador SLSQP
- [ ] Interface gráfica de lançamento clicável (click-to-connect nas coordenadas)
- [ ] **Snap Fase B**: otimização geométrica (nós) + snap discreto em loop iterativo — refinamento combinado geometria × perfis de catálogo *(Fase A — snap de áreas contínuas → perfis discretos — já implementada em v0.8–0.9)*
  > **Roteiro de implementação:**
  > 1. Ponto de partida: `dados_snap` (TrelicaInput com áreas discretas da Fase A)
  > 2. **Loop até convergência** (critério: variação de volume < ε entre iterações):
  >    - a. Otimização geométrica — SLSQP com `otimizar_geometria=True`, áreas fixas nos valores discretos atuais; variáveis = coordenadas X/Y dos nós internos; restrições UC ≤ 1,0 (`ConfigOtimizacao.usar_restricoes_norma=True`)
  >    - b. Snap discreto — com a nova geometria, re-executa Fase A para cada grupo: re-calcula comprimentos de flambagem e re-seleciona o menor perfil CHS com UC ≤ 1,0
  >    - c. Verifica convergência — se os perfis não mudaram E o volume variou < ε → encerra
  > 3. Saída: TrelicaInput com geometria otimizada **e** áreas discretas do catálogo
  > **Desafios principais:** acoplamento não-suave entre geometria e perfis (mudança de perfil é um salto discreto); o SLSQP pode oscilar se o snap trocar perfis a cada iteração — avaliar uso de relaxação ou limite de avanço de perfil por iteração.
- [ ] Versão Streamlit (secundário)
- [x] ~~Corrigir bug REV02: `bounds` (4 vars) incompatível com `x0` (7 vars)~~ — superado pela migração para TRELICA_APP *(app usa variáveis corretas desde v0.3.0)*
- [x] ~~Gráficos interativos~~ — implementado via **TrussCanvas** (tkinter nativo) com zoom, pan, tooltip e popup; abordagem `mpl_connect` descartada em favor do canvas *(v0.9.0)*
- [x] ~~Integrar `truss_norma` no botão "Dimensionar Estrutura" da GUI~~ *(v0.6.0)*
- [x] ~~Catálogo de perfis CHS + snap discreto pós-otimização (Fase A)~~ *(v0.8.0)*
- [x] ~~Unidades de entrada cm²/GPa com conversão interna~~ *(v0.8.0)*
- [x] ~~Dimensionamento com perfis do snap + comparativo visual Otimizado × Snap~~ *(v0.9.0)*

---

*Atualizado em 2026-04-27.*
