"""Joc de dades de demostració, totalment fictici.

Radiòlegs amb cognoms de lletres gregues (com al planning de guàrdies) i centres
"Hospital Demo ...". Inclou els casos que cal saber resoldre:
  - radiòloga fixa d'una agenda que és de vacances tota la setmana (substitució)
  - activitat superespecialitzada (cardio) amb una sola radiòloga competent i més
    demanda que capacitat (queda pendent amb motiu)
  - una activitat que no és al catàleg (RM Mama): queda pendent amb motiu
  - agendes amb ingressats (termini 24 h): només qui treballa aquell dia
  - contractes parcials amb dies sense activitat, un contracte que només cobreix
    guàrdies (Màxim 0), un radiòleg que no vol extra (Màxim = Mínim) i un d'inactiu
  - radiòlegs amb accés només a alguns centres
  - un nom de radiòleg fix escrit d'una altra manera ("Anna Alpha")
"""
from __future__ import annotations

import datetime as dt
import os

from .templates import build_input, DEFAULT_ACTIVITIES

DEMO_WEEK = dt.date(2026, 10, 19)
N, S, E, O, C = 'Hospital Demo Nord', 'Hospital Demo Sud', 'Hospital Demo Est', 'Hospital Demo Oest', 'Clínica Demo Centre'


def _rad(name, email, mn, mx, comps, centres='', days_off='', actiu='Sí', notes=''):
    return {'Radiòleg': name, 'Correu': email, 'Actiu aquesta setmana': actiu, 'Mínim setmanal': mn,
            'Màxim setmanal': mx, 'Centres on pot informar': centres, 'Dies sense activitat': days_off,
            'Observacions': notes, 'competències': comps}


RADIOLOGISTS = [
    _rad('Alpha, Anna', 'anna.alpha@demo.invalid', 60, 75, {'RM Neuro': 'P', 'TC Neuro': 'S'}, f"{N}, {S}"),
    _rad('Beta, Bernat', 'bernat.beta@demo.invalid', 60, 75, {'RM Body': 'P', 'TC Body': 'S'}, f"{N}, {O}"),
    _rad('Gamma, Carla', 'carla.gamma@demo.invalid', 48, 60, {'RM MSK': 'P', 'TC MSK': 'S', 'RM Body': 'S'}),
    _rad('Delta, David', 'david.delta@demo.invalid', 48, 60, {'RM Neuro': 'S', 'TC Neuro': 'P'}),
    _rad('Epsilon, Elena', 'elena.epsilon@demo.invalid', 30, 40, {'TC Body': 'P', 'RM Body': 'S', 'TC Miscel·lània': 'S'},
         days_off='Dj, Dv', notes='Contracte del 50%'),
    _rad('Zeta, Francesc', 'francesc.zeta@demo.invalid', 30, 45,
         {'TC Neuro': 'S', 'TC Body': 'S', 'TC MSK': 'S', 'TC Miscel·lània': 'P'}, f"{O}, {S}", notes='Polivalent TC'),
    _rad('Eta, Gabriela', 'gabriela.eta@demo.invalid', 0, 20, {'RM Body': 'S'}, notes='Contracte petit: programada si vol'),
    _rad('Theta, Hèctor', 'hector.theta@demo.invalid', 0, 0, {'RM Neuro': 'S'}, notes='Només cobreix guàrdies'),
    _rad('Iota, Irene', 'irene.iota@demo.invalid', 0, 16, {'RM Cardio': 'P', 'TC Cardio': 'P'}, notes="Unitat de cor (altra unitat de l'IDI)"),
    _rad('Kappa, Jordi', 'jordi.kappa@demo.invalid', 0, 25, {'RM MSK': 'P'}, notes="Altra unitat de l'IDI"),
    _rad('Lambda, Laia', 'laia.lambda@demo.invalid', 0, 30, {'TC Body': 'S', 'RM Body': 'S'}, f"{N}, {S}", notes="Altra unitat de l'IDI"),
    _rad('Mu, Marc', 'marc.mu@demo.invalid', 30, 30, {'RM Neuro': 'S'}, notes='No vol extra (Màxim = Mínim)'),
    _rad('Nu, Núria', 'nuria.nu@demo.invalid', 60, 75, {'RM MSK': 'P', 'RM Body': 'S'}),
    _rad('Xi, Oriol', 'oriol.xi@demo.invalid', 48, 60, {'RM Neuro': 'S', 'RM Body': 'S', 'RM Miscel·lània': 'S'}),
    _rad('Omicron, Pau', 'pau.omicron@demo.invalid', 30, 40, {'TC Body': 'S'}, actiu='No', notes='Excedència'),
    _rad('Pi, Queralt', '', 30, 40, {'TC Body': 'S', 'TC Neuro': 'S'}, days_off='Dl', notes='Falta el correu'),
    _rad('Rho, Sergi', 'sergi.rho@demo.invalid', 0, 20, {'RM MSK': 'S', 'TC MSK': 'S'}, S, notes='Extern'),
]

# Dia de la setmana: 0 = dilluns
ABSENCES = {
    'Nu, Núria': {0: 'V', 1: 'V', 2: 'V', 3: 'V', 4: 'V'},
    'Delta, David': {0: 'C', 1: 'C'},
    'Gamma, Carla': {4: 'M'},
    'Beta, Bernat': {3: 'V', 4: 'V'},
}


def _d(wd: int) -> dt.date:
    return DEMO_WEEK + dt.timedelta(days=wd)


def _row(centre, wd, franja, agenda, act, n, ambit='', fix='', notes=''):
    return {'Centre': centre, 'Data': _d(wd) if wd is not None else None, 'Franja': franja, 'Agenda / equip': agenda,
            'Activitat': act, 'Exploracions': n, 'Àmbit': ambit, 'Radiòleg fix': fix, 'Observacions': notes}


DEMAND = (
    [_row(N, wd, 'Tarda', 'RM1', 'RM Neuro', 18, fix='Anna Alpha' if wd == 0 else '') for wd in (0, 2, 4)]
    + [_row(N, wd, 'Matí', 'RM2', 'RM Body', 20) for wd in (1, 3)]
    + [_row(N, wd, 'Matí', 'TC1', 'TC Body', 16) for wd in range(5)]
    + [_row(N, 2, 'Tarda', 'TC1', 'TC Neuro', 12, 'Mixt', notes='Inclou pacients ingressats')]
    + [_row(S, 0, 'Matí', 'RM2', 'RM MSK', 20, fix='Nu, Núria'),
       _row(S, 2, 'Tarda', 'RM2', 'RM MSK', 18),
       _row(S, 3, 'Matí', 'RM1', 'RM Neuro', 16),
       _row(S, 1, 'Tarda', 'TC1', 'TC MSK', 12),
       _row(S, 3, 'Tarda', 'RM1', 'RM Cardio', 10)]
    + [_row(E, None, '', 'TC (volum)', 'TC Body', 50, notes='Volum setmanal sense agenda fixa'),
       _row(E, 1, 'Matí', 'TC2', 'TC Neuro', 14, 'Ingressat')]
    + [_row(O, wd, 'Matí', 'TC', 'TC Miscel·lània', 10, fix='Zeta, Francesc' if wd in (0, 1) else '') for wd in range(5)]
    + [_row(O, 2, 'Tarda', 'RM', 'RM Body', 15)]
    + [_row(C, 1, 'Tarda', 'RM-A', 'RM Neuro', 20),
       _row(C, 4, 'Matí', 'RM-A', 'RM MSK', 16),
       _row(C, 3, 'Matí', 'RM-B', 'RM Mama', 12, notes='Activitat nova: encara no és al catàleg'),
       _row(C, 2, 'Matí', 'TC', 'TC Cardio', 8)]
)


def build_demo_input(path: str) -> str:
    return build_input(path, week=DEMO_WEEK, holidays=[], radiologists=RADIOLOGISTS,
                       activities=DEFAULT_ACTIVITIES, demand=DEMAND, absences=ABSENCES)


def build_demo(out_dir: str) -> dict:
    """Escriu l'entrada de demostració i el pla resultant. Retorna {'entrada': path, 'pla': path}."""
    from .io_input import load_entrada
    from .planner import plan
    from .writer import write_plan
    os.makedirs(out_dir, exist_ok=True)
    inp = os.path.join(out_dir, 'DEMO_Entrada_Setmana_2026W43.xlsx')
    build_demo_input(inp)
    res = plan(load_entrada(inp))
    out = os.path.join(out_dir, 'DEMO_Assignacio_2026W43.xlsx')
    write_plan(res, out)
    return {'entrada': inp, 'pla': out, 'result': res}
