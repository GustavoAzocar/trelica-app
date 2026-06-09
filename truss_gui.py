"""
truss_gui.py
------------
Interface gráfica para lançamento, visualização e otimização de treliças planas 2D.

Dependências externas: ver requirements.json  (pip install <pacote>)
"""

# ─────────────────────────────────────────────────────────────────────────────
# Verificação de dependências — roda ANTES de qualquer import externo
# Usa somente stdlib: importlib, subprocess, tkinter, json, sys, pathlib
# ─────────────────────────────────────────────────────────────────────────────
import sys
import json
import csv
import threading
import subprocess
import importlib.util
from pathlib import Path
import tkinter as tk
from tkinter import messagebox


def _verificar_dependencias() -> bool:
    """
    Lê requirements.json, detecta pacotes ausentes e oferece instalação.
    Retorna True se todos estão disponíveis ao final, False se o usuário
    cancelou ou alguma instalação falhou.
    """
    req_path = Path(__file__).parent / 'requirements.json'
    if not req_path.exists():
        return True   # sem arquivo de requisitos → continua normalmente

    with open(req_path, encoding='utf-8') as f:
        reqs = json.load(f)

    ausentes = []
    for pkg in reqs.get('pacotes', []):
        if importlib.util.find_spec(pkg['import_name']) is None:
            ausentes.append(pkg)

    if not ausentes:
        return True

    # ── Janela de aviso (tkinter stdlib) ────────────────────────────────────
    root = tk.Tk()
    root.withdraw()   # janela principal oculta — só usamos os diálogos

    nomes = '\n'.join(
        f"  • {p['nome_exibicao']}  —  {p['descricao']}"
        for p in ausentes
    )
    resposta = messagebox.askyesno(
        title='Dependências ausentes',
        message=(
            f"Os seguintes pacotes não estão instalados:\n\n"
            f"{nomes}\n\n"
            "Deseja instalá-los agora via pip?"
        ),
        icon='warning',
    )

    if not resposta:
        messagebox.showinfo(
            'Instalação cancelada',
            'A aplicação não pode ser iniciada sem as dependências.\n'
            'Instale manualmente com:\n\n'
            + '  '.join(f"pip install {p['pip_name']}" for p in ausentes),
        )
        root.destroy()
        return False

    # ── Instala cada pacote ausente ─────────────────────────────────────────
    erros = []
    for pkg in ausentes:
        try:
            subprocess.check_call(
                [sys.executable, '-m', 'pip', 'install', pkg['pip_name']],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError:
            erros.append(pkg['nome_exibicao'])

    if erros:
        messagebox.showerror(
            'Erro na instalação',
            'Falha ao instalar:\n\n'
            + '\n'.join(f'  • {e}' for e in erros)
            + '\n\nInstale manualmente e reinicie a aplicação.',
        )
        root.destroy()
        return False

    messagebox.showinfo(
        'Instalação concluída',
        'Todos os pacotes foram instalados com sucesso!\n'
        'A aplicação será iniciada agora.',
    )
    root.destroy()
    return True


# Executa a verificação antes de qualquer import externo
if not _verificar_dependencias():
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Imports externos (só chegam aqui se todas as dependências estiverem OK)
# ─────────────────────────────────────────────────────────────────────────────
from tkinter import ttk, filedialog
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.backends.backend_pdf import PdfPages
import tksheet

from truss_input import dataframes_vazios, dataframes_para_trelica
from truss_engine import analise_fea, plotar_trelica, otimizar, ConfigOtimizacao
from truss_canvas import TrussCanvas


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de conversão DataFrame ↔ tksheet
# ─────────────────────────────────────────────────────────────────────────────

def _df_to_rows(df: pd.DataFrame) -> list:
    return [list(r) for r in df.itertuples(index=False)]


def _read_sheet(sheet: tksheet.Sheet, columns: list, dtypes: dict) -> pd.DataFrame:
    """Lê dados do tksheet e retorna DataFrame tipado, descartando linhas vazias."""
    raw = [list(r) for r in sheet.get_sheet_data()]
    # Descarta linhas onde todas as células são vazias
    raw = [r for r in raw if any(c not in ('', None) for c in r)]
    if not raw:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(raw, columns=columns)
    for col, typ in dtypes.items():
        if typ in (int, float):
            df[col] = pd.to_numeric(df[col], errors='coerce')
            if typ == int:
                df[col] = df[col].fillna(0).astype(int)

    # Descarta linhas onde QUALQUER coluna float é NaN
    # (evita guardar linhas em branco cujas colunas int viraram 0 via fillna)
    float_cols = [c for c, t in dtypes.items() if t == float]
    if float_cols:
        df = df.dropna(subset=float_cols, how='any')

    return df.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Distribuição de carga
# ─────────────────────────────────────────────────────────────────────────────

def calcular_forcas_distribuidas(
    df_nos: pd.DataFrame,
    df_barras: pd.DataFrame,
    q_Nm: float,
    descricao_banzo: str,
    dir_x: float = 0.0,
    dir_y: float = -1.0,
) -> pd.DataFrame:
    """
    Converte carga distribuída q (N/m) em forças nodais equivalentes.

    Para cada barra do banzo selecionado, metade da força resultante
    (q × comprimento / 2) é atribuída a cada nó extremo.
    Nós compartilhados por barras adjacentes acumulam as contribuições.
    """
    barras_banzo = df_barras[df_barras['descricao'] == descricao_banzo]
    if barras_banzo.empty:
        return pd.DataFrame(columns=['id_no', 'Fx_N', 'Fy_N'])

    nos_idx = df_nos.set_index('id_no')
    forcas: dict = {}

    for _, barra in barras_banzo.iterrows():
        n1, n2 = int(barra['no_inicio']), int(barra['no_fim'])
        x1, y1 = nos_idx.loc[n1, 'x'], nos_idx.loc[n1, 'y']
        x2, y2 = nos_idx.loc[n2, 'x'], nos_idx.loc[n2, 'y']
        L  = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        dF = q_Nm * L / 2          # contribuição de cada extremidade

        for nid in (n1, n2):
            if nid not in forcas:
                forcas[nid] = [0.0, 0.0]
            forcas[nid][0] += dF * dir_x
            forcas[nid][1] += dF * dir_y

    rows = [{'id_no': nid, 'Fx_N': v[0], 'Fy_N': v[1]}
            for nid, v in sorted(forcas.items())]
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Aplicação principal
# ─────────────────────────────────────────────────────────────────────────────

class TrussApp(tk.Tk):

    _BTN_W = 32

    def __init__(self):
        super().__init__()
        self.title("Otimização de Treliças — PIBIC UNESC")
        self.geometry("1280x740")
        self.minsize(950, 600)

        # ── Estado ─────────────────────────────────────────────────────────
        self.dfs: dict              = dataframes_vazios()
        self.resultado_inicial      = None   # dict de analise_fea
        self.resultado_otimizado    = None   # dict de otimizar
        self._dados_otim_ini        = None   # TrelicaInput no momento da otimização
        self._res_fea_otimizado     = None   # FEA da estrutura otimizada
        self.resultado_snap         = None   # dict de snap_discreto
        self._res_fea_snap          = None   # FEA da estrutura snap-discreta
        self._sheet_ref: tksheet.Sheet = None
        self._fig_ref: plt.Figure      = None

        # Parâmetros normativos — inicializados com defaults NBR 8800 / NBR 16239
        from truss_norma import ParamNorma
        self._param_norma = ParamNorma()

        # Restrições de otimização (configuradas em cmd_param_norma, lidas em cmd_otimizar)
        self._var_desl_ativo     = tk.BooleanVar(value=False)
        self._var_desl_n         = tk.StringVar(value='300')
        self._var_esbeltez_ativo = tk.BooleanVar(value=False)
        self._var_esbeltez_max   = tk.StringVar(value='200')

        # Otimização de forma (geometria) — nós livres e bounds
        self._var_geom_ativo   = tk.BooleanVar(value=False)
        self._var_geom_nos     = tk.StringVar(value='')    # id_no separados por vírgula
        self._var_geom_delta_x = tk.StringVar(value='0.50')  # ±ΔX [m]
        self._var_geom_delta_y = tk.StringVar(value='0.50')  # ±ΔY [m]

        # Indicadores de conclusão de cada etapa de entrada
        # chave → tk.StringVar com símbolo (○ pendente, ✓ concluído)
        self._etapas: dict = {
            'nos':         tk.StringVar(value='○'),
            'barras':      tk.StringVar(value='○'),
            'secoes':      tk.StringVar(value='○'),
            'apoios':      tk.StringVar(value='○'),
            'carregamento':tk.StringVar(value='○'),
        }

        self._build_layout()

    # ── Construção do layout ──────────────────────────────────────────────────

    def _build_layout(self):
        # Barra de status deve ser packed ANTES do frame principal para
        # garantir que reserve espaço antes do expand=True absorver tudo
        self._frm_status = ttk.Frame(self, relief='sunken')
        self._frm_status.pack(side='bottom', fill='x')
        self.status_var = tk.StringVar(value="Pronto — siga a ordem dos botões.")
        ttk.Label(self._frm_status, textvariable=self.status_var,
                  anchor='w', padding=(8, 3)
                  ).pack(side='left', fill='x', expand=True)
        self._progress = ttk.Progressbar(self._frm_status, mode='indeterminate',
                                         length=140, maximum=20)
        # progressbar fica oculto até ser necessário

        root = ttk.Frame(self, padding=6)
        root.pack(fill='both', expand=True)

        # Painel esquerdo — botões (largura fixa, alargado para caber o log)
        self.left = ttk.LabelFrame(root, text="  Ações  ", width=280)
        self.left.pack(side='left', fill='y', padx=(0, 6))
        self.left.pack_propagate(False)

        # Painel direito — área de trabalho
        self.right = ttk.LabelFrame(root, text="  Área de Trabalho  ")
        self.right.pack(side='left', fill='both', expand=True)

        # Frame interno do painel direito (conteúdo substituível)
        self.content = ttk.Frame(self.right)
        self.content.pack(fill='both', expand=True, padx=2, pady=2)

        self._build_buttons()

        # Painel de log de otimização — abaixo dos botões, no painel esquerdo
        ttk.Separator(self.left, orient='horizontal').pack(fill='x', padx=8, pady=4)
        ttk.Label(self.left, text='Log de otimização',
                  font=('Segoe UI', 8, 'bold'), anchor='w'
                  ).pack(fill='x', padx=8)
        frm_log = ttk.Frame(self.left)
        frm_log.pack(fill='both', expand=True, padx=6, pady=(2, 6))
        self._log_text = tk.Text(
            frm_log, height=8, font=('Courier New', 8),
            wrap='none', state='disabled',
            bg='#f5f5f5', fg='#1a1a1a',     # fundo claro, texto escuro
            relief='groove', bd=1,
        )
        _sb_log = ttk.Scrollbar(frm_log, orient='vertical',
                                command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=_sb_log.set)
        _sb_log.pack(side='right', fill='y')
        self._log_text.pack(fill='both', expand=True)

    def _build_buttons(self):
        def sep():
            ttk.Separator(self.left, orient='horizontal').pack(fill='x', padx=8, pady=5)

        # (texto, comando, chave_etapa ou None)
        grupos = [
            [
                ("Abrir Projeto",            self.cmd_abrir_projeto,   None),
                ("Salvar Projeto",           self.cmd_salvar_projeto,  None),
                ("Gerar Relatório PDF",      self.cmd_gerar_relatorio, None),
                ("Configurações",            self.cmd_configuracoes,   None),
                ("Ajuda",                    self.cmd_ajuda,           None),
            ],
            [
                ("1  Inserir Coordenadas",    self.cmd_inserir_nos,        'nos'),
                ("2  Inserir Barras",         self.cmd_inserir_barras,     'barras'),
                ("3  Informar Apoios",        self.cmd_informar_apoios,    'apoios'),
            ],
            [
                ("4  Visualizar Croqui",      self.cmd_visualizar_croqui,      None),
                ("5  Verificar Estaticidade", self.cmd_verificar_estaticidade, None),
            ],
            [
                ("6  Inserir Carregamento",   self.cmd_inserir_carregamento, 'carregamento'),
                ("7  Visualizar Completa",    self.cmd_visualizar_completa,  None),
            ],
            [
                ("8  Dimensionar Estrutura",  self.cmd_dimensionar,  None),
                ("9  Otimizar Estrutura",     self.cmd_otimizar,     None),
                ("10  Resultados",            self.cmd_resultados,     None),
                ("11  Snap Discreto",         self.cmd_snap_discreto,  None),
            ],
        ]

        for i, grupo in enumerate(grupos):
            if i > 0:
                sep()
            for text, cmd, etapa in grupo:
                row = ttk.Frame(self.left)
                row.pack(fill='x', padx=8, pady=2)
                ttk.Button(row, text=text, command=cmd, width=self._BTN_W
                           ).pack(side='left', fill='x', expand=True)
                if etapa:
                    lbl = ttk.Label(row, textvariable=self._etapas[etapa],
                                    width=2, anchor='center',
                                    font=('Segoe UI', 11))
                    lbl.pack(side='left', padx=(3, 0))

    def _marcar_etapa(self, etapa: str):
        """Atualiza o indicador visual de uma etapa (○ → ✓)."""
        if etapa in self._etapas:
            self._etapas[etapa].set('✓')

    # ── Gestão do painel direito ──────────────────────────────────────────────

    def _clear_right(self):
        if self._fig_ref is not None:
            plt.close(self._fig_ref)
            self._fig_ref = None
        for w in self.content.winfo_children():
            w.destroy()
        self._sheet_ref = None

    def _show_sheet(self, df: pd.DataFrame, titulo: str = '',
                    n_linhas_extras: int = 5) -> tksheet.Sheet:
        """Exibe um tksheet editável no painel direito. Retorna a referência."""
        self._clear_right()

        if titulo:
            ttk.Label(self.content, text=titulo,
                      font=('Segoe UI', 11, 'bold')
                      ).pack(anchor='w', padx=8, pady=(6, 2))

        data = _df_to_rows(df) if not df.empty else []
        # Linhas extras em branco para o usuário preencher
        ncols = len(df.columns)
        data += [[''] * ncols for _ in range(n_linhas_extras)]

        sheet = tksheet.Sheet(self.content,
                              data=data,
                              headers=list(df.columns))
        sheet.enable_bindings('all')   # inclui clique-direito → inserir/excluir linha
        sheet.pack(fill='both', expand=True, padx=8, pady=(0, 4))

        # Botão explícito para adicionar linha (mais visível que clique-direito)
        ttk.Button(self.content, text='+ Adicionar linha',
                   command=lambda: sheet.insert_row()
                   ).pack(side='left', padx=8, pady=(0, 4))

        self._sheet_ref = sheet
        return sheet

    def _show_two_sheets(self,
                         df_top: pd.DataFrame, titulo_top: str,
                         df_bot: pd.DataFrame, titulo_bot: str,
                         btn_top_extra=None,
                         ) -> tuple:
        """
        Dois tksheets empilhados num PanedWindow. Retorna (sheet_top, sheet_bot).

        btn_top_extra : (texto, comando) ou lista de (texto, comando) —
                        botões opcionais alinhados à direita no cabeçalho superior.
        """
        self._clear_right()

        pane = tk.PanedWindow(self.content, orient='vertical',
                              sashrelief='raised', sashwidth=5)
        pane.pack(fill='both', expand=True)

        def _make_pane_sheet(parent, df, titulo, height, btn_extra=None):
            frm_tit = ttk.Frame(parent)
            frm_tit.pack(fill='x', padx=6, pady=(4, 2))
            ttk.Label(frm_tit, text=titulo,
                      font=('Segoe UI', 10, 'bold')
                      ).pack(side='left')
            if btn_extra:
                extras = btn_extra if isinstance(btn_extra, list) else [btn_extra]
                for _txt, _cmd in extras:
                    ttk.Button(frm_tit, text=_txt, command=_cmd
                               ).pack(side='right', padx=4)
            data = _df_to_rows(df) if not df.empty else []
            data += [[''] * len(df.columns) for _ in range(4)]
            s = tksheet.Sheet(parent, data=data, headers=list(df.columns),
                              height=height)
            s.enable_bindings('all')
            s.pack(fill='both', expand=True, padx=6, pady=(0, 4))
            ttk.Button(parent, text='+ Adicionar linha',
                       command=lambda sheet=s: sheet.insert_row()
                       ).pack(side='left', padx=6, pady=(0, 4))
            return s

        top_f = ttk.Frame(pane)
        sheet_top = _make_pane_sheet(top_f, df_top, titulo_top,
                                     height=200, btn_extra=btn_top_extra)
        pane.add(top_f, minsize=120)

        bot_f = ttk.Frame(pane)
        sheet_bot = _make_pane_sheet(bot_f, df_bot, titulo_bot, height=300)
        pane.add(bot_f, minsize=150)

        return sheet_top, sheet_bot

    def _show_figure(self, fig: plt.Figure):
        """Incorpora figura matplotlib no painel direito."""
        self._clear_right()
        self._fig_ref = fig
        canvas = FigureCanvasTkAgg(fig, master=self.content)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True, padx=4, pady=4)

    def _show_canvas(self, modo: str, dados, resultado: dict = None):
        """Exibe TrussCanvas interativo no painel direito."""
        self._clear_right()
        tc = TrussCanvas(self.content)
        tc.pack(fill='both', expand=True)
        tc.render(modo, dados, resultado)

    def _show_canvas_2v(self, paineis: list):
        """Exibe 2 TrussCanvas empilhados verticalmente (topo / base)."""
        self._clear_right()
        outer = tk.Frame(self.content, bg='#ebebeb')
        outer.pack(fill='both', expand=True)
        outer.rowconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)

        for i, (modo, dados, resultado, titulo) in enumerate(paineis[:2]):
            cell = tk.Frame(outer, bg='white', bd=1, relief='solid')
            cell.grid(row=i, column=0, sticky='nsew', padx=3, pady=3)
            cell.rowconfigure(1, weight=1)
            cell.columnconfigure(0, weight=1)
            tk.Label(cell, text=titulo,
                     font=('Segoe UI', 9, 'bold'),
                     bg='white', fg='#444444',
                     anchor='w').grid(row=0, column=0, sticky='ew',
                                      padx=8, pady=(4, 0))
            tc = TrussCanvas(cell, bg='white')
            tc.grid(row=1, column=0, sticky='nsew')
            tc.render(modo, dados, resultado)

    def _show_canvas_comparativo(self, paineis: list):
        """
        Exibe até 4 TrussCanvas em grade 2×2 no painel direito.
        paineis: lista de (modo, dados, resultado, titulo)
        """
        self._clear_right()
        outer = tk.Frame(self.content, bg='#ebebeb')
        outer.pack(fill='both', expand=True)
        outer.rowconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)

        for i, (modo, dados, resultado, titulo) in enumerate(paineis[:4]):
            r, c = divmod(i, 2)
            cell = tk.Frame(outer, bg='white', bd=1, relief='solid')
            cell.grid(row=r, column=c, sticky='nsew', padx=3, pady=3)
            cell.rowconfigure(1, weight=1)
            cell.columnconfigure(0, weight=1)

            tk.Label(cell, text=titulo,
                     font=('Segoe UI', 9, 'bold'),
                     bg='white', fg='#444444',
                     anchor='w').grid(row=0, column=0, sticky='ew',
                                      padx=8, pady=(4, 0))

            tc = TrussCanvas(cell, bg='white')
            tc.grid(row=1, column=0, sticky='nsew')
            tc.render(modo, dados, resultado)

    def _confirm_bar(self, command, label='Confirmar e Salvar'):
        """Adiciona botão de confirmação na base do painel direito."""
        ttk.Button(self.content, text=label, command=command
                   ).pack(pady=6)

    def _set_status(self, msg: str):
        self.status_var.set(msg)
        self.update_idletasks()

    def _progress_start(self):
        if self._progress.winfo_exists():
            self._progress.pack(side='right', padx=6, pady=2)
            self._progress.start(12)

    def _progress_stop(self):
        if self._progress.winfo_exists():
            try:
                self._progress.stop()
            except Exception:
                pass
            self._progress.pack_forget()

    def _log_append(self, msg: str):
        """Acrescenta uma linha ao log de otimização no painel esquerdo."""
        if not self._log_text.winfo_exists():
            return
        self._log_text.config(state='normal')
        self._log_text.insert('end', msg + '\n')
        self._log_text.see('end')
        self._log_text.config(state='disabled')

    def _log_clear(self):
        if not self._log_text.winfo_exists():
            return
        self._log_text.config(state='normal')
        self._log_text.delete('1.0', 'end')
        self._log_text.config(state='disabled')

    # ─────────────────────────────────────────────────────────────────────────
    # Comandos — Entrada de dados
    # ─────────────────────────────────────────────────────────────────────────

    # 1 ── Inserir Coordenadas ─────────────────────────────────────────────────

    def cmd_inserir_nos(self):
        sheet = self._show_sheet(
            self.dfs['nos'],
            titulo='Coordenadas dos Nós  —  id_no | x (m) | y (m)',
        )

        def salvar():
            df = _read_sheet(sheet,
                             columns=['id_no', 'x', 'y'],
                             dtypes={'id_no': int, 'x': float, 'y': float})
            if df.empty:
                messagebox.showwarning("Aviso", "Nenhum nó válido para salvar.")
                return
            self.dfs['nos'] = df
            self._marcar_etapa('nos')
            self._set_status(f"Nós salvos — {len(df)} nós definidos.")
            messagebox.showinfo("Salvo", f"{len(df)} nós salvos com sucesso.")

        self._confirm_bar(salvar)
        self._set_status("Preencha as coordenadas e clique em Confirmar.")

    # 2 ── Inserir Barras + Seções ─────────────────────────────────────────────

    def cmd_inserir_barras(self):
        sheet_sec, sheet_bar = self._show_two_sheets(
            self.dfs['secoes'],
            titulo_top='Seções  —  id_secao | Designação | D(mm) | t(mm) | m (kg/m) | A (cm²) | E_GPa',
            df_bot=self.dfs['barras'],
            titulo_bot=(
                'Barras  —  id_barra | no_inicio | no_fim | id_secao | descricao\n'
                'descricao define o grupo para snap discreto: '
                'Banzo inferior | Banzo superior | Diagonal | Montante'
            ),
            btn_top_extra=[
                ('Ver Catálogo', self._abrir_catalogo_perfis),
                ('Inserir do Catálogo', lambda: self._abrir_catalogo_perfis(
                    on_select=self._inserir_perfil_na_secao)),
            ],
        )
        self._sheet_secoes = sheet_sec

        btn_f = ttk.Frame(self.content)
        btn_f.pack(pady=4)

        def salvar_secoes():
            df = _read_sheet(sheet_sec,
                             columns=['id_secao', 'designacao', 'D_mm', 't_mm',
                                      'm_kg_m', 'area_cm2', 'E_GPa'],
                             dtypes={'id_secao': int, 'area_cm2': float, 'E_GPa': float})
            if df.empty:
                messagebox.showwarning("Aviso", "Nenhuma seção válida.")
                return
            for col in ['D_mm', 't_mm', 'm_kg_m']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            self.dfs['secoes'] = df
            self._marcar_etapa('secoes')
            self._set_status(f"Seções salvas — {len(df)} seção(ões).")
            messagebox.showinfo("Salvo", f"{len(df)} seção(ões) salvas.")

        def salvar_barras():
            df = _read_sheet(sheet_bar,
                             columns=['id_barra', 'no_inicio', 'no_fim',
                                      'id_secao', 'descricao'],
                             dtypes={'id_barra': int, 'no_inicio': int,
                                     'no_fim': int, 'id_secao': int,
                                     'descricao': str})
            if df.empty:
                messagebox.showwarning("Aviso", "Nenhuma barra válida.")
                return
            self.dfs['barras'] = df
            self._marcar_etapa('barras')
            self._set_status(f"Barras salvas — {len(df)} barras definidas.")
            messagebox.showinfo("Salvo", f"{len(df)} barras salvas.")

        ttk.Button(btn_f, text='Salvar Seções',  command=salvar_secoes).pack(side='left', padx=6)
        ttk.Button(btn_f, text='Salvar Barras',  command=salvar_barras).pack(side='left', padx=6)
        self._set_status("Preencha seções e barras, salvando cada tabela separadamente.")

    # 3 ── Informar Apoios ─────────────────────────────────────────────────────

    def cmd_informar_apoios(self):
        titulo = (
            'Condições de Contorno\n'
            'restrito_x / restrito_y:  1 = restringido   0 = livre\n'
            'Rolete: (1,0) ou (0,1)  |  Pino / Fixo: (1,1)'
        )
        sheet = self._show_sheet(self.dfs['apoios'], titulo=titulo)

        def salvar():
            df = _read_sheet(sheet,
                             columns=['id_no', 'restrito_x', 'restrito_y'],
                             dtypes={'id_no': int, 'restrito_x': int, 'restrito_y': int})
            if df.empty:
                messagebox.showwarning("Aviso", "Nenhum apoio válido.")
                return
            self.dfs['apoios'] = df
            self._marcar_etapa('apoios')
            self._set_status(f"Apoios salvos — {len(df)} apoio(s).")
            messagebox.showinfo("Salvo", f"{len(df)} apoio(s) salvos.")

        self._confirm_bar(salvar)
        self._set_status("Informe os apoios e clique em Confirmar.")

    # ─────────────────────────────────────────────────────────────────────────
    # Comandos — Visualização e validação
    # ─────────────────────────────────────────────────────────────────────────

    # 4 ── Visualizar Croqui ───────────────────────────────────────────────────

    def cmd_visualizar_croqui(self):
        if not self._validar_basico():
            return
        dados = self._montar_trelica()
        if dados is None:
            return

        self._show_canvas('croqui', dados)
        self._set_status("Croqui geométrico — passe o mouse sobre nós/barras para detalhes. "
                         "Roda = zoom | arrastar = pan.")

    # 5 ── Verificar Estaticidade ──────────────────────────────────────────────

    def cmd_verificar_estaticidade(self):
        if not self._validar_basico():
            return

        m = len(self.dfs['barras'])
        n = len(self.dfs['nos'])
        r = int(
            self.dfs['apoios']['restrito_x'].sum() +
            self.dfs['apoios']['restrito_y'].sum()
        )
        grau = m + r - 2 * n

        if grau == 0:
            titulo = "Estrutura ISOSTÁTICA"
            msg    = f"m + r = 2n  ✓\nm = {m}  |  r = {r}  |  n = {n}"
            ok     = True
        elif grau < 0:
            titulo = "Estrutura LÁBIL — mecanismo!"
            msg    = (f"m + r < 2n  ✗\nm = {m}  |  r = {r}  |  n = {n}\n\n"
                      f"Faltam {abs(grau)} vínculo(s). A estrutura é instável.")
            ok     = False
        else:
            titulo = f"Estrutura HIPERESTÁTICA (grau {grau})"
            msg    = (f"m + r > 2n\nm = {m}  |  r = {r}  |  n = {n}\n\n"
                      f"A estrutura possui {grau} grau(s) de hiperestaticidade.")
            ok     = True

        self._set_status(f"Estaticidade: {titulo}  |  m={m}, r={r}, n={n}")
        if ok:
            messagebox.showinfo(titulo, msg)
        else:
            messagebox.showerror(titulo, msg)

    # ─────────────────────────────────────────────────────────────────────────
    # Comandos — Carregamento
    # ─────────────────────────────────────────────────────────────────────────

    # 6 ── Inserir Carregamento ────────────────────────────────────────────────

    def cmd_inserir_carregamento(self):
        if not self._validar_basico():
            return

        self._clear_right()
        self._set_status("Defina o carregamento: distribuído e/ou concentrado.")

        outer = tk.Frame(self.content)
        outer.pack(fill='both', expand=True)

        # ── Seção: carga distribuída ──────────────────────────────────────────
        f = ttk.Frame(outer, padding=(20, 12, 20, 4))
        f.pack(anchor='n', fill='x')

        ttk.Label(f, text='Carga Distribuída',
                  font=('Segoe UI', 11, 'bold')
                  ).grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 8))

        ttk.Label(f, text='Valor (kN/m):').grid(row=1, column=0, sticky='e', padx=8, pady=4)
        q_var = tk.StringVar(value='10.0')
        ttk.Entry(f, textvariable=q_var, width=14).grid(row=1, column=1, sticky='w')

        ttk.Label(f, text='Direção:').grid(row=2, column=0, sticky='e', padx=8, pady=4)
        dir_var = tk.StringVar(value='-Y  (para baixo)')
        ttk.Combobox(f, textvariable=dir_var, state='readonly', width=22,
                     values=['-Y  (para baixo)', '+Y  (para cima)',
                              '-X  (para esquerda)', '+X  (para direita)']
                     ).grid(row=2, column=1, sticky='w')

        descricoes = (list(self.dfs['barras']['descricao'].dropna().unique())
                      if not self.dfs['barras'].empty else [])
        ttk.Label(f, text='Aplicar em:').grid(row=3, column=0, sticky='e', padx=8, pady=4)
        banzo_var = tk.StringVar(value=descricoes[0] if descricoes else '')
        ttk.Combobox(f, textvariable=banzo_var, state='readonly', width=24,
                     values=descricoes
                     ).grid(row=3, column=1, sticky='w')

        msg_var = tk.StringVar(value='')
        ttk.Label(f, textvariable=msg_var,
                  font=('Segoe UI', 8, 'italic'), foreground='#336699'
                  ).grid(row=5, column=0, columnspan=3, sticky='w', pady=(2, 0))

        # ── Separador + tabela de forças nodais ───────────────────────────────
        ttk.Separator(outer, orient='horizontal').pack(fill='x', padx=10, pady=(6, 2))

        frm_tit = ttk.Frame(outer)
        frm_tit.pack(fill='x', padx=12, pady=(2, 2))
        ttk.Label(frm_tit, text='Forças Nodais',
                  font=('Segoe UI', 11, 'bold')).pack(side='left')
        ttk.Label(frm_tit, text='distribuídas e/ou concentradas  |  unidades: kN',
                  font=('Segoe UI', 8), foreground='#888888').pack(side='left', padx=8)

        # Pré-popula com forças já salvas (N → kN)
        df_f0 = self.dfs['forcas']
        if not df_f0.empty:
            data_ini = [[int(r['id_no']),
                         round(float(r['Fx_N']) / 1e3, 4),
                         round(float(r['Fy_N']) / 1e3, 4)]
                        for _, r in df_f0.iterrows()]
        else:
            data_ini = []
        n_extras = max(4, 8 - len(data_ini))
        data_ini += [['', '', ''] for _ in range(n_extras)]

        sheet_f = tksheet.Sheet(outer,
                                data=data_ini,
                                headers=['id_no', 'Fx (kN)', 'Fy (kN)'],
                                height=200)
        sheet_f.enable_bindings('all')
        sheet_f.pack(fill='both', expand=True, padx=12, pady=(0, 2))

        # ── Helpers ───────────────────────────────────────────────────────────

        def _ler_sheet():
            """Retorna lista de [id_no, Fx_kN, Fy_kN] para linhas não-vazias."""
            rows = []
            for r in sheet_f.get_sheet_data():
                if not any(c not in ('', None) for c in r):
                    continue
                try:
                    rows.append([int(r[0]),
                                 float(str(r[1]).replace(',', '.')),
                                 float(str(r[2]).replace(',', '.'))])
                except (ValueError, TypeError, IndexError):
                    pass
            return rows

        def _merge_distribuida(df_new):
            """Soma forças distribuídas às linhas existentes (acumula por id_no)."""
            current  = _ler_sheet()
            idx_map  = {row[0]: i for i, row in enumerate(current)}
            for _, r in df_new.iterrows():
                no = int(r['id_no'])
                fx = round(float(r['Fx_N']) / 1e3, 4)
                fy = round(float(r['Fy_N']) / 1e3, 4)
                if no in idx_map:
                    current[idx_map[no]][1] = round(current[idx_map[no]][1] + fx, 4)
                    current[idx_map[no]][2] = round(current[idx_map[no]][2] + fy, 4)
                else:
                    current.append([no, fx, fy])
            new_data = [[r[0], r[1], r[2]] for r in current]
            new_data += [['', '', ''] for _ in range(max(0, 4 - len(new_data)))]
            sheet_f.set_sheet_data(new_data)

        # ── Comandos ──────────────────────────────────────────────────────────

        def calcular_dist():
            try:
                q = float(q_var.get().replace(',', '.')) * 1e3
            except ValueError:
                messagebox.showerror("Erro", "Valor de q inválido.")
                return
            dir_map = {
                '-Y  (para baixo)':    ( 0.0, -1.0),
                '+Y  (para cima)':     ( 0.0,  1.0),
                '-X  (para esquerda)': (-1.0,  0.0),
                '+X  (para direita)':  ( 1.0,  0.0),
            }
            dx, dy = dir_map[dir_var.get()]
            df_d = calcular_forcas_distribuidas(
                self.dfs['nos'], self.dfs['barras'],
                q_Nm=q, descricao_banzo=banzo_var.get(),
                dir_x=dx, dir_y=dy,
            )
            if df_d.empty:
                messagebox.showwarning("Aviso",
                    "Nenhum nó encontrado no banzo selecionado.\n"
                    "Verifique se a descrição das barras está correta.")
                return
            _merge_distribuida(df_d)
            msg_var.set(f"✓ {len(df_d)} forças adicionadas à tabela — clique em Salvar para confirmar")

        def salvar():
            rows = _ler_sheet()
            if not rows:
                messagebox.showwarning("Aviso", "Nenhuma força definida na tabela.")
                return
            import pandas as pd
            self.dfs['forcas'] = pd.DataFrame({
                'id_no': [r[0] for r in rows],
                'Fx_N':  [r[1] * 1e3 for r in rows],
                'Fy_N':  [r[2] * 1e3 for r in rows],
            })
            self._marcar_etapa('carregamento')
            self._set_status(f"Carregamento salvo — {len(rows)} força(s) nodal(is).")
            messagebox.showinfo("Salvo", f"{len(rows)} força(s) nodal(is) salva(s).")

        def limpar():
            sheet_f.set_sheet_data([['', '', ''] for _ in range(6)])
            msg_var.set('')

        # ── Botões da seção distribuída (grid) ───────────────────────────────
        frm_dbtn = ttk.Frame(f)
        frm_dbtn.grid(row=4, column=0, columnspan=3, sticky='w', pady=(6, 0))
        ttk.Button(frm_dbtn, text='Calcular e Adicionar à Tabela',
                   command=calcular_dist).pack(side='left', padx=(0, 8))
        ttk.Button(frm_dbtn, text='Limpar Tabela',
                   command=limpar).pack(side='left')

        # ── Botões rodapé ─────────────────────────────────────────────────────
        frm_bot = ttk.Frame(outer)
        frm_bot.pack(fill='x', padx=12, pady=(0, 8))
        ttk.Button(frm_bot, text='+ Adicionar linha',
                   command=lambda: sheet_f.insert_row()).pack(side='left')
        ttk.Button(frm_bot, text='Salvar Carregamento',
                   command=salvar).pack(side='right')

    # ─────────────────────────────────────────────────────────────────────────
    # Comandos — Análise e Otimização
    # ─────────────────────────────────────────────────────────────────────────

    # 7 ── Visualizar Estrutura Completa ───────────────────────────────────────

    def cmd_visualizar_completa(self):
        if not self._validar_completo():
            return
        dados = self._montar_trelica()
        if dados is None:
            return

        self._show_canvas('completa', dados)
        self._set_status("Estrutura completa com cargas — passe o mouse sobre nós/barras. "
                         "Roda = zoom | arrastar = pan.")

    # 8 ── Dimensionar Estrutura ───────────────────────────────────────────────

    def cmd_dimensionar(self):
        if not self._validar_completo():
            return
        dados = self._montar_trelica()
        if dados is None:
            return

        self._set_status("Calculando estrutura — aguarde...")
        try:
            res = analise_fea(dados)
        except Exception as e:
            messagebox.showerror("Erro na análise", str(e))
            self._set_status("Erro na análise estrutural.")
            return

        self.resultado_inicial = res

        # ── Verificação normativa ─────────────────────────────────────────
        from truss_norma import verificar_barras
        norma = verificar_barras(dados, res, self._param_norma)
        self.resultado_inicial['norma'] = norma

        # ── Vista principal: esforços axiais + deformada (layout vertical) ──
        self._show_canvas_2v([
            ('esforcos',  dados, res, 'Esforços Axiais'),
            ('deformada', dados, res, 'Forma Deformada'),
        ])

        # ── Aba FF por barra (matplotlib) em Toplevel ─────────────────────
        self._mostrar_ff_chart(norma, dados.n_el)

        # ── Alertas de esbeltez ───────────────────────────────────────────
        alertas_txt = ''
        if norma['alertas']:
            alertas_txt = '\n\nAlertas:\n' + '\n'.join(f'  {a}' for a in norma['alertas'])

        reprovadas = int((norma['FF_max'] > 1.0).sum())
        W = float(res['compliance'])
        V = dados.volume_total()

        self._set_status(
            f"Dimensionamento concluído  |  FF máx = {norma['FF_global']:.3f}  "
            f"| Barras reprovadas: {reprovadas}  |  V = {V*1e6:.2f} cm³")
        messagebox.showinfo(
            "Dimensionamento concluído",
            f"Compliance:          {W:.4e} J\n"
            f"Volume total:        {V*1e6:.2f} cm³\n\n"
            f"── Verificação NBR ──────────────────\n"
            f"fy = {self._param_norma.fy/1e6:.0f} MPa  |  "
            f"γa1 = {self._param_norma.gama_a1}  |  "
            f"Curva {self._param_norma.curva.upper()}  |  "
            f"Seção: {self._param_norma.tipo_secao}\n\n"
            f"FF global (pior barra): {norma['FF_global']:.3f}  "
            + ('✓ OK' if norma['FF_global'] <= 1.0 else '✗ REPROVADO')
            + f"\nBarras reprovadas: {reprovadas} / {n_el}"
            + alertas_txt
            + "\n\nSalvo como benchmark para a otimização."
        )

    def cmd_visualizar_deformada(self):
        """Exibe a forma deformada da estrutura (requer dimensionamento prévio)."""
        if self.resultado_inicial is None:
            messagebox.showinfo(
                "Deformada",
                "Execute '8 Dimensionar Estrutura' antes de visualizar a deformada."
            )
            return
        dados = self._montar_trelica()
        if dados is None:
            return
        self._show_canvas('deformada', dados, self.resultado_inicial)
        u_max_mm = float(
            abs(self.resultado_inicial['deslocamentos']).max()
        ) * 1e3
        self._set_status(
            f"Deformada — δ_max = {u_max_mm:.4f} mm  |  "
            "Use o slider para ajustar a amplificação visual."
        )

    def _mostrar_ff_chart(self, norma, n_el: int):
        """Abre Toplevel com gráfico de barras de FF por barra (matplotlib)."""
        top = tk.Toplevel(self.root)
        top.title("Fator de Falha por Barra")
        top.geometry("750x340")

        fig, ax = plt.subplots(figsize=(9, 3.5))
        FF    = norma['FF_max']
        cores = ['#d62728' if ff > 1.0 else '#2ca02c' if ff < 0.8
                 else '#ff7f0e' for ff in FF]
        ax.bar(range(n_el), FF, color=cores, edgecolor='none', width=0.8)
        ax.axhline(1.0, color='red',    lw=1.5, ls='--', label='Limite (FF=1,0)')
        ax.axhline(0.8, color='orange', lw=1.0, ls=':',  label='Alerta (FF=0,8)')
        ax.set_xlabel('Barra')
        ax.set_ylabel('FF')
        ax.set_title(
            f'Verificação NBR 8800 / NBR 16239  —  FF máx = {norma["FF_global"]:.3f}'
            + ('  ✓ OK' if norma['FF_global'] <= 1.0 else '  ✗ REPROVADO'),
            fontsize=9)
        ax.set_xlim(-0.5, n_el - 0.5)
        ax.set_ylim(0, max(float(FF.max()) * 1.15, 1.1))
        ax.legend(fontsize=8)
        ax.grid(axis='y', alpha=0.3)
        fig.tight_layout()

        cv = FigureCanvasTkAgg(fig, master=top)
        cv.draw()
        cv.get_tk_widget().pack(fill='both', expand=True)
        top.protocol('WM_DELETE_WINDOW', lambda: (plt.close(fig), top.destroy()))

    # 9 ── Otimizar Estrutura ──────────────────────────────────────────────────

    # 10 ── Resultados ─────────────────────────────────────────────────────────

    def cmd_resultados(self):
        """Reabre o comparativo 2×2 e a janela de log da última otimização."""
        if self.resultado_otimizado is None or self._dados_otim_ini is None:
            messagebox.showinfo(
                "Sem resultados",
                "Nenhuma otimização foi executada nesta sessão.\n"
                "Execute 'Otimizar Estrutura' primeiro."
            )
            return
        dados_ini = self._dados_otim_ini
        dados_opt = self.resultado_otimizado['dados_otimizados']
        self._show_canvas_comparativo([
            ('esforcos', dados_ini, self.resultado_inicial,  'Inicial — Esforços'),
            ('croqui',   dados_ini, None,                    'Inicial — Croqui'),
            ('esforcos', dados_opt, self._res_fea_otimizado, 'Otimizado — Esforços'),
            ('croqui',   dados_opt, None,                    'Otimizado — Croqui'),
        ])
        V_i = dados_ini.volume_total()
        self._mostrar_log_otimizacao(self.resultado_otimizado, V_i, dados_ini)

    # 11 ── Snap Discreto ─────────────────────────────────────────────────────

    def cmd_snap_discreto(self):
        """Mapeia as áreas contínuas otimizadas para perfis comerciais do catálogo."""
        if self.resultado_otimizado is None or self._dados_otim_ini is None:
            messagebox.showinfo(
                "Snap Discreto",
                "Execute 'Otimizar Estrutura' antes de realizar o snap discreto."
            )
            return

        from truss_catalogo import snap_discreto, carregar_catalogo
        from truss_input import extrair_grupos

        dados_otim = self.resultado_otimizado['dados_otimizados']
        grupos = extrair_grupos(self.dfs['barras'])

        if not grupos:
            if not messagebox.askyesno(
                "Grupos não definidos",
                "Nenhum grupo encontrado na coluna 'grupo' das barras.\n\n"
                "Cada barra será tratada individualmente (snap solo).\n\n"
                "Deseja continuar?"
            ):
                return

        self._set_status("Snap discreto em andamento...")
        self.update_idletasks()

        try:
            catalogo = carregar_catalogo()
            resultado = snap_discreto(
                dados_otim,
                grupos=grupos,
                param_norma=self._param_norma,
                catalogo=catalogo,
            )
        except Exception as e:
            messagebox.showerror("Erro — Snap Discreto", str(e))
            self._set_status("Erro no snap discreto.")
            return

        self.resultado_snap = resultado
        self._set_status(
            f"Snap discreto concluído — "
            f"Vol: {resultado['volume_discreto']*1e6:.1f} cm³  |  "
            f"Massa: {resultado['massa_total_kg']:.1f} kg"
        )
        self._mostrar_resultado_snap(resultado, grupos)

    def _mostrar_resultado_snap(self, resultado, grupos):
        """Exibe janela com os perfis selecionados e FF final por barra."""
        import tkinter as tk
        from tkinter import ttk

        win = tk.Toplevel(self)
        win.title("Snap Discreto — Perfis Comerciais Selecionados")
        win.geometry("820x540")

        nb = ttk.Notebook(win)
        nb.pack(fill='both', expand=True, padx=6, pady=6)

        # ── Aba 1: Perfis por grupo ───────────────────────────────────────────
        frm1 = ttk.Frame(nb)
        nb.add(frm1, text='Perfis por Grupo')

        cols1 = ('Grupo', 'Perfil', 'D (mm)', 't (mm)', 'A (cm²)', 'r (cm)', 'm (kg/m)')
        tree1 = ttk.Treeview(frm1, columns=cols1, show='headings', height=12)
        for c in cols1:
            tree1.heading(c, text=c)
            tree1.column(c, width=105, anchor='center')
        tree1.column('Grupo',  width=130, anchor='w')
        tree1.column('Perfil', width=130, anchor='w')

        for nome, perfil in resultado['perfis_grupos'].items():
            tree1.insert('', 'end', values=(
                nome,
                perfil['designacao'],
                f"{perfil['d_mm']:.1f}",
                f"{perfil['t_mm']:.1f}",
                f"{perfil['A_cm2']:.2f}",
                f"{perfil['r_cm']:.2f}",
                f"{perfil['m_kg_m']:.2f}",
            ))

        sb1 = ttk.Scrollbar(frm1, orient='vertical', command=tree1.yview)
        tree1.configure(yscrollcommand=sb1.set)
        tree1.pack(side='left', fill='both', expand=True)
        sb1.pack(side='right', fill='y')

        # ── Aba 2: FF por barra ───────────────────────────────────────────────
        frm2 = ttk.Frame(nb)
        nb.add(frm2, text='FF por Barra')

        cols2 = ('Barra', 'Grupo', 'Perfil', 'A (cm²)', '%', 'Status')
        tree2 = ttk.Treeview(frm2, columns=cols2, show='headings', height=18)
        for c in cols2:
            tree2.heading(c, text=c)
            tree2.column(c, width=110, anchor='center')
        tree2.column('Barra',  width=60)
        tree2.column('Grupo',  width=120, anchor='w')
        tree2.column('Perfil', width=130, anchor='w')

        perfis_por_barra = resultado['perfis_por_barra']
        FF_por_barra     = resultado['FF_por_barra']

        barra_para_grupo = {i: g for g, idxs in grupos.items() for i in idxs}
        for i in range(len(perfis_por_barra)):
            uc     = FF_por_barra[i]
            status = '✓' if uc <= 1.0 else '✗ REPROVA'
            tag    = 'ok' if uc <= 1.0 else 'fail'
            nome_g = barra_para_grupo.get(i, '(solo)')
            # área do perfil em cm²
            A_cm2_str = ''
            for nome, p in resultado['perfis_grupos'].items():
                if nome == nome_g:
                    A_cm2_str = f"{p['A_cm2']:.2f}"
                    break
            tree2.insert('', 'end', tags=(tag,), values=(
                i,
                nome_g,
                perfis_por_barra[i],
                A_cm2_str,
                f"{uc*100:.1f}",
                status,
            ))

        tree2.tag_configure('ok',   background='#e8f5e9')
        tree2.tag_configure('fail', background='#ffebee')

        sb2 = ttk.Scrollbar(frm2, orient='vertical', command=tree2.yview)
        tree2.configure(yscrollcommand=sb2.set)
        tree2.pack(side='left', fill='both', expand=True)
        sb2.pack(side='right', fill='y')

        # ── Rodapé com resumo ────────────────────────────────────────────────
        resumo = ttk.Frame(win)
        resumo.pack(fill='x', padx=10, pady=6)

        V_cont = self._dados_otim_ini.volume_total() if self._dados_otim_ini else 0
        V_disc = resultado['volume_discreto']
        massa  = resultado['massa_total_kg']
        n_iter = resultado['iteracoes']
        n_repr = int((FF_por_barra > 1.0).sum())

        ttk.Label(resumo, text=(
            f"Volume contínuo: {V_cont*1e6:.1f} cm³   →   "
            f"Volume discreto: {V_disc*1e6:.1f} cm³   |   "
            f"Massa: {massa:.1f} kg   |   "
            f"Iterações snap: {n_iter}   |   "
            f"Barras reprovadas: {n_repr}"
        ), font=('Segoe UI', 9)).pack(anchor='w')

        # ── Botão de aceite ─────────────────────────────────────────────────
        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill='x', padx=10, pady=(2, 10))
        ttk.Button(
            btn_frame,
            text="✔  Aceitar e Dimensionar com Snap",
            command=lambda: self._aceitar_snap(resultado, win),
        ).pack(side='right')

    def _aceitar_snap(self, resultado_snap, win):
        """Roda FEA + norma com as áreas discretas do snap e exibe comparativo."""
        from truss_norma import verificar_barras

        dados_disc = resultado_snap['dados_discretos']

        self._set_status("Dimensionando com perfis do snap — aguarde...")
        self.update_idletasks()
        try:
            res_fea = analise_fea(dados_disc)
            norma   = verificar_barras(dados_disc, res_fea, self._param_norma)
            res_fea['norma'] = norma
        except Exception as e:
            messagebox.showerror("Erro — Snap Dimensionamento", str(e))
            self._set_status("Erro no dimensionamento snap.")
            return

        # Mapa área → designação CHS para exibição na legenda do croqui
        res_fea['perfis_snap'] = {
            round(float(a), 8): d
            for a, d in zip(dados_disc.areas,
                            resultado_snap['perfis_por_barra'])
        }

        self._res_fea_snap = res_fea
        win.destroy()

        n_repr = int((norma['FF_max'] > 1.0).sum())
        FF_max = float(norma['FF_max'].max())
        self._set_status(
            f"Snap dimensionado — FF_max: {FF_max:.3f}  |  "
            f"Barras reprovadas: {n_repr}  |  "
            f"Vol: {dados_disc.volume_total()*1e6:.1f} cm³"
        )

        dados_opt = self.resultado_otimizado['dados_otimizados']
        self._show_canvas_comparativo([
            ('esforcos', dados_opt,  self._res_fea_otimizado, 'Otimizado — Esforços'),
            ('croqui',   dados_opt,  None,                    'Otimizado — Croqui'),
            ('esforcos', dados_disc, res_fea,                 'Snap Discreto — Esforços'),
            ('croqui',   dados_disc, res_fea,                 'Snap Discreto — Croqui'),
        ])

    # ── Catálogo de perfis ────────────────────────────────────────────────────

    def _abrir_catalogo_perfis(self, on_select=None):
        """Abre janela com o catálogo CHS Vallourec.

        on_select : callable(row_dict) | None
            Se fornecido, habilita seleção por duplo-clique; recebe dict com
            todas as colunas do catálogo. Fácil de adaptar: mude apenas o que
            _inserir_perfil_na_secao faz com o dict, sem tocar aqui.
        """
        import tkinter as tk
        from tkinter import ttk
        from truss_catalogo import carregar_catalogo

        try:
            cat = carregar_catalogo()
        except Exception as e:
            messagebox.showerror("Catálogo", f"Erro ao carregar catálogo:\n{e}")
            return

        win = tk.Toplevel(self)
        win.title("Catálogo de Perfis — CHS Vallourec")
        win.geometry("900x540")

        # Filtro por diâmetro
        frm_fil = ttk.Frame(win)
        frm_fil.pack(fill='x', padx=8, pady=(8, 2))
        ttk.Label(frm_fil, text="Filtrar por diâmetro (mm):").pack(side='left')
        diams = ['Todos'] + [str(d) for d in sorted(cat['d_mm'].unique())]
        diam_var = tk.StringVar(value='Todos')
        cb = ttk.Combobox(frm_fil, textvariable=diam_var, values=diams,
                          state='readonly', width=10)
        cb.pack(side='left', padx=6)

        cols = ('designacao', 'd_mm', 't_mm', 'm_kg_m', 'A_cm2', 'r_cm',
                'I_cm4', 'W_cm3', 'U_m2m')
        hdrs = ('Designação', 'D (mm)', 't (mm)', 'm (kg/m)', 'A (cm²)',
                'r (cm)', 'I (cm⁴)', 'W (cm³)', 'U (m²/m)')

        frm_tree = ttk.Frame(win)
        frm_tree.pack(fill='both', expand=True, padx=8, pady=4)

        tree = ttk.Treeview(frm_tree, columns=cols, show='headings')
        tree.column('designacao', width=130, anchor='w')
        for c in cols:
            tree.column(c, width=85, anchor='center')
        tree.column('designacao', width=130, anchor='w')   # reafirma após loop

        vsb = ttk.Scrollbar(frm_tree, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')

        # Ordenação por coluna — estado por coluna (False = crescente)
        _sort_rev: dict = {}

        def _sort_col(col):
            rev = not _sort_rev.get(col, False)
            _sort_rev[col] = rev
            data = [(tree.set(child, col), child) for child in tree.get_children('')]
            try:
                data.sort(key=lambda t: float(str(t[0]).replace(',', '.')), reverse=rev)
            except ValueError:
                data.sort(key=lambda t: str(t[0]).lower(), reverse=rev)
            for i, (_, child) in enumerate(data):
                tree.move(child, '', i)
            arrow = ' ↓' if rev else ' ↑'
            for c, h in zip(cols, hdrs):
                tree.heading(c, text=(h + arrow) if c == col else h,
                             command=lambda cc=c: _sort_col(cc))

        for c, h in zip(cols, hdrs):
            tree.heading(c, text=h, command=lambda cc=c: _sort_col(cc))

        def _preencher(d_filter='Todos'):
            tree.delete(*tree.get_children())
            _sort_rev.clear()
            for c, h in zip(cols, hdrs):
                tree.heading(c, text=h, command=lambda cc=c: _sort_col(cc))
            df = cat if d_filter == 'Todos' else cat[cat['d_mm'] == float(d_filter)]
            for _, row in df.iterrows():
                tree.insert('', 'end', values=(
                    row['designacao'],
                    f"{row['d_mm']:.1f}",
                    f"{row['t_mm']:.1f}",
                    f"{row['m_kg_m']:.2f}",
                    f"{row['A_cm2']:.2f}",
                    f"{row['r_cm']:.2f}",
                    f"{row['I_cm4']:.0f}",
                    f"{row['W_cm3']:.1f}",
                    f"{row['U_m2m']:.3f}",
                ))

        cb.bind('<<ComboboxSelected>>', lambda _e: _preencher(diam_var.get()))
        _preencher()

        # Seleção por duplo-clique (só quando on_select fornecido)
        if on_select is not None:
            def _on_double(event):
                sel = tree.selection()
                if not sel:
                    return
                vals = tree.item(sel[0])['values']
                if vals:
                    on_select(dict(zip(cols, vals)))
                    win.destroy()

            tree.bind('<Double-Button-1>', _on_double)

        frm_rod = ttk.Frame(win)
        frm_rod.pack(fill='x', padx=8, pady=(0, 6))
        ttk.Label(frm_rod,
                  text=f"Total: {len(cat)} perfis  |  Fonte: Vallourec — Tubos Estruturais (TC)",
                  font=('Segoe UI', 8), foreground='gray'
                  ).pack(side='left')
        if on_select is not None:
            ttk.Label(frm_rod,
                      text="Duplo-clique para inserir na tabela de seções",
                      font=('Segoe UI', 8, 'italic'), foreground='#336699'
                      ).pack(side='right')

    def _inserir_perfil_na_secao(self, row: dict):
        """Insere um perfil do catálogo na tabela de seções.

        Recebe o dict completo da linha selecionada — chaves: designacao, d_mm,
        t_mm, m_kg_m, A_cm2, r_cm, I_cm4, W_cm3, U_m2m.
        Para mudar o que é inserido, edite apenas esta função;
        _abrir_catalogo_perfis não precisa ser tocada.
        """
        sheet = getattr(self, '_sheet_secoes', None)
        if sheet is None:
            return
        area_cm2   = float(str(row.get('A_cm2',  '0')).replace(',', '.'))
        designacao = str(row.get('designacao', ''))
        d_mm       = row.get('d_mm',   '')
        t_mm_val   = row.get('t_mm',   '')
        m_kg_m     = row.get('m_kg_m', '')
        data = [list(r) for r in sheet.get_sheet_data()]
        for idx, r in enumerate(data):
            if not any(c not in ('', None) for c in r):
                sheet.set_row_data(idx, [idx + 1, designacao, d_mm, t_mm_val,
                                         m_kg_m, f'{area_cm2:.2f}', '200.0'])
                return
        sheet.insert_row(values=[len(data) + 1, designacao, d_mm, t_mm_val,
                                  m_kg_m, f'{area_cm2:.2f}', '200.0'])

    def cmd_otimizar(self):
        if self.resultado_inicial is None:
            messagebox.showwarning(
                "Benchmark ausente",
                "Execute 'Dimensionar Estrutura' antes de otimizar."
            )
            return

        dados = self._montar_trelica()
        if dados is None:
            return

        # Bounds: área pode reduzir até 30% da menor seção atual, crescer 3×
        A_min = max(dados.areas.min() * 0.3, 1e-4)
        A_max = dados.areas.max() * 3.0

        # Restrição δ_adm
        n_desl    = 0.0
        delta_adm = None
        if self._var_desl_ativo.get():
            try:
                n_desl = float(self._var_desl_n.get())
                if n_desl > 0:
                    span      = float(dados.nos[:, 0].max() - dados.nos[:, 0].min())
                    delta_adm = span / n_desl
            except ValueError:
                pass

        # Restrição kL/r
        esbeltez_max = None
        if self._var_esbeltez_ativo.get():
            try:
                esbeltez_max = float(self._var_esbeltez_max.get())
            except ValueError:
                pass

        # Otimização de forma — nós livres e bounds
        nos_livres  = []
        bounds_nos  = []
        geom_dx = geom_dy = 0.0
        if self._var_geom_ativo.get():
            try:
                geom_dx = float(self._var_geom_delta_x.get())
                geom_dy = float(self._var_geom_delta_y.get())
                raw = self._var_geom_nos.get().strip()
                if raw:
                    # converte id_no → índice posicional (mesmo critério de truss_input)
                    nos_ord    = self.dfs['nos'].sort_values('id_no').reset_index(drop=True)
                    id_para_idx = {int(r.id_no): i for i, r in nos_ord.iterrows()}
                    for tok in raw.split(','):
                        tok = tok.strip()
                        if not tok:
                            continue
                        id_no = int(tok)
                        if id_no not in id_para_idx:
                            continue
                        idx = id_para_idx[id_no]
                        x0, y0 = float(dados.nos[idx, 0]), float(dados.nos[idx, 1])
                        nos_livres.append(idx)
                        bounds_nos += [(x0 - geom_dx, x0 + geom_dx),
                                       (y0 - geom_dy, y0 + geom_dy)]
            except ValueError:
                pass

        n_vars_geom = len(nos_livres) * 2

        cfg = ConfigOtimizacao(
            otimizar_areas=True,
            otimizar_geometria=bool(nos_livres),
            bounds_areas=[(A_min, A_max)] * dados.n_el,
            nos_geometria_livre=nos_livres,
            bounds_nos=bounds_nos,
            objetivo='volume',
            usar_restricoes_norma=True,
            param_norma=self._param_norma,
            restricao_deslocamento_adm=delta_adm,
            restricao_esbeltez_max=esbeltez_max,
        )

        # Prepara log e indicadores
        self._log_clear()
        self._log_append('▶ Otimizador iniciado')
        n_vars_total = dados.n_el + n_vars_geom
        if n_vars_geom:
            self._log_append(
                f'  Barras: {dados.n_el}   Variáveis: {n_vars_total}'
                f' ({dados.n_el} áreas + {n_vars_geom} coords)'
            )
        else:
            self._log_append(f'  Barras: {dados.n_el}   Variáveis: {n_vars_total}')
        self._log_append(f'  Vol. inicial: {dados.volume_total()*1e6:.1f} cm³')
        if nos_livres:
            self._log_append(
                f'  Nós livres: {[self.dfs["nos"].sort_values("id_no").iloc[i]["id_no"] for i in nos_livres]}'
                f'  ΔX=±{geom_dx:.2f}m  ΔY=±{geom_dy:.2f}m'
            )
        if delta_adm is not None:
            self._log_append(f'  δ_adm: L/{n_desl:.0f} = {delta_adm*1e3:.1f} mm')
        if esbeltez_max is not None:
            self._log_append(f'  kL/r ≤ {esbeltez_max:.0f}')
        self._log_append('─' * 32)
        self._set_status("Otimizando — aguarde...")
        self._progress_start()

        # callback_iter: chamado pelo engine a cada iteração (thread separada)
        # usa self.after() para atualizar a GUI de forma segura
        def _on_iter(n, vol_m3, compliance):
            def _update():
                self._log_append(
                    f'  Iter {n:>3} | Vol {vol_m3*1e6:>9.2f} cm³ | '
                    f'C {compliance:.3e}'
                )
                self._set_status(
                    f"Otimizando — iteração {n} | "
                    f"Volume: {vol_m3*1e6:.1f} cm³"
                )
            self.after(0, _update)

        _dados = dados
        _cfg   = cfg
        self._dados_otim_ini = dados   # guarda para o botão Resultados

        def _run():
            try:
                res = otimizar(_dados, _cfg, callback_iter=_on_iter)
            except Exception as exc:
                self.after(0, lambda: self._otim_erro(str(exc)))
                return
            self.after(0, lambda: self._otim_concluido(res, _dados))

        threading.Thread(target=_run, daemon=True).start()

    def _otim_erro(self, msg: str):
        self._progress_stop()
        self._log_append('─' * 32)
        self._log_append(f'✗ ERRO: {msg}')
        messagebox.showerror("Erro na otimização", msg)
        self._set_status("Erro na otimização.")

    def _otim_concluido(self, res_opt: dict, dados):
        """Chamado na thread principal via after() quando a otimização termina."""
        self._progress_stop()
        conv  = res_opt['sucesso']
        nit   = res_opt['resultado_scipy'].nit
        V_o   = res_opt['volume_final']
        V_i   = dados.volume_total()
        self._log_append('─' * 32)
        self._log_append(f'{"✓" if conv else "~"} Concluído — {nit} iterações')
        self._log_append(f'  Vol final: {V_o*1e6:.2f} cm³  ({(V_o/V_i-1)*100:+.1f}%)')
        if not conv:
            self._log_append(f'  ⚠ {res_opt["mensagem"]}')
        self.resultado_otimizado = res_opt
        dados_opt = res_opt['dados_otimizados']
        res_fea   = analise_fea(dados_opt)
        self._res_fea_otimizado = res_fea

        # Quatro painéis Canvas 2×2: esforços e croqui, inicial e otimizado
        self._show_canvas_comparativo([
            ('esforcos', dados,     self.resultado_inicial, 'Inicial — Esforços'),
            ('croqui',   dados,     None,                   'Inicial — Croqui'),
            ('esforcos', dados_opt, res_fea,                'Otimizado — Esforços'),
            ('croqui',   dados_opt, None,                   'Otimizado — Croqui'),
        ])

        # Métricas comparativas
        V_i  = dados.volume_total()
        V_o  = res_opt['volume_final']
        dV   = (V_o / V_i - 1) * 100
        W_i  = float(self.resultado_inicial['compliance'])
        W_o  = float(res_opt['compliance_final'])
        dW   = (W_o / W_i - 1) * 100
        nit  = res_opt['resultado_scipy'].nit
        conv = "Sim" if res_opt['sucesso'] else "Não"
        rho_aco = 7850.0
        m_i = V_i * rho_aco
        m_o = V_o * rho_aco

        self._set_status(
            f"Otimização concluída  |  "
            f"Volume: {V_i*1e6:.1f} → {V_o*1e6:.1f} cm³  ({dV:+.1f}%)  |  "
            f"{nit} iterações  |  Convergiu: {conv}"
        )

        messagebox.showinfo(
            "Otimização concluída",
            f"{'─'*44}\n"
            f" VOLUME DE AÇO\n"
            f"{'─'*44}\n"
            f"  Inicial:   {V_i*1e6:10.2f} cm³   ({m_i:.2f} kg)\n"
            f"  Otimizado: {V_o*1e6:10.2f} cm³   ({m_o:.2f} kg)\n"
            f"  Variação:  {dV:+10.1f} %\n"
            f"\n"
            f"{'─'*44}\n"
            f" COMPLIANCE (rigidez global)\n"
            f"{'─'*44}\n"
            f"  Inicial:   {W_i:10.4e} J\n"
            f"  Otimizado: {W_o:10.4e} J\n"
            f"  Variação:  {dW:+10.1f} %\n"
            f"\n"
            f"{'─'*44}\n"
            f"  Iterações : {nit}\n"
            f"  Convergiu : {conv}\n"
            f"  Msg scipy : {res_opt['mensagem']}\n"
        )

        # Exibe log de iterações em janela separada
        self._mostrar_log_otimizacao(res_opt, V_i, dados)

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers internos
    # ─────────────────────────────────────────────────────────────────────────

    def _mostrar_log_otimizacao(self, res_opt: dict, V_inicial: float,
                                 dados_ini) -> None:
        """Exibe janela com log de iterações e comparativo de áreas por barra."""
        win = tk.Toplevel(self)
        win.title("Log da Otimização")
        win.geometry("720x560")
        win.resizable(True, True)
        win.lift()
        win.focus_set()

        nb = ttk.Notebook(win)
        nb.pack(fill='both', expand=True, padx=6, pady=6)

        # ── Aba 1: log de iterações ───────────────────────────────────────────
        frm_log = ttk.Frame(nb)
        nb.add(frm_log, text="Iterações")

        txt = tk.Text(frm_log, font=('Courier New', 9), wrap='none')
        sb_v = ttk.Scrollbar(frm_log, orient='vertical',   command=txt.yview)
        sb_h = ttk.Scrollbar(frm_log, orient='horizontal', command=txt.xview)
        txt.configure(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)
        sb_v.pack(side='right', fill='y')
        sb_h.pack(side='bottom', fill='x')
        txt.pack(fill='both', expand=True)

        hist = res_opt.get('historico', [])
        header = f"{'Iter':>5}  {'Volume (cm³)':>14}  {'Compliance (J)':>16}  {'Var.Vol (%)':>11}\n"
        sep    = "─" * 54 + "\n"
        txt.insert('end', header)
        txt.insert('end', sep)
        for h in hist:
            dv = (h['volume_m3'] / V_inicial - 1) * 100
            linha = (f"{h['iter']:>5}  "
                     f"{h['volume_m3']*1e6:>14.2f}  "
                     f"{h['compliance']:>16.4e}  "
                     f"{dv:>+11.2f}\n")
            txt.insert('end', linha)

        txt.insert('end', sep)
        nit  = res_opt['resultado_scipy'].nit
        conv = "Sim" if res_opt['sucesso'] else f"Não — {res_opt['mensagem']}"
        txt.insert('end', f"  Total iterações: {nit}    Convergiu: {conv}\n")
        txt.config(state='disabled')

        # ── Aba 2: comparativo de áreas por barra ────────────────────────────
        frm_areas = ttk.Frame(nb)
        nb.add(frm_areas, text="Áreas por Barra")

        cols = ('Barra', 'Área ini (cm²)', 'Área oti (cm²)', 'Variação (%)')
        tree = ttk.Treeview(frm_areas, columns=cols, show='headings', height=20)
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=140, anchor='center')

        A_ini = dados_ini.areas
        A_oti = res_opt['dados_otimizados'].areas
        rows_areas = []
        for el in range(len(A_ini)):
            dA = (A_oti[el] / A_ini[el] - 1) * 100
            row = (el, f"{A_ini[el]*1e4:.4f}", f"{A_oti[el]*1e4:.4f}", f"{dA:+.1f}")
            rows_areas.append(row)
            tree.insert('', 'end', values=row)
        sb2 = ttk.Scrollbar(frm_areas, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=sb2.set)
        sb2.pack(side='right', fill='y')
        tree.pack(fill='both', expand=True)

        # ── Funções de exportação CSV ─────────────────────────────────────────
        def _exportar_iteracoes():
            path = filedialog.asksaveasfilename(
                parent=win, defaultextension='.csv',
                filetypes=[('CSV', '*.csv')],
                initialfile='otimizacao_iteracoes.csv',
                title='Exportar Iterações')
            if not path:
                return
            with open(path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['iter', 'volume_cm3', 'compliance_J', 'var_vol_pct'])
                for h in hist:
                    dv = (h['volume_m3'] / V_inicial - 1) * 100
                    w.writerow([h['iter'],
                                f"{h['volume_m3']*1e6:.4f}",
                                f"{h['compliance']:.6e}",
                                f"{dv:.4f}"])
            messagebox.showinfo("Exportado", f"Arquivo salvo:\n{path}", parent=win)

        def _exportar_areas():
            path = filedialog.asksaveasfilename(
                parent=win, defaultextension='.csv',
                filetypes=[('CSV', '*.csv')],
                initialfile='otimizacao_areas.csv',
                title='Exportar Áreas por Barra')
            if not path:
                return
            with open(path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['barra', 'area_ini_cm2', 'area_oti_cm2', 'variacao_pct'])
                for row in rows_areas:
                    w.writerow(row)
            messagebox.showinfo("Exportado", f"Arquivo salvo:\n{path}", parent=win)

        # ── Rodapé da janela ──────────────────────────────────────────────────
        frm_btn = ttk.Frame(win)
        frm_btn.pack(fill='x', padx=6, pady=(0, 6))
        ttk.Button(frm_btn, text="Exportar Iterações (CSV)",
                   command=_exportar_iteracoes).pack(side='left', padx=4)
        ttk.Button(frm_btn, text="Exportar Áreas (CSV)",
                   command=_exportar_areas).pack(side='left', padx=4)
        ttk.Button(frm_btn, text="Fechar",
                   command=win.destroy).pack(side='right', padx=4)

    def _validar_basico(self) -> bool:
        """Verifica nós, barras, seções e apoios."""
        for key, nome in [('nos',    'Coordenadas dos nós'),
                          ('barras', 'Barras'),
                          ('secoes', 'Seções'),
                          ('apoios', 'Apoios')]:
            if self.dfs[key].empty:
                messagebox.showwarning(
                    "Dados insuficientes",
                    f"'{nome}' ainda não foram preenchidos.\n"
                    "Siga a ordem dos botões."
                )
                return False
        return True

    def _validar_completo(self) -> bool:
        """Verifica todos os dados incluindo forças."""
        if not self._validar_basico():
            return False
        if self.dfs['forcas'].empty:
            messagebox.showwarning(
                "Dados insuficientes",
                "Insira o carregamento (botão 6) antes de prosseguir."
            )
            return False
        return True

    def _montar_trelica(self):
        """Converte DataFrames → TrelicaInput com tratamento de erro."""
        try:
            return dataframes_para_trelica(
                self.dfs['nos'],
                self.dfs['barras'],
                self.dfs['secoes'],
                self.dfs['forcas'],
                self.dfs['apoios'],
            )
        except Exception as e:
            messagebox.showerror("Erro ao montar a treliça", str(e))
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Arquivo — Salvar / Abrir / Relatório
    # ─────────────────────────────────────────────────────────────────────────

    def cmd_configuracoes(self):
        """Janela de configurações: norma, material e seção transversal."""
        from truss_norma import ParamNorma

        win = tk.Toplevel(self)
        win.title("Configurações de Análise")
        win.resizable(False, False)
        win.geometry("520x420")
        win.grab_set()   # modal

        nb = ttk.Notebook(win)
        nb.pack(fill='both', expand=True, padx=8, pady=8)

        p = self._param_norma   # referência atual

        # ── Aba: Norma ────────────────────────────────────────────────────
        frm_norma = ttk.Frame(nb, padding=12)
        nb.add(frm_norma, text='  Norma  ')

        ttk.Label(frm_norma, text='Norma aplicável:',
                  font=('Segoe UI', 10, 'bold')).grid(row=0, column=0,
                  columnspan=2, sticky='w', pady=(0, 8))

        norma_var = tk.StringVar(value='NBR 8800:2024 + NBR 16239:2013 (perfis tubulares)')
        normas_disp = [
            'NBR 8800:2024 + NBR 16239:2013 (perfis tubulares)',
            # futuras implementações:
            # 'NBR 8800:2024 — perfis laminados (I/H)',
            # 'NBR 8800:2024 — perfis dobrados a frio',
        ]
        cb_norma = ttk.Combobox(frm_norma, textvariable=norma_var,
                                values=normas_disp, state='readonly', width=48)
        cb_norma.grid(row=1, column=0, columnspan=2, sticky='w', pady=2)

        ttk.Separator(frm_norma, orient='horizontal').grid(
            row=2, column=0, columnspan=2, sticky='ew', pady=10)

        ttk.Label(frm_norma, text='Curva de flambagem (Tabela 5.1 NBR 8800):',
                  font=('Segoe UI', 9)).grid(row=3, column=0, sticky='w')
        curva_var = tk.StringVar(value=p.curva)
        curvas = [('a  — α=0,21  (tubulares CHS/SHS)', 'a'),
                  ('b  — α=0,34', 'b'),
                  ('c  — α=0,49', 'c'),
                  ('d  — α=0,76', 'd')]
        frm_curvas = ttk.Frame(frm_norma)
        frm_curvas.grid(row=4, column=0, columnspan=2, sticky='w', pady=4)
        for txt, val in curvas:
            ttk.Radiobutton(frm_curvas, text=txt, variable=curva_var,
                            value=val).pack(anchor='w')

        ttk.Separator(frm_norma, orient='horizontal').grid(
            row=5, column=0, columnspan=2, sticky='ew', pady=10)

        ttk.Label(frm_norma, text='Coeficientes de ponderação (γ):',
                  font=('Segoe UI', 9)).grid(row=6, column=0, sticky='w')
        frm_gama = ttk.Frame(frm_norma)
        frm_gama.grid(row=7, column=0, columnspan=2, sticky='w', pady=4)

        gama_a1_var = tk.StringVar(value=str(p.gama_a1))
        gama_a2_var = tk.StringVar(value=str(p.gama_a2))
        k_var       = tk.StringVar(value=str(p.k_flambagem))

        for col, (lbl, var) in enumerate([
            ('γa1 (escoamento):', gama_a1_var),
            ('γa2 (ruptura):', gama_a2_var),
            ('k (comprimento efetivo):', k_var),
        ]):
            ttk.Label(frm_gama, text=lbl).grid(row=0, column=col*2, sticky='e', padx=(8,2))
            ttk.Entry(frm_gama, textvariable=var, width=6).grid(row=0, column=col*2+1, padx=(0,8))

        # ── Aba: Material ─────────────────────────────────────────────────
        frm_mat = ttk.Frame(nb, padding=12)
        nb.add(frm_mat, text='  Material  ')

        ttk.Label(frm_mat, text='Propriedades do aço:',
                  font=('Segoe UI', 10, 'bold')).grid(row=0, column=0,
                  columnspan=3, sticky='w', pady=(0, 10))

        campos_mat = [
            ('fy  — tensão de escoamento (MPa):', p.fy / 1e6),
            ('fu  — resistência à ruptura (MPa):', p.fu / 1e6),
            ('E   — módulo de elasticidade (GPa):', p.E / 1e9),
        ]
        fy_var = tk.StringVar(value=str(p.fy / 1e6))
        fu_var = tk.StringVar(value=str(p.fu / 1e6))
        E_var  = tk.StringVar(value=str(p.E  / 1e9))

        for i, (lbl, var) in enumerate(zip(
                [c[0] for c in campos_mat], [fy_var, fu_var, E_var])):
            ttk.Label(frm_mat, text=lbl).grid(row=i+1, column=0, sticky='e', padx=(0,8), pady=4)
            ttk.Entry(frm_mat, textvariable=var, width=10).grid(row=i+1, column=1, sticky='w')

        ttk.Label(frm_mat, text='Aços comuns:', font=('Segoe UI', 9, 'italic'),
                  foreground='gray').grid(row=5, column=0, columnspan=2,
                  sticky='w', pady=(12, 2))
        aceira = [
            ('ASTM A36 / CA-25', 250, 400),
            ('ASTM A572 Gr.50 / CA-50', 345, 450),
            ('API 5L X52', 358, 455),
        ]
        for i, (nome, fy_mpa, fu_mpa) in enumerate(aceira):
            def _preset(fy=fy_mpa, fu=fu_mpa):
                fy_var.set(str(fy)); fu_var.set(str(fu))
            ttk.Button(frm_mat, text=nome, command=_preset, width=28
                       ).grid(row=6+i, column=0, columnspan=2, sticky='w', pady=1)

        # ── Aba: Seção Transversal ────────────────────────────────────────
        frm_sec = ttk.Frame(nb, padding=12)
        nb.add(frm_sec, text='  Seção  ')

        ttk.Label(frm_sec, text='Tipo de seção transversal:',
                  font=('Segoe UI', 10, 'bold')).grid(row=0, column=0,
                  columnspan=2, sticky='w', pady=(0, 8))

        tipo_var = tk.StringVar(value=p.tipo_secao)
        tipos = [
            ('CHS — Circular Hollow Section (tubo redondo)',  'CHS'),
            ('SHS — Square Hollow Section   (tubo quadrado)', 'SHS'),
            ('Barra sólida circular',                         'solida_circular'),
        ]
        for i, (txt, val) in enumerate(tipos):
            ttk.Radiobutton(frm_sec, text=txt, variable=tipo_var,
                            value=val).grid(row=i+1, column=0, columnspan=2,
                            sticky='w', pady=2)

        ttk.Separator(frm_sec, orient='horizontal').grid(
            row=5, column=0, columnspan=2, sticky='ew', pady=10)

        beta_var = tk.StringVar(value=str(p.beta_td))
        ttk.Label(frm_sec, text='β = t/D  (relação espessura/diâmetro para CHS/SHS):',
                  ).grid(row=6, column=0, sticky='w')
        ttk.Entry(frm_sec, textvariable=beta_var, width=8
                  ).grid(row=6, column=1, sticky='w', padx=6)
        ttk.Label(frm_sec, text='Faixa típica: 0,05 a 0,12',
                  foreground='gray', font=('Segoe UI', 8)
                  ).grid(row=7, column=0, columnspan=2, sticky='w')

        # ── Aba: Restrições ────────────────────────────────────────────────
        frm_rest = ttk.Frame(nb, padding=12)
        nb.add(frm_rest, text='  Restrições  ')

        ttk.Label(frm_rest, text='Restrições de otimização (etapa 9):',
                  font=('Segoe UI', 10, 'bold')).grid(
                  row=0, column=0, columnspan=3, sticky='w', pady=(0, 6))

        ttk.Separator(frm_rest, orient='horizontal').grid(
            row=1, column=0, columnspan=3, sticky='ew', pady=(0, 6))

        ttk.Checkbutton(frm_rest, text='Limitar deslocamento máximo',
                        variable=self._var_desl_ativo).grid(
                        row=2, column=0, columnspan=3, sticky='w')
        ttk.Label(frm_rest, text='   δ_adm = vão / ').grid(
                  row=3, column=0, sticky='e', padx=(20, 2), pady=4)
        ttk.Entry(frm_rest, textvariable=self._var_desl_n, width=7).grid(
                  row=3, column=1, sticky='w')
        ttk.Label(frm_rest, text='(ex: 250, 300, 400)',
                  foreground='gray', font=('Segoe UI', 8)).grid(
                  row=3, column=2, sticky='w', padx=6)

        ttk.Separator(frm_rest, orient='horizontal').grid(
            row=4, column=0, columnspan=3, sticky='ew', pady=8)

        ttk.Checkbutton(frm_rest, text='Limitar esbeltez máxima  k·L/r',
                        variable=self._var_esbeltez_ativo).grid(
                        row=5, column=0, columnspan=3, sticky='w')
        ttk.Label(frm_rest, text='   k·L/r ≤ ').grid(
                  row=6, column=0, sticky='e', padx=(20, 2), pady=4)
        ttk.Entry(frm_rest, textvariable=self._var_esbeltez_max, width=7).grid(
                  row=6, column=1, sticky='w')
        ttk.Label(frm_rest, text='NBR 8800 item 5.3.2: ≤ 200',
                  foreground='gray', font=('Segoe UI', 8)).grid(
                  row=6, column=2, sticky='w', padx=6)

        ttk.Separator(frm_rest, orient='horizontal').grid(
            row=7, column=0, columnspan=3, sticky='ew', pady=(8, 4))

        ttk.Label(frm_rest,
                  text='k e β utilizados: definidos nas abas Norma / Seção.',
                  foreground='gray', font=('Segoe UI', 8)).grid(
                  row=8, column=0, columnspan=3, sticky='w')

        # ── Aba: Geometria ────────────────────────────────────────────────
        frm_geom = ttk.Frame(nb, padding=12)
        nb.add(frm_geom, text='  Geometria  ')

        ttk.Label(frm_geom, text='Otimização de forma (etapa 9):',
                  font=('Segoe UI', 10, 'bold')).grid(
                  row=0, column=0, columnspan=3, sticky='w', pady=(0, 6))

        ttk.Separator(frm_geom, orient='horizontal').grid(
            row=1, column=0, columnspan=3, sticky='ew', pady=(0, 8))

        ttk.Checkbutton(frm_geom, text='Incluir otimização de forma (mover nós)',
                        variable=self._var_geom_ativo).grid(
                        row=2, column=0, columnspan=3, sticky='w')

        ttk.Separator(frm_geom, orient='horizontal').grid(
            row=3, column=0, columnspan=3, sticky='ew', pady=8)

        ttk.Label(frm_geom, text='Nós livres (id_no, separados por vírgula):',
                  ).grid(row=4, column=0, columnspan=3, sticky='w', pady=(0, 4))

        frm_nos_row = ttk.Frame(frm_geom)
        frm_nos_row.grid(row=5, column=0, columnspan=3, sticky='ew', pady=(0, 4))

        nos_entry = ttk.Entry(frm_nos_row, textvariable=self._var_geom_nos, width=30)
        nos_entry.pack(side='left', padx=(0, 6))

        def _auto_detectar_nos():
            try:
                apoio_ids = set(self.dfs['apoios']['id_no'].astype(int).tolist())
                todos_ids = sorted(self.dfs['nos']['id_no'].astype(int).tolist())
                livres = [str(n) for n in todos_ids if n not in apoio_ids]
                self._var_geom_nos.set(', '.join(livres))
            except Exception:
                messagebox.showwarning(
                    "Sem dados", "Carregue os nós e apoios antes de auto-detectar.",
                    parent=win)

        ttk.Button(frm_nos_row, text='Auto', command=_auto_detectar_nos, width=6
                   ).pack(side='left')
        ttk.Label(frm_nos_row, text='(nós sem apoio)',
                  foreground='gray', font=('Segoe UI', 8)).pack(side='left', padx=6)

        ttk.Separator(frm_geom, orient='horizontal').grid(
            row=6, column=0, columnspan=3, sticky='ew', pady=8)

        ttk.Label(frm_geom, text='Deslocamento máximo por nó (relativo à posição inicial):'
                  ).grid(row=7, column=0, columnspan=3, sticky='w', pady=(0, 6))

        ttk.Label(frm_geom, text='±ΔX  ').grid(row=8, column=0, sticky='e', padx=(20, 2))
        ttk.Entry(frm_geom, textvariable=self._var_geom_delta_x, width=8
                  ).grid(row=8, column=1, sticky='w')
        ttk.Label(frm_geom, text='m', foreground='gray', font=('Segoe UI', 8)
                  ).grid(row=8, column=2, sticky='w', padx=4)

        ttk.Label(frm_geom, text='±ΔY  ').grid(row=9, column=0, sticky='e', padx=(20, 2), pady=4)
        ttk.Entry(frm_geom, textvariable=self._var_geom_delta_y, width=8
                  ).grid(row=9, column=1, sticky='w')
        ttk.Label(frm_geom, text='m', foreground='gray', font=('Segoe UI', 8)
                  ).grid(row=9, column=2, sticky='w', padx=4)

        ttk.Separator(frm_geom, orient='horizontal').grid(
            row=10, column=0, columnspan=3, sticky='ew', pady=(8, 4))

        ttk.Label(frm_geom,
                  text='Bounds absolutos = posição inicial ± ΔX / ΔY.\n'
                       'Use ΔX=0 para nós que só podem mover verticalmente.',
                  foreground='gray', font=('Segoe UI', 8)).grid(
                  row=11, column=0, columnspan=3, sticky='w')

        # ── Botões Aplicar / Cancelar ─────────────────────────────────────
        frm_btn = ttk.Frame(win)
        frm_btn.pack(fill='x', padx=8, pady=(0, 10))

        def _aplicar():
            try:
                self._param_norma = ParamNorma(
                    fy          = float(fy_var.get()) * 1e6,
                    fu          = float(fu_var.get()) * 1e6,
                    E           = float(E_var.get())  * 1e9,
                    gama_a1     = float(gama_a1_var.get()),
                    gama_a2     = float(gama_a2_var.get()),
                    k_flambagem = float(k_var.get()),
                    curva       = curva_var.get(),
                    tipo_secao  = tipo_var.get(),
                    beta_td     = float(beta_var.get()),
                    beta_td_shs = float(beta_var.get()),
                )
                self._set_status(
                    f"Configurações aplicadas — Norma: {norma_var.get().split('(')[0].strip()}  "
                    f"| fy={float(fy_var.get()):.0f} MPa  | seção: {tipo_var.get()}")
                win.destroy()
            except ValueError as e:
                messagebox.showerror("Valor inválido", str(e), parent=win)

        ttk.Button(frm_btn, text='Aplicar', command=_aplicar, width=14
                   ).pack(side='right', padx=4)
        ttk.Button(frm_btn, text='Cancelar', command=win.destroy, width=14
                   ).pack(side='right')

    def cmd_ajuda(self):
        win = tk.Toplevel(self)
        win.title("Ajuda — Treliça Plana 2D")
        win.resizable(True, True)
        win.geometry("660x560")

        nb = ttk.Notebook(win)
        nb.pack(fill='both', expand=True, padx=8, pady=8)

        # ── aba: Fluxo de trabalho ─────────────────────────────────────────
        frm_fluxo = ttk.Frame(nb)
        nb.add(frm_fluxo, text="Fluxo de Trabalho")

        txt_fluxo = (
            "FLUXO RECOMENDADO\n"
            "═══════════════════════════════════════════════════════\n\n"
            "① Inserir Coordenadas\n"
            "   Informe cada nó com id, x e y (em metros).\n"
            "   Os índices devem começar em 0 e ser sequenciais.\n\n"
            "② Inserir Barras\n"
            "   Defina a conectividade: id da barra, nó inicial,\n"
            "   nó final, id da seção e uma descrição opcional.\n\n"
            "③ Informar Apoios\n"
            "   Indique para cada nó de apoio quais direções são\n"
            "   restritas (1 = restrito, 0 = livre).\n"
            "   • Pino:       restrito_x=1, restrito_y=1\n"
            "   • Rolete Y:   restrito_x=0, restrito_y=1\n"
            "   • Rolete X:   restrito_x=1, restrito_y=0\n\n"
            "④ Visualizar Croqui\n"
            "   Exibe apenas a geometria (nós, barras e apoios).\n"
            "   Use para confirmar o lançamento antes de continuar.\n\n"
            "⑤ Verificar Estaticidade\n"
            "   Confere a condição m + r = 2n.\n"
            "   Estrutura isostática: OK para prosseguir.\n\n"
            "⑥ Inserir Carregamento\n"
            "   Informe as forças nodais em Newtons (Fx e Fy).\n"
            "   Forças para baixo → Fy negativo.\n\n"
            "⑦ Visualizar Estrutura Completa\n"
            "   Exibe geometria + apoios + forças aplicadas.\n\n"
            "⑧ Dimensionar Estrutura\n"
            "   Executa a análise por Elementos Finitos (FEA).\n"
            "   Exibe deslocamentos e esforços internos (N) por barra.\n\n"
            "⑨ Otimizar Estrutura\n"
            "   Minimiza o volume de aço (∝ massa e custo) sujeito a\n"
            "   restrições de resistência por barra (FF ≤ 1,0, NBR 8800).\n"
        )

        txt_w = tk.Text(frm_fluxo, wrap='word', font=('Courier New', 10),
                        relief='flat', bg=frm_fluxo.cget('bg'))
        txt_w.insert('1.0', txt_fluxo)
        txt_w.config(state='disabled')
        sb = ttk.Scrollbar(frm_fluxo, command=txt_w.yview)
        txt_w.config(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        txt_w.pack(fill='both', expand=True, padx=6, pady=6)

        # ── aba: Seções ────────────────────────────────────────────────────
        frm_sec = ttk.Frame(nb)
        nb.add(frm_sec, text="Seções Transversais")

        txt_sec = (
            "SEÇÕES TRANSVERSAIS\n"
            "═══════════════════════════════════════════════════════\n\n"
            "As seções são referenciadas nas barras pelo campo id_secao.\n"
            "Você pode ter quantas seções quiser.\n\n"
            "Campos obrigatórios:\n"
            "  • id_secao  — índice inteiro (0, 1, 2...)\n"
            "  • area_cm2  — área da seção em cm²  (conversão interna: ×1e-4 → m²)\n"
            "                Exemplo: TC 48,3x4,0 → A = 5,52 cm²\n"
            "  • E_GPa     — módulo de elasticidade em GPa  (conversão interna: ×1e9 → Pa)\n"
            "                Aço:     200 GPa\n"
            "                Madeira:  12 GPa\n\n"
            "Dica: use seções distintas para banzo, diagonal e vertical\n"
            "se quiser controlar o dimensionamento por grupo.\n"
        )

        txt_w2 = tk.Text(frm_sec, wrap='word', font=('Courier New', 10),
                         relief='flat', bg=frm_sec.cget('bg'))
        txt_w2.insert('1.0', txt_sec)
        txt_w2.config(state='disabled')
        sb2 = ttk.Scrollbar(frm_sec, command=txt_w2.yview)
        txt_w2.config(yscrollcommand=sb2.set)
        sb2.pack(side='right', fill='y')
        txt_w2.pack(fill='both', expand=True, padx=6, pady=6)

        # ── aba: Arquivo ────────────────────────────────────────────────────
        frm_arq = ttk.Frame(nb)
        nb.add(frm_arq, text="Salvar / Abrir")

        txt_arq = (
            "GERENCIAMENTO DE ARQUIVOS\n"
            "═══════════════════════════════════════════════════════\n\n"
            "Salvar Projeto\n"
            "   Grava todos os dados em um arquivo .trelica (JSON).\n"
            "   O arquivo pode ser aberto em qualquer editor de texto.\n\n"
            "Abrir Projeto\n"
            "   Carrega um arquivo .trelica salvo anteriormente.\n"
            "   Os indicadores ○/✓ são atualizados automaticamente.\n\n"
            "Gerar Relatório PDF\n"
            "   Cria um memorial de cálculo em PDF com:\n"
            "   • Tabelas de nós, barras, seções, apoios e forças\n"
            "   • Croqui geométrico\n"
            "   • Diagrama de esforços (se dimensionado)\n"
            "   • Comparativo antes/depois da otimização (se otimizado)\n"
        )

        txt_w3 = tk.Text(frm_arq, wrap='word', font=('Courier New', 10),
                         relief='flat', bg=frm_arq.cget('bg'))
        txt_w3.insert('1.0', txt_arq)
        txt_w3.config(state='disabled')
        sb3 = ttk.Scrollbar(frm_arq, command=txt_w3.yview)
        txt_w3.config(yscrollcommand=sb3.set)
        sb3.pack(side='right', fill='y')
        txt_w3.pack(fill='both', expand=True, padx=6, pady=6)

        ttk.Button(win, text="Fechar", command=win.destroy).pack(pady=(0, 8))

    def cmd_salvar_projeto(self):
        path = filedialog.asksaveasfilename(
            title='Salvar projeto',
            defaultextension='.trelica',
            filetypes=[('Projeto Treliça', '*.trelica'), ('JSON', '*.json')],
        )
        if not path:
            return
        data = {key: df.to_dict(orient='records') for key, df in self.dfs.items()}
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._set_status(f"Projeto salvo em {path}")
        messagebox.showinfo("Salvo", f"Projeto salvo com sucesso:\n{path}")

    def cmd_abrir_projeto(self):
        path = filedialog.askopenfilename(
            title='Abrir projeto',
            filetypes=[('Projeto Treliça', '*.trelica'), ('JSON', '*.json')],
        )
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Erro ao abrir", str(e))
            return

        vazios = dataframes_vazios()
        for key in vazios:
            if key in data:
                self.dfs[key] = pd.DataFrame(data[key])

        # Migração: area_m2/E_Pa → area_cm2/E_GPa (arquivos pré-v0.8)
        sec = self.dfs['secoes']
        if 'area_m2' in sec.columns and 'area_cm2' not in sec.columns:
            sec = sec.rename(columns={'area_m2': 'area_cm2'})
            sec['area_cm2'] = sec['area_cm2'] * 1e4
        if 'E_Pa' in sec.columns and 'E_GPa' not in sec.columns:
            sec = sec.rename(columns={'E_Pa': 'E_GPa'})
            sec['E_GPa'] = sec['E_GPa'] * 1e-9
        # Migração: adiciona colunas de perfil se ausentes (arquivos pré-v0.9.5)
        for col, default in [('designacao', ''), ('D_mm', float('nan')),
                              ('t_mm', float('nan')), ('m_kg_m', float('nan'))]:
            if col not in sec.columns:
                sec = sec.copy()
                sec[col] = default
        cols_order = ['id_secao', 'designacao', 'D_mm', 't_mm', 'm_kg_m', 'area_cm2', 'E_GPa']
        sec = sec.reindex(columns=[c for c in cols_order if c in sec.columns])
        self.dfs['secoes'] = sec

        # Atualiza indicadores
        mapa = {'nos': 'nos', 'barras': 'barras', 'secoes': 'secoes',
                'apoios': 'apoios', 'forcas': 'carregamento'}
        for df_key, etapa in mapa.items():
            if not self.dfs[df_key].empty:
                self._marcar_etapa(etapa)

        self._set_status(f"Projeto carregado: {path}")
        messagebox.showinfo("Aberto", f"Projeto carregado com sucesso:\n{path}")

    def cmd_gerar_relatorio(self):
        path = filedialog.asksaveasfilename(
            title='Salvar relatório PDF',
            defaultextension='.pdf',
            filetypes=[('PDF', '*.pdf')],
        )
        if not path:
            return

        tem_resultado = self.resultado_inicial is not None
        dados = self._montar_trelica() if not self.dfs['nos'].empty else None

        with PdfPages(path) as pdf:

            # ── Página 1: tabelas de dados ─────────────────────────────────
            fig = plt.figure(figsize=(11.69, 8.27))   # A4 paisagem
            fig.suptitle('Memorial de Cálculo — Treliça Plana 2D',
                         fontsize=14, fontweight='bold', y=0.98)

            tabelas = [
                ('Nós',    self.dfs['nos']),
                ('Barras', self.dfs['barras']),
                ('Seções', self.dfs['secoes']),
                ('Apoios', self.dfs['apoios']),
                ('Forças nodais (N)', self.dfs['forcas']),
            ]
            n_tab = len(tabelas)
            for i, (titulo, df) in enumerate(tabelas):
                ax = fig.add_subplot(2, 3, i + 1)
                ax.axis('off')
                ax.set_title(titulo, fontsize=9, fontweight='bold', pad=4)
                if df.empty:
                    ax.text(0.5, 0.5, '(sem dados)', ha='center', va='center',
                            fontsize=8, color='gray', transform=ax.transAxes)
                else:
                    tbl = ax.table(
                        cellText=df.values.tolist(),
                        colLabels=list(df.columns),
                        loc='center', cellLoc='center',
                    )
                    tbl.auto_set_font_size(False)
                    tbl.set_fontsize(7)
                    tbl.auto_set_column_width(list(range(len(df.columns))))

            fig.tight_layout(rect=[0, 0, 1, 0.96])
            pdf.savefig(fig)
            plt.close(fig)

            # ── Página 2: croqui + estrutura completa ─────────────────────
            if dados is not None:
                fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11.69, 8.27))
                plotar_trelica(dados, titulo='Croqui da Estrutura',
                               ax=ax1, mostrar_elementos=False)
                plotar_trelica(dados,
                               titulo='Estrutura Completa — cargas, apoios e elementos',
                               ax=ax2, mostrar_elementos=True,
                               mostrar_forcas=True, mostrar_apoios=True)
                fig.tight_layout(pad=2.0)
                pdf.savefig(fig)
                plt.close(fig)

            # ── Página 3: resultados do dimensionamento ────────────────────
            if tem_resultado and dados is not None:
                res = self.resultado_inicial
                fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11.69, 8.27))
                fig.suptitle(
                    f"Dimensionamento Inicial  |  "
                    f"Compliance = {res['compliance']:.4e} J  |  "
                    f"Volume = {dados.volume_total()*1e6:.2f} cm³",
                    fontsize=10, y=0.99)
                plotar_trelica(dados, res,
                               titulo='Esforços Axiais  (azul=tração | vermelho=compressão)',
                               ax=ax1)

                # Tabela de esforços internos
                ax2.axis('off')
                ax2.set_title('Esforços Internos por Barra', fontsize=9,
                              fontweight='bold')
                N   = res['forcas_internas']
                desloc = res['deslocamentos'].flatten()
                rows = [[i, f'{N[i]/1e3:.3f}',
                          'Tração' if N[i] >= 0 else 'Compressão']
                        for i in range(len(N))]
                tbl = ax2.table(
                    cellText=rows,
                    colLabels=['Barra', 'N (kN)', 'Tipo'],
                    loc='center', cellLoc='center',
                )
                tbl.auto_set_font_size(False)
                tbl.set_fontsize(7)
                tbl.auto_set_column_width([0, 1, 2])
                fig.tight_layout(rect=[0, 0, 1, 0.97], pad=2.0)
                pdf.savefig(fig)
                plt.close(fig)

            # ── Página 4: comparativo otimização ──────────────────────────
            if self.resultado_otimizado is not None and dados is not None:
                res_opt   = self.resultado_otimizado
                dados_opt = res_opt['dados_otimizados']
                res_fea   = analise_fea(dados_opt)
                V_i_pdf = dados.volume_total()
                V_o_pdf = float(res_opt['volume_final'])
                W_i_pdf = float(self.resultado_inicial['compliance'])
                W_o_pdf = float(res_opt['compliance_final'])

                fig, axes = plt.subplots(2, 2, figsize=(11.69, 8.27))
                fig.suptitle(
                    f"Otimização  |  Volume: {V_i_pdf*1e6:.1f} → {V_o_pdf*1e6:.1f} cm³  "
                    f"({(V_o_pdf/V_i_pdf-1)*100:+.1f}%)   "
                    f"Compliance: {W_i_pdf:.3e} → {W_o_pdf:.3e} J",
                    fontsize=10, y=0.99)
                plotar_trelica(dados,     self.resultado_inicial,
                               titulo='Inicial — Esforços', ax=axes[0, 0])
                plotar_trelica(dados,
                               titulo='Inicial — Croqui',   ax=axes[0, 1],
                               mostrar_elementos=False, mostrar_forcas=False)
                plotar_trelica(dados_opt, res_fea,
                               titulo='Otimizado — Esforços', ax=axes[1, 0])
                plotar_trelica(dados_opt,
                               titulo='Otimizado — Croqui',   ax=axes[1, 1],
                               mostrar_elementos=False, mostrar_forcas=False)
                fig.tight_layout(rect=[0, 0, 1, 0.96], pad=2.0)
                pdf.savefig(fig)
                plt.close(fig)

        self._set_status(f"Relatório gerado: {path}")
        messagebox.showinfo("Relatório gerado",
                            f"PDF salvo com sucesso:\n{path}")


# ─────────────────────────────────────────────────────────────────────────────

def main():
    app = TrussApp()
    app.mainloop()


if __name__ == '__main__':
    main()
