"""Propietats del motor d'assignació."""
from programada.model import ERROR
from programada.normalize import INGR, MIXT
from programada.availability import build_radweeks
from conftest import Factory, WEEK, solve_factory, plan_factory, loads


def test_capacity_and_competence_respected():
    f = Factory()
    f.rad('A', 0, 20, {'RM Neuro': 'S'})
    f.rad('B', 0, 20, {'RM Body': 'S'})
    for i in range(5):
        f.block('RM Neuro', 8, day=i)
    f.block('RM Body', 10)
    ent, rws, out = solve_factory(f)
    load = loads(out)
    assert load['a'] <= 20 and load['b'] <= 20
    bmap = {b.id: b for b in f.blocks}
    for (bid, rk), n in out.x.items():
        assert ent.radiologists[rk].can_do(bmap[bid].activity_key)
    assert sum(out.unassigned.values()) == 40 - 20


def test_skill_interplay_avoids_greedy_trap():
    """El polivalent ha d'anar a l'activitat que només ell pot fer."""
    f = Factory()
    f.rad('Polivalent', 0, 30, {'RM Neuro': 'S', 'RM Body': 'S'})
    f.rad('Nomes body', 0, 30, {'RM Body': 'S'})
    f.block('RM Body', 30, day=0)
    f.block('RM Neuro', 30, day=1)
    ent, rws, out = solve_factory(f)
    assert not out.unassigned
    assert out.x.get(('F002', 'polivalent')) == 30
    assert out.x.get(('F001', 'nomesbody')) == 30


def test_extra_is_proportional_to_declared_capacity():
    f = Factory(split_cost_exams=0, min_chunk=1)
    f.rad('Petit', 0, 10, {'TC Body': 'S'})
    f.rad('Mitja', 0, 20, {'TC Body': 'S'})
    f.rad('Gran', 0, 30, {'TC Body': 'S'})
    for i in range(6):
        f.block('TC Body', 5, day=i % 5)
    ent, rws, out = solve_factory(f)
    load = loads(out)
    occ = {k: load[k] / rws[k].cap for k in rws}
    assert max(occ.values()) - min(occ.values()) <= 0.2, occ
    assert load['gran'] > load['mitja'] > load['petit']


def test_obligation_filled_before_voluntary_extra():
    f = Factory()
    f.rad('Contracte', 40, 50, {'TC Body': 'S'})
    f.rad('Voluntari', 0, 50, {'TC Body': 'S'})
    for i in range(4):
        f.block('TC Body', 10, day=i)
    ent, rws, out = solve_factory(f)
    load = loads(out)
    assert load['contracte'] == 40 and load['voluntari'] == 0


def test_fixed_radiologist_and_substitution_when_absent():
    f = Factory()
    f.rad('Fix', 0, 50, {'RM Neuro': 'S'})
    f.rad('Altre', 0, 50, {'RM Neuro': 'S'})
    f.block('RM Neuro', 16, day=0, fixed='Fix')
    f.block('RM Neuro', 16, day=1)
    ent, rws, out = solve_factory(f)
    assert out.x.get(('F001', 'fix')) == 16
    # Ara és de vacances tota la setmana: el bloc va a l'altre i queda marcat com a substitució
    f.absent('Fix', 0, 1, 2, 3, 4)
    res = plan_factory(f)
    a = next(a for a in res.assignments if a.block_id == 'F001')
    assert a.radiologist_key == 'altre'
    assert any(fl.startswith('Substitueix el radiòleg fix Fix (vacances tota la setmana)') for fl in a.flags)


def test_fixed_without_competence_only_for_its_share():
    f = Factory()
    f.rad('Fix', 0, 50, {'RM Neuro': 'S'})          # no té TC Body registrat
    f.rad('A', 0, 50, {'TC Body': 'S'})
    f.block('TC Body', 20, fixed=['Fix'])
    res = plan_factory(f)
    got = {a.radiologist_key: a for a in res.assignments}
    assert got['fix'].n_exams == 20
    assert any('sense la competència TC Body' in fl for fl in got['fix'].flags)
    assert not [w for w in res.validation if w.level == ERROR]
    # Dos fixos, un sense competència: aquest no pot passar de la seva meitat
    f2 = Factory()
    f2.rad('Fix', 0, 50, {'RM Neuro': 'S'})
    f2.rad('Fix2', 0, 8, {'TC Body': 'S'})
    f2.rad('A', 0, 50, {'TC Body': 'S'})
    f2.block('TC Body', 20, fixed=['Fix', 'Fix2'])
    ent, rws, out = solve_factory(f2)
    assert out.x.get(('F001', 'fix'), 0) <= 10


def test_inpatients_require_same_day_availability():
    f = Factory()
    f.rad('Absent dimarts', 0, 50, {'TC Body': 'S'})
    f.rad('No treballa dimarts', 0, 50, {'TC Body': 'S'}, days_off='Dt')
    f.rad('Present', 0, 10, {'TC Body': 'S'})
    f.absent('Absent dimarts', 1)
    f.block('TC Body', 10, day=1, scope=INGR)
    ent, rws, out = solve_factory(f)
    assert out.x.get(('F001', 'present')) == 10
    assert set(out.eligible['F001']) == {'present'}
    assert 'dia sense activitat' in out.ineligible_reasons['F001']['notreballadimarts']
    # Festiu: ningú hi treballa, queda pendent amb motiu
    f2 = Factory()
    f2.params.holidays = [WEEK + __import__('datetime').timedelta(days=2)]
    f2.rad('A', 0, 50, {'TC Body': 'S'})
    f2.block('TC Body', 10, day=2, scope=MIXT)
    res = plan_factory(f2)
    assert sum(p.n_exams for p in res.pendings) == 10
    assert any('festiu' in r for r in res.pendings[0].reasons)


def test_centre_access_is_a_hard_rule():
    f = Factory()
    f.rad('Nomes Nord', 0, 50, {'TC Body': 'S'}, centres=['Hospital Demo Nord'])
    f.rad('Tots', 0, 10, {'TC Body': 'S'})
    f.block('TC Body', 20, centre='Hospital Demo Sud')
    res = plan_factory(f)
    assert all(a.radiologist_key == 'tots' for a in res.assignments)
    assert sum(p.n_exams for p in res.pendings) == 10
    assert any('sense accés a Hospital Demo Sud' in r for r in res.pendings[0].reasons)
    # Coincidència per paraules: 'Sud' val per a 'Hospital Demo Sud'
    f.rads['nomesnord'].centres = ['Nord', 'Sud']
    res = plan_factory(f)
    assert not res.pendings


def test_preference_decides_the_mix_not_the_amount():
    f = Factory()
    f.rad('Vol neuro', 0, 30, {'RM Neuro': 'P', 'RM Body': 'S'})
    f.rad('Vol body', 0, 30, {'RM Neuro': 'S', 'RM Body': 'P'})
    f.block('RM Neuro', 20, day=0)
    f.block('RM Body', 20, day=1)
    ent, rws, out = solve_factory(f)
    assert out.x.get(('F001', 'volneuro')) == 20 and out.x.get(('F002', 'volbody')) == 20


def test_agenda_goes_to_who_is_there_that_day():
    f = Factory()
    f.rad('Absent dilluns', 0, 30, {'RM Body': 'S'})
    f.rad('Present', 0, 30, {'RM Body': 'S'})
    f.absent('Absent dilluns', 0)
    f.block('RM Body', 15, day=0)
    f.block('RM Body', 15, day=2)
    ent, rws, out = solve_factory(f)
    assert out.x.get(('F001', 'present')) == 15


def test_days_off_do_not_reduce_capacity_but_absences_do():
    f = Factory()
    f.rad('Parcial', 30, 40, {'RM Body': 'S'}, days_off='Dj, Dv')
    f.rad('Parcial absent', 30, 40, {'RM Body': 'S'}, days_off='Dj, Dv')
    f.absent('Parcial absent', 0)
    f.absent('Parcial absent', 3)                  # dijous ja no treballa: no compta
    rws, _ = build_radweeks(f.entrada())
    assert rws['parcial'].cap == 40 and rws['parcial'].availability == 1
    assert abs(rws['parcialabsent'].cap - 40 * 2 / 3) < 1e-9
    assert abs(rws['parcialabsent'].min - 30 * 2 / 3) < 1e-9


def test_holiday_reduces_capacity_only_of_who_works_that_day():
    import datetime as dt
    f = Factory()
    f.params.holidays = [WEEK + dt.timedelta(days=4)]
    f.rad('Ple', 0, 50, {'RM Body': 'S'})
    f.rad('No treballa dv', 0, 40, {'RM Body': 'S'}, days_off='Dv')
    rws, _ = build_radweeks(f.entrada())
    assert rws['ple'].cap == 40
    assert rws['notreballadv'].cap == 40


def test_fractional_capacity_is_never_exceeded():
    f = Factory(min_chunk=1, split_cost_exams=0)
    f.rad('A', 30, 45, {'TC Body': 'S'})
    f.absent('A', 0, code='M')                     # 0,9 × 45 = 40,5
    for i in range(6):
        f.block('TC Body', 9, day=i % 5)
    ent, rws, out = solve_factory(f)
    assert loads(out)['a'] <= 40


def test_min_chunk_and_max_radiologists_per_block():
    f = Factory(min_chunk=5, max_rads_per_block=2)
    for n in ('A', 'B', 'C'):
        f.rad(n, 0, 12, {'TC Body': 'S'})
    f.block('TC Body', 30)
    ent, rws, out = solve_factory(f)
    parts = [n for (bid, _), n in out.x.items() if bid == 'F001']
    assert len(parts) <= 2 and all(n >= 5 for n in parts)


def test_unknown_activity_stays_pending_with_reason():
    f = Factory()
    f.rad('A', 0, 50, {'RM Body': 'S'})
    f.block('RM Mama', 12)
    res = plan_factory(f)
    assert res.pendings and "no és cap de les columnes" in res.pendings[0].reasons[0]


def test_determinism():
    def build():
        f = Factory()
        for n in ['A', 'B', 'C', 'D']:
            f.rad(n, 0, 40, {'TC Body': 'S', 'RM Body': 'S'})
        for i in range(10):
            f.block('TC Body' if i % 2 else 'RM Body', 9, day=i % 5)
        return f
    _, _, o1 = solve_factory(build(), seed=7)
    _, _, o2 = solve_factory(build(), seed=7)
    assert o1.x == o2.x
