"""Estructures de dades del nucli d'assignació.

Vocabulari:
  Activitat  modalitat + subespecialitat tal com surt a les columnes de competències
             de la pestanya Radiòlegs (p. ex. "RM Neuro"). La unitat és l'exploració.
  Bloc       una fila de la pestanya Demanda: centre, data (o tota la setmana), franja,
             activitat i nombre d'exploracions. Opcionalment, el radiòleg fix pactat.
  Capacitat  Mínim (obligació contractual) i Màxim (el que el radiòleg declara que pot
             fer) per setmana, en exploracions, escalats per la disponibilitat real.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import ClassVar, Optional

from .normalize import AMB, words, norm_key, has_inpatients, WEEKDAY_SHORT

# ---------------------------------------------------------------------------
# Avisos
# ---------------------------------------------------------------------------

ERROR, AVIS, INFO = 'Error', 'Avís', 'Info'


@dataclass
class DataWarning:
    level: str            # Error | Avís | Info
    category: str         # p. ex. 'Radiòlegs', 'Demanda', 'Absències', 'Validació'
    message: str
    source: str = ''      # pestanya / fila
    suggestion: str = ''  # acció recomanada

    def as_row(self) -> dict:
        return {'Nivell': self.level, 'Categoria': self.category, 'Missatge': self.message,
                'Origen': self.source, 'Suggeriment': self.suggestion}


# ---------------------------------------------------------------------------
# Paràmetres
# ---------------------------------------------------------------------------

@dataclass
class Params:
    target_utilisation: float = 0.80        # ocupació objectiu de la capacitat extra
    min_chunk: int = 5                      # mida mínima d'un lot quan es divideix un bloc
    max_rads_per_block: int = 4
    split_cost_exams: float = 20.0          # cost de dividir un bloc, en "exploracions equivalents"
    time_limit_s: float = 20.0
    working_days: list = field(default_factory=lambda: [0, 1, 2, 3, 4])
    holidays: list = field(default_factory=list)   # festius (dates) de la setmana
    seed: Optional[int] = None              # None -> derivat de la setmana

    LIMITS: ClassVar[dict] = {'target_utilisation': (0.3, 1.0), 'min_chunk': (1, 50), 'max_rads_per_block': (1, 20),
                              'split_cost_exams': (0.0, 100.0), 'time_limit_s': (1.0, 300.0)}

    def clamp(self) -> 'Params':
        """Porta cada paràmetre dins del seu rang (els mateixos rangs a la lectura, la CLI i l'app)."""
        for name, (lo, hi) in self.LIMITS.items():
            v = getattr(self, name)
            v = min(hi, max(lo, v))
            setattr(self, name, int(round(v)) if isinstance(lo, int) else float(v))
        return self

    def describe(self) -> list:
        return [
            ("Ocupació objectiu de l'extra (%)", f"{self.target_utilisation * 100:.0f}"),
            ('Mida mínima de lot (exploracions)', str(self.min_chunk)),
            ('Màxim de radiòlegs per bloc', str(self.max_rads_per_block)),
            ('Cost de dividir un bloc (exploracions equivalents)', f"{self.split_cost_exams:g}"),
            ('Temps màxim de càlcul (s)', f"{self.time_limit_s:g}"),
            ('Dies laborables', ', '.join(WEEKDAY_SHORT[d] for d in self.working_days)),
            ('Festius', ', '.join(d.strftime('%d/%m/%Y') for d in sorted(self.holidays)) or '-'),
        ]


# ---------------------------------------------------------------------------
# Activitats i radiòlegs
# ---------------------------------------------------------------------------

@dataclass
class Activity:
    key: str        # norm_key de l'etiqueta: 'rmneuro'
    label: str      # 'RM Neuro'


def centre_matches(token: str, centre: str) -> bool:
    """'Bellvitge' i 'H. Bellvitge' casen amb 'Hospital Universitari de Bellvitge';
    'CAP Badalona 2' no casa amb 'CAP Badalona 1', ni 'Edifici A' amb 'Edifici B'.

    Els números i les lletres soltes sense punt ('Edifici A', 'CAP Terrassa A') formen
    part del nom; les lletres amb punt ('H.', 'H.U.') són abreviatures i no compten."""
    if norm_key(token) == norm_key(centre):
        return True
    tw = words(token, singles=True)
    return bool(tw) and tw <= words(centre, singles=True)


@dataclass
class Radiologist:
    name: str
    key: str
    email: str = ''
    active: bool = True
    weekly_min: float = 0.0       # obligació contractual setmanal (exploracions)
    weekly_max: float = 0.0       # capacitat màxima declarada (exploracions)
    centres: list = field(default_factory=list)      # centres on pot informar ([] = tots)
    days_off: list = field(default_factory=list)     # dies de la setmana sense activitat (0 = dilluns)
    notes: str = ''
    competences: dict = field(default_factory=dict)  # clau d'activitat -> 'S' | 'P'
    row: int = 0

    def can_do(self, activity_key: str) -> bool:
        return self.competences.get(activity_key) in ('S', 'P')

    def prefers(self, activity_key: str) -> bool:
        return self.competences.get(activity_key) == 'P'

    def can_report_at(self, centre: str) -> bool:
        return not self.centres or any(centre_matches(t, centre) for t in self.centres)


# ---------------------------------------------------------------------------
# Demanda
# ---------------------------------------------------------------------------

@dataclass
class Block:
    id: str                      # 'F012' = fila 12 de la pestanya Demanda
    row: int
    week: dt.date
    date: Optional[dt.date]      # None = qualsevol dia de la setmana
    franja: str
    centre: str
    agenda: str
    activity_key: str            # '' si l'activitat no és al catàleg
    activity_label: str
    n_exams: int
    scope: str = AMB
    fixed_keys: list = field(default_factory=list)   # radiòlegs fixos pactats (claus)
    fixed_names: list = field(default_factory=list)
    notes: str = ''

    @property
    def priority(self) -> int:
        """3 = amb pacients ingressats (termini 24 h), 1 = la resta."""
        return 3 if has_inpatients(self.scope) else 1

    @property
    def weekday(self) -> Optional[int]:
        return self.date.weekday() if self.date else None

    def when(self) -> str:
        return f"{WEEKDAY_SHORT[self.date.weekday()]} {self.date:%d/%m}" if self.date else 'Setmana'

    def label(self) -> str:
        parts = [self.centre, self.agenda, self.activity_label, self.when(), self.franja]
        return ' · '.join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Disponibilitat setmanal
# ---------------------------------------------------------------------------

NON_ABSENCE = ('festiu', 'dia sense activitat', 'cap de setmana', 'dia no laborable')


@dataclass
class RadWeek:
    """Capacitat d'un radiòleg per a la setmana planificada."""
    radiologist: Radiologist
    availability: float                 # 0-1: dies que treballa aquesta setmana / dies habituals
    work_days: set = field(default_factory=set)      # dates en què treballa (sense festius ni absències)
    unavailable: dict = field(default_factory=dict)  # data -> motiu ('vacances', 'festiu', 'dia sense activitat'...)
    half_days: set = field(default_factory=set)
    cap: float = 0.0
    min: float = 0.0

    @property
    def key(self) -> str:
        return self.radiologist.key

    @property
    def extra(self) -> float:
        return max(0.0, self.cap - self.min)

    def available_on(self, d: dt.date) -> bool:
        return d in self.work_days

    def why_unavailable(self, d: dt.date) -> str:
        return self.unavailable.get(d, 'no treballa aquell dia')

    def absence_text(self) -> str:
        """Absències pròpies agrupades: 'vacances Dj 22/10-Dv 23/10, mig dia Dl 19/10'."""
        own = sorted((d, m) for d, m in self.unavailable.items() if m not in NON_ABSENCE)
        if not own and not self.half_days:
            return ''
        if self.availability <= 0 and len({m for _, m in own}) == 1:
            return f"{own[0][1]} tota la setmana"
        groups = []
        for d, m in own:
            if groups and groups[-1][2] == m and (d - groups[-1][1]).days == 1:
                groups[-1][1] = d
            else:
                groups.append([d, d, m])

        def day(x):
            return f"{WEEKDAY_SHORT[x.weekday()]} {x:%d/%m}"
        parts = [f"{m} {day(a)}" if a == b else f"{m} {day(a)}-{day(b)}" for a, b, m in groups]
        parts += [f"mig dia {day(d)}" for d in sorted(self.half_days)]
        return ', '.join(parts)

    def next_work_day(self, d: dt.date) -> Optional[dt.date]:
        later = [x for x in self.work_days if x > d]
        return min(later) if later else None


# ---------------------------------------------------------------------------
# Entrada i resultat
# ---------------------------------------------------------------------------

@dataclass
class Entrada:
    source: str
    week: dt.date
    params: Params
    activities: dict                    # clau -> Activity
    radiologists: dict                  # clau -> Radiologist
    blocks: list
    absences: dict = field(default_factory=dict)    # clau radiòleg -> {data: codi}
    warnings: list = field(default_factory=list)

    def has_errors(self) -> bool:
        return any(w.level == ERROR for w in self.warnings)


KIND_FIX, KIND_OBLIG, KIND_EXTRA = 'Fixa', 'Obligació', 'Extra'


@dataclass
class Assignment:
    id: str
    block_id: str
    radiologist_key: str
    n_exams: int
    kind: str                 # 'Fixa', 'Obligació', 'Extra', 'Obligació + extra', 'Fixa + extra'
    oblig_exams: int          # part dins de l'obligació setmanal
    extra_exams: int          # part per sobre de l'obligació
    fixed: bool = False
    reason: str = ''
    flags: list = field(default_factory=list)


@dataclass
class Pending:
    block_id: str
    n_exams: int
    reasons: list = field(default_factory=list)
    candidates: list = field(default_factory=list)


@dataclass
class SolveStats:
    status: str
    wall_time: float
    objective: float
    bound: float
    n_vars: int
    n_blocks: int
    n_radiologists: int
    seed: int

    @property
    def gap(self) -> Optional[float]:
        if not self.objective:
            return None
        return abs(self.objective - self.bound) / max(1.0, abs(self.objective))


@dataclass
class PlanResult:
    entrada: Entrada
    week: dt.date
    params: Params
    radweeks: dict
    assignments: list
    pendings: list
    warnings: list
    stats: SolveStats
    generated_at: dt.datetime
    validation: list = field(default_factory=list)

    @property
    def blocks(self) -> list:
        return self.entrada.blocks

    def blocks_by_id(self) -> dict:
        return {b.id: b for b in self.entrada.blocks}

    def block(self, block_id: str) -> Optional[Block]:
        return self.blocks_by_id().get(block_id)
