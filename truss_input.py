"""
truss_input.py
--------------
Camada de entrada de dados via pandas DataFrames.

Funções principais
------------------
    dataframes_vazios()            — retorna os 5 DataFrames com colunas corretas e sem linhas
    dataframes_para_trelica(...)   — converte DataFrames → TrelicaInput (usado pelo truss_engine)
    exemplo_rev02()                — preenche os DataFrames com a treliça do REV02 (referência)
"""

import numpy as np
import pandas as pd
from truss_engine import TrelicaInput


# ---------------------------------------------------------------------------
# 1. Templates vazios
# ---------------------------------------------------------------------------

def dataframes_vazios() -> dict:
    """
    Retorna dicionário com os 5 DataFrames de entrada, sem nenhuma linha,
    mas com os tipos de coluna já definidos.

    Chaves
    ------
    'nos'     : id_no (int), x (float), y (float)
    'barras'  : id_barra (int), no_inicio (int), no_fim (int),
                id_secao (int), descricao (str)
    'secoes'  : id_secao (int), area_cm2 (float), E_GPa (float)
    'forcas'  : id_no (int), Fx_N (float), Fy_N (float)
    'apoios'  : id_no (int), restrito_x (int), restrito_y (int)
    """
    nos = pd.DataFrame({
        'id_no': pd.Series(dtype=int),
        'x':     pd.Series(dtype=float),
        'y':     pd.Series(dtype=float),
    })

    barras = pd.DataFrame({
        'id_barra':  pd.Series(dtype=int),
        'no_inicio': pd.Series(dtype=int),
        'no_fim':    pd.Series(dtype=int),
        'id_secao':  pd.Series(dtype=int),
        'descricao': pd.Series(dtype=str),
    })

    secoes = pd.DataFrame({
        'id_secao': pd.Series(dtype=int),
        'area_cm2': pd.Series(dtype=float),
        'E_GPa':    pd.Series(dtype=float),
    })

    forcas = pd.DataFrame({
        'id_no': pd.Series(dtype=int),
        'Fx_N':  pd.Series(dtype=float),
        'Fy_N':  pd.Series(dtype=float),
    })

    apoios = pd.DataFrame({
        'id_no':      pd.Series(dtype=int),
        'restrito_x': pd.Series(dtype=int),
        'restrito_y': pd.Series(dtype=int),
    })

    return {
        'nos':    nos,
        'barras': barras,
        'secoes': secoes,
        'forcas': forcas,
        'apoios': apoios,
    }


# ---------------------------------------------------------------------------
# 2. Conversão DataFrames → TrelicaInput
# ---------------------------------------------------------------------------

def dataframes_para_trelica(
    df_nos:    pd.DataFrame,
    df_barras: pd.DataFrame,
    df_secoes: pd.DataFrame,
    df_forcas: pd.DataFrame,
    df_apoios: pd.DataFrame,
) -> TrelicaInput:
    """
    Converte os 5 DataFrames de entrada no objeto TrelicaInput aceito pelo
    truss_engine.

    Regras de mapeamento
    --------------------
    - Os nós são ordenados por 'id_no'; o índice posicional (0, 1, 2...) é
      o que o engine usa internamente.
    - As barras referenciam nós pelo 'id_no' original; a função converte para
      índice posicional automaticamente.
    - Cada barra recebe área e E da seção indicada em 'id_secao'.
    - Forças e apoios também são convertidos de 'id_no' para índice posicional.

    Parâmetros
    ----------
    df_nos    : DataFrame com colunas [id_no, x, y]
    df_barras : DataFrame com colunas [id_barra, no_inicio, no_fim, id_secao, descricao]
    df_secoes : DataFrame com colunas [id_secao, area_cm2, E_GPa]
    df_forcas : DataFrame com colunas [id_no, Fx_N, Fy_N]
    df_apoios : DataFrame com colunas [id_no, restrito_x, restrito_y]

    Retorna
    -------
    TrelicaInput
    """
    # --- Nós: ordenar e criar mapa id_no → índice posicional ---
    nos_ord = df_nos.sort_values('id_no').reset_index(drop=True)
    id_para_idx = {int(row.id_no): i for i, row in nos_ord.iterrows()}

    nos_array = nos_ord[['x', 'y']].to_numpy(dtype=float)

    # --- Seções: mapa id_secao → (area, E) — converte cm²→m² e GPa→Pa ---
    sec_map = {
        int(row.id_secao): (float(row.area_cm2) * 1e-4, float(row.E_GPa) * 1e9)
        for _, row in df_secoes.iterrows()
    }

    # --- Barras ---
    barras_ord = df_barras.sort_values('id_barra').reset_index(drop=True)

    conectividade = np.array([
        [id_para_idx[int(row.no_inicio)], id_para_idx[int(row.no_fim)]]
        for _, row in barras_ord.iterrows()
    ], dtype=int)

    areas = np.array([sec_map[int(row.id_secao)][0] for _, row in barras_ord.iterrows()], dtype=float)
    E_arr = np.array([sec_map[int(row.id_secao)][1] for _, row in barras_ord.iterrows()], dtype=float)

    # --- Forças ---
    forcas_array = np.array([
        [id_para_idx[int(row.id_no)], float(row.Fx_N), float(row.Fy_N)]
        for _, row in df_forcas.iterrows()
    ], dtype=float)

    if len(forcas_array) == 0:
        forcas_array = np.zeros((0, 3))

    # --- Apoios ---
    apoios_array = np.array([
        [id_para_idx[int(row.id_no)], int(row.restrito_x), int(row.restrito_y)]
        for _, row in df_apoios.iterrows()
    ], dtype=float)

    if len(apoios_array) == 0:
        apoios_array = np.zeros((0, 3))

    return TrelicaInput(
        nos=nos_array,
        conectividade=conectividade,
        areas=areas,
        E=E_arr,
        forcas=forcas_array,
        apoios=apoios_array,
    )


def extrair_grupos(df_barras: pd.DataFrame) -> dict:
    """
    Extrai o mapeamento grupo → [índices de barra] a partir da coluna 'descricao'.

    O valor de 'descricao' é usado como nome do grupo (ex: 'Banzo inferior',
    'Diagonal'). O índice de barra é a posição 0-based após ordenação por id_barra,
    igual ao índice interno usado pelo TrelicaInput.

    Barras com descricao vazia ou NaN recebem snap individual.

    Retorna
    -------
    dict[str, list[int]]
        Exemplo: {'Banzo inferior': [0,1,2,3], 'Diagonal': [8,9,10]}
    """
    if 'descricao' not in df_barras.columns:
        return {}

    barras_ord = df_barras.sort_values('id_barra').reset_index(drop=True)
    grupos: dict = {}
    for idx, row in barras_ord.iterrows():
        g = str(row.get('descricao', '')).strip()
        if g and g.lower() not in ('nan', 'none', ''):
            grupos.setdefault(g, []).append(int(idx))
    return grupos


# ---------------------------------------------------------------------------
# 3. Exemplo: treliça do REV02
# ---------------------------------------------------------------------------

def exemplo_rev02() -> dict:
    """
    Preenche os DataFrames com a treliça de referência usada no REV02.

    Geometria fixa (parâmetros de projeto no ponto inicial):
        inclinacao = 0.05  (m/m)
        altura_base = 1.0  m
        area_horiz  = 0.000115 m²  (banzo inf, sup e montantes)
        area_diag   = 0.000115 m²  (diagonais)
        xs livres   = [1.25, 2.5, 3.75]  m  (nós 3, 5, 7)

    Retorna
    -------
    dict com chaves 'nos', 'barras', 'secoes', 'forcas', 'apoios'
    """
    inclinacao  = 0.05
    altura_base = 1.0
    area_h      = 1.15    # cm² — banzo e montantes
    area_d      = 1.15    # cm² — diagonais
    E           = 200.0   # GPa

    # Coordenadas dos 22 nós (0–21)
    # Pares → banzo inferior (y=0); Ímpares → banzo superior (y = incl*x + h)
    xs_banzo_inf = [0.0, 1.25, 2.5, 3.75, 5.0, 6.25, 7.5, 8.75, 10.0, 11.25, 12.5]
    nos_rows = []
    for i, x_val in enumerate(xs_banzo_inf):
        id_inf = 2 * i
        id_sup = 2 * i + 1
        y_sup  = inclinacao * x_val + altura_base
        nos_rows.append({'id_no': id_inf, 'x': x_val, 'y': 0.0})
        nos_rows.append({'id_no': id_sup, 'x': x_val, 'y': y_sup})

    df_nos = pd.DataFrame(nos_rows)

    # Seções
    df_secoes = pd.DataFrame([
        {'id_secao': 0, 'area_cm2': area_h, 'E_GPa': E},   # banzo / montantes
        {'id_secao': 1, 'area_cm2': area_d, 'E_GPa': E},   # diagonais
    ])

    # Conectividade
    barras_rows = []
    bid = 0

    # Banzo inferior: pares consecutivos (0-2, 2-4, ..., 18-20)
    for i in range(10):
        barras_rows.append({
            'id_barra': bid, 'no_inicio': 2*i, 'no_fim': 2*i+2,
            'id_secao': 0, 'descricao': 'Banzo inferior'
        })
        bid += 1

    # Banzo superior: ímpares consecutivos (1-3, 3-5, ..., 19-21)
    for i in range(10):
        barras_rows.append({
            'id_barra': bid, 'no_inicio': 2*i+1, 'no_fim': 2*i+3,
            'id_secao': 0, 'descricao': 'Banzo superior'
        })
        bid += 1

    # Montantes: par ↔ ímpar no mesmo x (0-1, 2-3, ..., 20-21)
    for i in range(11):
        barras_rows.append({
            'id_barra': bid, 'no_inicio': 2*i, 'no_fim': 2*i+1,
            'id_secao': 0, 'descricao': 'Montante'
        })
        bid += 1

    # Diagonais: par_i ↔ ímpar_{i+1}  (0-3, 2-5, ..., 18-21)
    for i in range(10):
        barras_rows.append({
            'id_barra': bid, 'no_inicio': 2*i, 'no_fim': 2*i+3,
            'id_secao': 1, 'descricao': 'Diagonal'
        })
        bid += 1

    df_barras = pd.DataFrame(barras_rows)

    # Forças (valores do REV02 com parâmetros iniciais)
    df_forcas = pd.DataFrame([
        {'id_no': 1, 'Fx_N': 0.0, 'Fy_N': -37460.9375},   # nó 1
        {'id_no': 3, 'Fx_N': 0.0, 'Fy_N': -37460.9375},   # nó 3
        {'id_no': 4, 'Fx_N': 0.0, 'Fy_N': -667200.0},     # nó 4
        {'id_no': 5, 'Fx_N': 0.0, 'Fy_N': -667200.0},     # nó 5
    ])

    # Apoios
    df_apoios = pd.DataFrame([
        {'id_no':  0, 'restrito_x': 1, 'restrito_y': 1},  # pino
        {'id_no': 20, 'restrito_x': 1, 'restrito_y': 0},  # rolete x
        {'id_no': 21, 'restrito_x': 1, 'restrito_y': 0},  # rolete x
    ])

    return {
        'nos':    df_nos,
        'barras': df_barras,
        'secoes': df_secoes,
        'forcas': df_forcas,
        'apoios': df_apoios,
    }
