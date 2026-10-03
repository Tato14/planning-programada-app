"""Wrapper a l'arrel perquè Streamlit Cloud trobi l'app sense configuració.

Igual que al planning de guàrdies: Streamlit Cloud pot conservar a sys.modules la
versió ANTIGA dels mòduls propis després d'un desplegament. Es purguen abans
d'executar l'app perquè sempre es carreguin del disc.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

for _m in [m for m in list(sys.modules) if m == 'programada' or m.startswith('programada.')]:
    sys.modules.pop(_m, None)

exec(open(ROOT / 'app' / 'app.py', encoding='utf-8').read())
