import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from programada.model import Params, Activity, Radiologist, Block, Entrada  # noqa: E402
from programada.normalize import norm_key, AMB, parse_weekday_list  # noqa: E402
from programada.templates import DEFAULT_ACTIVITIES  # noqa: E402

WEEK = dt.date(2026, 10, 19)


class Factory:
    """Entrades petites en memòria (sense Excel) per provar el motor."""

    def __init__(self, **params):
        params.setdefault('time_limit_s', 5)
        self.params = Params(**params)
        self.acts = {norm_key(a): Activity(norm_key(a), a) for a in DEFAULT_ACTIVITIES}
        self.rads = {}
        self.blocks = []
        self.absences = {}

    def rad(self, name, mn=0, mx=50, comps=None, centres=None, days_off='', active=True):
        r = Radiologist(name=name, key=norm_key(name), email=f"{norm_key(name)}@demo.invalid", active=active,
                        weekly_min=mn, weekly_max=mx, centres=list(centres or []),
                        days_off=parse_weekday_list(days_off) or [],
                        competences={norm_key(k): v for k, v in (comps or {}).items()}, row=len(self.rads) + 5)
        self.rads[r.key] = r
        return r

    def absent(self, name, *weekdays, code='V'):
        d = self.absences.setdefault(norm_key(name), {})
        for wd in weekdays:
            d[WEEK + dt.timedelta(days=wd)] = code

    def block(self, act, n, day=0, centre='H', scope=AMB, fixed=None, franja='Tarda', agenda=None):
        i = len(self.blocks) + 1
        fixed = [fixed] if isinstance(fixed, str) else list(fixed or [])
        b = Block(id=f"F{i:03d}", row=i + 4, week=WEEK, date=None if day is None else WEEK + dt.timedelta(days=day),
                  franja=franja, centre=centre, agenda=agenda or f"EQ{i}",
                  activity_key=norm_key(act) if norm_key(act) in self.acts else '', activity_label=act,
                  n_exams=n, scope=scope, fixed_keys=[norm_key(x) for x in fixed], fixed_names=fixed)
        self.blocks.append(b)
        return b

    def entrada(self) -> Entrada:
        return Entrada(source='test', week=WEEK, params=self.params, activities=self.acts, radiologists=self.rads,
                       blocks=self.blocks, absences=self.absences)


def solve_factory(f: Factory, seed: int = 1):
    from programada.availability import build_radweeks
    from programada.solver import SolveInput, solve
    ent = f.entrada()
    rws, _ = build_radweeks(ent)
    return ent, rws, solve(SolveInput(ent.blocks, rws, ent.params, seed))


def plan_factory(f: Factory):
    from programada.planner import plan
    return plan(f.entrada())


def loads(out) -> dict:
    from collections import defaultdict
    load = defaultdict(int)
    for (_, rk), n in out.x.items():
        load[rk] += n
    return load
