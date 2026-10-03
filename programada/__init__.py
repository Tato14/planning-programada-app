"""Nucli d'assignació de l'activitat programada de Telediagnòstic (TD) de l'IDI.

Donada la demanda d'una setmana (blocs d'agenda) i el perfil i les preferències dels
radiòlegs, reparteix les exploracions respectant competències, accés als centres,
disponibilitat, activitat fixa pactada i obligació contractual, i distribueix
l'extra en proporció a la capacitat declarada.

El codi no conté cap nom de professional ni de centre: tot arriba al fitxer
d'entrada que es puja a l'app.

Mòduls:
  normalize     normalització de textos, dates, franges i dies
  model         estructures de dades
  xlsx_tables   lectura tolerant de taules d'Excel
  io_input      lectura del fitxer d'entrada setmanal
  availability  capacitat setmanal de cada radiòleg
  solver        model d'optimització (OR-Tools CP-SAT)
  explain       classificació de les assignacions i motius dels pendents
  validator     validació independent del pla
  planner       orquestrador
  writer        Excel de sortida amb taules amb nom
  templates     plantilla d'entrada (buida o amb dades)
  demo          joc de dades fictici
"""

__version__ = "0.2.0"
