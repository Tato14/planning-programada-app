# Assignació d'activitat programada TD (nucli)

Donada la demanda d'una setmana i el perfil i les preferències dels radiòlegs, l'eina decideix **qui informa què**: reparteix les exploracions de cada agenda respectant competències, accés als centres, absències, activitat fixa pactada i obligació contractual, i distribueix l'extra en proporció a la capacitat que cadascú declara.

És l'equivalent per a l'activitat programada del planning de guàrdies (`planning-guardies-app`): mateixa filosofia (un fitxer d'entrada, una app Streamlit, cap dada real al repositori), però amb un optimitzador (OR-Tools CP-SAT) en lloc d'una roda, perquè aquí cal combinar competències, centres, capacitats i pactes alhora.

## Abast d'aquesta versió

Entra:

- Demanda per blocs (una fila per agenda o volum setmanal), amb àmbit (ingressats) i radiòleg fix opcional.
- Perfil de cada radiòleg: Mínim (obligació) i Màxim (capacitat) setmanals, activitats que fa (S) i que prefereix (P), centres on pot informar, dies sense activitat.
- Absències de la setmana i festius.
- Assignació, motius de cada assignació, motius de cada pendent i validació independent.
- Excel de sortida amb taules amb nom.

Queda per a més endavant (és a la versió completa arxivada, vegeu el final): plantilla de previsió dels centres i mapatge equip/agenda a activitat, correus i propostes amb acceptació, replanificació de la mateixa setmana, saldo d'equitat entre setmanes, previsió de capacitat a diverses setmanes i temps de resposta a partir de BO.

## Com es fa servir

**App**

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

A la barra lateral: pujar el fitxer d'entrada (o "Carregar la demo"), "Assignar" i descarregar l'Excel. Els paràmetres es poden canviar per a un càlcul concret sense tocar el fitxer.

**Línia d'ordres**

```bash
python -m programada assignar Entrada_Setmana_2026W43.xlsx -o Assignacio_2026W43.xlsx
python -m programada plantilla -o Plantilla_Entrada_Setmanal.xlsx
python -m programada demo -o demo
```

## Fitxer d'entrada

Una sola plantilla (`plantilles/Plantilla_Entrada_Setmanal.xlsx`) amb desplegables. Cada setmana es copia el fitxer de la setmana anterior i es canvien la data, la demanda i les absències.

| Pestanya | Contingut |
|---|---|
| Configuració | Setmana (dilluns), festius, dies laborables i paràmetres (ocupació objectiu, lot mínim, màxim de radiòlegs per bloc, cost de dividir, temps de càlcul) |
| Radiòlegs | Radiòleg, correu, actiu aquesta setmana, Mínim setmanal, Màxim setmanal, centres on pot informar (buit = tots), dies sense activitat i una columna per activitat amb S o P |
| Demanda | Centre, data (buida = volum de la setmana), franja, agenda/equip, activitat, exploracions, àmbit (Ambulatori, Ingressat, Mixt), radiòleg fix, observacions |
| Absències | Una fila per radiòleg amb absències: V, B, C, A, G (dia complet), M (mig dia), X (informatiu) |

Les activitats són les capçaleres de les columnes de competències ("RM Neuro", "TC Body"...): per afegir-ne una, s'afegeix una columna. La lectura és tolerant (capçaleres amb àlies, accents, noms en un altre ordre, "Dimecres" en lloc d'una data, "15-21" com a franja) i tot el que no entén queda a la llista d'avisos amb pestanya i fila.

## Com decideix

Per ordre de prioritat (cada nivell domina els següents):

1. Cobrir la demanda; els blocs amb ingressats compten el triple.
2. Respectar el radiòleg fix pactat.
3. Omplir l'obligació contractual de cadascú; si no hi ha prou demanda de les seves competències, el dèficit es reparteix en proporció al mínim.
4. Repartir l'extra en proporció a la capacitat extra declarada, fins a l'ocupació objectiu (80%); per sobre, el cost es dispara.
5. No dividir agendes sense necessitat.
6. Que l'agenda vagi a qui treballa aquell dia i a qui prefereix l'activitat.

Regles dures: competència, accés al centre, capacitat de la setmana (Màxim × disponibilitat) i, si hi ha ingressats, que el radiòleg treballi aquell dia. El detall és a [`docs/Regles_assignacio.md`](docs/Regles_assignacio.md).

## Sortida

Excel amb les pestanyes Resum, Assignacions, Radiòlegs, Pendents, Avisos i Paràmetres. Cada vista és una Taula d'Excel amb nom (`tAssignacions`, `tRadiolegs`, `tPendents`...), filtrable a Excel i llegible des de Power Automate amb "List rows present in a table" quan toqui automatitzar-ne l'enviament.

## Codi

| Mòdul | Què fa |
|---|---|
| `io_input` | Lectura i validació del fitxer d'entrada |
| `availability` | Capacitat i obligació de cada radiòleg per a la setmana |
| `solver` | Model CP-SAT (determinista: la mateixa entrada dona sempre el mateix pla) |
| `explain` | Tipus de cada assignació (fixa, obligació, extra), avisos i motius dels pendents |
| `validator` | Torna a comprovar totes les regles dures sense fer servir el solver |
| `writer` | Excel de sortida |
| `templates`, `demo` | Plantilla buida i joc de dades fictici |
| `app/app.py` | Interfície Streamlit |

Tests: `python -m pytest -q` (59 tests: propietats del motor, lectura de variants, regressions d'una revisió independent, flux complet, CLI i app).

## Privacitat

El codi no conté cap nom ni correu. **Regla dura: cap fitxer amb noms o correus reals no entra mai al repositori.** El `.gitignore` bloqueja tots els Excel excepte la plantilla buida i la demo fictícia (`demo/DEMO_*`).

## Versió completa arxivada

La versió anterior, amb tot el flux (plantilla dels centres, mapatge, correus, propostes, replanificació, saldo, capacitat i temps de resposta), és a la carpeta `Planning programada - paquet` i al seu zip. El motor d'aquesta versió en deriva directament, de manera que els mòduls es poden reincorporar un a un.
