"""
truss_canvas.py
---------------
Renderizador interativo de treliças usando tkinter Canvas.

Classe pública
--------------
    TrussCanvas  — widget Canvas com zoom (roda), pan (arrastar),
                   tooltips por hover em nós e barras e popup por
                   duplo clique.

Modos de renderização
---------------------
    'croqui'   — geometria, apoios, grid, comprimentos de barra,
                 números de nós e barras; barras coloridas e com
                 espessura proporcional por seção (área única)
    'completa' — croqui + setas de força com labels em kN
    'esforcos'  — barras coloridas por N (azul = tração / vermelho = compressão),
                  espessura proporcional ao esforço, apoios, reações (se disponíveis),
                  números de barras, grid, colorbar
    'deformada' — ghost cinza (posição original) + estrutura deslocada em azul;
                  setas laranja do nó original ao deformado; slider de amplificação
                  com valor inicial auto-calculado (δ_max ≈ 15 % do vão)
"""

import math
import tkinter as tk
import numpy as np


# ---------------------------------------------------------------------------
# Helpers de cor e largura
# ---------------------------------------------------------------------------

def _axial_color(N: float, N_max: float) -> str:
    if N_max < 1e-12:
        return '#4477aa'
    t = max(-1.0, min(1.0, N / N_max))
    if t >= 0:        # tração (N > 0) → azul
        v = int(255 * (1.0 - t * 0.85))
        return f'#{v:02x}{v:02x}ff'
    else:             # compressão (N < 0) → vermelho
        v = int(255 * (1.0 + t * 0.85))
        return f'#ff{v:02x}{v:02x}'


def _axial_width(N: float, N_max: float,
                 w_min: float = 1.5, w_max: float = 5.5) -> float:
    if N_max < 1e-12:
        return w_min
    return w_min + (w_max - w_min) * abs(N) / N_max


def _pt_seg_dist(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax)*dx + (py - ay)*dy) / (dx*dx + dy*dy)))
    return math.hypot(px - ax - t*dx, py - ay - t*dy)


# Paleta discreta para identificar seções transversais distintas
_PALETA_SECOES = [
    '#2196F3', '#F44336', '#4CAF50', '#FF9800', '#9C27B0',
    '#00BCD4', '#FF5722', '#607D8B', '#E91E63', '#795548',
]


# ---------------------------------------------------------------------------
# Widget TrussCanvas
# ---------------------------------------------------------------------------

class TrussCanvas(tk.Canvas):
    """
    Canvas interativo para visualização de treliças planas 2D.
    Zoom com roda do mouse, pan com clique-arrasto, tooltip por hover.
    """

    _PAD   = 0.15   # padding lateral relativo ao span
    _HIT   = 12     # raio de detecção hover (px)
    _NR    = 4      # raio dos pontos de nó (px)

    def __init__(self, parent, **kw):
        kw.setdefault('bg', 'white')
        kw.setdefault('cursor', 'crosshair')
        super().__init__(parent, **kw)

        self._dados     = None
        self._resultado = None
        self._modo      = None

        # Slider de amplificação (modo deformada)
        self._var_escala       = None
        self._scale_widget     = None
        self._escala_deformada = 1.0

        # Transformação afim: mundo (m) → tela (px)
        self._scale = 1.0
        self._ox    = 0.0   # offset X
        self._oy    = 0.0   # offset Y (referência: y=0 do modelo → pixel calculado)

        # Estado do pan
        self._pan_sx = 0;  self._pan_sy = 0
        self._pan_ox = 0.0; self._pan_oy = 0.0

        self.bind('<Configure>',        self._on_resize)
        self.bind('<MouseWheel>',       self._on_zoom)
        self.bind('<Button-4>',         self._on_zoom)       # Linux scroll up
        self.bind('<Button-5>',         self._on_zoom)       # Linux scroll down
        self.bind('<ButtonPress-1>',    self._on_pan_start)
        self.bind('<B1-Motion>',        self._on_pan)
        self.bind('<Motion>',           self._on_hover)
        self.bind('<Leave>',            self._hide_tip)
        self.bind('<Double-Button-1>',  self._open_popup)

    # ── API pública ──────────────────────────────────────────────────────────

    def render(self, modo: str, dados, resultado: dict = None):
        self._modo      = modo
        self._dados     = dados
        self._resultado = resultado

        if modo == 'deformada' and resultado and 'deslocamentos' in resultado:
            u     = np.asarray(resultado['deslocamentos']).ravel()
            max_u = float(np.abs(u).max())
            nos   = dados.nos
            span  = max(nos[:, 0].max() - nos[:, 0].min(),
                        nos[:, 1].max() - nos[:, 1].min(), 1e-6)
            auto  = max(1, int((span * 0.15) / max_u) if max_u > 1e-12 else 100)
            self._init_escala_slider(auto)

        self.update_idletasks()
        self._fit_view()
        self._redraw()

    # ── Transformação mundo ↔ tela ───────────────────────────────────────────

    def _w2s(self, x: float, y: float):
        sx = x * self._scale + self._ox
        sy = self.winfo_height() - (y * self._scale + self._oy)
        return sx, sy

    def _s2w(self, sx: float, sy: float):
        x = (sx - self._ox) / self._scale
        y = (self.winfo_height() - sy - self._oy) / self._scale
        return x, y

    def _fit_view(self):
        nos = self._dados.nos
        W   = max(self.winfo_width(),  10)
        H   = max(self.winfo_height(), 10)

        x_min, x_max = nos[:, 0].min(), nos[:, 0].max()
        y_min, y_max = nos[:, 1].min(), nos[:, 1].max()
        span_x = max(x_max - x_min, 1e-6)
        span_y = max(y_max - y_min, 1e-6)

        avail_w = W * (1.0 - 2.0 * self._PAD)
        avail_h = H * 0.55              # 55 % para o modelo; 45 % para apoios/legend

        self._scale = min(avail_w / span_x, avail_h / span_y)

        cx = (x_min + x_max) / 2
        self._ox = W / 2 - cx * self._scale
        self._oy = H * 0.22 - y_min * self._scale  # 22 % de margem inferior

    # ── Popup ampliado ───────────────────────────────────────────────────────

    def _open_popup(self, _event=None):
        if self._dados is None:
            return
        nomes = {'croqui': 'Croqui', 'completa': 'Estrutura com Cargas',
                 'esforcos': 'Esforços Axiais'}
        titulo = nomes.get(self._modo, self._modo)
        top = tk.Toplevel(self.winfo_toplevel())
        top.title(f'Vista Ampliada — {titulo}')
        top.geometry('1050x720')
        top.configure(bg='white')
        tc = TrussCanvas(top, bg='white')
        tc.pack(fill='both', expand=True, padx=4, pady=4)
        tc.render(self._modo, self._dados, self._resultado)

    # ── Redraw completo ───────────────────────────────────────────────────────

    def _redraw(self):
        if self._dados is None:
            return
        self.delete('all')
        self._draw_grid()
        if self._modo == 'deformada':
            self._draw_deformada()
            self._draw_supports()
            self._place_escala_slider()
        else:
            self._draw_bars()
            if self._modo == 'croqui':
                self._draw_bar_lengths()
                self._draw_secoes_legend()
            self._draw_supports()
            self._draw_nodes()
            if self._modo == 'completa':
                self._draw_forces()
            if self._modo == 'esforcos':
                self._draw_reactions()
                self._draw_colorbar()
        self._draw_expand_hint()

    def _draw_expand_hint(self):
        W = max(self.winfo_width(), 200)
        H = max(self.winfo_height(), 200)
        self.create_text(W - 6, H - 6, text='⤢',
                         font=('Segoe UI', 9), fill='#cccccc',
                         anchor='se', tags='expand_hint')

    # ── Slider de amplificação (modo deformada) ───────────────────────────────

    def _init_escala_slider(self, auto: int):
        to_val = max(auto * 5, 500)
        if self._scale_widget is None:
            self._var_escala   = tk.IntVar(value=auto)
            self._scale_widget = tk.Scale(
                self,
                variable=self._var_escala,
                from_=1, to=to_val,
                orient='vertical',
                length=180,
                label='× amp.',
                command=lambda _: self._on_escala_change(),
                bg='#f0f0f0',
                highlightthickness=0,
                troughcolor='#d0d0d0',
                font=('Segoe UI', 7),
            )
        else:
            self._var_escala.set(auto)
            self._scale_widget.config(to=to_val)
        self._escala_deformada = float(auto)

    def _place_escala_slider(self):
        W = max(self.winfo_width(),  200)
        H = max(self.winfo_height(), 200)
        self.create_window(W - 6, H // 2, window=self._scale_widget,
                           anchor='e', tags='slider_win')

    def _on_escala_change(self):
        if self._modo == 'deformada' and self._var_escala:
            self._escala_deformada = float(self._var_escala.get())
            self._redraw()

    # ── Deformada ─────────────────────────────────────────────────────────────

    def _draw_deformada(self):
        if not self._resultado or 'deslocamentos' not in self._resultado:
            return
        nos   = self._dados.nos
        conec = self._dados.conectividade
        u     = np.asarray(self._resultado['deslocamentos']).ravel()
        esc   = self._escala_deformada
        r     = self._NR

        # Nós deformados
        nos_def = nos.copy()
        for i in range(self._dados.n_nos):
            nos_def[i, 0] = nos[i, 0] + esc * float(u[2 * i])
            nos_def[i, 1] = nos[i, 1] + esc * float(u[2 * i + 1])

        # Ghost: estrutura original (cinza tracejado)
        for el in range(self._dados.n_el):
            no1, no2 = conec[el]
            self.create_line(*self._w2s(*nos[no1]), *self._w2s(*nos[no2]),
                             fill='#cccccc', width=1.5, dash=(5, 4),
                             tags='ghost')
        for i in range(self._dados.n_nos):
            sx, sy = self._w2s(*nos[i])
            self.create_oval(sx - r + 1, sy - r + 1, sx + r - 1, sy + r - 1,
                             fill='#dddddd', outline='', tags='ghost')

        # Setas de deslocamento: original → deformado
        for i in range(self._dados.n_nos):
            ox, oy = self._w2s(*nos[i])
            dx, dy = self._w2s(*nos_def[i])
            if math.hypot(dx - ox, dy - oy) > 4:
                self.create_line(ox, oy, dx, dy,
                                 fill='#E65100', width=1.2, dash=(2, 3),
                                 arrow=tk.LAST, arrowshape=(6, 8, 3),
                                 tags='disp_arrow')

        # Barras deformadas (azul sólido)
        for el in range(self._dados.n_el):
            no1, no2 = conec[el]
            self.create_line(*self._w2s(*nos_def[no1]),
                             *self._w2s(*nos_def[no2]),
                             fill='#1565C0', width=2.5,
                             capstyle='round', tags='deformed')

        # Nós deformados
        for i in range(self._dados.n_nos):
            sx, sy = self._w2s(*nos_def[i])
            self.create_oval(sx - r, sy - r, sx + r, sy + r,
                             fill='#1565C0', outline='white', width=1,
                             tags='deformed')
            self.create_text(sx + r + 3, sy - r - 2, text=str(i),
                             font=('Segoe UI', 8, 'bold'), fill='#1565C0',
                             tags='deformed')

        # Anotação: δ_max e fator de amplificação
        u_max_mm = float(np.abs(u).max()) * 1e3
        W = max(self.winfo_width(), 200)
        self.create_text(W // 2, 14, anchor='n',
                         text=f'δ_max = {u_max_mm:.4f} mm   |   amplificação ×{int(esc)}',
                         font=('Segoe UI', 9, 'bold'), fill='#333333',
                         tags='def_info')

    # ── Grid ─────────────────────────────────────────────────────────────────

    def _draw_grid(self):
        nos = self._dados.nos
        W   = max(self.winfo_width(),  10)
        H   = max(self.winfo_height(), 10)

        for x in np.unique(np.round(nos[:, 0], 5)):
            sx, _ = self._w2s(x, 0)
            self.create_line(sx, 0, sx, H,
                             fill='#e0e0e0', dash=(3, 5), tags='grid')
            self.create_text(sx, H - 6, text=f'{x:.2f}',
                             font=('Segoe UI', 7), fill='#b0b0b0',
                             anchor='s', tags='grid')

        ys_uni = np.unique(np.round(nos[:, 1], 5))
        for i, y in enumerate(ys_uni):
            _, sy = self._w2s(0, y)
            self.create_line(0, sy, W, sy,
                             fill='#e0e0e0', dash=(3, 5), tags='grid')
            # Label só no primeiro e no último nível Y
            if i == 0 or i == len(ys_uni) - 1:
                self.create_text(8, sy, text=f'y={y:.2f}',
                                 font=('Segoe UI', 7), fill='#b0b0b0',
                                 anchor='w', tags='grid')

    # ── Helpers de seção ─────────────────────────────────────────────────────

    def _secoes_info(self):
        """Retorna (unique_areas_m2, {area_m2: cor}) para o dados atual."""
        areas    = self._dados.areas
        unique_a = np.unique(np.round(areas, 12))
        color_map = {a: _PALETA_SECOES[i % len(_PALETA_SECOES)]
                     for i, a in enumerate(unique_a)}
        return unique_a, color_map

    # ── Barras ───────────────────────────────────────────────────────────────

    def _draw_bars(self):
        nos   = self._dados.nos
        conec = self._dados.conectividade

        N     = (self._resultado['forcas_internas']
                 if self._modo == 'esforcos' and self._resultado else None)
        N_max = (float(np.abs(N).max()) if N is not None and np.abs(N).max() > 0
                 else 1.0)

        # Pré-calcula mapa de cores por seção para modo croqui
        if self._modo == 'croqui':
            unique_a, color_map = self._secoes_info()
            a_min  = float(unique_a.min())
            a_max  = float(unique_a.max())
            a_span = max(a_max - a_min, 1e-20)

        for el in range(self._dados.n_el):
            no1, no2 = conec[el]
            sx1, sy1 = self._w2s(*nos[no1])
            sx2, sy2 = self._w2s(*nos[no2])

            if N is not None:
                cor = _axial_color(N[el], N_max)
                lw  = _axial_width(N[el], N_max)
            elif self._modo == 'croqui':
                a     = float(self._dados.areas[el])
                a_key = unique_a[int(np.argmin(np.abs(unique_a - a)))]
                cor   = color_map[a_key]
                lw    = 1.5 + 3.5 * (a - a_min) / a_span
            else:
                cor = '#4477aa'
                lw  = 2.0

            self.create_line(sx1, sy1, sx2, sy2,
                             fill=cor, width=lw,
                             capstyle='round', tags=('bar', f'bar_{el}'))

            # Número da barra — discreto, fundo branco
            mx, my = (sx1 + sx2) / 2, (sy1 + sy2) / 2
            self.create_rectangle(mx - 7, my - 6, mx + 7, my + 6,
                                  fill='white', outline='', tags='bar_lbl')
            self.create_text(mx, my, text=str(el),
                             font=('Segoe UI', 7), fill='#888888',
                             tags='bar_lbl')

    # ── Legenda de seções (modo croqui) ──────────────────────────────────────

    def _draw_secoes_legend(self):
        unique_a, color_map = self._secoes_info()
        n          = len(unique_a)
        W          = max(self.winfo_width(), 200)
        perfis_map = (self._resultado or {}).get('perfis_snap', {})
        has_perfis = bool(perfis_map)

        sw    = 14
        sh    = 10
        pad   = 6
        lh    = 26 if has_perfis else 18
        box_w = 148 if has_perfis else 110
        box_h = pad + 14 + n * lh + pad
        x0    = W - box_w - 8
        y0    = 12

        self.create_rectangle(x0, y0, x0 + box_w, y0 + box_h,
                              fill='#f8f8f8', outline='#cccccc',
                              width=1, tags='legend')
        self.create_text(x0 + box_w // 2, y0 + pad,
                         text='Seções', anchor='n',
                         font=('Segoe UI', 8, 'bold'), fill='#444444',
                         tags='legend')

        for i, a in enumerate(unique_a):
            cor   = color_map[a]
            ry    = y0 + pad + 14 + i * lh
            sx    = x0 + pad
            desig = perfis_map.get(round(float(a), 8), '')

            self.create_rectangle(sx, ry, sx + sw, ry + sh,
                                  fill=cor, outline='', tags='legend')

            if desig:
                self.create_text(sx + sw + 4, ry,
                                 text=desig,
                                 font=('Segoe UI', 8, 'bold'), fill='#333333',
                                 anchor='nw', tags='legend')
                self.create_text(sx + sw + 4, ry + 14,
                                 text=f'{a * 1e4:.2f} cm²',
                                 font=('Segoe UI', 7), fill='#666666',
                                 anchor='nw', tags='legend')
            else:
                self.create_text(sx + sw + 4, ry + sh // 2,
                                 text=f'{a * 1e4:.2f} cm²',
                                 font=('Segoe UI', 8), fill='#333333',
                                 anchor='w', tags='legend')

    # ── Comprimentos de barra (modo croqui) ──────────────────────────────────

    def _draw_bar_lengths(self):
        nos   = self._dados.nos
        conec = self._dados.conectividade
        span  = max(nos[:, 0].max() - nos[:, 0].min(), 1e-6)
        off   = span * 0.035

        for el in range(self._dados.n_el):
            no1, no2 = conec[el]
            x1, y1   = nos[no1]
            x2, y2   = nos[no2]
            L        = math.hypot(x2 - x1, y2 - y1)

            nm = L
            if nm < 1e-12:
                continue
            nx, ny = -(y2 - y1) / nm, (x2 - x1) / nm   # normal (gira +90°)

            wx = (x1 + x2) / 2 + nx * off
            wy = (y1 + y2) / 2 + ny * off
            sx, sy = self._w2s(wx, wy)

            self.create_text(sx, sy, text=f'{L:.2f} m',
                             font=('Segoe UI', 6), fill='#aaaaaa',
                             tags='bar_len')

    # ── Nós ──────────────────────────────────────────────────────────────────

    def _draw_nodes(self):
        nos = self._dados.nos
        r   = self._NR

        for i in range(self._dados.n_nos):
            sx, sy = self._w2s(*nos[i])
            self.create_oval(sx - r, sy - r, sx + r, sy + r,
                             fill='#222222', outline='white', width=1,
                             tags=('node', f'node_{i}'))
            self.create_text(sx + r + 3, sy - r - 2, text=str(i),
                             font=('Segoe UI', 8, 'bold'), fill='#333333',
                             tags='node_lbl')

    # ── Apoios ───────────────────────────────────────────────────────────────

    def _draw_supports(self):
        nos  = self._dados.nos
        span = max(nos[:, 0].max() - nos[:, 0].min(),
                   nos[:, 1].max() - nos[:, 1].min(), 1.0)
        t    = span * 0.025

        for k in range(self._dados.apoios.shape[0]):
            no = int(self._dados.apoios[k, 0])
            rx = int(self._dados.apoios[k, 1])
            ry = int(self._dados.apoios[k, 2])
            px, py = self._dados.nos[no]

            if rx and ry:
                self._draw_pin(px, py, t)
            elif ry and not rx:
                self._draw_roller_y(px, py, t)
            elif rx and not ry:
                self._draw_roller_x(px, py, t)

    def _draw_pin(self, px, py, t):
        flat = [c for p in [self._w2s(px, py),
                             self._w2s(px - t, py - 1.6*t),
                             self._w2s(px + t, py - 1.6*t)] for c in p]
        self.create_polygon(*flat, fill='#888888', outline='#888888', tags='support')

        self.create_line(*self._w2s(px - 1.2*t, py - 1.7*t),
                         *self._w2s(px + 1.2*t, py - 1.7*t),
                         fill='#888888', width=2, tags='support')

        for hx in np.linspace(px - t, px + t, 5):
            self.create_line(*self._w2s(hx,          py - 1.7*t),
                             *self._w2s(hx - 0.3*t,  py - 2.1*t),
                             fill='#888888', width=1, tags='support')

    def _draw_roller_y(self, px, py, t):
        rc   = t * 0.22
        flat = [c for p in [self._w2s(px,     py),
                             self._w2s(px - t, py - 1.6*t),
                             self._w2s(px + t, py - 1.6*t)] for c in p]
        self.create_polygon(*flat, fill='#888888', outline='#888888', tags='support')

        self.create_line(*self._w2s(px - 1.2*t, py - 1.65*t),
                         *self._w2s(px + 1.2*t, py - 1.65*t),
                         fill='#888888', width=1.5, tags='support')

        for i in range(3):
            cx, cy = px + (i - 1)*2.6*rc, py - 1.65*t - rc
            self.create_oval(*self._w2s(cx - rc, cy - rc),
                             *self._w2s(cx + rc, cy + rc),
                             fill='#888888', outline='', tags='support')

        self.create_line(*self._w2s(px - 1.3*t, py - 1.65*t - 2.4*rc),
                         *self._w2s(px + 1.3*t, py - 1.65*t - 2.4*rc),
                         fill='#888888', width=2, tags='support')

    def _draw_roller_x(self, px, py, t):
        rc   = t * 0.22
        flat = [c for p in [self._w2s(px,          py),
                             self._w2s(px - 1.6*t,  py + t),
                             self._w2s(px - 1.6*t,  py - t)] for c in p]
        self.create_polygon(*flat, fill='#888888', outline='#888888', tags='support')

        self.create_line(*self._w2s(px - 1.65*t, py - 1.2*t),
                         *self._w2s(px - 1.65*t, py + 1.2*t),
                         fill='#888888', width=1.5, tags='support')

        for i in range(3):
            cy, cx = py + (i - 1)*2.6*rc, px - 1.65*t - rc
            self.create_oval(*self._w2s(cx - rc, cy - rc),
                             *self._w2s(cx + rc, cy + rc),
                             fill='#888888', outline='', tags='support')

        self.create_line(*self._w2s(px - 1.65*t - 2.4*rc, py - 1.3*t),
                         *self._w2s(px - 1.65*t - 2.4*rc, py + 1.3*t),
                         fill='#888888', width=2, tags='support')

    # ── Forças aplicadas (modo completa) ─────────────────────────────────────

    def _draw_forces(self):
        nos    = self._dados.nos
        forcas = self._dados.forcas
        span   = max(nos[:, 0].max() - nos[:, 0].min(), 1.0)
        escala = span * 0.15

        mags  = [math.hypot(forcas[k, 1], forcas[k, 2]) for k in range(forcas.shape[0])]
        F_max = max(mags) if mags else 1.0

        placed = []   # posições de labels já colocados

        for k in range(forcas.shape[0]):
            no    = int(forcas[k, 0])
            Fx, Fy = forcas[k, 1], forcas[k, 2]
            F_mag  = math.hypot(Fx, Fy)
            if F_mag < 1e-12:
                continue

            px, py = nos[no]
            ratio  = F_mag / F_max
            dx     = (Fx / F_mag) * escala * ratio
            dy     = (Fy / F_mag) * escala * ratio

            sox, soy = self._w2s(px - dx, py - dy)   # cauda da seta
            spx, spy = self._w2s(px,      py)          # ponta (no nó)

            self.create_line(sox, soy, spx, spy,
                             fill='#cc3300', width=2,
                             arrow=tk.LAST, arrowshape=(10, 12, 4),
                             tags='force')

            # Label na cauda, com anti-sobreposição simples por deslocamento vertical
            lx = sox - (Fy / F_mag) * 14
            ly = soy + (Fx / F_mag) * 14
            for plx, ply in placed:
                if abs(lx - plx) < 55 and abs(ly - ply) < 15:
                    ly -= 15
            placed.append((lx, ly))

            self.create_text(lx, ly, text=f'{F_mag/1e3:.1f} kN',
                             font=('Segoe UI', 8, 'bold'), fill='#cc3300',
                             tags='force_lbl')

    # ── Reações de apoio (modo esforcos) ─────────────────────────────────────

    def _draw_reactions(self):
        reacoes = (self._resultado or {}).get('reacoes')
        if reacoes is None or len(reacoes) == 0:
            return

        nos    = self._dados.nos
        span   = max(nos[:, 0].max() - nos[:, 0].min(), 1.0)
        escala = span * 0.12

        mags  = [math.hypot(reacoes[k, 1], reacoes[k, 2]) for k in range(reacoes.shape[0])]
        R_max = max(mags) if mags else 1.0

        for k in range(reacoes.shape[0]):
            no     = int(reacoes[k, 0])
            Rx, Ry = reacoes[k, 1], reacoes[k, 2]
            R_mag  = math.hypot(Rx, Ry)
            if R_mag < 1e-3:
                continue

            px, py = nos[no]
            ratio  = R_mag / R_max
            dx     = (Rx / R_mag) * escala * ratio
            dy     = (Ry / R_mag) * escala * ratio

            # Cauda fora da estrutura → ponta no nó
            sox, soy = self._w2s(px - dx, py - dy)   # cauda (fora)
            sex, sey = self._w2s(px,      py)          # ponta (no nó)

            self.create_line(sox, soy, sex, sey,
                             fill='#227722', width=2,
                             arrow=tk.LAST, arrowshape=(10, 12, 4),
                             tags='reaction')
            self.create_text(sox, soy + 4, text=f'{R_mag/1e3:.1f} kN',
                             font=('Segoe UI', 11, 'bold'), fill='#227722',
                             anchor='n', tags='reaction')

    # ── Colorbar (modo esforcos) ──────────────────────────────────────────────

    def _draw_colorbar(self):
        if not self._resultado or 'forcas_internas' not in self._resultado:
            return

        N     = self._resultado['forcas_internas']
        N_max = float(np.abs(N).max()) if np.abs(N).max() > 0 else 1.0

        W  = max(self.winfo_width(),  200)
        H  = max(self.winfo_height(), 200)
        bw = 14
        bh = min(140, H // 3)
        x0 = W - 90
        y0 = 24

        # Gradiente linha a linha: topo = tração (azul), base = compressão (vermelho)
        for i in range(bh):
            t   = i / max(bh - 1, 1)
            Nv  = (1.0 - 2.0 * t) * N_max
            self.create_line(x0, y0 + i, x0 + bw, y0 + i,
                             fill=_axial_color(Nv, N_max), tags='colorbar')

        self.create_rectangle(x0, y0, x0 + bw, y0 + bh,
                              outline='#888888', tags='colorbar')

        N_t = float(N.max())
        N_c = float(N.min())
        lx  = x0 + bw + 4

        # Topo: tração
        self.create_text(lx, y0,      anchor='nw', tags='colorbar',
                         text=f'+{N_t/1e3:.1f} kN',
                         font=('Segoe UI', 7), fill='#2244cc')
        self.create_text(lx, y0 + 11, anchor='nw', tags='colorbar',
                         text='tração',
                         font=('Segoe UI', 6, 'italic'), fill='#2244cc')

        # Centro: zero
        self.create_text(lx, y0 + bh//2, anchor='w', tags='colorbar',
                         text='0',
                         font=('Segoe UI', 7), fill='#555555')

        # Base: compressão
        self.create_text(lx, y0 + bh - 11, anchor='sw', tags='colorbar',
                         text='compressão',
                         font=('Segoe UI', 6, 'italic'), fill='#cc2222')
        self.create_text(lx, y0 + bh,      anchor='sw', tags='colorbar',
                         text=f'{N_c/1e3:.1f} kN',
                         font=('Segoe UI', 7), fill='#cc2222')

        self.create_text(x0 + bw//2, y0 - 10, anchor='s', tags='colorbar',
                         text='N axial',
                         font=('Segoe UI', 8, 'bold'), fill='#444444')

    # ── Hover / Tooltip ───────────────────────────────────────────────────────

    def _on_hover(self, event):
        self._hide_tip()
        if self._dados is None:
            return
        info = self._hit_test(event.x, event.y)
        if info:
            self._show_tip(event.x, event.y, info)

    def _hit_test(self, sx, sy) -> str | None:
        nos   = self._dados.nos
        conec = self._dados.conectividade

        # Nós têm prioridade
        for i in range(self._dados.n_nos):
            cx, cy = self._w2s(*nos[i])
            if math.hypot(sx - cx, sy - cy) < self._HIT:
                x, y  = nos[i]
                lines = [f'Nó {i}', f'x = {x:.3f} m', f'y = {y:.3f} m']
                if self._resultado and 'deslocamentos' in self._resultado:
                    u  = self._resultado['deslocamentos']
                    ux = float(u[2*i])   * 1e3
                    uy = float(u[2*i+1]) * 1e3
                    lines += [f'δx = {ux:.4f} mm', f'δy = {uy:.4f} mm']
                return '\n'.join(lines)

        # Barras
        for el in range(self._dados.n_el):
            no1, no2 = conec[el]
            sx1, sy1 = self._w2s(*nos[no1])
            sx2, sy2 = self._w2s(*nos[no2])
            if _pt_seg_dist(sx, sy, sx1, sy1, sx2, sy2) < self._HIT:
                x1, y1 = nos[no1]
                x2, y2 = nos[no2]
                L      = math.hypot(x2 - x1, y2 - y1)
                lines  = [f'Barra {el}', f'L = {L:.3f} m']
                if self._resultado and 'forcas_internas' in self._resultado:
                    Nv   = float(self._resultado['forcas_internas'][el])
                    tipo = 'Tração' if Nv >= 0 else 'Compressão'
                    lines += [f'N = {Nv/1e3:.2f} kN  ({tipo})']
                if self._resultado and 'norma' in self._resultado:
                    UC = float(self._resultado['norma']['UC_max'][el])
                    cor = '✓' if UC <= 1.0 else '✗'
                    lines.append(f'UC = {UC:.3f}  {cor}')
                return '\n'.join(lines)

        return None

    def _show_tip(self, sx, sy, text):
        lines = text.split('\n')
        pad   = 8
        lh    = 16
        tw    = max(len(l) for l in lines) * 6 + 2 * pad
        th    = len(lines) * lh + 2 * pad
        x     = min(sx + 14, max(self.winfo_width()  - tw - 4, 4))
        y     = min(sy + 14, max(self.winfo_height() - th - 4, 4))

        self.create_rectangle(x, y, x + tw, y + th,
                              fill='#fffde7', outline='#ccaa00',
                              width=1, tags='tooltip')
        self.create_text(x + pad, y + pad, text=text,
                         font=('Segoe UI', 8), fill='#333333',
                         anchor='nw', tags='tooltip')

    def _hide_tip(self, _e=None):
        self.delete('tooltip')

    # ── Zoom ─────────────────────────────────────────────────────────────────

    def _on_zoom(self, event):
        if event.num == 4 or getattr(event, 'delta', 0) > 0:
            factor = 1.15
        else:
            factor = 1.0 / 1.15

        wx, wy       = self._s2w(event.x, event.y)
        self._scale *= factor
        self._ox     = event.x - wx * self._scale
        self._oy     = self.winfo_height() - event.y - wy * self._scale
        self._redraw()

    # ── Pan ──────────────────────────────────────────────────────────────────

    def _on_pan_start(self, event):
        self._pan_sx = event.x;  self._pan_sy = event.y
        self._pan_ox = self._ox; self._pan_oy = self._oy

    def _on_pan(self, event):
        self._ox = self._pan_ox + (event.x - self._pan_sx)
        self._oy = self._pan_oy - (event.y - self._pan_sy)
        self._redraw()

    # ── Resize ───────────────────────────────────────────────────────────────

    def _on_resize(self, _e=None):
        if self._dados is not None:
            self._fit_view()
            self._redraw()
