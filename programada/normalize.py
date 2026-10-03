"""Normalització de textos, números, dates, dies de la setmana, franges i àmbit.

Tot el que entra per Excel passa per aquí abans d'arribar al model, de manera que
"RM-Neuro", "rm neuro" i "RM Neuro" són la mateixa activitat, i "dilluns", "Dl" i
"lunes" són el mateix dia.
"""
from __future__ import annotations

import datetime as dt
import math
import re
import unicodedata
from typing import Optional

# ---------------------------------------------------------------------------
# Textos
# ---------------------------------------------------------------------------


def fold(s) -> str:
    """Minúscules sense accents ni espais als extrems. None -> ''."""
    if s is None:
        return ''
    s = str(s)
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return s.strip().lower()


def norm_key(s) -> str:
    """Clau de comparació: fold + sense espais, guions, punts ni barres.

    "RM-Neuro" -> "rmneuro", "Hospital Demo Nord" -> "hospitaldemonord".
    """
    return re.sub(r'[\s\-_./·,;:()\[\]\'"]+', '', fold(s))


def clean(s) -> str:
    """Text net per mostrar (manté accents i majúscules)."""
    if s is None:
        return ''
    if isinstance(s, float) and s.is_integer():
        s = int(s)
    return re.sub(r'\s+', ' ', str(s)).strip()


_STOP = {'de', 'del', 'dels', 'la', 'el', 'els', 'les', 'l', 'd', 'i', 'y', 'the'}


def words(s, singles: bool = False) -> set:
    """Paraules significatives (sense accents ni articles) per comparar noms.

    Els números es mantenen sempre ('CAP Badalona 2'). Les lletres soltes només si
    singles=True, i encara llavors una lletra amb punt ('H.', 'U.', 'A.') és una
    abreviatura i no compta; una lletra sense punt ('Edifici A') forma part del nom."""
    out = set()
    for m in re.finditer(r'([a-z0-9]+)(\.?)', fold(s)):
        w, dot = m.group(1), m.group(2)
        if w in _STOP:
            continue
        if len(w) >= 2 or w.isdigit() or (singles and not dot):
            out.add(w)
    return out


def split_list(v) -> list:
    """'Hospital A, Hospital B; C' -> ['Hospital A', 'Hospital B', 'C']."""
    if v is None:
        return []
    out = []
    for part in re.split(r'[,;\n]+', str(v)):
        p = clean(part)
        if p and p not in out:
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# Sí / No i números
# ---------------------------------------------------------------------------

_YES = {'si', 's', 'yes', 'y', 'true', 'cert', '1', 'x', 'ok'}
_NO = {'no', 'n', 'false', 'fals', '0', '-'}


def parse_bool(v, default: bool) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    f = fold(v)
    if f == '':
        return default
    if f in _YES:
        return True
    if f in _NO:
        return False
    return default


def parse_number(v, default: Optional[float] = None) -> Optional[float]:
    """'12,5' -> 12.5 · '1.000' -> 1000 · '1.234,5' -> 1234.5 · '1,234.5' -> 1234.5."""
    if v is None or v == '':
        return default
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace('%', '').replace(' ', '').replace('\u00a0', '')
    if s == '':
        return default
    if ',' in s and '.' in s:
        # El separador que surt l'últim és el decimal
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif re.fullmatch(r'-?\d{1,3}(\.\d{3})+', s):
        s = s.replace('.', '')          # 1.000 = mil (separador de milers)
    else:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return default


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


_ACTIVE_NO = {'no', 'n', 'inactiu', 'inactiva', 'baixa', 'excedencia', 'vacances', 'fals', 'false',
              'jubilat', 'jubilada', 'permis', '0'}
_ACTIVE_YES = {'si', 's', 'yes', 'y', 'actiu', 'activa', 'x', '1', 'ok', 'cert', 'true'}


def parse_active(v) -> Optional[bool]:
    """Columna 'Actiu': buit = sí. 'No', 'No (baixa)', 'Baixa', 'Excedència'... = no.
    Es mira la primera paraula sencera ('Nou' o 'Només matins' no són 'no'). None si no s'entén."""
    if v is None:
        return True
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    raw = str(v).strip()
    if raw == '':
        return True
    if raw in ('-', '–', '—'):
        return False
    toks = [t for t in re.split(r'[^a-z0-9]+', fold(raw)) if t]
    if not toks:
        return None
    if toks[0] in _ACTIVE_NO:
        return False
    if toks[0] in _ACTIVE_YES:
        return True
    return None


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

EXCEL_EPOCH = dt.date(1899, 12, 30)


def parse_date(v) -> Optional[dt.date]:
    """Accepta date, datetime, número de sèrie d'Excel o text dd/mm/aaaa, aaaa-mm-dd."""
    if v is None or v == '':
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 20000 < v < 80000:
            return EXCEL_EPOCH + dt.timedelta(days=int(v))
        return None
    s = str(v).strip()
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})', s)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r'^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})$', s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return dt.date(y, mo, d)
        except ValueError:
            return None
    return None


def parse_date_list(v) -> list:
    """'12/10/2026, 01/11/2026' -> [date, date]. Accepta també una sola data."""
    if v is None or v == '':
        return []
    if isinstance(v, (dt.date, dt.datetime)):
        return [parse_date(v)]
    out = []
    for part in re.split(r'[,;\s]+', str(v)):
        d = parse_date(part)
        if d and d not in out:
            out.append(d)
    return sorted(out)


def monday_of(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def next_monday(today: Optional[dt.date] = None) -> dt.date:
    today = today or dt.date.today()
    return monday_of(today) + dt.timedelta(days=7)


def week_label(monday: dt.date) -> str:
    """'2026-W43 (19/10-25/10)'."""
    y, w, _ = monday.isocalendar()
    sunday = monday + dt.timedelta(days=6)
    return f"{y}-W{w:02d} ({monday:%d/%m}-{sunday:%d/%m})"


def week_code(monday: dt.date) -> str:
    y, w, _ = monday.isocalendar()
    return f"{y}W{w:02d}"


def fmt_date(d: Optional[dt.date]) -> str:
    return d.strftime('%d/%m/%Y') if d else ''


# ---------------------------------------------------------------------------
# Dies de la setmana
# ---------------------------------------------------------------------------

WEEKDAY_SHORT = ['Dl', 'Dt', 'Dc', 'Dj', 'Dv', 'Ds', 'Dg']
WEEKDAY_LONG = ['Dilluns', 'Dimarts', 'Dimecres', 'Dijous', 'Divendres', 'Dissabte', 'Diumenge']

_WEEKDAY_MAP = {}
for i, (s_, l_) in enumerate(zip(WEEKDAY_SHORT, WEEKDAY_LONG)):
    _WEEKDAY_MAP[fold(s_)] = i
    _WEEKDAY_MAP[fold(l_)] = i
for i, names in enumerate([
        ('lunes', 'lun', 'l', 'monday', 'mon'),
        ('martes', 'mar', 'm', 'tuesday', 'tue'),
        ('miercoles', 'mie', 'x', 'wednesday', 'wed'),
        ('jueves', 'jue', 'j', 'thursday', 'thu'),
        ('viernes', 'vie', 'v', 'friday', 'fri'),
        ('sabado', 'sab', 's', 'saturday', 'sat'),
        ('domingo', 'dom', 'd', 'sunday', 'sun')]):
    for n in names:
        _WEEKDAY_MAP.setdefault(n, i)


def parse_weekday(v) -> Optional[int]:
    """0 = dilluns ... 6 = diumenge. None si no s'interpreta."""
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        i = int(v)
        return i - 1 if 1 <= i <= 7 else None
    f = fold(v).rstrip('.')
    return _WEEKDAY_MAP.get(f)


def parse_weekday_list(v) -> Optional[list]:
    """"Dl,Dt,Dc,Dj,Dv" -> [0,1,2,3,4]. Accepta rangs "Dl-Dv". Buit -> []. Il·legible -> None."""
    if v is None or str(v).strip() == '':
        return []
    s = str(v)
    m = re.match(r'^\s*([^\s,;\-]+)\s*-\s*([^\s,;\-]+)\s*$', s)
    if m:
        a, b = parse_weekday(m.group(1)), parse_weekday(m.group(2))
        if a is not None and b is not None and a <= b:
            return list(range(a, b + 1))
    out = []
    for part in re.split(r'[,;/\s]+', s):
        if not part or fold(part) in ('i', 'y', 'e', 'and', 'et'):
            continue
        d = parse_weekday(part)
        if d is None:
            return None
        if d not in out:
            out.append(d)
    return sorted(out)


def weekday_list_text(days) -> str:
    return ', '.join(WEEKDAY_SHORT[d] for d in sorted(days))


# ---------------------------------------------------------------------------
# Franges
# ---------------------------------------------------------------------------

FRANGES = ['Matí', 'Tarda', 'Nit', 'Tot el dia']
FRANJA_ORDER = {'Matí': 0, 'Tarda': 1, 'Nit': 2, 'Tot el dia': 3, '': 4}
_FRANJA_MAP = {
    'mati': 'Matí', 'm': 'Matí', 'manana': 'Matí', 'morning': 'Matí', 'am': 'Matí', 'mat': 'Matí',
    'tarda': 'Tarda', 't': 'Tarda', 'tarde': 'Tarda', 'afternoon': 'Tarda', 'pm': 'Tarda', 'tar': 'Tarda',
    'nit': 'Nit', 'n': 'Nit', 'noche': 'Nit', 'night': 'Nit',
    'toteldia': 'Tot el dia', 'dia': 'Tot el dia', 'tot': 'Tot el dia',
    'todoeldia': 'Tot el dia', 'diasencer': 'Tot el dia', 'diacomplet': 'Tot el dia', 'all': 'Tot el dia',
}


def parse_franja(v) -> str:
    """Retorna una de FRANGES o '' si és buit o no interpretable."""
    if v is None:
        return ''
    k = norm_key(v)
    if k == '':
        return ''
    if k in _FRANJA_MAP:
        return _FRANJA_MAP[k]
    # Formats horaris: "8-15", "15-21", "08:00-15:00" -> punt mig del rang
    m = re.match(r'^(\d{1,2})(?::?\d{2})?[-a](\d{1,2})', fold(v).replace(' ', ''))
    if m:
        a, b = int(m.group(1)) % 24, int(m.group(2)) % 24
        if b <= a:
            b += 24
        mid = ((a + b) / 2) % 24
        if 7 <= mid < 15:
            return 'Matí'
        if 15 <= mid < 21:
            return 'Tarda'
        return 'Nit'
    for key, val in _FRANJA_MAP.items():
        if len(key) > 2 and k.startswith(key):
            return val
    return ''


# ---------------------------------------------------------------------------
# Àmbit del pacient
# ---------------------------------------------------------------------------

AMBITS = ['Ambulatori', 'Ingressat', 'Mixt']
AMB, INGR, MIXT = 'Ambulatori', 'Ingressat', 'Mixt'


def parse_ambit(v) -> Optional[str]:
    """'' si és buit; None si no s'interpreta. Si el text parla d'ingressats i d'ambulatoris
    alhora ('Ambulatori i ingressat', 'CEX + ingressats') és Mixt."""
    k = norm_key(v)
    if k == '':
        return ''
    if k in ('i', 'h', 'ing'):
        return INGR
    if k == 'a':
        return AMB
    if 'mix' in k:
        return MIXT
    text = fold(v)
    negated = (re.search(r'\b(sense|sin|no|without)\b[^a-z]*(pacients?\s+|pacientes?\s+)?(ingr|hosp|inpat)', text)
               or re.search(r'\bcap\s+(pacients?\s+)?(ingr|hosp|inpat)', text))      # 'cap ingressat', no 'CAP/Hosp'

    inp = any(t in k for t in ('ingr', 'hosp', 'inpat', 'planta')) and not negated
    amb = any(t in k for t in ('amb', 'cex', 'consult', 'extern', 'outpat')) or bool(negated)
    if inp and amb:
        return MIXT
    if inp:
        return INGR
    if amb:
        return AMB
    return None


def has_inpatients(scope: str) -> bool:
    return scope in (INGR, MIXT)
