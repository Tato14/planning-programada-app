"""Capacitat setmanal de cada radiòleg.

  dies habituals   = dies laborables (Dl-Dv per defecte) menys els seus "dies sense activitat"
  dies treballats  = dies habituals menys festius i absències (V, B, C, A, G); M = mig dia
  disponibilitat   = (dies treballats - ½ × mitges jornades) / dies habituals
  capacitat        = Màxim setmanal × disponibilitat
  obligació        = Mínim setmanal × disponibilitat (mai per sobre de la capacitat)

El Màxim declarat d'un contracte parcial ja té en compte que no treballa cada dia:
per això els dies sense activitat no el redueixen, només defineixen quins dies hi és
(ingressats) i la base sobre la qual es compten les absències.
"""
from __future__ import annotations

import datetime as dt

from typing import Optional

from .model import Entrada, Params, RadWeek, DataWarning, AVIS, INFO
from .normalize import fold

FULL_ABSENCE = {'V': 'vacances', 'B': 'baixa', 'C': 'congrés/formació', 'A': 'absència',
                'G': 'guàrdia en una altra institució'}
HALF_ABSENCE = {'M': 'mig dia'}
INFO_ONLY = {'X': 'guàrdia ja assignada'}
CODES_HELP = 'V vacances, B baixa, C congrés/formació, A altra absència, G guàrdia en una altra institució, M mig dia, X guàrdia ja assignada (informatiu)'


_ABS_WORDS = [('vac', 'V'), ('baix', 'B'), ('baja', 'B'), ('cong', 'C'), ('form', 'C'), ('curs', 'C'),
              ('abs', 'A'), ('perm', 'A'), ('lliu', 'A'), ('libr', 'A'), ('fest', 'A'),
              ('mig', 'M'), ('mitj', 'M'), ('medio', 'M')]


def parse_absence_code(v) -> tuple:
    """Retorna (codi, reconegut). ('', True) si és buit. Accepta el codi d'una lletra o
    la paraula ('vacances' -> V). Un valor desconegut es tracta com a absència de dia
    complet (A) i es marca com a no reconegut perquè se'n generi un avís."""
    f = fold(v)
    if not f:
        return '', True
    if len(f) == 1:
        c = f.upper()
        if c in FULL_ABSENCE or c in HALF_ABSENCE or c in INFO_ONLY:
            return c, True
        if c in ('L', 'F'):          # lliure, festiu personal
            return 'A', True
        return 'A', False
    if f.startswith('guard'):
        # 'guàrdia ja assignada' és informatiu (X); 'guàrdia' sola és ambigua: es bloqueja el dia i s'avisa
        return ('X', True) if ('assign' in f or ' ja' in f) else ('G', False)
    for prefix, c in _ABS_WORDS:
        if f.startswith(prefix):
            return c, True
    return 'A', False


def build_radweeks(entrada: Entrada, params: Optional[Params] = None) -> tuple:
    week = entrada.week
    p = params or entrada.params
    warnings = []
    holidays = {d for d in p.holidays if week <= d <= week + dt.timedelta(days=6)}
    if holidays:
        warnings.append(DataWarning(INFO, 'Disponibilitat', f"Setmana amb {len(holidays)} festiu(s): la capacitat de qui treballa aquell dia es redueix en proporció."))
    out = {}
    for r in entrada.radiologists.values():
        if not r.active:
            continue
        days_off = set(r.days_off)
        habitual = [week + dt.timedelta(days=d) for d in p.working_days if d not in days_off]
        if not habitual:
            warnings.append(DataWarning(AVIS, 'Radiòlegs', f"{r.name}: els dies sense activitat cobreixen tots els dies laborables; no es tenen en compte i es compta com si treballés cada dia.",
                                        f"Radiòlegs, fila {r.row}", 'Revisa la columna Dies sense activitat.'))
            days_off = set()
            habitual = [week + dt.timedelta(days=d) for d in p.working_days]
        unavailable = {}
        for d in range(7):
            day = week + dt.timedelta(days=d)
            if day.weekday() not in p.working_days:
                unavailable[day] = 'cap de setmana' if day.weekday() >= 5 else 'dia no laborable'
            elif day.weekday() in days_off:
                unavailable[day] = 'dia sense activitat'
            if day in holidays:
                unavailable[day] = 'festiu'
        half = set()
        for day, code in sorted(entrada.absences.get(r.key, {}).items()):
            if not (week <= day <= week + dt.timedelta(days=6)):
                continue
            if day in unavailable:          # ja era festiu, cap de setmana o dia sense activitat
                continue
            if code in FULL_ABSENCE:
                unavailable[day] = FULL_ABSENCE[code]
            elif code in HALF_ABSENCE:
                half.add(day)
        work = {d for d in habitual if d not in unavailable}
        frac = max(0.0, (len(work) - 0.5 * len(half & work)) / len(habitual))
        cap = r.weekly_max * frac
        mn = min(r.weekly_min * frac, cap)
        out[r.key] = RadWeek(radiologist=r, availability=frac, work_days=work, unavailable=unavailable,
                             half_days=half & work, cap=cap, min=mn)
    return out, warnings


