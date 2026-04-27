"""
truss_engine.py
---------------
Módulo genérico para análise e otimização de treliças planas 2D.

Estrutura de dados de entrada (TrelicaInput):
    nos           : np.ndarray (n_nos, 2)      — coordenadas [x, y] de cada nó
    conectividade : np.ndarray (n_el, 2)       — [no_i, no_j] de cada elemento
    areas         : np.ndarray (n_el,)         — área da seção transversal de cada barra [m²]
    E             : float ou np.ndarray (n_el,)— módulo de elasticidade [Pa]
    forcas        : np.ndarray (n_f, 3)        — [no, Fx, Fy] de cada carga aplicada [N]
    apoios        : np.ndarray (n_a, 3)        — [no, rest_x, rest_y] (1 = restringido)

Funções principais:
    analise_fea(dados)           — análise estrutural, retorna dict com resultados
    otimizar(dados, config)      — otimização dimensional e/ou geométrica
"""

import numpy as np
from dataclasses import dataclass, field
from scipy.optimize import minimize
from truss_norma import ParamNorma, verificar_barras, constraints_norma


# ---------------------------------------------------------------------------
# Estrutura de dados para input do usuário
# ---------------------------------------------------------------------------

@dataclass
class TrelicaInput:
    """
    Contém todos os dados necessários para descrever uma treliça plana.

    Parâmetros
    ----------
    nos : np.ndarray, shape (n_nos, 2)
        Coordenadas [x, y] de cada nó. O índice da linha é o número do nó.
        Exemplo para 3 nós:
            np.array([[0.0, 0.0],
                      [1.0, 0.0],
                      [0.5, 1.0]])

    conectividade : np.ndarray, shape (n_el, 2)
        Cada linha define um elemento: [índice_no_inicial, índice_no_final].
        Exemplo para 3 barras:
            np.array([[0, 1],
                      [1, 2],
                      [0, 2]])

    areas : np.ndarray, shape (n_el,)
        Área da seção transversal de cada barra [m²].
        Exemplo (todas com 1e-4 m²):
            np.full(3, 1e-4)

    E : float ou np.ndarray, shape (n_el,)
        Módulo de elasticidade [Pa]. Pode ser um escalar (igual para todas)
        ou um array por elemento.
        Exemplo: 200e9  ou  np.array([200e9, 70e9, 200e9])

    forcas : np.ndarray, shape (n_forcas, 3)
        Cargas aplicadas: [número_do_nó, Fx, Fy] em Newtons.
        Exemplo (força vertical de -10kN no nó 2):
            np.array([[2, 0.0, -10e3]])

    apoios : np.ndarray, shape (n_apoios, 3)
        Condições de contorno: [número_do_nó, rest_x, rest_y].
        1 = grau de liberdade restringido, 0 = livre.
        Exemplo (nó 0 fixo, nó 1 apoio de rolete vertical):
            np.array([[0, 1, 1],
                      [1, 0, 1]])
    """
    nos:           np.ndarray
    conectividade: np.ndarray
    areas:         np.ndarray
    E:             object          # float ou np.ndarray
    forcas:        np.ndarray
    apoios:        np.ndarray

    def __post_init__(self):
        """Converte listas para arrays e faz validações básicas."""
        self.nos           = np.array(self.nos,           dtype=float)
        self.conectividade = np.array(self.conectividade, dtype=int)
        self.areas         = np.array(self.areas,         dtype=float)
        self.forcas        = np.array(self.forcas,        dtype=float)
        self.apoios        = np.array(self.apoios,        dtype=float)

        n_el = self.conectividade.shape[0]

        if np.isscalar(self.E):
            self.E = np.full(n_el, float(self.E))
        else:
            self.E = np.array(self.E, dtype=float)

        # Validações
        n_nos = self.nos.shape[0]
        nos_ref = self.conectividade.flatten()
        if nos_ref.max() >= n_nos:
            raise ValueError(
                f"Conectividade referencia nó {nos_ref.max()}, "
                f"mas só existem {n_nos} nós (índices 0 a {n_nos-1})."
            )
        if self.areas.shape[0] != n_el:
            raise ValueError(
                f"'areas' tem {self.areas.shape[0]} elementos, "
                f"mas 'conectividade' define {n_el} barras."
            )
        if self.E.shape[0] != n_el:
            raise ValueError(
                f"'E' tem {self.E.shape[0]} elementos, "
                f"mas 'conectividade' define {n_el} barras."
            )

    @property
    def n_nos(self):
        return self.nos.shape[0]

    @property
    def n_el(self):
        return self.conectividade.shape[0]

    def comprimentos(self):
        """Retorna array com o comprimento de cada barra."""
        p1 = self.nos[self.conectividade[:, 0]]
        p2 = self.nos[self.conectividade[:, 1]]
        return np.linalg.norm(p2 - p1, axis=1)

    def volume_total(self):
        """Retorna o volume total de material da treliça."""
        return float(np.sum(self.areas * self.comprimentos()))

    def copia_com_areas(self, novas_areas):
        """Retorna uma nova TrelicaInput com áreas substituídas."""
        import copy
        copia = copy.copy(self)
        copia.areas = np.array(novas_areas, dtype=float)
        return copia

    def copia_com_nos(self, novos_nos):
        """Retorna uma nova TrelicaInput com coordenadas dos nós substituídas."""
        import copy
        copia = copy.copy(self)
        copia.nos = np.array(novos_nos, dtype=float)
        return copia


# ---------------------------------------------------------------------------
# Motor de análise FEA
# ---------------------------------------------------------------------------

def analise_fea(dados: TrelicaInput) -> dict:
    """
    Realiza a análise estática linear de uma treliça plana 2D.

    Parâmetros
    ----------
    dados : TrelicaInput
        Dados completos da estrutura.

    Retorna
    -------
    dict com as chaves:
        'compliance'       : float — energia de deformação (W = u^T K u) [J]
        'volume'           : float — volume total de material [m³]
        'deslocamentos'    : np.ndarray (2*n_nos, 1) — vetor de deslocamentos nodais [m]
        'forcas_internas'  : np.ndarray (n_el,) — força axial de cada barra [N]
        'tensoes'          : np.ndarray (n_el,) — tensão axial de cada barra [Pa]
        'deformacoes'      : np.ndarray (n_el,) — deformação axial de cada barra [-]
        'K_global'         : np.ndarray (2n, 2n) — matriz de rigidez global (antes de CC)
    """
    nos           = dados.nos
    conec         = dados.conectividade
    areas         = dados.areas
    E             = dados.E
    forcas        = dados.forcas
    apoios        = dados.apoios

    n_nos = dados.n_nos
    n_el  = dados.n_el
    GDL   = 2 * n_nos

    # --- Montagem da matriz de rigidez global ---
    K = np.zeros((GDL, GDL))

    for el in range(n_el):
        no1 = conec[el, 0]
        no2 = conec[el, 1]

        dx = nos[no2, 0] - nos[no1, 0]
        dy = nos[no2, 1] - nos[no1, 1]
        L  = np.sqrt(dx**2 + dy**2)

        if L < 1e-12:
            raise ValueError(f"Elemento {el}: comprimento nulo (nós {no1} e {no2} coincidentes).")

        c = dx / L   # cosseno diretor
        s = dy / L   # seno diretor

        k  = E[el] * areas[el] / L
        ke = k * np.array([[ 1, -1],
                           [-1,  1]])
        T  = np.array([[c, s, 0, 0],
                       [0, 0, c, s]])
        kg = T.T @ ke @ T   # rigidez local → global (4x4)

        # Matriz de incidência cinemática
        b = np.zeros((4, GDL))
        b[0, 2*no1]     = 1
        b[1, 2*no1 + 1] = 1
        b[2, 2*no2]     = 1
        b[3, 2*no2 + 1] = 1

        K += b.T @ kg @ b

    # --- Vetor de forças global ---
    F = np.zeros((GDL, 1))
    for i in range(forcas.shape[0]):
        no = int(forcas[i, 0])
        F[2*no]     = forcas[i, 1]
        F[2*no + 1] = forcas[i, 2]

    # Guarda K original antes de aplicar CC (necessário para compliance)
    K_orig = K.copy()

    Kg = K.copy()
    Fg = F.copy()

    # --- Condições de contorno (método de penalidade: zeragem de linha/coluna) ---
    for k in range(apoios.shape[0]):
        no = int(apoios[k, 0])
        for dof_offset, restringido in enumerate([int(apoios[k, 1]), int(apoios[k, 2])]):
            if restringido:
                j = 2 * no + dof_offset
                Kg[j, :] = 0
                Kg[:, j] = 0
                Kg[j, j] = 1
                Fg[j]    = 0

    # --- Resolução do sistema linear ---
    desloc = np.linalg.solve(Kg, Fg)

    # --- Compliance ---
    # .item() converte array (1,1) para escalar Python (compatível com NumPy ≥ 1.25)
    W = float((desloc.T @ K_orig @ desloc).item())

    # --- Volume ---
    comprimentos = dados.comprimentos()
    vol = float(np.sum(areas * comprimentos))

    # --- Forças internas, tensões e deformações por barra ---
    forcas_internas = np.zeros(n_el)
    tensoes         = np.zeros(n_el)
    deformacoes     = np.zeros(n_el)

    for el in range(n_el):
        no1 = conec[el, 0]
        no2 = conec[el, 1]

        dx = nos[no2, 0] - nos[no1, 0]
        dy = nos[no2, 1] - nos[no1, 1]
        L  = comprimentos[el]
        c  = dx / L
        s  = dy / L

        # Deslocamentos locais do elemento
        u_el = np.array([desloc[2*no1, 0],
                         desloc[2*no1+1, 0],
                         desloc[2*no2, 0],
                         desloc[2*no2+1, 0]])

        # Deformação axial: δ = (u2-u1)·cos + (v2-v1)·sen  dividido por L
        delta_u = (desloc[2*no2, 0]   - desloc[2*no1, 0])   * c
        delta_v = (desloc[2*no2+1, 0] - desloc[2*no1+1, 0]) * s
        eps = (delta_u + delta_v) / L

        sigma = E[el] * eps
        N     = sigma * areas[el]

        deformacoes[el]     = eps
        tensoes[el]         = sigma
        forcas_internas[el] = N

    # --- Reações de apoio: R = K_orig·u − F (nos GDLs restritos) ---
    # ravel() garante vetor 1-D independente do shape de desloc
    r_vec = np.asarray(K_orig @ desloc - F).ravel()
    reacoes_list = []
    for k in range(int(apoios.shape[0])):
        no = int(apoios[k, 0])
        Rx = float(r_vec[2*no])   if apoios[k, 1] else 0.0
        Ry = float(r_vec[2*no+1]) if apoios[k, 2] else 0.0
        reacoes_list.append([no, Rx, Ry])
    reacoes = (np.array(reacoes_list, dtype=float)
               if reacoes_list else np.zeros((0, 3)))

    return {
        'compliance':      W,
        'volume':          vol,
        'deslocamentos':   desloc,
        'forcas_internas': forcas_internas,
        'tensoes':         tensoes,
        'deformacoes':     deformacoes,
        'reacoes':         reacoes,
        'K_global':        K_orig,
    }


# ---------------------------------------------------------------------------
# Visualização
# ---------------------------------------------------------------------------

def plotar_trelica(
    dados: TrelicaInput,
    resultado: dict = None,
    titulo: str = 'Treliça',
    mostrar_nos: bool = True,
    mostrar_elementos: bool = True,
    mostrar_forcas: bool = True,
    mostrar_apoios: bool = True,
    escala_forca: float = None,
    ax=None,
) -> 'plt.Axes':
    """
    Plota a treliça com nós, barras, apoios e cargas.

    Parâmetros
    ----------
    dados : TrelicaInput
        Estrutura a ser plotada.
    resultado : dict, opcional
        Saída de `analise_fea()`. Se fornecido, as barras são coloridas pelo
        esforço axial: azul = tração, vermelho = compressão.
    titulo : str
        Título do gráfico.
    mostrar_nos : bool
        Se True, plota e numera os nós.
    mostrar_elementos : bool
        Se True, plota os números dos elementos no meio de cada barra.
    mostrar_forcas : bool
        Se True, desenha setas nas forças aplicadas.
    mostrar_apoios : bool
        Se True, desenha símbolos de apoio (triângulo = pino/engaste, círculo = rolete).
    escala_forca : float, opcional
        Comprimento da seta de força em unidades do modelo. Calculado
        automaticamente se None.
    ax : matplotlib.axes.Axes, opcional
        Eixo no qual plotar. Se None, cria uma nova figura.

    Retorna
    -------
    matplotlib.axes.Axes
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib.cm as cm
    import matplotlib.colors as mcolors

    nos  = dados.nos
    conec = dados.conectividade

    if ax is None:
        fig, ax = plt.subplots(figsize=(14, 5))

    # --- Escala automática para setas de força ---
    span = max(nos[:, 0].max() - nos[:, 0].min(),
               nos[:, 1].max() - nos[:, 1].min())
    if escala_forca is None:
        escala_forca = span * 0.12

    # --- Colormap para esforços axiais ---
    tem_resultado = resultado is not None and 'forcas_internas' in resultado
    if tem_resultado:
        N = resultado['forcas_internas']
        N_max = np.abs(N).max() if np.abs(N).max() > 0 else 1.0
        norm = mcolors.TwoSlopeNorm(vmin=-N_max, vcenter=0, vmax=N_max)
        cmap = cm.RdBu   # vermelho = compressão, azul = tração

    # --- Barras ---
    for el in range(dados.n_el):
        no1, no2 = conec[el]
        px = [nos[no1, 0], nos[no2, 0]]
        py = [nos[no1, 1], nos[no2, 1]]

        if tem_resultado:
            cor_el = cmap(norm(N[el]))
            lw = 1.5 + 3.5 * (abs(N[el]) / N_max)   # espessura proporcional ao esforço
        else:
            cor_el = 'steelblue'
            lw = 1.5

        ax.plot(px, py, '-', color=cor_el, linewidth=lw, zorder=2)

        if mostrar_elementos:
            mx = (nos[no1, 0] + nos[no2, 0]) / 2
            my = (nos[no1, 1] + nos[no2, 1]) / 2
            ax.text(mx, my, str(el),
                    fontsize=6, color='dimgray', ha='center', va='center',
                    bbox=dict(boxstyle='round,pad=0.1', fc='white', alpha=0.6, lw=0),
                    zorder=4)

    # --- Nós ---
    ax.plot(nos[:, 0], nos[:, 1], 'o',
            color='black', markersize=5, zorder=5)

    if mostrar_nos:
        for i in range(dados.n_nos):
            ax.annotate(str(i),
                        xy=(nos[i, 0], nos[i, 1]),
                        xytext=(4, 4), textcoords='offset points',
                        fontsize=8, color='black', zorder=6)

    # --- Apoios ---
    if mostrar_apoios:
        for k in range(dados.apoios.shape[0]):
            no  = int(dados.apoios[k, 0])
            rx  = int(dados.apoios[k, 1])
            ry  = int(dados.apoios[k, 2])
            px_ = nos[no, 0]
            py_ = nos[no, 1]

            tam = span * 0.04

            r_circ = tam * 0.22   # raio das rodinhas do rolete

            if rx and ry:
                # ── Pino: triângulo + linha de base ──────────────────────────
                ax.add_patch(plt.Polygon(
                    [[px_, py_],
                     [px_ - tam, py_ - 1.6*tam],
                     [px_ + tam, py_ - 1.6*tam]],
                    closed=True, color='gray', zorder=3))
                ax.plot([px_ - 1.2*tam, px_ + 1.2*tam],
                        [py_ - 1.7*tam, py_ - 1.7*tam],
                        '-', color='gray', lw=2, zorder=3)
                # hachura abaixo da linha (solo)
                for hx in np.linspace(px_ - tam, px_ + tam, 5):
                    ax.plot([hx, hx - 0.4*tam],
                            [py_ - 1.7*tam, py_ - 2.1*tam],
                            '-', color='gray', lw=1, zorder=3)

            elif rx and not ry:
                # ── Rolete X (desliza em Y): triângulo ← + rodinhas à esquerda
                ax.add_patch(plt.Polygon(
                    [[px_, py_],
                     [px_ - 1.6*tam, py_ + tam],
                     [px_ - 1.6*tam, py_ - tam]],
                    closed=True, color='gray', zorder=3))
                # linha vertical de contato
                ax.plot([px_ - 1.65*tam, px_ - 1.65*tam],
                        [py_ - 1.2*tam, py_ + 1.2*tam],
                        '-', color='gray', lw=1.5, zorder=3)
                # 3 rodinhas
                for i in range(3):
                    yi = py_ + (i - 1) * 2.6 * r_circ
                    ax.add_patch(mpatches.Circle(
                        (px_ - 1.65*tam - r_circ, yi), r_circ,
                        color='gray', zorder=3))
                # parede
                ax.plot([px_ - 1.65*tam - 2.4*r_circ,
                         px_ - 1.65*tam - 2.4*r_circ],
                        [py_ - 1.3*tam, py_ + 1.3*tam],
                        '-', color='gray', lw=2, zorder=3)

            elif ry and not rx:
                # ── Rolete Y (desliza em X): triângulo ↓ + rodinhas na base
                ax.add_patch(plt.Polygon(
                    [[px_, py_],
                     [px_ - tam, py_ - 1.6*tam],
                     [px_ + tam, py_ - 1.6*tam]],
                    closed=True, color='gray', zorder=3))
                # linha horizontal de contato
                ax.plot([px_ - 1.2*tam, px_ + 1.2*tam],
                        [py_ - 1.65*tam, py_ - 1.65*tam],
                        '-', color='gray', lw=1.5, zorder=3)
                # 3 rodinhas
                for i in range(3):
                    xi = px_ + (i - 1) * 2.6 * r_circ
                    ax.add_patch(mpatches.Circle(
                        (xi, py_ - 1.65*tam - r_circ), r_circ,
                        color='gray', zorder=3))
                # linha do solo
                ax.plot([px_ - 1.3*tam, px_ + 1.3*tam],
                        [py_ - 1.65*tam - 2.4*r_circ,
                         py_ - 1.65*tam - 2.4*r_circ],
                        '-', color='gray', lw=2, zorder=3)

    # --- Forças ---
    if mostrar_forcas:
        for k in range(dados.forcas.shape[0]):
            no  = int(dados.forcas[k, 0])
            Fx  = dados.forcas[k, 1]
            Fy  = dados.forcas[k, 2]
            px_ = nos[no, 0]
            py_ = nos[no, 1]

            F_mag = np.sqrt(Fx**2 + Fy**2)
            if F_mag < 1e-12:
                continue

            # Normaliza e escala a seta
            dx_arrow = (Fx / F_mag) * escala_forca
            dy_arrow = (Fy / F_mag) * escala_forca

            ax.annotate(
                '',
                xy=(px_, py_),
                xytext=(px_ - dx_arrow, py_ - dy_arrow),
                arrowprops=dict(arrowstyle='->', color='orangered', lw=2),
                zorder=6,
            )
            label = f'{F_mag/1e3:.1f} kN'
            ax.text(px_ - dx_arrow * 1.1, py_ - dy_arrow * 1.1,
                    label, fontsize=7, color='orangered', ha='center', va='center')

    # --- Barra de cores (quando há resultado) ---
    if tem_resultado:
        sm = cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cbar = ax.get_figure().colorbar(sm, ax=ax, fraction=0.02, pad=0.02)
        cbar.set_label('Força axial [N]\n(+) Tração  /  (−) Compressão', fontsize=8)

    # --- Coordenadas X no eixo: marcações nas posições reais dos nós ---
    xs_unicos = np.unique(np.round(nos[:, 0], 6))
    ax.set_xticks(xs_unicos)
    ax.set_xticklabels([f'{v:.2f}' for v in xs_unicos], fontsize=7, rotation=45, ha='right')

    # --- Coordenadas Y ao lado de cada nó ---
    # Para evitar sobreposição, agrupa nós com mesma coordenada Y
    ys_plotados = {}   # chave: y arredondado → lista de x já anotados
    for i in range(dados.n_nos):
        xi, yi = nos[i, 0], nos[i, 1]
        y_key = round(yi, 4)
        # Só anota se ainda não foi anotado um nó com esse y muito próximo a esse x
        ja_anotado = any(abs(xi - xp) < span * 0.02
                         for xp in ys_plotados.get(y_key, []))
        if not ja_anotado:
            ax.text(xi + span * 0.015, yi,
                    f'y={yi:.2f}',
                    fontsize=6.5, color='dimgray', va='center', ha='left',
                    zorder=7)
            ys_plotados.setdefault(y_key, []).append(xi)

    ax.set_title(titulo, fontsize=11)
    ax.set_xlabel('x [m]')
    ax.set_ylabel('y [m]')
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)

    return ax


# ---------------------------------------------------------------------------
# Configuração da otimização
# ---------------------------------------------------------------------------

@dataclass
class ConfigOtimizacao:
    """
    Parâmetros para o problema de otimização.

    Campos obrigatórios
    -------------------
    otimizar_areas : bool
        Se True, as áreas das barras são variáveis de projeto.
    otimizar_geometria : bool
        Se True, as coordenadas dos nós livres são variáveis de projeto.
    bounds_areas : list of (float, float), comprimento n_el
        Limites [min, max] para a área de cada barra [m²].

    Campos opcionais
    ----------------
    nos_geometria_livre : list of int
        Índices dos nós cujas coordenadas podem ser movidas pelo otimizador.
        Ignorado se otimizar_geometria=False.
    bounds_nos : list of (float, float)
        Limites para cada coordenada livre, na ordem [x0, y0, x1, y1, ...].
        Deve ter comprimento 2 * len(nos_geometria_livre).
    restricao_volume : float ou None
        Se fornecido, adiciona restrição de igualdade: volume == restricao_volume.
    restricao_volume_max : float ou None
        Se fornecido, adiciona restrição de desigualdade: volume <= restricao_volume_max.
    metodo : str
        Método do scipy.optimize.minimize. Padrão: 'SLSQP'.
    """
    otimizar_areas:       bool
    otimizar_geometria:   bool
    bounds_areas:         list

    nos_geometria_livre:  list  = field(default_factory=list)
    bounds_nos:           list  = field(default_factory=list)
    restricao_volume:     float = None
    restricao_volume_max: float = None
    metodo:               str   = 'SLSQP'

    # ── Objetivo ─────────────────────────────────────────────────────────────
    objetivo: str = 'volume'
    # 'volume'    — minimiza volume de aço (∝ massa e custo)
    # 'compliance'— minimiza compliance (maximiza rigidez global)

    # ── Restrições normativas (NBR 8800 / NBR 16239) ──────────────────────────
    usar_restricoes_norma: bool       = False
    param_norma:           ParamNorma = None
    # Se True, adiciona para cada barra:
    #   • restrição de tração:    1 − N/Nt,Rd ≥ 0
    #   • restrição de compressão: 1 − |N|/Nc,Rd ≥ 0 (com flambagem global)


# ---------------------------------------------------------------------------
# Motor de otimização
# ---------------------------------------------------------------------------

def otimizar(dados: TrelicaInput, config: ConfigOtimizacao,
             callback_iter=None) -> dict:
    """
    callback_iter : callable(iter, volume_m3, compliance) | None
        Chamado ao final de cada iteração do SLSQP.
        Útil para atualizar interfaces gráficas em tempo real.
    """
    """
    Otimiza a treliça minimizando volume ou compliance, com restrições de
    volume e/ou de resistência normativa (NBR 8800 / NBR 16239).

    Parâmetros
    ----------
    dados  : TrelicaInput       — estrutura inicial
    config : ConfigOtimizacao   — configuração do problema de otimização

    Retorna
    -------
    dict com as chaves:
        'resultado_scipy'  : OptimizeResult do scipy
        'dados_otimizados' : TrelicaInput com as variáveis de projeto otimizadas
        'compliance_final' : float
        'volume_final'     : float
        'sucesso'          : bool
        'mensagem'         : str
    """

    # --- Monta vetor x0 e bounds ---
    x0     = []
    bounds = []

    if config.otimizar_areas:
        x0     += list(dados.areas)
        bounds += list(config.bounds_areas)

    if config.otimizar_geometria:
        for no_idx in config.nos_geometria_livre:
            x0     += [dados.nos[no_idx, 0], dados.nos[no_idx, 1]]
        bounds += list(config.bounds_nos)

    x0     = np.array(x0)
    n_vars = len(x0)

    if n_vars == 0:
        raise ValueError("Nenhuma variável de projeto definida. "
                         "Ative 'otimizar_areas' e/ou 'otimizar_geometria'.")

    # --- Função que reconstrói TrelicaInput a partir de x ---
    def reconstruir_dados(x):
        novo_dados = dados  # referência original
        offset = 0

        if config.otimizar_areas:
            novas_areas = x[offset: offset + dados.n_el]
            novo_dados  = novo_dados.copia_com_areas(novas_areas)
            offset += dados.n_el

        if config.otimizar_geometria:
            novos_nos = dados.nos.copy()
            for no_idx in config.nos_geometria_livre:
                novos_nos[no_idx, 0] = x[offset]
                novos_nos[no_idx, 1] = x[offset + 1]
                offset += 2
            novo_dados = novo_dados.copia_com_nos(novos_nos)

        return novo_dados

    # --- Função objetivo ---
    if config.objetivo == 'volume':
        def objetivo(x):
            return analise_fea(reconstruir_dados(x))['volume']
    elif config.objetivo == 'compliance':
        def objetivo(x):
            return analise_fea(reconstruir_dados(x))['compliance']
    else:
        raise ValueError(f"objetivo '{config.objetivo}' inválido. "
                         "Use 'volume' ou 'compliance'.")

    # --- Restrições ---
    constraints = []

    if config.restricao_volume is not None:
        vol_alvo = config.restricao_volume
        def rest_volume_eq(x):
            return analise_fea(reconstruir_dados(x))['volume'] - vol_alvo
        constraints.append({'type': 'eq', 'fun': rest_volume_eq})

    if config.restricao_volume_max is not None:
        vol_max = config.restricao_volume_max
        def rest_volume_ineq(x):
            return vol_max - analise_fea(reconstruir_dados(x))['volume']
        constraints.append({'type': 'ineq', 'fun': rest_volume_ineq})

    # --- Restrições normativas (NBR 8800 / NBR 16239) ---
    if config.usar_restricoes_norma:
        pn = config.param_norma or ParamNorma()
        n_areas = dados.n_el if config.otimizar_areas else 0

        for el in range(dados.n_el):
            L_el = float(np.sqrt(np.sum(
                (dados.nos[dados.conectividade[el, 1]] -
                 dados.nos[dados.conectividade[el, 0]])**2)))
            E_el = float(dados.E) if np.ndim(dados.E) == 0 else float(dados.E[el])

            # Restrição de tração: 1 − N_el/Nt,Rd ≥ 0
            def _ct(x, el=el):
                res = analise_fea(reconstruir_dados(x))
                N_el = res['forcas_internas'][el]
                if N_el <= 0:
                    return 1.0
                A_el = float(x[el]) if config.otimizar_areas else float(dados.areas[el])
                from truss_norma import Nt_Rd
                return 1.0 - N_el / Nt_Rd(A_el, pn.fy, pn.gama_a1)
            constraints.append({'type': 'ineq', 'fun': _ct})

            # Restrição de compressão/flambagem: 1 − |N_el|/Nc,Rd ≥ 0
            def _cc(x, el=el, L=L_el, E=E_el):
                res = analise_fea(reconstruir_dados(x))
                N_el = res['forcas_internas'][el]
                if N_el >= 0:
                    return 1.0
                A_el = float(x[el]) if config.otimizar_areas else float(dados.areas[el])
                r_el = pn.raio_giracao(A_el)
                from truss_norma import Nc_Rd
                nc, _, _ = Nc_Rd(A_el, pn.fy, E, L, r_el,
                                 pn.k_flambagem, pn.gama_a1, pn.curva)
                return 1.0 - abs(N_el) / nc
            constraints.append({'type': 'ineq', 'fun': _cc})

    # --- Callback: registra progresso por iteração ---
    historico: list[dict] = []

    def _callback(xk):
        d_tmp = reconstruir_dados(xk)
        r_tmp = analise_fea(d_tmp)
        n = len(historico) + 1
        historico.append({
            'iter':       n,
            'volume_m3':  r_tmp['volume'],
            'compliance': r_tmp['compliance'],
            'f_obj':      objetivo(xk),
        })
        if callback_iter is not None:
            try:
                callback_iter(n, r_tmp['volume'], r_tmp['compliance'])
            except Exception:
                pass   # nunca deixar o callback quebrar a otimização

    # --- Executa otimização ---
    resultado = minimize(
        objetivo,
        x0,
        method=config.metodo,
        bounds=bounds,
        constraints=constraints,
        callback=_callback,
        options={'ftol': 1e-9, 'maxiter': 500},
    )

    dados_otim = reconstruir_dados(resultado.x)
    res_final  = analise_fea(dados_otim)

    saida = {
        'resultado_scipy':  resultado,
        'dados_otimizados': dados_otim,
        'compliance_final': res_final['compliance'],
        'volume_final':     res_final['volume'],
        'sucesso':          resultado.success,
        'mensagem':         resultado.message,
        'historico':        historico,
    }

    if config.usar_restricoes_norma:
        pn = config.param_norma or ParamNorma()
        saida['norma'] = verificar_barras(dados_otim, res_final, pn)

    return saida
