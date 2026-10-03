"""Del resultat del solver a assignacions explicades i pendents amb motiu.

Cada assignació es classifica respecte a l'obligació setmanal del radiòleg: es
recorren les seves assignacions (primer les fixes, després per data) i s'omple el
Mínim; el que en queda per sobre és extra. És informatiu: indica quina part de la
feina va més enllà del contracte.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict

from .model import Assignment, Pending, Entrada, KIND_FIX, KIND_OBLIG, KIND_EXTRA
from .normalize import FRANJA_ORDER, WEEKDAY_SHORT, has_inpatients, week_code


def short_id(prefix: str, *parts) -> str:
    h = hashlib.sha1('|'.join(str(p) for p in parts).encode()).hexdigest()[:8].upper()
    return f"{prefix}-{h}"


def _sort_key(b):
    return (b.date or b.week, FRANJA_ORDER.get(b.franja, 4), b.centre, b.id)


def fixed_status(entrada: Entrada, radweeks: dict, x: dict, targets: dict, why: dict, suspended: dict) -> dict:
    """{(bloc, radiòleg fix): (nom, motiu)} per als fixos que no tenen la seva part del bloc."""
    out = {}
    for b in entrada.blocks:
        if not b.activity_key:
            continue
        for k, name in zip(b.fixed_keys, b.fixed_names):
            got = x.get((b.id, k), 0)
            if (b.id, k) in suspended:
                if got == 0:
                    out[(b.id, k)] = (name, suspended[(b.id, k)])
                continue
            if (b.id, k) not in targets:
                rw = radweeks.get(k)
                if k not in entrada.radiologists or rw is None:
                    reason = 'no és actiu aquesta setmana'
                else:
                    reason = why.get(b.id, {}).get(k) or 'no elegible'
                    absent = rw.absence_text()
                    if reason == 'no disponible aquesta setmana' and absent:
                        reason = absent
                out[(b.id, k)] = (name, reason)
            elif got < targets[(b.id, k)]:
                out[(b.id, k)] = (name, f"capacitat esgotada ({got} de {targets[(b.id, k)]})")
    return out


def classify(entrada: Entrada, radweeks: dict, x: dict, targets: dict, why: dict, suspended: dict) -> list:
    bmap = {b.id: b for b in entrada.blocks}
    per_rad = defaultdict(list)
    n_rads_block = defaultdict(int)
    for (bid, rk), n in x.items():
        if n > 0 and bid in bmap:
            per_rad[rk].append((bmap[bid], n))
            n_rads_block[bid] += 1
    missing_fixed = fixed_status(entrada, radweeks, x, targets, why, suspended)
    used_ids = set()
    out = []
    for rk, items in sorted(per_rad.items()):
        rw = radweeks.get(rk)
        if rw is None:
            continue
        r = rw.radiologist
        items.sort(key=lambda bn: (0 if rk in bn[0].fixed_keys else 1,) + _sort_key(bn[0]))
        remaining = rw.min
        for b, n in items:
            oblig = min(n, int(remaining + 1e-6)) if remaining > 0 else 0
            remaining -= oblig
            extra = n - oblig
            fixed = rk in b.fixed_keys
            if fixed:
                kind = KIND_FIX + (' + extra' if extra and rw.min > 0 else '')
                reason = 'Radiòleg fix pactat' + (' (aquell dia no hi és)' if (b.id, rk) in suspended else '')

            elif extra == 0:
                kind, reason = KIND_OBLIG, f"Dins l'obligació setmanal ({rw.min:g})"
            elif oblig == 0:
                kind, reason = KIND_EXTRA, 'Capacitat extra declarada'
            else:
                kind, reason = f"{KIND_OBLIG} + extra", f"{oblig} dins l'obligació + {extra} extra"

            flags = []
            if has_inpatients(b.scope):
                flags.append('Inclou ingressats: termini 24 h' if b.date else 'Inclou ingressats sense data: revisar el termini amb el centre')
            elif b.date and not rw.available_on(b.date):
                nxt = rw.next_work_day(b.date)
                when = f"a partir del {WEEKDAY_SHORT[nxt.weekday()]} {nxt:%d/%m}" if nxt else 'la setmana següent'
                flags.append(f"{b.when()}: {rw.why_unavailable(b.date)}; l'informarà {when}")
            if fixed and (b.id, rk) not in suspended and not r.can_do(b.activity_key):
                flags.append(f"Radiòleg fix sense la competència {b.activity_label} registrada")
            if fixed and (b.id, rk) not in suspended and not r.can_report_at(b.centre):
                flags.append(f"Radiòleg fix sense accés registrat a {b.centre}")
            if n_rads_block[b.id] > 1:
                flags.append(f"Bloc dividit entre {n_rads_block[b.id]} radiòlegs")
            if r.prefers(b.activity_key):
                flags.append('Activitat preferida')
            if not fixed:
                for k in b.fixed_keys:
                    if (b.id, k) in missing_fixed:
                        name, motiu = missing_fixed[(b.id, k)]
                        flags.append(f"Substitueix el radiòleg fix {name} ({motiu})")

            aid = short_id('A', week_code(entrada.week), b.id, rk)
            while aid in used_ids:
                aid = short_id('A', aid, 'x')
            used_ids.add(aid)
            out.append(Assignment(id=aid, block_id=b.id, radiologist_key=rk, n_exams=n, kind=kind,
                                  oblig_exams=oblig, extra_exams=extra, fixed=fixed, reason=reason, flags=flags))
    out.sort(key=lambda a: _sort_key(bmap[a.block_id]) + (a.radiologist_key,))
    return out


def analyse_pending(entrada: Entrada, radweeks: dict, unassigned: dict, eligible: dict, why: dict,
                    x: dict, targets: dict, exempt: dict, params, suspended: dict) -> list:
    """Motius dels blocs pendents, amb els paràmetres del càlcul (no els del fitxer)."""
    p = params
    bmap = {b.id: b for b in entrada.blocks}
    load = defaultdict(int)
    parts = defaultdict(int)
    for (bid, rk), n in x.items():
        load[rk] += n
        if n > 0:
            parts[bid] += 1
    missing_fixed = fixed_status(entrada, radweeks, x, targets, why, suspended)
    out = []
    for bid, n in unassigned.items():
        if n <= 0 or bid not in bmap:
            continue
        b = bmap[bid]
        reasons, cands = [], []
        if not b.activity_key:
            reasons.append(f"L'activitat '{b.activity_label}' no és cap de les columnes de competències de la pestanya Radiòlegs")
        else:
            competent = [r for r in entrada.radiologists.values() if r.active and r.can_do(b.activity_key)]
            if not competent:
                reasons.append(f"Cap radiòleg actiu amb la competència {b.activity_label}")
            full, small, roomy = [], [], []
            for rk in eligible.get(bid, []):
                rw = radweeks[rk]
                free = int(rw.cap + 1e-6) - load[rk]
                if (bid, rk) in exempt:
                    # Fix sense competència o accés registrat: només pot fer la seva part del bloc
                    free = min(free, targets.get((bid, rk), 0) - x.get((bid, rk), 0))
                    if free <= 0:
                        continue
                name = rw.radiologist.name
                if free >= min(n, p.min_chunk) and (bid, rk) not in x:
                    roomy.append((free, name))
                elif free > 0:
                    small.append((free, name))
                else:
                    full.append((load[rk] / rw.cap * 100 if rw.cap else 100, name))
            if roomy:
                roomy.sort(reverse=True)
                names = ', '.join(f"{nm} ({fr} lliures)" for fr, nm in roomy[:4])
                if parts[bid] >= p.max_rads_per_block:
                    why_not = f"el bloc ja té el màxim de radiòlegs ({p.max_rads_per_block})"
                else:
                    why_not = f"el lot mínim ({p.min_chunk}) no deixa repartir-les sense desquadrar la resta"
                reasons.append(f"Hi ha capacitat ({names}) però {why_not}: assigna-les a mà o ajusta els paràmetres")
                cands.extend(nm for _, nm in roomy[:3])
            if small:
                small.sort(reverse=True)
                reasons.append("Elegibles amb poc marge: " + ', '.join(f"{nm} ({fr} lliures)" for fr, nm in small[:5])
                               + (f", per sota del lot mínim ({p.min_chunk})" if any(fr < p.min_chunk for fr, _ in small) else ''))
                cands.extend(nm for _, nm in small[:3])
            if full:
                full.sort(reverse=True)
                reasons.append('Capacitat esgotada dels elegibles: ' + ', '.join(f"{nm} {occ:.0f}%" for occ, nm in full[:5]))
            groups = defaultdict(list)
            for rk, reason in why.get(bid, {}).items():
                r = entrada.radiologists.get(rk)
                if r is None or not r.can_do(b.activity_key):
                    continue
                groups[reason].append(r.name)
                if reason.startswith('sense accés a'):
                    cands.append(f"{r.name} (si té accés a {b.centre})")
            for reason, names in sorted(groups.items()):
                names = sorted(names)
                reasons.append(f"Competents però {reason}: {', '.join(names[:6])}{'…' if len(names) > 6 else ''}")
            for k in b.fixed_keys:
                if (bid, k) in missing_fixed:
                    name, motiu = missing_fixed[(bid, k)]
                    reasons.append(f"Radiòleg fix {name}: {motiu}")
        out.append(Pending(block_id=bid, n_exams=n, reasons=reasons or ['Sense candidats'], candidates=cands[:5]))
    out.sort(key=lambda pd: (-bmap[pd.block_id].priority,) + _sort_key(bmap[pd.block_id]))
    return out
