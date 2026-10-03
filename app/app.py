"""Assignació d'activitat programada TD: interfície Streamlit d'una pàgina."""
from __future__ import annotations

import copy
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import pandas as pd
import streamlit as st

_here = Path(__file__).resolve().parent
ROOT = _here if (_here / 'programada').is_dir() else _here.parent   # també quan s'executa via streamlit_app.py
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from programada import __version__  # noqa: E402
from programada.io_input import load_entrada  # noqa: E402
from programada.planner import plan  # noqa: E402
from programada.writer import write_plan, assignment_rows, radiologist_rows  # noqa: E402
from programada.templates import build_input  # noqa: E402
from programada.demo import build_demo_input  # noqa: E402
from programada.normalize import week_label, week_code, WEEKDAY_SHORT  # noqa: E402
from programada.model import ERROR, AVIS, INFO, Params  # noqa: E402
from programada.availability import build_radweeks  # noqa: E402

st.set_page_config(page_title='Activitat programada TD', page_icon='🗓️', layout='wide')

# Paleta validada (categòrica, slots 1-2) i gris de context; variants per a mode fosc
PALETTE = {'light': {'oblig': '#2a78d6', 'extra': '#eb6834', 'free': '#c3c2b7', 'surface': '#ffffff'},
           'dark': {'oblig': '#3987e5', 'extra': '#d95926', 'free': '#5f5e57', 'surface': '#0e1117'}}


def _secret(name, default=None):
    """Secret de Streamlit (Cloud) o, si no n'hi ha, variable d'entorn (Docker)."""
    try:
        v = st.secrets.get(name)
        if v:
            return v
    except Exception:
        pass
    return os.environ.get(name, default)


def _gate():
    pwd = _secret('APP_PASSWORD')
    if not pwd or st.session_state.get('auth_ok'):
        return
    st.title('Activitat programada TD')
    v = st.text_input('Contrasenya', type='password')
    if v:
        if v == pwd:
            st.session_state['auth_ok'] = True
            st.rerun()
        else:
            st.error('Contrasenya incorrecta.')
    st.stop()


def _theme() -> dict:
    try:
        return PALETTE.get(st.context.theme.type or 'light', PALETTE['light'])
    except Exception:
        return PALETTE['light']


@st.cache_data(show_spinner=False)
def _template_bytes() -> bytes:
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
        path = f.name
    build_input(path)
    data = Path(path).read_bytes()
    os.unlink(path)
    return data


@st.cache_data(show_spinner=False)
def _demo_bytes() -> bytes:
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
        path = f.name
    build_demo_input(path)
    data = Path(path).read_bytes()
    os.unlink(path)
    return data


@st.cache_data(show_spinner=False, max_entries=8)
def _load(data: bytes, name: str):
    """(entrada, None) o (None, missatge d'error) si el fitxer no es pot obrir com a Excel."""
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
        f.write(data)
        path = f.name
    try:
        return load_entrada(path, display_name=name), None
    except Exception as e:          # fitxer corrupte, protegit amb contrasenya, no és un .xlsx...
        return None, f"No es pot llegir '{name}' com a Excel ({type(e).__name__}). Comprova que sigui un .xlsx desat amb Excel i sense contrasenya."
    finally:
        os.unlink(path)


def _plan_bytes(res) -> bytes:
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
        path = f.name
    write_plan(res, path)
    data = Path(path).read_bytes()
    os.unlink(path)
    return data


def _fmt_date(d) -> str:
    return d.strftime('%d/%m/%Y') if d is not None and not pd.isna(d) else ''


def _fmt_pct(v) -> str:
    return '' if v is None or pd.isna(v) else f"{v * 100:.0f}%"


def _height(n: int) -> int:
    return min(36 * (n + 1) + 4, 720)


def _warnings_table(ws: list, title: str, expanded: bool = False):
    order = {ERROR: 0, AVIS: 1, INFO: 2}
    errs = sum(1 for w in ws if w.level == ERROR)
    avis = sum(1 for w in ws if w.level == AVIS)
    infos = sum(1 for w in ws if w.level == INFO)
    with st.expander(f"{title}: {errs} errors · {avis} avisos · {infos} informatius", expanded=expanded or bool(errs)):
        if not ws:
            st.write('Cap avís.')
            return
        rows = [w.as_row() for w in sorted(ws, key=lambda w: order.get(w.level, 3))]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')


def _capacity_chart(res):
    import altair as alt
    pal = _theme()
    per = defaultdict(lambda: [0, 0])
    for a in res.assignments:
        per[a.radiologist_key][0] += a.oblig_exams
        per[a.radiologist_key][1] += a.extra_exams
    rows = []
    for k, rw in sorted(res.radweeks.items(), key=lambda kv: kv[1].radiologist.name):
        ob, ex = per[k]
        if rw.cap <= 0 and ob + ex == 0:
            continue
        free = max(0.0, rw.cap - ob - ex)
        occ = f"{(ob + ex) / rw.cap * 100:.0f}%" if rw.cap else '-'
        for tram, v, o in (('Dins obligació', ob, 0), ('Extra', ex, 1), ('Capacitat lliure', round(free, 1), 2)):
            rows.append({'Radiòleg': rw.radiologist.name, 'Tram': tram, 'Exploracions': v, 'ordre': o,
                         'Capacitat': round(rw.cap, 1), 'Ocupació': occ})
    if not rows:
        return None
    df = pd.DataFrame(rows)
    return alt.Chart(df).mark_bar(cornerRadiusEnd=4, stroke=pal['surface'], strokeWidth=2).encode(
        y=alt.Y('Radiòleg:N', sort=None, title=None, scale=alt.Scale(paddingInner=0.3),
                axis=alt.Axis(labelOverlap=False, labelLimit=220, labelFontSize=12)),
        x=alt.X('sum(Exploracions):Q', title='Exploracions de la setmana', stack='zero'),
        color=alt.Color('Tram:N', scale=alt.Scale(domain=['Dins obligació', 'Extra', 'Capacitat lliure'],
                                                  range=[pal['oblig'], pal['extra'], pal['free']]),
                        legend=alt.Legend(orient='top', title=None)),
        order=alt.Order('ordre:Q'),
        tooltip=['Radiòleg', 'Tram', alt.Tooltip('Exploracions:Q', format='.0f'),
                 alt.Tooltip('Capacitat:Q', format='.1f'), 'Ocupació'],
    ).properties(height=alt.Step(26))


def _params_form(base):
    """Paràmetres de la pestanya Configuració, editables per a aquest càlcul (mateixos rangs que la lectura)."""
    L = Params.LIMITS
    p = copy.deepcopy(base).clamp()
    with st.sidebar.expander('Paràmetres de l\'assignació', expanded=False):
        st.caption('Valors de la pestanya Configuració. Els canvis només valen per a aquest càlcul.')
        lo, hi = L['target_utilisation']
        p.target_utilisation = st.slider("Ocupació objectiu de l'extra (%)", int(lo * 100), int(hi * 100),
                                         int(round(p.target_utilisation * 100)), 5) / 100
        lo, hi = L['min_chunk']
        p.min_chunk = int(st.number_input('Mida mínima de lot (exploracions)', lo, hi, int(p.min_chunk)))
        lo, hi = L['max_rads_per_block']
        p.max_rads_per_block = int(st.number_input('Màxim de radiòlegs per bloc', lo, hi, int(p.max_rads_per_block)))
        lo, hi = L['split_cost_exams']
        p.split_cost_exams = float(st.number_input('Cost de dividir un bloc', float(lo), float(hi), float(p.split_cost_exams), 5.0,
                                                   help='En exploracions equivalents. Com més alt, menys es divideixen les agendes.'))
        lo, hi = L['time_limit_s']
        p.time_limit_s = float(st.number_input('Temps màxim de càlcul (s)', float(lo), float(hi), float(p.time_limit_s), 5.0))
    return p


def _same_params(a, b) -> bool:
    """Compara per valor: després d'un desplegament les classes poden ser objectes diferents."""
    fields = ('target_utilisation', 'min_chunk', 'max_rads_per_block', 'split_cost_exams', 'time_limit_s',
              'working_days', 'holidays', 'seed')
    return all(getattr(a, f, None) == getattr(b, f, None) for f in fields)


def main():
    _gate()
    st.title('Assignació d\'activitat programada TD')
    st.caption("Demanda de la setmana + perfil i preferències dels radiòlegs → qui fa què. Versió " + __version__)

    # ------------------------------------------------------------- Entrada
    sb = st.sidebar
    sb.header('Entrada')
    up = sb.file_uploader('Fitxer d\'entrada setmanal (.xlsx)', type=['xlsx'])
    if sb.button('Carregar la demo', help='Dades fictícies: radiòlegs Alpha, Beta... i centres Hospital Demo.'):
        st.session_state['input'] = ('DEMO_Entrada_Setmana_2026W43.xlsx', _demo_bytes())
        st.session_state['input_source'] = 'demo'
        st.session_state.pop('result', None)
    if up is not None and st.session_state.get('upload_id') != up.file_id:
        # Fitxer nou a l'uploader (no es torna a carregar si després s'ha triat la demo)
        st.session_state['upload_id'] = up.file_id
        st.session_state['input'] = (up.name, up.getvalue())
        st.session_state['input_source'] = 'upload'
        st.session_state.pop('result', None)
    elif up is None and st.session_state.get('input_source') == 'upload':
        # S'ha tret el fitxer de l'uploader: es buida l'entrada
        for k in ('input', 'input_source', 'upload_id', 'result'):
            st.session_state.pop(k, None)
    sb.divider()
    sb.download_button('Plantilla d\'entrada buida', _template_bytes(), 'Plantilla_Entrada_Setmanal.xlsx',
                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', width='stretch')
    sb.download_button('Entrada de demostració', _demo_bytes(), 'DEMO_Entrada_Setmana_2026W43.xlsx',
                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', width='stretch')

    if 'input' not in st.session_state:
        st.info("Puja el fitxer d'entrada de la setmana o carrega la demo (barra lateral).")
        st.markdown(
            "- **Radiòlegs**: un cop, i quan hi ha canvis. Mínim (obligació) i Màxim (capacitat) setmanals, "
            "centres on pot informar, dies sense activitat i, per a cada activitat, S (la fa) o P (la prefereix).\n"
            "- **Demanda**: cada setmana, una fila per agenda o volum: centre, data, franja, activitat, exploracions, "
            "àmbit i, si hi ha pacte, el radiòleg fix.\n"
            "- **Absències**: V, B, C, A, G, M a la graella de la setmana.\n\n"
            "L'ordre de prioritat és: cobrir la demanda (primer la que té ingressats), respectar el radiòleg fix, "
            "omplir l'obligació de cadascú, repartir l'extra en proporció a la capacitat declarada, no partir agendes "
            "sense necessitat i, finalment, l'activitat preferida.")
        return

    name, data = st.session_state['input']
    ent, load_error = _load(data, name)
    if load_error:
        st.error(load_error)
        return
    if ent.week is None or ent.has_errors():
        st.error("L'entrada té errors que impedeixen assignar. Corregeix-los al fitxer i torna'l a pujar.")
        _warnings_table(ent.warnings, 'Lectura de l\'entrada', expanded=True)
        return

    params = _params_form(ent.params)
    rws, _ = build_radweeks(ent, params)
    demand = sum(b.n_exams for b in ent.blocks)
    st.subheader(f"Setmana {week_label(ent.week)}")
    c = st.columns(4)
    c[0].metric('Exploracions demanades', demand, help=f"{len(ent.blocks)} blocs de demanda")
    c[1].metric('Capacitat disponible', f"{sum(rw.cap for rw in rws.values()):.0f}",
                help='Màxim declarat × disponibilitat de la setmana (absències i festius).')
    c[2].metric('Obligació contractual', f"{sum(rw.min for rw in rws.values()):.0f}",
                help='Suma dels Mínims, ajustats a la disponibilitat.')
    c[3].metric('Radiòlegs disponibles', sum(1 for rw in rws.values() if rw.cap > 0),
                help=f"{sum(1 for r in ent.radiologists.values() if r.active)} actius al fitxer")
    st.caption(f"Fitxer: {name}")
    _warnings_table(ent.warnings, 'Lectura de l\'entrada')

    if st.button('Assignar', type='primary'):
        with st.spinner('Calculant l\'assignació...'):
            st.session_state['result'] = plan(ent, params)
    res = st.session_state.get('result')
    if res is None:
        return
    if not _same_params(res.params, params):
        st.info("Has canviat els paràmetres: torna a prémer Assignar per recalcular. Es mostra el resultat anterior.")

    # ----------------------------------------------------------- Resultat
    asg = sum(a.n_exams for a in res.assignments)
    pend = sum(p.n_exams for p in res.pendings)
    errs = [w for w in res.validation if w.level == ERROR]
    st.divider()
    c = st.columns(5)
    c[0].metric('Assignades', asg)
    c[1].metric('Pendents', pend)
    c[2].metric('Cobertura', f"{asg / demand * 100:.0f}%" if demand else '-')
    c[3].metric('Radiòlegs amb activitat', len({a.radiologist_key for a in res.assignments}))
    status = {'OPTIMAL': 'Òptim', 'FEASIBLE': 'Vàlid'}.get(res.stats.status, res.stats.status)
    c[4].metric('Càlcul', status, help=f"{res.stats.wall_time:.1f} s. Òptim = la millor assignació possible amb aquestes regles; "
                                       "Vàlid = compleix les regles però no s'ha pogut demostrar que sigui la millor dins del temps.")
    if errs:
        st.error(f"La validació independent ha trobat {len(errs)} errors: vegeu Avisos.")
    else:
        st.success('Validació independent superada: cap infracció de les regles dures.')
    if res.stats.status.startswith('RESERVA'):
        st.warning("El càlcul no ha trobat solució dins del temps i s'ha fet servir un repartiment simple de reserva. "
                   "Augmenta el temps màxim de càlcul i torna a assignar abans de fer-lo servir.")
    st.download_button('Descarregar l\'assignació (Excel)', _plan_bytes(res), f"Assignacio_{week_code(res.week)}.xlsx",
                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', type='primary')

    t1, t2, t3, t4 = st.tabs(['Assignacions', 'Per radiòleg', f'Pendents ({pend})', 'Avisos'])
    with t1:
        h, rows = assignment_rows(res)
        df = pd.DataFrame(rows, columns=h)
        df['Data'] = df['Data'].apply(_fmt_date)
        f = st.columns(3)
        rads = f[0].multiselect('Radiòleg', sorted(df['Radiòleg'].unique()), placeholder='Tots')
        centres = f[1].multiselect('Centre', sorted(df['Centre'].unique()), placeholder='Tots')
        days = f[2].multiselect('Dia', [d for d in WEEKDAY_SHORT + ['Setmana'] if d in set(df['Dia'])], placeholder='Tots')
        if rads:
            df = df[df['Radiòleg'].isin(rads)]
        if centres:
            df = df[df['Centre'].isin(centres)]
        if days:
            df = df[df['Dia'].isin(days)]
        st.dataframe(df.drop(columns=['ID', 'Correu']), hide_index=True, width='stretch', height=_height(len(df)))
    with t2:
        ch = _capacity_chart(res)
        if ch is not None:
            st.altair_chart(ch, use_container_width=True)
        h, rows = radiologist_rows(res)
        dfr = pd.DataFrame(rows, columns=h)
        for col in ('Disponibilitat', 'Ocupació', "Ocupació de l'extra", 'En activitat preferida'):
            dfr[col] = dfr[col].apply(_fmt_pct)
        st.dataframe(dfr.drop(columns=['Correu']), hide_index=True, width='stretch', height=_height(len(dfr)))
    with t3:
        if not res.pendings:
            st.write('Tota la demanda està assignada.')
        bmap = res.blocks_by_id()
        for pd_ in res.pendings:
            b = bmap[pd_.block_id]
            when = f"{_fmt_date(b.date)} {b.when().split()[0]}" if b.date else 'Setmana'
            head = ' · '.join(x for x in (when, b.franja, b.centre, b.agenda, b.activity_label, b.scope) if x)
            st.markdown(f"**{head}**: {pd_.n_exams} pendents (fila {b.row} de la Demanda)")
            st.markdown('\n'.join(f"- {r}" for r in pd_.reasons)
                        + (f"\n- Candidats per a una gestió manual: {', '.join(pd_.candidates)}" if pd_.candidates else ''))
    with t4:
        seen = {tuple(w.as_row().values()) for w in ent.warnings}
        own = [w for w in res.warnings if tuple(w.as_row().values()) not in seen]
        _warnings_table(list(res.validation) + own, 'Validació i càlcul', expanded=True)


main()
