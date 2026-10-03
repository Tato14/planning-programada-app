"""Validació independent d'un pla.

No fa servir el càlcul d'elegibilitat del solver: torna a comprovar les regles a
partir de l'entrada. Error = viola una regla dura; Avís = cal revisar-ho.

  E1 Capacitat setmanal superada
  E2 Radiòleg sense competència per a l'activitat (i no és el fix del bloc)
  E3 Radiòleg inactiu o no disponible en tota la setmana
  E4 Bloc amb ingressats assignat a algú que no treballa aquell dia
  E5 Radiòleg sense accés al centre (i no és el fix del bloc)
  E6 Exploracions assignades + pendents ≠ demanda del bloc
  E7 Radiòleg fix sense competència o accés amb més exploracions que la seva part
  A1 Ocupació de la capacitat extra per sobre de l'objectiu
  A2 Bloc dividit en lots més petits que la mida mínima
  A3 Radiòleg fix disponible que no té el seu bloc
  A4 Bloc repartit entre més radiòlegs del màxim
"""
from __future__ import annotations

from collections import defaultdict

from .model import PlanResult, DataWarning, ERROR, AVIS, INFO
from .normalize import has_inpatients
from .solver import split_int


def _suspended(b, rw, p) -> bool:
    """El pacte del fix no s'aplica si no treballa un dia que el servei sí (com al solver)."""
    return bool(b.date and b.date.weekday() in p.working_days and b.date not in set(p.holidays)
                and rw is not None and not rw.available_on(b.date))


def validate_result(res: PlanResult) -> list:
    ent = res.entrada
    p = res.params
    out = []
    bmap = res.blocks_by_id()
    load = defaultdict(int)
    per_block = defaultdict(int)
    per_block_rads = defaultdict(list)
    for a in res.assignments:
        b = bmap.get(a.block_id)
        if b is None:
            out.append(DataWarning(ERROR, 'Validació', f"Assignació {a.id} d'un bloc inexistent ({a.block_id})."))
            continue
        r = ent.radiologists.get(a.radiologist_key)
        rw = res.radweeks.get(a.radiologist_key)
        name = r.name if r else a.radiologist_key
        load[a.radiologist_key] += a.n_exams
        per_block[b.id] += a.n_exams
        per_block_rads[b.id].append(a)
        if r is None or not r.active or rw is None:
            out.append(DataWarning(ERROR, 'Validació', f"E3 {name}: no és actiu però té assignat {b.label()}."))
            continue
        if rw.availability <= 0 or rw.cap <= 0:
            out.append(DataWarning(ERROR, 'Validació', f"E3 {name}: no disponible aquesta setmana però té assignat {b.label()}."))
        is_fixed = a.radiologist_key in b.fixed_keys and not _suspended(b, rw, p)
        if not r.can_do(b.activity_key) and not is_fixed:
            out.append(DataWarning(ERROR, 'Validació', f"E2 {name}: sense competència {b.activity_label} ({b.label()})."))
        if not r.can_report_at(b.centre) and not is_fixed:
            out.append(DataWarning(ERROR, 'Validació', f"E5 {name}: sense accés a {b.centre} ({b.label()})."))
        if has_inpatients(b.scope) and b.date and not rw.available_on(b.date):
            out.append(DataWarning(ERROR, 'Validació', f"E4 {name}: {rw.why_unavailable(b.date)} el {b.date:%d/%m} però té el bloc amb ingressats {b.label()}."))
        if is_fixed and (not r.can_do(b.activity_key) or not r.can_report_at(b.centre)):
            usable = [k for k in b.fixed_keys if k in res.radweeks and res.radweeks[k].cap > 0
                      and not (has_inpatients(b.scope) and b.date and not res.radweeks[k].available_on(b.date))
                      and not _suspended(b, res.radweeks[k], p)]
            share = split_int(b.n_exams, len(usable))[usable.index(a.radiologist_key)] if a.radiologist_key in usable else 0
            if a.n_exams > share:
                out.append(DataWarning(ERROR, 'Validació', f"E7 {name}: és el fix de {b.label()} sense competència o accés registrat i té {a.n_exams} exploracions, més que la seva part ({share})."))
    for k, l in load.items():
        rw = res.radweeks.get(k)
        if rw is None:
            continue
        if l > rw.cap + 1e-6:
            out.append(DataWarning(ERROR, 'Validació', f"E1 {rw.radiologist.name}: {l} exploracions > capacitat {rw.cap:g}."))
        elif rw.extra > 0 and l - rw.min > rw.extra * p.target_utilisation + 1e-6:
            occ = (l - rw.min) / rw.extra * 100
            out.append(DataWarning(AVIS, 'Validació', f"A1 {rw.radiologist.name}: se li assigna el {occ:.0f}% de la capacitat extra declarada (objectiu {p.target_utilisation * 100:.0f}%).",
                                   suggestion="Sol voler dir que no hi havia prou capacitat d'altres radiòlegs competents (o que és activitat fixa): convé confirmar-ho amb ell o ella."))
    pend = {pd_.block_id: pd_.n_exams for pd_ in res.pendings}
    for b in res.blocks:
        tot = per_block.get(b.id, 0) + pend.get(b.id, 0)
        if tot != b.n_exams:
            out.append(DataWarning(ERROR, 'Validació', f"E6 Bloc {b.id}: assignades {per_block.get(b.id, 0)} + pendents {pend.get(b.id, 0)} ≠ demanda {b.n_exams}."))
        rads = per_block_rads.get(b.id, [])
        if len(rads) > 1:
            small = [a for a in rads if a.n_exams < min(p.min_chunk, b.n_exams) and a.radiologist_key not in b.fixed_keys]
            if small:
                out.append(DataWarning(AVIS, 'Validació', f"A2 Bloc {b.id}: lot de {small[0].n_exams} exploracions (mínim {p.min_chunk})."))
            limit = max(p.max_rads_per_block, len(b.fixed_keys))
            if len(rads) > limit:
                out.append(DataWarning(AVIS, 'Validació', f"A4 Bloc {b.id}: repartit entre {len(rads)} radiòlegs (màxim {limit})."))
        for k, name in zip(b.fixed_keys, b.fixed_names):
            rw = res.radweeks.get(k)
            got = sum(a.n_exams for a in rads if a.radiologist_key == k)
            if rw and rw.cap > 0 and got == 0 and b.n_exams > 0 and b.activity_key:
                if (b.date and has_inpatients(b.scope) and not rw.available_on(b.date)) or _suspended(b, rw, p):
                    continue
                out.append(DataWarning(AVIS, 'Validació', f"A3 {name} és el fix de {b.label()} però no se li ha assignat (capacitat insuficient)."))
    if not any(w.level == ERROR for w in out):
        out.insert(0, DataWarning(INFO, 'Validació', f"Validació independent superada: {len(res.assignments)} assignacions sense infraccions de regles dures."))
    return out
