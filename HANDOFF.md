# Desplegament

Mateix procediment que `planning-guardies-app` (vegeu el seu `HANDOFF_VSCODE.md`), amb dues diferències: repositori nou i una dependència més (OR-Tools).

## 1. Repositori nou

Des de la carpeta del nucli:

```bash
git init -b main
git add .
git ls-files | grep -v -E '^(plantilles/|demo/DEMO_)' | grep -i -E '\.(xlsx|csv|eml|zip)$'   # ha de sortir buit
git commit -m "Nucli d'assignació de l'activitat programada"
git remote add origin https://github.com/Tato14/planning-programada-app.git
git push -u origin main
```

(O amb VSCode: Source Control › Initialize Repository › Publish Branch.)

**Recomanat: guardar la versió completa com a branca d'arxiu**, en lloc de deixar-la només en un zip. Així es pot recuperar mòdul a mòdul amb historial:

```bash
git switch --orphan arxiu/versio-completa
# descomprimeix aquí "Planning programada - paquet.zip" (la versió completa)
git add .
git commit -m "Versió completa (arxiu): previsió, mapatge, correus, propostes, saldo, capacitat, temps de resposta"
git push -u origin arxiu/versio-completa
git switch main
```

## 2. Streamlit Community Cloud

1. https://share.streamlit.io › New app › repo `planning-programada-app`, branca `main`, fitxer `streamlit_app.py`.
2. Advanced settings › Python **3.11**.
3. Secrets:

   ```toml
   APP_PASSWORD = "una-contrasenya-llarga"
   ```

4. Settings › Sharing: restringir per correu als usuaris de Gestió TD.

OR-Tools s'instal·la des de `requirements.txt` (roda precompilada, uns 30 MB). El càlcul és determinista i en aquesta infraestructura pot trigar uns segons més que en local.

L'app tracta noms i correus de professionals (no dades de pacients). Per al prototip, Streamlit Cloud amb contrasenya és acceptable; per a producció, millor un servidor de l'IDI (Docker, a sota). La contrasenya compartida no és autenticació.

## 3. Validar el desplegament

Obre l'URL › "Carregar la demo" › Assignar. Ha de sortir: setmana 2026-W43, 447 exploracions demanades, 433 assignades, 14 pendents (12 de RM Mama, que no és al catàleg, i 2 de RM Cardio per capacitat esgotada de l'única radiòloga competent), càlcul òptim i validació independent superada.

## Docker / servidor propi (recomanat per a producció)

```bash
docker build -t programada .
docker run -p 8501:8501 -e APP_PASSWORD=... programada
```

`APP_PASSWORD` com a variable d'entorn activa la mateixa contrasenya que a Streamlit Cloud. En un servidor de l'IDI, millor encara posar l'app darrere de l'autenticació corporativa.
