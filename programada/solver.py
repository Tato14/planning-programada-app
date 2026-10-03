"""Model d'assignació (OR-Tools CP-SAT).

Variables
  x[b,r]  exploracions del bloc b assignades al radiòleg r (enter)
  y[b,r]  1 si r participa al bloc b
  u[b]    exploracions del bloc b sense assignar

Restriccions dures
  - Σ_r x[b,r] + u[b] = n_b
  - Exploracions de r a la setmana ≤ capacitat de r
  - Només radiòlegs elegibles: actius i amb capacitat aquesta setmana, amb la
    competència per a l'activitat, amb accés al centre (si en tenen de registrats) i,
    si el bloc té ingressats, treballant aquell mateix dia. El radiòleg fix d'un bloc
    és elegible encara que no tingui la competència o el centre registrats, però
    només fins a la seva part del bloc. Si no treballa un dia que el servei sí (absència
    o dia sense activitat), el pacte no s'aplica aquell dia: queda com a candidat normal
    i el bloc pot anar a un substitut. En caps de setmana i festius el pacte es manté.
  - Si es divideix un bloc: lots d'una mida mínima i un màxim de radiòlegs per bloc.

Objectiu (de més a menys important; els pesos estan escalonats perquè cada nivell
domini els següents)
  1. Cobrir la demanda (els blocs amb ingressats compten el triple)
  2. Respectar el radiòleg fix pactat
  3. Omplir l'obligació contractual; si no n'hi ha per a tothom, el dèficit es
     reparteix en proporció al mínim de cadascú
  4. Repartir l'extra en proporció a la capacitat extra declarada (trams convexos:
     cada exploració costa més com més a prop és del màxim, i per sobre de
     l'ocupació objectiu el cost es dispara)
  5. No dividir blocs sense necessitat (cada radiòleg addicional en un bloc té un cost)
  6. Que l'agenda vagi a qui treballa aquell dia, i l'activitat preferida (P):
     decideixen el repartiment entre opcions equivalents
  7. Desempat determinista (llavor fixa)
"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from .model import Params, SolveStats
from .normalize import has_inpatients

SCALE = 100            # exploracions -> centèsimes (la capacitat pot ser fraccionària)

# Costos per centèsima d'exploració (1 exploració = 100)
OBL_TIERS = 10                 # trams de la zona d'obligació (10% cadascun)
OBL_REWARD = 300               # recompensa del primer tram d'obligació
OBL_STEP = 10                  # la recompensa baixa 10 per tram -> s'iguala el % d'obligació cobert
EXTRA_BELOW = [10, 20, 30, 40, 50, 60, 70, 80]   # 8 trams fins a l'ocupació objectiu
EXTRA_ABOVE = [200, 300, 400, 500]               # 4 trams de l'objectiu al 100%
UNC_COST = 2000       # × prioritat del bloc (1 normal, 3 amb ingressats)
FIX_COST = 1000       # per exploració del radiòleg fix que va a un altre
PREF_BONUS = 3        # per sota d'un tram d'equitat: tria la barreja, no la quantitat
AWAY_COST = 5         # bloc ambulatori d'un dia en què el radiòleg no hi és (l'informarà més tard)
SUSPENDED_COST = 900  # el fix que no hi és aquell dia: per sobre d'obligació i equitat (≤ 800), per sota de cobrir (2000)
SPLIT_UNIT = 1000     # cost per "exploració equivalent" de la penalització de dividir
NOISE_MAX = 9         # per exploració


@dataclass
class SolveInput:
    blocks: list
    radweeks: dict
    params: Params
    seed: int = 0


@dataclass
class SolveOutput:
    x: dict                    # {(block_id, rad_key): n}
    unassigned: dict           # {block_id: n}
    eligible: dict             # {block_id: [rad_key]}
    ineligible_reasons: dict   # {block_id: {rad_key: motiu}}
    fixed_targets: dict        # {(block_id, rad_key): exploracions pactades}
    exempt: dict               # {(block_id, rad_key): 'competència' | 'accés al centre'}
    stats: SolveStats
    notes: list = field(default_factory=list)
    suspended: dict = field(default_factory=dict)   # {(block_id, fix): motiu} pacte no aplicable aquell dia


def _noise(seed: int, a: str, b: str) -> int:
    h = hashlib.sha1(f"{seed}|{a}|{b}".encode()).digest()
    return h[0] % (NOISE_MAX + 1)


def split_int(total: int, k: int) -> list:
    base = total // k
    rest = total - base * k
    return [base + (1 if i < rest else 0) for i in range(k)]


def build_tiers(min_cu: int, cap_cu: int, target: float) -> list:
    """[(amplada, cost per unitat)] convexos (cost creixent).

    Zona d'obligació: recompenses decreixents (s'omple primer i, si no n'hi ha prou
    per a tothom, el dèficit es reparteix en proporció al mínim de cadascú).
    Zona extra: costos creixents relatius a la capacitat extra de cadascú, amb un salt
    a partir de l'ocupació objectiu (equitat proporcional a la capacitat declarada).
    """
    tiers = []
    min_cu = max(0, min(min_cu, cap_cu))
    if min_cu > 0:
        for k, w in enumerate(split_int(min_cu, OBL_TIERS)):
            if w > 0:
                tiers.append((w, -(OBL_REWARD - k * OBL_STEP)))
    extra = cap_cu - min_cu
    if extra > 0:
        t = min(max(target, 0.3), 1.0)
        bounds = [t * (i + 1) / len(EXTRA_BELOW) for i in range(len(EXTRA_BELOW))]
        bounds += [t + (1 - t) * (i + 1) / len(EXTRA_ABOVE) for i in range(len(EXTRA_ABOVE))]
        costs = EXTRA_BELOW + EXTRA_ABOVE
        prev = 0
        for f, c in zip(bounds, costs):
            bound = round(extra * f)
            w = bound - prev
            if w > 0:
                tiers.append((w, c))
            prev = bound
        if prev < extra:
            tiers.append((extra - prev, costs[-1]))
    return tiers


def service_day(params: Params, d) -> bool:
    """Dia en què el servei treballa (laborable i no festiu)."""
    return d.weekday() in params.working_days and d not in set(params.holidays)


def eligibility(inp: SolveInput) -> tuple:
    """({bloc: [elegibles]}, {bloc: {radiòleg: motiu}}, {(bloc, radiòleg): exempció},
    {(bloc, radiòleg fix): motiu pel qual el pacte no s'aplica aquell dia})."""
    elig, why, exempt, suspended = {}, {}, {}, {}
    for b in inp.blocks:
        elig[b.id], why[b.id] = [], {}
        if not b.activity_key or b.n_exams <= 0:
            continue
        fixed = set(b.fixed_keys)
        for key, rw in inp.radweeks.items():
            r = rw.radiologist
            if rw.cap <= 0:
                if rw.availability <= 0:
                    why[b.id][key] = 'no disponible aquesta setmana'
                else:
                    why[b.id][key] = 'sense capacitat declarada'
                continue
            if has_inpatients(b.scope) and b.date is not None and not rw.available_on(b.date):
                why[b.id][key] = f"{rw.why_unavailable(b.date)} el {b.date:%d/%m} (ingressats, termini 24 h)"
                continue
            special = key in fixed
            if special and b.date is not None and service_day(inp.params, b.date) and not rw.available_on(b.date):
                # El fix no treballa un dia que el servei sí: el pacte no s'aplica aquell dia. Continua
                # com a candidat normal (si té competència i accés) i el bloc pot anar a un substitut.
                suspended[(b.id, key)] = f"{rw.why_unavailable(b.date)} el {b.date:%d/%m}"
                special = False
            if not r.can_do(b.activity_key):
                if not special:
                    why[b.id][key] = f"sense competència {b.activity_label}"
                    continue
                exempt[(b.id, key)] = 'competència'
            if not r.can_report_at(b.centre):
                if not special:
                    why[b.id][key] = f"sense accés a {b.centre}"
                    continue
                exempt.setdefault((b.id, key), 'accés al centre')
            elig[b.id].append(key)
    return elig, why, exempt, suspended


def fixed_targets(blocks: list, elig: dict, suspended: dict) -> dict:
    """{(bloc, radiòleg fix): exploracions}. Si un bloc té diversos fixos elegibles, es reparteix."""
    out = {}
    for b in blocks:
        usable = [k for k in b.fixed_keys if k in elig.get(b.id, []) and (b.id, k) not in suspended]
        for k, share in zip(usable, split_int(b.n_exams, len(usable)) if usable else []):
            if share > 0:
                out[(b.id, k)] = share
    return out


def _greedy(inp: SolveInput, elig: dict, targets: dict, exempt: dict, cap_cu: dict) -> dict:
    """Solució inicial ràpida (i pla B si el solver no troba res a temps)."""
    load = defaultdict(int)
    x = defaultdict(int)
    for (bid, k), t in sorted(targets.items()):
        take = min(t, (cap_cu.get(k, 0) - load[k]) // SCALE)
        if take > 0:
            x[(bid, k)] += take
            load[k] += take * SCALE
    for b in sorted(inp.blocks, key=lambda b: (-b.priority, b.date or b.week, -b.n_exams, b.id)):
        remaining = b.n_exams - sum(v for (bid, _), v in x.items() if bid == b.id)
        cands = [k for k in elig.get(b.id, []) if (b.id, k) not in exempt]
        while remaining > 0 and cands:
            cands.sort(key=lambda k: (load[k] / cap_cu[k] if cap_cu.get(k) else 9e9, k))
            k = cands.pop(0)
            take = min(remaining, (cap_cu.get(k, 0) - load[k]) // SCALE)
            if take > 0:
                x[(b.id, k)] += take
                load[k] += take * SCALE
                remaining -= take
    return {k: v for k, v in x.items() if v > 0}


def solve(inp: SolveInput) -> SolveOutput:
    t0 = time.time()
    p = inp.params
    elig, why, exempt, suspended = eligibility(inp)
    targets = fixed_targets(inp.blocks, elig, suspended)
    solvable = [b for b in inp.blocks if b.activity_key and b.n_exams > 0]
    cap_cu = {k: int(rw.cap * SCALE + 1e-6) for k, rw in inp.radweeks.items()}
    min_cu = {k: int(rw.min * SCALE + 1e-6) for k, rw in inp.radweeks.items()}

    model = cp_model.CpModel()
    x, y, u = {}, {}, {}
    obj = []
    for b in solvable:
        n = b.n_exams
        u[b.id] = model.NewIntVar(0, n, f"u_{b.id}")
        terms, ys = [], []
        fixed_here = {k for (bid, k) in targets if bid == b.id}
        for rk in elig[b.id]:
            # L'exempció (fix sense competència o accés registrat) val només fins a la seva part
            ub = targets.get((b.id, rk), 0) if (b.id, rk) in exempt else n
            if ub <= 0:
                continue
            chunk = 1 if rk in fixed_here else min(p.min_chunk, ub)
            yv = model.NewBoolVar(f"y_{b.id}_{rk}")
            if chunk == ub == n:
                xv = n * yv            # bloc petit (≤ lot mínim): sencer o res
            else:
                xv = model.NewIntVar(0, ub, f"x_{b.id}_{rk}")
                model.Add(xv <= ub * yv)
                model.Add(xv >= chunk * yv)
            x[(b.id, rk)] = xv
            y[(b.id, rk)] = yv
            terms.append(xv)
            ys.append(yv)
            r = inp.radweeks[rk].radiologist
            per_exam = _noise(inp.seed, b.id, rk)
            if r.prefers(b.activity_key):
                per_exam -= PREF_BONUS * SCALE
            if (b.id, rk) in suspended:
                per_exam += SUSPENDED_COST * SCALE       # va a qui hi és sempre que algú el pugui fer
            elif b.date is not None and not inp.radweeks[rk].available_on(b.date):
                per_exam += AWAY_COST * SCALE
            if per_exam:
                obj.append(per_exam * xv)
        model.Add(sum(terms) + u[b.id] == n)
        max_r = max(p.max_rads_per_block, len(fixed_here))
        if len(ys) > max_r:
            model.Add(sum(ys) <= max_r)
        if len(ys) > 1 and p.split_cost_exams > 0:
            # Només es penalitza cada radiòleg addicional: un bloc amb un sol radiòleg no paga res
            extra_r = model.NewIntVar(0, len(ys) - 1, f"split_{b.id}")
            model.Add(extra_r >= sum(ys) - 1)
            obj.append(int(p.split_cost_exams * SPLIT_UNIT) * extra_r)
        obj.append(UNC_COST * b.priority * SCALE * u[b.id])

    # Capacitat i trams de càrrega
    for rk, rw in inp.radweeks.items():
        mine = [x[(b.id, rk)] for b in solvable if (b.id, rk) in x]
        if not mine:
            continue
        load = SCALE * sum(mine)
        cap = cap_cu[rk]
        if cap <= 0:
            model.Add(load == 0)
            continue
        tv = []
        for i, (w, c) in enumerate(build_tiers(min_cu[rk], cap, p.target_utilisation)):
            v = model.NewIntVar(0, w, f"t_{rk}_{i}")
            tv.append(v)
            obj.append(c * v)
        model.Add(sum(tv) == load)

    # Radiòleg fix pactat (restricció tova)
    for (bid, rk), t in targets.items():
        if (bid, rk) not in x:
            continue
        s = model.NewIntVar(0, t, f"fix_{bid}_{rk}")
        model.Add(s >= t - x[(bid, rk)])
        obj.append(FIX_COST * SCALE * s)

    model.Minimize(sum(obj))

    g = _greedy(inp, elig, targets, exempt, cap_cu)
    for key, v in x.items():
        # Si x = n·y amb n = 1, OR-Tools retorna la mateixa variable y: no s'ha de suggerir dues vegades
        if isinstance(v, cp_model.IntVar) and v is not y[key]:
            model.AddHint(v, g.get(key, 0))
        model.AddHint(y[key], 1 if g.get(key, 0) > 0 else 0)

    solver = cp_model.CpSolver()
    # Cerca paral·lela determinista: el mateix input dona sempre el mateix pla,
    # independentment de la càrrega de la màquina (límit en temps determinista).
    solver.parameters.num_workers = 8
    solver.parameters.interleave_search = True
    solver.parameters.max_deterministic_time = float(p.time_limit_s)
    solver.parameters.max_time_in_seconds = max(120.0, 10 * float(p.time_limit_s))   # només de seguretat
    solver.parameters.random_seed = int(inp.seed) % (2 ** 31)
    status = solver.Solve(model)
    st_name = solver.StatusName(status)

    notes = []
    xs, us = {}, {}
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for key, v in x.items():
            val = solver.Value(v)
            if val > 0:
                xs[key] = int(val)
        for bid, v in u.items():
            val = solver.Value(v)
            if val > 0:
                us[bid] = int(val)
        objective, bound = solver.ObjectiveValue(), solver.BestObjectiveBound()
    else:
        detail = model.Validate() if st_name == 'MODEL_INVALID' else ''
        notes.append(f"El càlcul no ha trobat solució ({st_name}{': ' + detail if detail else ''}); s'usa el repartiment simple de reserva.")
        xs = dict(g)
        for b in solvable:
            got = sum(v for (bid, _), v in xs.items() if bid == b.id)
            if got < b.n_exams:
                us[b.id] = b.n_exams - got
        objective = bound = 0.0
        st_name = f"RESERVA ({st_name})"

    for b in inp.blocks:
        if b not in solvable and b.n_exams > 0:
            us[b.id] = b.n_exams

    stats = SolveStats(status=st_name, wall_time=time.time() - t0, objective=objective, bound=bound,
                       n_vars=len(x) * 2 + len(u), n_blocks=len(inp.blocks), n_radiologists=len(inp.radweeks),
                       seed=inp.seed)
    return SolveOutput(x=xs, unassigned=us, eligible=elig, ineligible_reasons=why,
                       fixed_targets=targets, exempt=exempt, stats=stats, notes=notes, suspended=suspended)
