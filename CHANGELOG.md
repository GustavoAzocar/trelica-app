# Changelog — PIBIC: Otimização de Treliças Planas 2D
## UNESC — Programa de Iniciação Científica
### Equipe: Augusto Wanderlind · Emily (colaboradora) · Claude (assistente IA)

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).  
Versionamento: `MAJOR.MINOR.PATCH`  
— MAJOR: mudança de arquitetura ou objetivo do projeto  
— MINOR: nova funcionalidade ou módulo  
— PATCH: correção de bug ou melhoria pontual

---

## [0.9.12] — 2026-10-02

### Corrigido
- **FF (Fator de Falha) não aparecia no hover da treliça OTIMIZADA** (reportado
  por Emily e Augusto, por vídeo): no "Dimensionar" (inicial) e após "Otimizar
  Perfil Comercial" (snap), passar o mouse sobre uma barra mostra `N` e
  `FF = x.xxx ✓/✗` no tooltip. No resultado do **"9 Otimizar Estrutura"**
  (contínuo, antes do snap) só aparecia `N` — faltava a verificação normativa
  no `res_fea` montado em `_otim_concluido`.
  - Causa: `res_fea = analise_fea(dados_opt)` não chamava `verificar_barras`,
    então `TrussCanvas._hit_test` não encontrava a chave `'norma'` no
    resultado e omitia a linha de FF (ela já checava essa chave — o problema
    era a chave nunca ter sido gravada para o otimizado contínuo).
  - Correção: `_otim_concluido` agora grava
    `res_fea['norma'] = verificar_barras(dados_opt, res_fea, self._param_norma)`,
    igual já era feito em `cmd_dimensionar` e `_aceitar_snap`. Como
    `self._res_fea_otimizado` é a única fonte usada pelos painéis "Otimizado —
    Esforços" (em `_otim_concluido`, `cmd_resultados` e `_aceitar_snap`), a
    correção cobre os três lugares de uma vez.

---

## [0.9.11] — 2026-09-11

### Adicionado
- **`.trelica` passa a salvar todas as opções de ☰ Configurar Análise**, não
  só o modelo da treliça e δ_adm. Bloco `_meta` agora inclui:
  - `param_norma`: fy, fu, E, γa1, γa2, k_flambagem, curva, tipo_secao,
    beta_td, beta_td_shs (abas Norma/Material/Seção)
  - `esbeltez_ativo` / `esbeltez_max` (restrição k·L/r)
  - `geom_ativo` / `geom_nos` / `geom_delta_x` / `geom_delta_y` (aba Geometria)
  - (já existiam desde v0.9.10: `meia_trelica`, `desl_ativo`, `desl_n`)
  - `cmd_abrir_projeto` restaura tudo automaticamente; leitura tolerante a
    campos ausentes/arquivos antigos (mantém os defaults de `ParamNorma()`).
  - Objetivo: reabrir um `.trelica` reproduz fielmente o cálculo de origem,
    sem precisar reconfigurar manualmente material/norma/restrições.

---

## [0.9.10] — 2026-09-10

### Corrigido
- **Flecha admissível δ_adm calculada para meia treliça** (reportado por Emily e Augusto):
  em `cmd_otimizar`, `span` era `x_max − x_min` do modelo. Quando a treliça é
  modelada **pela metade** (simetria no centro do vão), esse valor é L/2, então
  `δ_adm = span/n` saía pela metade do correto — restrição ~2× mais rígida.
  Agora o vão de referência é sempre o **vão cheio L**: novo helper
  `_vao_referencia(dados)` retorna `2 × extensão_X` quando o modelo é meia treliça.
- **`truss_engine.py` — restrição de deslocamento passa a ser só flecha vertical**:
  `restricao_deslocamento_adm` usava `max(|u|)` sobre todos os GDL (incluindo
  deslocamento horizontal no apoio de rolete). Agora usa `max(|u_y|)` (GDL
  verticais, `u[1::2]`) — é o que a Tabela C.1 da NBR 8800 limita.
- **`truss_gui.py:963` — `NameError: n_el`** no messagebox de "Dimensionar
  Estrutura" (variável indefinida) → `dados.n_el`.
- **`truss_gui.py:1051` — `AttributeError: 'TrussApp' object has no attribute
  'root'`** em `_mostrar_ff_chart` (`tk.Toplevel(self.root)` → `tk.Toplevel(self)`).
  Esses dois últimos travavam todo o fluxo de dimensionamento/otimização.

### Adicionado
- **Seletor "Modelo da treliça" na etapa 1 (Inserir Coordenadas)**: dois
  radio-buttons — *Treliça inteira* / *Metade da treliça (simetria)* — visíveis
  no fluxo de lançamento, pois é dado de projeto que impacta o resultado.
  Persistido no `.trelica` (`_meta.meia_trelica`), junto de `desl_ativo`/`desl_n`.
- **Eco do modelo na aba Restrições** (☰ Configurar Análise): mostra em texto
  qual modelo está ativo e lembra que δ_adm é sempre referido ao vão cheio.
- **Verificação de flecha vertical na etapa 8 (Dimensionar)**: o messagebox e a
  barra de status passam a exibir `δy,máx` vs `δ_adm = L/n` (com δy/δ_adm e
  OK/EXCEDE) quando a restrição de deslocamento está ativada; caso contrário,
  informa apenas `δy,máx`.

### Alterado
- Denominador padrão de `δ_adm` passa de **L/300 → L/250** (NBR 8800 Anexo C,
  treliça de cobertura). Campo continua editável na aba Restrições.
- Aba Restrições: checkbox renomeado para "Limitar flecha vertical máxima
  (δy ≤ δ_adm)"; label do campo agora cita a referência normativa.

### Pendências resolvidas nesta versão
- [x] ~~δ_adm errado para modelos de meia treliça~~
- [x] ~~Restrição de deslocamento considerando GDL horizontais~~

---

## [0.9.9] — 2026-05-07

### Alterado (terminologia e labels da GUI)
- **UC → FF (Fator de Falha)**: renomeada a grandeza em todo o código e na interface
  - Chaves do dict de saída de `verificar_barras`: `UC_tracao/UC_compressao/UC_max/UC_global` → `FF_tracao/FF_compressao/FF_max/FF_global`
  - Função `_uc_barra` → `_ff_barra`; variável `UC_por_barra` → `FF_por_barra` em `truss_catalogo.py`
  - Método `_mostrar_uc_chart` → `_mostrar_ff_chart`; todos os labels, títulos e status bar atualizados
  - Tooltip de hover na canvas: `UC = 0.xxx` → `FF = 0.xxx`
- **Coluna FF na tabela snap**: cabeçalho `FF` → `%`; valores exibidos em porcentagem (0–100, 1 casa decimal). Ex: `0.426` → `42.6`
- **Botão "Snap Discreto"** → **"Otimizar Perfil Comercial"** (barra lateral, etapa 11)
- **Botão "Aceitar e Dimensionar com Snap"** → **"Aceitar e Dimensionar com Perfil Comercial"** (janela de resultados)
- Título da janela de resultados: `"Snap Discreto — Perfis Comerciais Selecionados"` → `"Otimizar Perfil Comercial — Perfis Selecionados"`

---

## [0.9.8] — 2026-05-07

### Adicionado
- **`truss_gui.py` — otimização de forma (shape optimization) na GUI**:
  - Nova aba "Geometria" no painel ☰ Configurar Análise
  - Checkbox "Incluir otimização de forma (mover nós)"
  - Campo para os IDs dos nós livres (separados por vírgula) + botão **Auto** (detecta automaticamente todos os nós sem apoio)
  - Campos ±ΔX e ±ΔY: limites de deslocamento de cada nó em relação à posição inicial; bounds absolutos = posição_inicial ± Δ
  - `cmd_otimizar()` constrói `nos_geometria_livre` e `bounds_nos` e passa `otimizar_geometria=True` à `ConfigOtimizacao`
  - Log da otimização exibe nós livres, ΔX/ΔY e número de variáveis (áreas + coordenadas)

### Notas técnicas
- O engine (`truss_engine.py`) já suportava `otimizar_geometria` desde a versão 0.8 — esta versão apenas expõe a funcionalidade na GUI
- `bounds_nos` é calculado em runtime (no `cmd_otimizar`) a partir das coordenadas reais do `TrelicaInput`, garantindo que os bounds acompanhem a geometria atual mesmo após carregamento de arquivo
- Usando ΔX = 0 é possível restringir nós a movimento puramente vertical (útil para nós do banzo inferior que não devem mudar de x)

### Pendências resolvidas nesta versão
- [x] ~~**Otimização de forma e topologia — GUI** (exposição do `otimizar_geometria` na GUI)~~

---

## [0.9.7] — 2026-05-03

### Adicionado
- **`truss_engine.py` — restrições de projeto configuráveis no otimizador**:
  - `ConfigOtimizacao.restricao_deslocamento_adm` (float, m): adiciona `max(|u|) ≤ δ_adm` ao SLSQP; forçar deslocamento máximo abaixo de `vão/n`
  - `ConfigOtimizacao.restricao_esbeltez_max` (float): adiciona `k·L/r ≤ λ_max` por barra; impede que o otimizador produza barras muito esbeltas
- **`truss_gui.py` — aba "Restrições" no painel de configurações** (botão ☰ Configurar Análise):
  - Checkbutton + campo "δ_adm = vão / [n]" (padrão: desativado / n = 300)
  - Checkbutton + campo "k·L/r ≤ [λ]" (padrão: desativado / λ = 200)
  - Valores persistem durante a sessão; log do otimizador exibe as restrições ativas
  - `k` e `β` utilizados: definidos nas abas Norma / Seção (reutilizam `param_norma`)

### Notas técnicas
- `restricao_esbeltez_max` aplica-se a todas as barras (conservador em relação à norma, que limita apenas compressão principal); controle fino pode ser feito ajustando o campo
- `restricao_deslocamento_adm` usa `max(|u|)` sobre todos os nós livres; para projetos onde a limitação é apenas deflexão vertical, L/300 já é referência coerente
- Restrições de esbeltez usam `raio_giracao()` da `ParamNorma` (analítico, C_r·√A); após snap discreto o `r_cm` real do catálogo é o valor preciso

### Pendências resolvidas nesta versão
- [x] ~~Restrição de deslocamento admissível (δ_adm = L/n) no otimizador~~
- [x] ~~Esbeltez máxima enforçada como constraint (antes: só alerta)~~

---

## [0.9.6] — 2026-05-03

### Adicionado
- **`truss_canvas.py` — seletor de unidade do deslocamento**: no modo `'deformada'`, um `OptionMenu` aparece no canto superior direito (acima do slider) com opções `mm` e `cm`; ao trocar, atualiza imediatamente a anotação `δ_max = X.XXXX <unidade>` e o tooltip de hover dos nós (`δx / δy / δ`)
- **`truss_gui.py` / `truss_input.py` — tabela de seções expandida**: as colunas da tabela de seções passam de 3 para 7: `id_secao | Designação | D(mm) | t(mm) | m (kg/m) | A (cm²) | E_GPa`
  - "Inserir do Catálogo": duplo-clique agora preenche todas as colunas diretamente do perfil selecionado (designação, D, t, m e A)
  - Colunas Designação, D, t e m são opcionais — linhas com apenas `id_secao`, `A` e `E` continuam válidas
  - Migração automática ao abrir: arquivos anteriores (sem as novas colunas) recebem as colunas com valores em branco/NaN sem perda de dados

### Alterado
- `truss_input.py — dataframes_vazios()`: `secoes` agora tem 7 colunas com os novos campos; `dataframes_para_trelica()` não foi alterado (usa apenas `area_cm2`/`E_GPa` para o FEA)

---

## [0.9.5] — 2026-05-03

### Adicionado
- **`truss_norma.py` — flambagem local CHS (NBR 8800:2024 Seção 5.3.4.3)**:
  - Nova função `_fator_Q_chs(D_t, fy, E) → (Q, classificacao)`: classifica a seção e retorna o fator Q
    - D/t ≤ 0,15·E/fy → `'nao_esbelta'`, Q = 1,0
    - 0,15·E/fy < D/t ≤ 0,45·E/fy → `'esbelta'`, Q = (0,038·E/fy)/(D/t) + 2/3
    - D/t > 0,45·E/fy → `'invalida'`, alerta normativo
  - `Nc_Rd` aceita novo parâmetro `Q=1.0`: interação global × local via λo_eff = λo·√Q e Nc,Rd = χ(λo_eff)·Q·Ag·fy/γa1 (equivalente EN 1993-1-1 Seção 6.3.1 para classe 4)
  - `verificar_barras`: computa D_t = 1/beta_td automaticamente; passa Q ao Nc_Rd; retorna `'Q'` (ndarray) e `'classificacao_local'` (list) no dict; emite alerta resumido quando Q < 1
  - `constraints_norma`: incorpora Q na restrição de compressão do SLSQP — otimização considera flambagem local
- **`truss_catalogo.py` — Q real por perfil no snap discreto**: `_uc_barra(... D_t=None)` aceita D/t do catálogo e aplica `_fator_Q_chs` para compressão; `snap_discreto` passa `d_mm/t_mm` do perfil selecionado — UC agora considera flambagem local com o perfil real

### Notas sobre a norma
- Seção D.2.6 (NBR 8800) **não se aplica** a CHS em compressão axial: é para chapa enrijecida/viga mista. A formulação correta é a Seção 5.3.4.3
- NBR 16239:2013 Seção 5.2 é consistente: mesma fórmula Q com curva 'a'
- Para D/t típicos de perfis estruturais CHS (10–30) com fy = 250 MPa: λr = 120 → todos não-esbeltos (Q = 1,0 em uso normal). A verificação é preventiva para projetos com paredes finas

### Pendências resolvidas nesta versão
- [x] ~~Flambagem local CHS (NBR 8800:2024 / NBR 16239:2013)~~

---

## [0.9.4] — 2026-05-02

### Adicionado
- **`truss_gui.py` — cargas concentradas nodais na etapa 6**: o painel de carregamento foi reestruturado em duas seções separadas por divisor:
  - **Carga distribuída** (topo): controles q (kN/m), direção e banzo — igual ao anterior
  - **Forças Nodais** (abaixo): `tksheet.Sheet` editável com colunas `id_no | Fx (kN) | Fy (kN)`, pré-populado com forças já salvas (N→kN); permite inserção manual de cargas concentradas por nó
  - `_merge_distribuida(df_new)`: acumula forças distribuídas calculadas nas linhas existentes por `id_no` (soma, não substitui) — permite carregamentos mistos
  - "Calcular e Adicionar à Tabela": converte carga distribuída em forças nodais e mescla na tabela; feedback na label de status
  - "Salvar Carregamento": lê a tabela inteira, converte kN→N e persiste em `self.dfs['forcas']`; único ponto de persistência
  - "+ Adicionar linha": insere linha em branco para forças concentradas adicionais

### Pendências resolvidas nesta versão
- [x] ~~Cargas concentradas nodais — input na GUI~~

---

## [0.9.3] — 2026-04-28

### Adicionado
- **`truss_canvas.py` — tooltip na deformada**: no modo `'deformada'`, `_hit_test()` agora calcula as posições amplificadas (`nos_hit = nos + esc·u`) e checa o hover contra elas; tooltip de nó exibe `δx`, `δy`, `δ = √(δx²+δy²)` em mm; tooltip de barra mantém N axial se disponível
- **`truss_gui.py` — catálogo com ordenação por coluna**: clicar em qualquer cabeçalho da Treeview ordena crescente (↑); segundo clique inverte para decrescente (↓); ordenação numérica para colunas de valor, lexicográfica para designação; filtro por diâmetro zera a ordenação
- **`truss_gui.py` — inserir perfil por duplo-clique**: botão "Inserir do Catálogo" na aba Seções abre o catálogo em modo seleção; duplo-clique numa linha insere `area_cm2` (e E = 200 GPa) na primeira linha vazia da tabela de seções, ou acrescenta ao final
  - Arquitetura: `_abrir_catalogo_perfis(on_select=None)` aceita callback; quando `None` = modo leitura (botão "Ver Catálogo"); `_inserir_perfil_na_secao(row)` é o único ponto a editar quando o campo a inserir mudar (área → espessura, designação, etc.)
  - Hint "Duplo-clique para inserir na tabela de seções" só aparece no modo seleção

### Alterado
- `_show_two_sheets`: `btn_top_extra` passa a aceitar lista de `(texto, comando)`, mantendo compatibilidade com tupla simples

### Pendências resolvidas nesta versão
- [x] ~~Tooltip na deformada (posições deformadas + δx/δy/δ_total)~~

---

## [0.9.2] — 2026-04-27

### Adicionado
- **`truss_canvas.py` — `_lookup_perfil(a_m2)`**: busca o perfil CHS Vallourec de área mais próxima no catálogo; carregamento lazy com cache por instância (zero custo em redraws subsequentes); retorna `''` se catálogo indisponível
- **Legenda de seções** — denominação CHS em **todos** os modos croqui:
  - Prioridade 1: perfil exato do snap (`perfis_snap` em `resultado`)
  - Prioridade 2: lookup por proximidade de área no catálogo Vallourec
  - Layout de duas linhas: designação bold (ex: `TC 38,1×3,6`) + `X.XX cm²` em cinza; `box_w` e `lh` se ajustam automaticamente
- **`truss_gui.py` — `_aceitar_snap()`**: adiciona `res_fea['perfis_snap']` (dict `{round(area,8): designação}`) e passa `res_fea` também no painel `'Snap Discreto — Croqui'` do comparativo

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

### GUI
- [x] ~~**Tooltip na deformada**~~ *(v0.9.3)*
- [x] ~~**Catálogo de perfis — ordenação por coluna**~~ *(v0.9.3)*
- [x] ~~**Catálogo de perfis — inserir área por clique**~~ *(v0.9.3)*
- [x] ~~**Cargas concentradas nodais — input na GUI**~~ *(v0.9.4)*
- [ ] Interface gráfica de lançamento clicável (click-to-connect nas coordenadas)
- [ ] **Tabela de seções — coluna E_GPa por perfil**: atualmente E = 200 GPa fixo ao inserir do catálogo; futuramente derivar E do material escolhido (aço carbono / alumínio) ou permitir edição direta

### Engine / Norma
- [x] ~~**Flambagem local — CHS (NBR 8800:2024 / NBR 16239:2013)**~~ *(v0.9.5)*
- [ ] **Validação normativa — comparação cruzada com artigo**: validar `truss_norma.py` (App) e o notebook da Emily (`Trelica_REV03_tubular_`) contra um mesmo exemplo de artigo; verificar N, Nc,Rd, Nt,Rd e UC por barra; confirmar alinhamento com NBR 8800:2024 (χ pela curva europeia — o notebook da Emily usa fórmula da NBR 8800:2008 revogada); observações adicionais: bug `s = dy²/L` no notebook da Emily precisa ser corrigido antes da rodada de validação; notebook `VALIDACAO_truss_norma.ipynb` criado, aguarda exemplo de artigo

### Otimizador
- [x] ~~**Otimização de forma — GUI** (aba "Geometria" com nós livres, ΔX/ΔY e botão Auto)~~ *(v0.9.8)*
- [ ] **Topologia** (avançado): remover barras com área → 0 em pós-processamento do snap
- [x] ~~**Restrição de deslocamento máximo — δ_adm = L/n**~~ *(v0.9.7 — `restricao_deslocamento_adm` em `ConfigOtimizacao`, aba "Restrições" na GUI)*
- [x] ~~**Esbeltez máxima enforçada como constraint — k·L/r ≤ λ_max**~~ *(v0.9.7 — `restricao_esbeltez_max` em `ConfigOtimizacao`)*

### Roadmaps
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

## Estratégia de Publicação (artigo científico)

*Discussão: Prof. Augusto Wanderlind (orientador PIBIC), Prof. Rafael Holdorf Lopez (orientador mestrado UFSC/CORE)*  
*Referência pesquisa: 2026-05-06*

### Lacuna identificada na literatura

Nenhum paper indexado (até mai/2026) combina otimização de treliças com NBR 8800 (qualquer versão) ou NBR 16239. A literatura internacional usa AISC 360, EN 1993, ou apenas limites de tensão/deslocamento sem norma específica. Catálogo real de fabricante (Vallourec CHS) nunca foi usado para quantificar o gap contínuo→discreto de forma rigorosa.

### Ângulos possíveis

**Ângulo 1 — Lacuna NBR (mais forte para LAJSS / Structures)**  
Primeiro otimizador dimensional + geométrico de treliças com constraints NBR 8800:2024 e NBR 16239:2013 completas: fator Q de flambagem local, curvas europeias χ (curva 'a'), δ_adm e k·L/r como constraints do SLSQP. Aplicado a perfis CHS do catálogo Vallourec.

**Ângulo 2 — SLSQP vs. metaheurística com norma completa**  
Aproveitar o debate aberto (SMO 2025): SLSQP bate metaheurísticas com menos avaliações. A novidade aqui é o conjunto de constraints normativas NBR — ninguém fez essa comparação nesse cenário. Para a metaheurística (GA/PSO), usar a técnica de variáveis mistas do Prof. Rafael (Aula 09): o algoritmo opera em espaço contínuo (0, N_cat) e internamente mapeia `x_i = Ω(ceil(x_i))` para o perfil do catálogo. SLSQP usa o snap pós-otimização. Os dois paradigmas com suas estratégias naturais de discretização.

**Ângulo 3 — Custo da discretização**  
Quantificar sistematicamente o acréscimo de peso (%) ao passar do ótimo contínuo para o perfil mais próximo do catálogo, em função da geometria da treliça (vão, altura, inclinação). Mencionado como lacuna na literatura, nunca medido com catálogo real.

**Ângulo 4 — Fator Q como constraint ativa**  
Demonstrar casos onde ignorar Q leva a ótimos não-conservadores e que incluí-lo desloca a solução para um perfil mais pesado mas normativo. Contribuição direta para as literaturas de otimização e de projeto em CHS.

**Ângulo 5 — Ferramenta open-source reprodutível**  
Documentar o TRELICA_APP como entregável do artigo. Vários papers MDPI recentes têm a ferramenta como contribuição principal; aumenta valor de citação e beneficia a comunidade latino-americana.

### Combinação recomendada

**Ângulos 1 + 3 + 4** num artigo único (target: *LAJSS* ou *Structures*, IF ~1.5–3.5):
> *"Otimização dimensional e geométrica de treliças planas em perfis CHS segundo NBR 8800:2024: flambagem local e custo da discretização para catálogo comercial"*

O Ângulo 2 (comparação com metaheurística + técnica Ω(ceil)) é o mais rico metodologicamente e conecta diretamente ao mestrado; pode entrar como extensão ou segundo artigo.

### O que ainda falta para o artigo

- [ ] **Benchmark 25-bar** (mais citado para size+shape além do 10-bar): implementar em `truss_engine` e validar
- [ ] **Experimento de discretização**: rodar contínuo + snap para N combinações de geometria e tabular Δpeso
- [ ] **Casos com Q < 1**: encontrar (ou construir) configuração onde flambagem local é ativa no ótimo
- [ ] **Caso de aplicação real**: cobertura de galpão ou passarela (mesmo simplificada) — eleva relevância prática
- [ ] **Bug save/JSON**: converter NaN → None antes de `json.dump` em `cmd_salvar_projeto` (seções com D/t/m opcional)
- [ ] **Validação cruzada com Emily**: mesmo exemplo → comparar N, Nc,Rd, Nt,Rd, UC por barra (após correção bug `dy²/L` e atualização χ NBR 2024 no notebook dela)

---

*Atualizado em 2026-05-06 (v0.9.7).*
