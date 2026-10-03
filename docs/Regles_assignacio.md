# Regles d'assignació

Document per a Gestió TD i Direcció Clínica: com decideix l'eina, amb quins números i on són els límits d'aquesta versió.

## 1. Capacitat de la setmana

Cada radiòleg declara un **Mínim** (obligació contractual) i un **Màxim** (el que pot fer) per a una setmana completa, en exploracions. La setmana real els ajusta:

- **Dies habituals**: dies laborables (Dl-Dv) menys els seus dies sense activitat.
- **Dies treballats**: dies habituals menys festius i absències de dia complet (V, B, C, A, G). M compta mig dia.
- **Disponibilitat** = (dies treballats - ½ × mitges jornades) / dies habituals.
- **Capacitat** = Màxim × disponibilitat. **Obligació** = Mínim × disponibilitat.

Exemples:

| Cas | Mínim / Màxim | Setmana | Disponibilitat | Obligació / Capacitat |
|---|---|---|---|---|
| Dedicació del 80% | 48 / 60 | congrés dilluns i dimarts | 60% | 28,8 / 36 |
| Contracte del 50% que no treballa dj i dv | 30 / 40 | sense absències | 100% | 30 / 40 |
| El mateix, de vacances dilluns | 30 / 40 | 2 de 3 dies habituals | 67% | 20 / 26,7 |
| Festiu el divendres | 0 / 50 | treballa Dl-Dv | 80% | 0 / 40 |

Els dies sense activitat no redueixen el Màxim, perquè el Màxim d'un contracte parcial ja ho té en compte. Serveixen per saber quins dies hi és (ingressats) i per comptar bé les absències. Si no vol extra, Màxim = Mínim. Si només cobreix guàrdies, Màxim = 0.

## 2. Qui pot fer cada bloc (regles dures)

Un radiòleg és elegible per a un bloc si compleix totes aquestes condicions:

1. Està actiu i té capacitat aquesta setmana.
2. Té la competència (S o P) per a l'activitat del bloc.
3. Té accés al centre: si la columna "Centres on pot informar" és plena, el centre ha de ser-hi (n'hi ha prou amb el nom curt: "Bellvitge" val per a "Hospital Universitari de Bellvitge").
4. Si el bloc té ingressats (Ingressat o Mixt) i data, treballa aquell dia: termini de 24 h.

El **radiòleg fix** d'un bloc és elegible encara que no tingui la competència o el centre registrats (l'Excel ho marca perquè es corregeixi el perfil), però només fins a la seva part del bloc. Si no té capacitat aquesta setmana, el bloc va a un altre i queda marcat com a substitució, amb el motiu. Si treballa la setmana però no el dia del bloc (absència o dia sense activitat), el pacte no s'aplica aquell dia: el bloc va preferentment a qui hi és (substitució marcada) i, si ningú més el pot fer, se li manté i l'informa quan torna. En caps de setmana i festius, en què el servei no treballa, el pacte es manté.

## 3. Ordre de prioritat

L'optimitzador minimitza un cost amb pesos escalonats, de manera que cada nivell domina els següents:

| Nivell | Què | Com |
|---|---|---|
| 1 | Cobrir la demanda | Cada exploració sense assignar és el cost més alt; les de blocs amb ingressats (amb data o sense) compten el triple |
| 2 | Radiòleg fix | Donar el bloc a un altre té un cost més alt que qualsevol diferència d'equitat |
| 3 | Obligació | Omplir el Mínim de cadascú té recompensa; si no n'hi ha per a tothom, el dèficit es reparteix en proporció al Mínim |
| 4 | Extra proporcional | Cada exploració extra costa més com més a prop és el radiòleg del seu màxim; a partir de l'ocupació objectiu (80% de la capacitat extra) el cost es multiplica |
| 5 | No dividir | Cada radiòleg addicional en una agenda costa l'equivalent a 20 exploracions; cap part per sota del lot mínim (5) i com a màxim 4 radiòlegs per bloc |
| 6 | Dia i preferència | Que l'agenda vagi a qui treballa aquell dia i a qui té l'activitat com a preferida (P). Decideixen la barreja, no la quantitat |
| 7 | Desempat | Determinista: la mateixa entrada dona sempre el mateix pla |

L'equitat es mesura sobre la capacitat **declarada**: si un radiòleg declara 40 d'extra i un altre 20, el primer en rep el doble. Per això és important que el Màxim reflecteixi el que cadascú vol fer de debò.

## 4. Paràmetres

| Paràmetre | Per defecte | Efecte |
|---|---|---|
| Ocupació objectiu de l'extra | 80% (30-100%) | Fins on s'omple la capacitat extra abans de començar a penalitzar fort |
| Mida mínima de lot | 5 (1-50) | Si es divideix una agenda, cap part per sota d'aquesta mida |
| Màxim de radiòlegs per bloc | 4 (1-20) | Límit de divisions d'una agenda |
| Cost de dividir un bloc | 20 (0-100) | En exploracions equivalents, per cada radiòleg addicional. Més alt = menys divisions, a costa d'una mica d'equitat. Fins a 100, dividir mai no pesa més que deixar una exploració sense cobrir |
| Temps màxim de càlcul | 20 s (1-300) | Temps de càlcul determinista; si no arriba a l'òptim, retorna la millor solució vàlida i ho indica |

Un valor fora de rang a la pestanya Configuració s'ajusta al límit i surt un avís.

## 5. Com llegir el resultat

**Tipus** de cada assignació: Fixa, Obligació (dins del Mínim), Extra (per sobre del Mínim) o Obligació + extra. Les columnes "Dins obligació" i "Extra" en donen el detall.

**Avisos** de cada assignació: ingressats (termini 24 h), agenda d'un dia en què el radiòleg no hi és (l'informarà més tard), radiòleg fix sense la competència o el centre registrats, bloc dividit, activitat preferida i substitució del fix.

**Pendents**: cada bloc no cobert porta el motiu (activitat que no és al catàleg, cap competent, competents sense accés al centre o absents aquell dia, capacitat esgotada dels elegibles, o lot mínim que no deixa repartir) i, si n'hi ha, candidats per a una gestió manual.

**Validació independent**: torna a comprovar totes les regles dures sense fer servir el solver. Si dona errors, el pla no s'ha de fer servir.

## 6. Límits d'aquesta versió

- **Sense memòria entre setmanes.** L'equitat és dins la setmana: qui aquesta setmana rep poc extra no en rep més la següent. El saldo acumulat és a la versió completa arxivada.
- **Pes 1 per a totes les activitats.** La capacitat es compta en exploracions. Si una activitat pesa més (p. ex. RM cardio), es pot afegir el pes més endavant; el motor ja ho suporta.
- **Agendes ambulatòries en un dia d'absència.** Es poden assignar (termini de 14 dies): el radiòleg les informa quan torna. Si és l'últim dia que treballa la setmana, l'avís diu que les informarà la setmana següent i, per tant, li consumeixen capacitat d'aquella setmana.
- **Obligació no coberta.** Si la demanda de les seves competències no arriba al Mínim, el radiòleg en queda per sota; es veu a la pestanya Radiòlegs.
- **Guàrdies.** G (guàrdia en una altra institució) bloqueja el dia. Una guàrdia de nit pròpia no redueix la capacitat de l'endemà (pregunta oberta C4).
- **Accés al HIS.** Si la columna de centres és buida, s'assumeix accés a tots. Cal una font fiable per omplir-la (pregunta C6).

## 7. Decisions pendents que canvien el resultat

- **C2**: Mínim setmanal per dedicació (100%, 80%, 50%, 20%) per a programada, separat de les guàrdies. És la xifra que més pesa en el repartiment.
- **C6**: d'on surt l'accés al HIS de cada radiòleg i qui el manté.
- **D1**: ocupació objectiu (80% proposat a la reunió).
- **D5**: si en algun centre no es poden dividir agendes (quan el tècnic posa el nom en fer l'exploració), cal un cost de dividir més alt per a aquell centre.
