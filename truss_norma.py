"""
truss_norma.py
--------------
Verificações de dimensionamento de barras de aço segundo:

  • ABNT NBR 8800:2024  — Projeto de estruturas de aço e estruturas mistas
  • ABNT NBR 16239:2013 — Estruturas com perfis tubulares

Funções públicas
----------------
  Nt_Rd(Ag, fy, gama_a1)                    → resistência à tração [N]
  Nc_Rd(Ag, fy, E, L, r, k, gama_a1, curva) → resistência à compressão [N]
  verificar_barras(dados, res_fea, params)   → dict com verificação por barra

Classes
-------
  ParamNorma  — parâmetros do material, seção e coeficientes normativos
"""

import numpy as np
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Parâmetros normativos
# ---------------------------------------------------------------------------

@dataclass
class ParamNorma:
    """
    Parâmetros do material e da seção transversal para verificação normativa.

    Campos
    ------
    fy : float
        Tensão de escoamento do aço [Pa].
        Padrão: 250 MPa (ASTM A36 / CA-25).

    fu : float
        Resistência à ruptura do aço [Pa].
        Padrão: 400 MPa.

    E : float
        Módulo de elasticidade [Pa].
        NBR 8800:2024 item 3.1: E = 200 GPa.

    gama_a1 : float
        Coeficiente de ponderação da resistência ao escoamento.
        NBR 8800:2024 item 4.4: γa1 = 1,10.

    gama_a2 : float
        Coeficiente de ponderação da resistência à ruptura.
        NBR 8800:2024 item 4.4: γa2 = 1,35.

    k_flambagem : float
        Fator de comprimento efetivo de flambagem.
        Para barras de treliça bi-articuladas: k = 1,0.

    curva : str
        Curva de flambagem NBR 8800:2024 Tabela 5.1.
        Perfis tubulares CHS/SHS (NBR 16239): curva 'a'.
        Valores: 'a' (α=0,21) | 'b' (α=0,34) | 'c' (α=0,49) | 'd' (α=0,76).

    tipo_secao : str
        Tipo de seção transversal para cálculo do raio de giração.
        'CHS'  — Circular Hollow Section (perfil tubular circular)
        'SHS'  — Square Hollow Section   (perfil tubular quadrado)
        'solida_circular' — barra sólida circular

    beta_td : float
        Relação espessura/diâmetro (t/D) para seções CHS.
        Perfis estruturais típicos: 0,05 a 0,12.
        Padrão: 0,10 (10 % do diâmetro externo).

    beta_td_shs : float
        Relação espessura/lado (t/b) para seções SHS.
        Padrão: 0,10.
    """
    fy:           float = 250e6
    fu:           float = 400e6
    E:            float = 200e9
    gama_a1:      float = 1.10
    gama_a2:      float = 1.35
    k_flambagem:  float = 1.0
    curva:        str   = 'a'
    tipo_secao:   str   = 'CHS'
    beta_td:      float = 0.10
    beta_td_shs:  float = 0.10

    @property
    def C_r(self) -> float:
        """
        Fator de forma: r = C_r · √A  (raio de giração × inverso de √área).

        Derivado analiticamente para cada tipo de seção:

        CHS (circular hollow section), β = t/D:
            A  = π·D²·β·(1−β)   (aproximação: π/4·(D²−d²) com d=D(1−2β))
            I  = π·D⁴·(1−(1−2β)⁴)/64
            r² = D²·(1−(1−2β)⁴) / (16·(1−(1-2β)²)²)  →  expressar em função de A

        SHS (square hollow section), β = t/b, b = lado externo:
            A  = 4·b·t·(1−β)
            I  = b⁴·(1−(1−2β)⁴)/12
            r  ≈ b·√((1−(1−2β)⁴)/12) / √(4β(1−β))  →  expressar em função de A

        Barra sólida circular:
            r = D/4 = √A/(2√π) ≈ 0,282·√A
        """
        if self.tipo_secao == 'CHS':
            b = self.beta_td
            x = (1 - 2*b)**2
            x2 = (1 - 2*b)**4
            # r² = A · (1−x²) / [4π·(1−x)²]  com x = (1−2β)²
            return np.sqrt((1 - x2) / (4 * np.pi * (1 - x)**2))

        elif self.tipo_secao == 'SHS':
            b = self.beta_td_shs
            x2 = (1 - 2*b)**4
            # r² = A · (1−x²) / [12 · (4β(1−β))²]
            return np.sqrt((1 - x2) / (12 * (4*b*(1-b))**2))

        elif self.tipo_secao == 'solida_circular':
            return 1.0 / (2 * np.sqrt(np.pi))    # ≈ 0,282

        else:
            raise ValueError(f"tipo_secao '{self.tipo_secao}' não suportado. "
                             "Use 'CHS', 'SHS' ou 'solida_circular'.")

    def raio_giracao(self, A: float) -> float:
        """Raio de giração mínimo [m] para uma seção de área A [m²]."""
        return self.C_r * np.sqrt(A)


# ---------------------------------------------------------------------------
# Resistência à tração
# ---------------------------------------------------------------------------

def Nt_Rd(Ag: float, fy: float, gama_a1: float = 1.10) -> float:
    """
    Resistência de cálculo à tração — escoamento da seção bruta.

    NBR 8800:2024 — Seção 5.2, Equação 5.1 (a):
        Nt,Rd = Ag · fy / γa1

    Parâmetros
    ----------
    Ag : float      Área bruta da seção transversal [m²].
    fy : float      Tensão de escoamento [Pa].
    gama_a1 : float Coeficiente de ponderação γa1 (padrão 1,10).

    Retorna
    -------
    float  Resistência à tração [N].

    Notas
    -----
    Para barras sem furos (treliças soldadas ou com pinos sem furo), a
    verificação da seção líquida (Eq. 5.1 b) não se aplica e esta
    equação governa.
    """
    return Ag * fy / gama_a1


# ---------------------------------------------------------------------------
# Instabilidade global por flambagem
# ---------------------------------------------------------------------------

def _indice_esbeltez_reduzido(L: float, r: float, fy: float, E: float,
                               k: float = 1.0) -> float:
    """
    Índice de esbeltez reduzido λo (adimensional).

    NBR 8800:2024 — Seção 5.3, Equação 5.7:
        λo = (k·L/r) / (π·√(E/fy))
    """
    return (k * L / r) / (np.pi * np.sqrt(E / fy))


def _fator_reducao_flambagem(lambda_o: float, curva: str = 'a') -> float:
    """
    Fator de redução χ para instabilidade global por flambagem.

    NBR 8800:2024 — Seção 5.3, Equações 5.8 e 5.9:

        Φ  = 0,5 · [1 + α · (λo − 0,2) + λo²]
        χ  = 1 / (Φ + √(Φ² − λo²))  ≤ 1,0

    Fatores de imperfeição α (Tabela 5.1):
        Curva a: α = 0,21  (perfis tubulares CHS/SHS — NBR 16239)
        Curva b: α = 0,34
        Curva c: α = 0,49
        Curva d: α = 0,76

    Parâmetros
    ----------
    lambda_o : float  Índice de esbeltez reduzido.
    curva : str       Curva de flambagem ('a', 'b', 'c', 'd').

    Retorna
    -------
    float  Fator de redução χ ∈ (0, 1].
    """
    alpha_imp = {'a': 0.21, 'b': 0.34, 'c': 0.49, 'd': 0.76}
    if curva not in alpha_imp:
        raise ValueError(f"Curva '{curva}' inválida. Use 'a', 'b', 'c' ou 'd'.")

    if lambda_o <= 0.2:          # platô de plastificação
        return 1.0

    alpha = alpha_imp[curva]
    phi = 0.5 * (1.0 + alpha * (lambda_o - 0.2) + lambda_o**2)
    chi = 1.0 / (phi + np.sqrt(max(phi**2 - lambda_o**2, 0.0)))
    return min(chi, 1.0)


# ---------------------------------------------------------------------------
# Flambagem local — perfis CHS (seções esbeltas em compressão)
# ---------------------------------------------------------------------------

def _fator_Q_chs(D_t: float, fy: float, E: float) -> tuple[float, str]:
    """
    Fator Q de redução por flambagem local — perfis CHS em compressão axial.

    NBR 8800:2024 Seção 5.3.4.3 — área efetiva para seções esbeltas:
        Q_a = (0,038 · E/fy) / (D/t)  +  2/3      para D/t > λr

    Para CHS não há elementos não-enrijecidos projetantes (Qs = 1,0), logo Q = Qa.

    Classificação da seção (NBR 8800:2024 Tabela C.2 / NBR 16239:2013 Seção 5.2):
        D/t ≤ λr = 0,15·E/fy      →  'nao_esbelta'  (Q = 1,0)
        λr < D/t ≤ 0,45·E/fy     →  'esbelta'       (0 < Q < 1)
        D/t > 0,45·E/fy           →  'invalida'      (fora do escopo normativo)

    Parâmetros
    ----------
    D_t : float   Relação diâmetro / espessura (D/t) do perfil CHS.
    fy  : float   Tensão de escoamento [Pa].
    E   : float   Módulo de elasticidade [Pa].

    Retorna
    -------
    (Q, classificacao)
        Q             — fator adimensional ∈ (0, 1]
        classificacao — 'nao_esbelta' | 'esbelta' | 'invalida'
    """
    lim_r   = 0.15 * E / fy
    lim_max = 0.45 * E / fy

    if D_t <= lim_r:
        return 1.0, 'nao_esbelta'
    if D_t > lim_max:
        return 0.0, 'invalida'

    Q = (0.038 * E / fy) / D_t + 2.0 / 3.0
    return float(min(Q, 1.0)), 'esbelta'


def Nc_Rd(Ag: float, fy: float, E: float, L: float, r: float,
          k: float = 1.0, gama_a1: float = 1.10,
          curva: str = 'a', Q: float = 1.0) -> tuple[float, float, float]:
    """
    Resistência de cálculo à compressão com flambagem global e local.

    NBR 8800:2024 — Seções 5.3 e 5.3.4.3:
        Nc,Rd = χ(λo_eff) · Q · Ag · fy / γa1

    NBR 16239:2013 — Seção 5.2 (perfis tubulares):
        Mesma formulação, usando curva 'a'.

    Parâmetros
    ----------
    Ag : float      Área bruta da seção transversal [m²].
    fy : float      Tensão de escoamento [Pa].
    E  : float      Módulo de elasticidade [Pa].
    L  : float      Comprimento da barra [m]  (comprimento de flambagem = k·L).
    r  : float      Raio de giração mínimo [m].
    k  : float      Fator de comprimento efetivo (1,0 para bi-articulada).
    gama_a1 : float Coeficiente de ponderação γa1 (padrão 1,10).
    curva : str     Curva de flambagem (padrão 'a' para tubulares).
    Q : float       Fator de redução por flambagem local (padrão 1,0 = não-esbelta).
                    Para CHS com D/t > 0,15·E/fy, usar _fator_Q_chs().
                    Interação global × local (NBR 8800:2024 Seção 5.3.4.3):
                        λo_eff = λo · √Q
                        Nc,Rd  = χ(λo_eff) · Q · Ag · fy / γa1

    Retorna
    -------
    (Nc_Rd, lambda_o, chi) : tuple
        Nc_Rd    — Resistência à compressão [N].
        lambda_o — Índice de esbeltez geométrico (kL/r normalizado) [-].
        chi      — Fator χ calculado com λo_eff = λo·√Q [-].

    Notas
    -----
    NBR 8800:2024 limita kL/r ≤ 200 para elementos de compressão principais
    (item 5.3.2). A verificação é alertada mas não impõe erro.
    """
    lambda_o     = _indice_esbeltez_reduzido(L, r, fy, E, k)
    lambda_o_eff = lambda_o * np.sqrt(Q)
    chi          = _fator_reducao_flambagem(lambda_o_eff, curva)
    return chi * Q * Ag * fy / gama_a1, lambda_o, chi


# ---------------------------------------------------------------------------
# Verificação completa das barras
# ---------------------------------------------------------------------------

def verificar_barras(dados, res_fea: dict,
                     params: ParamNorma = None) -> dict:
    """
    Verifica todas as barras da treliça conforme NBR 8800:2024 / NBR 16239:2013.

    Parâmetros
    ----------
    dados : TrelicaInput
        Estrutura com nós, conectividade e áreas.
    res_fea : dict
        Saída de `analise_fea()`. Deve conter 'forcas_internas' (N, por barra).
    params : ParamNorma, opcional
        Parâmetros do material/seção. Usa ParamNorma() padrão se None.

    Retorna
    -------
    dict com as chaves:

        'Nt_Rd'              : ndarray(n_el) — resistência à tração [N]
        'Nc_Rd'              : ndarray(n_el) — resistência à compressão [N]
        'N'                  : ndarray(n_el) — esforço axial FEA [N] (+ = tração)
        'lambda_o'           : ndarray(n_el) — índice de esbeltez geométrico kL/r·√(fy/E)/π [-]
        'chi'                : ndarray(n_el) — fator χ calculado com λo·√Q [-]
        'Q'                  : ndarray(n_el) — fator de flambagem local (1,0 se não-esbelta)
        'r'                  : ndarray(n_el) — raio de giração [m]
        'L'                  : ndarray(n_el) — comprimento de cada barra [m]
        'esbeltez_kLr'       : ndarray(n_el) — esbeltez geométrica k·L/r
        'UC_tracao'          : ndarray(n_el) — taxa de utilização à tração  (N/Nt,Rd)
        'UC_compressao'      : ndarray(n_el) — taxa de utilização à compressão (|N|/Nc,Rd)
        'UC_max'             : ndarray(n_el) — max(UC_tracao, UC_compressao) por barra
        'aprovado'           : ndarray(n_el, bool) — True se UC_max ≤ 1,0
        'UC_global'          : float — pior taxa de utilização (governa o projeto)
        'classificacao_local': list[str] — 'nao_esbelta' | 'esbelta' | 'invalida' por barra
        'alertas'            : list[str] — avisos (esbeltez excessiva, seção esbelta, etc.)
    """
    if params is None:
        params = ParamNorma()

    N     = res_fea['forcas_internas']
    nos   = dados.nos
    conec = dados.conectividade
    n_el  = dados.n_el

    # D/t constante para o tipo de seção configurado (forma preservada na otimização)
    D_t_global = (1.0 / params.beta_td
                  if params.tipo_secao == 'CHS' and params.beta_td > 0
                  else None)

    L_arr       = np.zeros(n_el)
    r_arr       = np.zeros(n_el)
    lam_arr     = np.zeros(n_el)
    chi_arr     = np.zeros(n_el)
    klr_arr     = np.zeros(n_el)
    Q_arr       = np.ones(n_el)
    Nt_arr      = np.zeros(n_el)
    Nc_arr      = np.zeros(n_el)
    UC_t_arr    = np.zeros(n_el)
    UC_c_arr    = np.zeros(n_el)
    class_local = ['nao_esbelta'] * n_el
    alertas     = []

    for el in range(n_el):
        ni, nj = conec[el]
        L = float(np.sqrt(np.sum((nos[nj] - nos[ni])**2)))
        A = float(dados.areas[el])
        E = float(dados.E) if np.ndim(dados.E) == 0 else float(dados.E[el])

        # Flambagem local — Q para CHS (NBR 8800:2024 Seção 5.3.4.3)
        Q = 1.0
        if D_t_global is not None:
            Q, cls = _fator_Q_chs(D_t_global, params.fy, E)
            class_local[el] = cls
            if cls == 'invalida':
                alertas.append(
                    f"Barra {el}: D/t = {D_t_global:.1f} > 0,45·E/fy = "
                    f"{0.45 * E / params.fy:.0f} — seção fora do escopo "
                    "normativo (NBR 8800:2024 Seção 5.3.4.3)")
        Q_arr[el] = Q

        r   = params.raio_giracao(A)
        kLr = params.k_flambagem * L / r
        nc, lo, chi = Nc_Rd(A, params.fy, E, L, r,
                             params.k_flambagem, params.gama_a1, params.curva,
                             Q=Q)
        nt  = Nt_Rd(A, params.fy, params.gama_a1)

        L_arr[el]   = L
        r_arr[el]   = r
        lam_arr[el] = lo
        chi_arr[el] = chi
        klr_arr[el] = kLr
        Nt_arr[el]  = nt
        Nc_arr[el]  = nc

        if N[el] < 0 and kLr > 200:
            alertas.append(
                f"Barra {el}: esbeltez k·L/r = {kLr:.1f} > 200 "
                "(limite NBR 8800:2024 item 5.3.2)")

        if N[el] >= 0.0:
            UC_t_arr[el] = N[el] / nt if nt > 0 else np.inf
        else:
            UC_c_arr[el] = abs(N[el]) / nc if nc > 0 else np.inf

    # Alerta resumido para seções esbeltas
    n_esbelta = sum(1 for c in class_local if c == 'esbelta')
    if n_esbelta > 0 and D_t_global is not None:
        E_ref = float(dados.E) if np.ndim(dados.E) == 0 else float(dados.E[0])
        alertas.insert(0,
            f"Flambagem local: D/t = {D_t_global:.1f} > 0,15·E/fy = "
            f"{0.15 * E_ref / params.fy:.0f} em {n_esbelta} barra(s) "
            f"(Q_mín = {Q_arr[Q_arr > 0].min():.3f}) — "
            "NBR 8800:2024 Seção 5.3.4.3")

    UC_max = np.maximum(UC_t_arr, UC_c_arr)

    return {
        'Nt_Rd':               Nt_arr,
        'Nc_Rd':               Nc_arr,
        'N':                   N,
        'lambda_o':            lam_arr,
        'chi':                 chi_arr,
        'Q':                   Q_arr,
        'r':                   r_arr,
        'L':                   L_arr,
        'esbeltez_kLr':        klr_arr,
        'UC_tracao':           UC_t_arr,
        'UC_compressao':       UC_c_arr,
        'UC_max':              UC_max,
        'aprovado':            UC_max <= 1.0,
        'UC_global':           float(UC_max.max()),
        'classificacao_local': class_local,
        'alertas':             alertas,
    }


# ---------------------------------------------------------------------------
# Restrições para uso no otimizador scipy
# ---------------------------------------------------------------------------

def constraints_norma(dados, params: ParamNorma = None):
    """
    Gera lista de constraints scipy para uso com minimize(..., constraints=...).

    Cada barra gera até duas restrições de desigualdade (≥ 0):
        tração:     1 − N_el / Nt_Rd(A_el) ≥ 0
        compressão: 1 − |N_el| / Nc_Rd(A_el, L_el) ≥ 0

    Parâmetros
    ----------
    dados : TrelicaInput
        Estrutura base (conectividade, nós). As áreas serão sobrepostas
        pelo vetor x do otimizador.
    params : ParamNorma, opcional

    Retorna
    -------
    list[dict]  Lista de constraints no formato scipy.

    Uso
    ---
    >>> from truss_engine import analise_fea
    >>> from truss_norma import constraints_norma, ParamNorma
    >>> p = ParamNorma(fy=250e6)
    >>> C = constraints_norma(dados, p)
    >>> result = minimize(obj, x0, constraints=C, method='SLSQP')
    """
    from truss_engine import TrelicaInput

    if params is None:
        params = ParamNorma()

    n_el  = dados.n_el
    nos   = dados.nos
    conec = dados.conectividade
    E_ref = float(dados.E) if np.ndim(dados.E) == 0 else None

    # Comprimentos fixos (geometria não muda se só áreas são otimizadas)
    L_arr = np.array([
        np.sqrt(np.sum((nos[conec[el, 1]] - nos[conec[el, 0]])**2))
        for el in range(n_el)
    ])

    def _analise_com_areas(areas):
        """Reanalisa a estrutura substituindo as áreas."""
        d = TrelicaInput(
            nos=dados.nos,
            conectividade=dados.conectividade,
            areas=np.asarray(areas),
            E=dados.E,
            forcas=dados.forcas,
            apoios=dados.apoios,
        )
        from truss_engine import analise_fea
        return analise_fea(d)

    constrs = []

    for el in range(n_el):
        # --- tração ---
        def _ct(x, el=el):
            res = _analise_com_areas(x[:n_el])
            N_el = res['forcas_internas'][el]
            if N_el < 0:      # não está em tração — restrição não governa
                return 1.0
            A_el = x[el]
            nt   = Nt_Rd(A_el, params.fy, params.gama_a1)
            return 1.0 - N_el / nt

        constrs.append({'type': 'ineq', 'fun': _ct})

        # --- compressão / flambagem (global + local) ---
        def _cc(x, el=el):
            res = _analise_com_areas(x[:n_el])
            N_el = res['forcas_internas'][el]
            if N_el >= 0:
                return 1.0
            A_el = float(x[el])
            E_el = E_ref if E_ref is not None else float(dados.E[el])
            r_el = params.raio_giracao(A_el)
            Q    = 1.0
            if params.tipo_secao == 'CHS' and params.beta_td > 0:
                Q, _ = _fator_Q_chs(1.0 / params.beta_td, params.fy, E_el)
            nc, _, _ = Nc_Rd(A_el, params.fy, E_el, L_arr[el], r_el,
                             params.k_flambagem, params.gama_a1, params.curva,
                             Q=Q)
            return 1.0 - abs(N_el) / nc

        constrs.append({'type': 'ineq', 'fun': _cc})

    return constrs
