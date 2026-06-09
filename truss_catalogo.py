"""
truss_catalogo.py
-----------------
Catálogo de perfis comerciais e snap discreto pós-otimização contínua.

Funções públicas
----------------
  carregar_catalogo(caminho=None) -> pd.DataFrame
  snap_discreto(dados, grupos, param_norma, catalogo, max_iter) -> dict
"""

from pathlib import Path
import numpy as np
import pandas as pd

_CSV_PADRAO = Path(__file__).parent / "catalogo_chs_vallourec.csv"


def carregar_catalogo(caminho=None) -> pd.DataFrame:
    """
    Carrega catálogo de perfis CHS (Vallourec) e adiciona colunas em SI.

    O CSV esperado usa separador ';' com colunas:
        designacao, d_mm, t_mm, m_kg_m, A_cm2, I_cm4, r_cm, ...

    Retorna DataFrame ordenado por área crescente com colunas adicionais:
        A_m2 (m²), r_m (m), I_m4 (m⁴)
    """
    path = Path(caminho) if caminho else _CSV_PADRAO
    df = pd.read_csv(path, sep=';')
    df['A_m2'] = df['A_cm2'] * 1e-4
    df['r_m']  = df['r_cm']  * 1e-2
    df['I_m4'] = df['I_cm4'] * 1e-8
    return df.sort_values('A_m2').reset_index(drop=True)


def _ff_barra(N, A, r, L, E, param_norma, D_t=None):
    """
    Fator de falha (FF) de uma barra usando propriedades reais do catálogo.

    Usa r fornecido diretamente (do catálogo) em vez da fórmula analítica.
    Quando D_t (D/t real do perfil) é fornecido, aplica redução Q por
    flambagem local conforme NBR 8800:2024 Seção 5.3.4.3.
    """
    from truss_norma import Nt_Rd, Nc_Rd, _fator_Q_chs
    if N >= 0.0:
        nt = Nt_Rd(A, param_norma.fy, param_norma.gama_a1)
        return N / nt if nt > 0 else np.inf
    else:
        Q = 1.0
        if D_t is not None and param_norma.tipo_secao == 'CHS':
            Q, _ = _fator_Q_chs(D_t, param_norma.fy, E)
        nc, _, _ = Nc_Rd(A, param_norma.fy, E, L, r,
                         param_norma.k_flambagem, param_norma.gama_a1,
                         param_norma.curva, Q=Q)
        return abs(N) / nc if nc > 0 else np.inf


def snap_discreto(
    dados,
    grupos: dict,
    param_norma=None,
    catalogo: pd.DataFrame = None,
    max_iter: int = 15,
) -> dict:
    """
    Snap discreto pós-otimização: mapeia cada grupo de barras para o menor
    perfil comercial do catálogo que satisfaz FF ≤ 1,0 (NBR 8800 / NBR 16239).

    Algoritmo (Fase A)
    ------------------
    Para cada grupo de barras:
      1. Inicia pelo menor perfil com A ≥ max(A_contínua do grupo).
      2. Re-executa FEA com todas as áreas snappadas simultaneamente.
      3. Verifica FF usando as propriedades reais do catálogo (r_cm do perfil).
      4. Se alguma barra reprovar, avança para o próximo perfil e repete.
      5. Para quando todos os grupos aprovam ou o catálogo se esgota.

    Parâmetros
    ----------
    dados : TrelicaInput
        Estrutura com áreas contínuas otimizadas (saída do otimizador).
    grupos : dict[str, list[int]]
        Agrupamento das barras por nome de grupo.
        Exemplo: {'banzo_sup': [0,1,2,3], 'diagonal': [7,8,9,10]}
        Barras não listadas em nenhum grupo recebem snap individual.
    param_norma : ParamNorma | None
        Parâmetros normativos. Usa padrão (A36 / CHS curva-a) se None.
    catalogo : pd.DataFrame | None
        DataFrame do catálogo. Carrega CHS Vallourec padrão se None.
    max_iter : int
        Número máximo de avanços de perfil por grupo.

    Retorna
    -------
    dict:
        'dados_discretos'   : TrelicaInput com áreas do catálogo [m²]
        'perfis_grupos'     : dict[str, pd.Series]  — perfil por grupo nomeado
        'perfis_por_barra'  : list[str]             — designação por índice de barra
        'FF_por_barra'      : np.ndarray            — fator de falha final
        'resultado_fea'     : dict                  — FEA com áreas snappadas
        'volume_discreto'   : float [m³]
        'massa_total_kg'    : float [kg]
        'iteracoes'         : int                   — iterações de snap realizadas
        'barras_sem_grupo'  : list[int]             — barras com snap individual
    """
    from truss_engine import analise_fea

    if catalogo is None:
        catalogo = carregar_catalogo()
    if param_norma is None:
        from truss_norma import ParamNorma
        param_norma = ParamNorma()

    n_el  = dados.n_el
    E_arr = dados.E
    L_arr = dados.comprimentos()

    # Grupos efetivos: nomeados + individuais para barras sem grupo
    barra_para_grupo = {i: g for g, idxs in grupos.items() for i in idxs}
    barras_sem_grupo = [i for i in range(n_el) if i not in barra_para_grupo]

    grupos_ef = dict(grupos)
    for i in barras_sem_grupo:
        grupos_ef[f'_solo_{i}'] = [i]

    # Índice inicial no catálogo para cada grupo (menor perfil A >= A_max do grupo)
    idx_cat = {}
    for nome, idxs in grupos_ef.items():
        A_max  = max(float(dados.areas[i]) for i in idxs)
        cands  = catalogo.index[catalogo['A_m2'] >= A_max]
        idx_cat[nome] = int(cands[0]) if len(cands) else len(catalogo) - 1

    # Loop snap-e-verifica
    iteracao = 0
    for iteracao in range(max_iter):
        # Monta vetor de áreas snappadas
        areas_snap = dados.areas.copy()
        for nome, idxs in grupos_ef.items():
            A_cat = catalogo.loc[idx_cat[nome], 'A_m2']
            for i in idxs:
                areas_snap[i] = A_cat

        # Re-executa FEA com as áreas snappadas
        dados_snap = dados.copia_com_areas(areas_snap)
        res_fea    = analise_fea(dados_snap)
        N          = res_fea['forcas_internas']

        # Verifica FF e promove grupos reprovados
        algum_reprovado = False
        for nome, idxs in grupos_ef.items():
            perfil = catalogo.loc[idx_cat[nome]]
            A_cat  = perfil['A_m2']
            r_cat  = perfil['r_m']
            D_t_cat = (perfil['d_mm'] / perfil['t_mm']
                       if 'd_mm' in catalogo.columns and perfil['t_mm'] > 0
                       else None)

            for i in idxs:
                E_i = float(E_arr) if np.ndim(E_arr) == 0 else float(E_arr[i])
                uc  = _ff_barra(N[i], A_cat, r_cat, L_arr[i], E_i, param_norma,
                                D_t=D_t_cat)
                if uc > 1.0:
                    if idx_cat[nome] < len(catalogo) - 1:
                        idx_cat[nome] += 1
                    algum_reprovado = True
                    break  # passa para o próximo grupo; recalcula FEA na próxima iteração

        if not algum_reprovado:
            break

    # Monta resultado final com as áreas convergidas
    areas_fin        = dados.areas.copy()
    perfis_grupos    = {}
    perfis_por_barra = [''] * n_el
    FF_por_barra     = np.zeros(n_el)

    for nome, idxs in grupos_ef.items():
        perfil  = catalogo.loc[idx_cat[nome]]
        A_cat   = perfil['A_m2']
        r_cat   = perfil['r_m']
        D_t_cat = (perfil['d_mm'] / perfil['t_mm']
                   if 'd_mm' in catalogo.columns and perfil['t_mm'] > 0
                   else None)
        for i in idxs:
            areas_fin[i]        = A_cat
            perfis_por_barra[i] = str(perfil['designacao'])
            E_i = float(E_arr) if np.ndim(E_arr) == 0 else float(E_arr[i])
            FF_por_barra[i] = _ff_barra(N[i], A_cat, r_cat, L_arr[i], E_i,
                                         param_norma, D_t=D_t_cat)
        if not nome.startswith('_solo_'):
            perfis_grupos[nome] = perfil

    dados_disc  = dados.copia_com_areas(areas_fin)
    res_fea_fin = analise_fea(dados_disc)

    # Massa total (kg): m_kg_m × comprimento por barra
    comp_fin = dados_disc.comprimentos()
    massa = sum(
        catalogo.loc[idx_cat[nome], 'm_kg_m'] * comp_fin[i]
        for nome, idxs in grupos_ef.items()
        for i in idxs
    )

    return {
        'dados_discretos':  dados_disc,
        'perfis_grupos':    perfis_grupos,
        'perfis_por_barra': perfis_por_barra,
        'FF_por_barra':     FF_por_barra,
        'resultado_fea':    res_fea_fin,
        'volume_discreto':  res_fea_fin['volume'],
        'massa_total_kg':   massa,
        'iteracoes':        iteracao + 1,
        'barras_sem_grupo': barras_sem_grupo,
    }
