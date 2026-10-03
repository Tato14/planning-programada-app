"""Orquestrador: entrada -> capacitat -> solver -> explicacions -> validació."""
from __future__ import annotations

import copy
import datetime as dt
from typing import Optional

from .model import Entrada, Params, PlanResult, DataWarning, AVIS, INFO
from .normalize import week_code
from .availability import build_radweeks
from .solver import SolveInput, solve
from .explain import classify, analyse_pending
from .validator import validate_result


def plan(entrada: Entrada, params: Optional[Params] = None, now: Optional[dt.datetime] = None) -> PlanResult:
    """Assigna la demanda de la setmana. `params` substitueix els de la pestanya Configuració."""
    if entrada.week is None:
        raise ValueError("L'entrada no té setmana: revisa els errors de lectura.")
    p = copy.deepcopy(params or entrada.params)
    seed = p.seed if p.seed is not None else int(week_code(entrada.week).replace('W', ''))
    radweeks, warns = build_radweeks(entrada, p)
    out = solve(SolveInput(entrada.blocks, radweeks, p, seed))
    assignments = classify(entrada, radweeks, out.x, out.fixed_targets, out.ineligible_reasons, out.suspended)
    pendings = analyse_pending(entrada, radweeks, out.unassigned, out.eligible, out.ineligible_reasons,
                               out.x, out.fixed_targets, out.exempt, p, out.suspended)
    warnings = list(entrada.warnings) + warns + [DataWarning(AVIS, 'Càlcul', n) for n in out.notes]
    gap = out.stats.gap
    if out.stats.status.startswith('RESERVA'):
        warnings.append(DataWarning(AVIS, 'Càlcul', "El càlcul no ha trobat cap solució dins del temps i s'ha fet servir un repartiment simple de reserva: "
                                    "respecta les regles dures però no reparteix bé l'extra ni evita dividir agendes.",
                                    suggestion='Augmenta el temps màxim de càlcul i torna a assignar.'))
    elif out.stats.status == 'FEASIBLE':
        warnings.append(DataWarning(INFO, 'Càlcul', "Solució vàlida però no demostrada òptima dins del temps de càlcul"
                                    + (f" (marge fins a l'òptim ≤ {gap * 100:.1f}%)" if gap is not None else '') + '.',
                                    suggestion='Si cal, augmenta el temps màxim de càlcul.'))
    res = PlanResult(entrada=entrada, week=entrada.week, params=p, radweeks=radweeks, assignments=assignments,
                     pendings=pendings, warnings=warnings, stats=out.stats,
                     generated_at=now or dt.datetime.now().replace(microsecond=0))
    res.validation = validate_result(res)
    return res
