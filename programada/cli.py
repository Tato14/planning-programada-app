"""Línia d'ordres.

  python -m programada assignar ENTRADA.xlsx [-o SORTIDA.xlsx] [--objectiu 80] [--lot 5]
                                [--max-radiolegs 4] [--cost-dividir 20] [--temps 20]
  python -m programada plantilla [-o Plantilla_Entrada_Setmanal.xlsx]
  python -m programada demo [-o carpeta]

Codi de sortida: 0 correcte · 1 errors a l'entrada · 2 el pla no supera la validació.
"""
from __future__ import annotations

import argparse
import copy
import os
import sys

from .io_input import load_entrada
from .model import ERROR, AVIS
from .normalize import week_label, week_code


def _print_warnings(ws, levels=(ERROR, AVIS)):
    for w in ws:
        if w.level in levels:
            src = f" [{w.source}]" if w.source else ''
            print(f"  {w.level}: {w.message}{src}")


def cmd_assignar(a) -> int:
    from .planner import plan
    from .writer import write_plan
    ent = load_entrada(a.entrada)
    if ent.has_errors() or ent.week is None:
        print("L'entrada té errors:")
        _print_warnings(ent.warnings, (ERROR,))
        return 1
    p = copy.deepcopy(ent.params)
    if a.objectiu is not None:
        p.target_utilisation = a.objectiu / 100 if a.objectiu > 1 else a.objectiu
    if a.lot is not None:
        p.min_chunk = a.lot
    if a.max_radiolegs is not None:
        p.max_rads_per_block = a.max_radiolegs
    if a.cost_dividir is not None:
        p.split_cost_exams = a.cost_dividir
    if a.temps is not None:
        p.time_limit_s = a.temps
    res = plan(ent, p.clamp())
    out = a.o or os.path.join(os.path.dirname(os.path.abspath(a.entrada)), f"Assignacio_{week_code(res.week)}.xlsx")
    write_plan(res, out)
    dem = sum(b.n_exams for b in res.blocks)
    asg = sum(x.n_exams for x in res.assignments)
    print(f"{week_label(res.week)}: {asg} de {dem} exploracions assignades, {dem - asg} pendents · {res.stats.status} en {res.stats.wall_time:.1f} s")
    print(f"Sortida: {out}")
    _print_warnings(res.warnings + res.validation)
    return 2 if any(w.level == ERROR for w in res.validation) else 0


def cmd_plantilla(a) -> int:
    from .templates import build_input
    out = a.o or 'Plantilla_Entrada_Setmanal.xlsx'
    build_input(out)
    print(f"Plantilla: {out}")
    return 0


def cmd_demo(a) -> int:
    from .demo import build_demo
    d = build_demo(a.o or 'demo')
    print(f"Entrada: {d['entrada']}\nAssignació: {d['pla']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='programada', description="Assignació d'activitat programada TD")
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('assignar', help="assigna la demanda d'un fitxer d'entrada")
    s.add_argument('entrada')
    s.add_argument('-o', help='Excel de sortida')
    s.add_argument('--objectiu', type=float, help="ocupació objectiu de l'extra (%%)")
    s.add_argument('--lot', type=int, help='mida mínima de lot')
    s.add_argument('--max-radiolegs', type=int, help='màxim de radiòlegs per bloc')
    s.add_argument('--cost-dividir', type=float, help='cost de dividir un bloc (exploracions equivalents)')
    s.add_argument('--temps', type=float, help='temps màxim de càlcul (s)')
    s.set_defaults(fn=cmd_assignar)
    s = sub.add_parser('plantilla', help="plantilla d'entrada buida")
    s.add_argument('-o')
    s.set_defaults(fn=cmd_plantilla)
    s = sub.add_parser('demo', help='entrada i assignació de demostració (dades fictícies)')
    s.add_argument('-o')
    s.set_defaults(fn=cmd_demo)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == '__main__':
    sys.exit(main())
