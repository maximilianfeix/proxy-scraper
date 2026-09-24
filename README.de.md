<div align="center">

# ⚡ proxy-scraper

### Freie Proxys, die wirklich funktionieren.
**700+ Quellen · ~1 Mio. Kandidaten in 25 Sekunden · jeder Treffer echt geprüft · mit jedem Lauf klüger**

[English](README.md) · **Deutsch**

[![tests](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/tests.yml/badge.svg)](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/tests.yml)
[![lint](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/lint.yml/badge.svg)](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/lint.yml)
[![codeql](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/codeql.yml/badge.svg)](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/codeql.yml)
[![proxy list](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/proxy-list.yml/badge.svg)](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/proxy-list.yml)
<br>
[![Release](https://img.shields.io/github/v/release/maximilianfeix/proxy-scraper?color=38BDF8)](https://github.com/maximilianfeix/proxy-scraper/releases/latest)
![Python](https://img.shields.io/badge/python-3.9%20–%203.13-3776AB?logo=python&logoColor=white)
![Plattform](https://img.shields.io/badge/macOS%20·%20Linux%20·%20Windows-lightgrey?logo=gnometerminal&logoColor=white)
![Abhängigkeiten](https://img.shields.io/badge/abhängigkeiten-rich%20%2B%20certifi-informational)
[![Lizenz: MIT](https://img.shields.io/badge/lizenz-MIT-green)](LICENSE)

<br>

<img src="docs/demo.svg" alt="Animierte Demo: Einrichtungsassistent, Sammeln, Live-Dashboard und Abschlussbericht" width="880">

<br>

[**Installation**](#schnellstart) · [**Live-Liste**](#live-liste) · [**Proxy-Server**](#proxy-server) · [**Features**](#features) · [**So funktioniert's**](#so-funktionierts) · [**Optionen**](#optionen) · [**FAQ**](#faq)

</div>

---

Die meisten freien Proxy-Listen sind zu 95 % tot. **proxy-scraper** probiert nicht stumpf alles durch, sondern lernt dazu: Proxys, die schon einmal funktioniert haben, kommen zuerst dran, danach die aus Quellen mit guter Trefferquote. Tote und nicht mehr gepflegte Listen fliegen automatisch raus, neue findet das Tool selbst auf GitHub – und jeder Treffer wird nicht nur angepingt, sondern muss eine echte Seite abrufen, HTTPS tunneln und zeigen, wie anonym er ist.

<a id="live-liste"></a>

## 📡 Live-Proxyliste

Keine Lust, selbst zu scannen? Alle 6 Stunden läuft das Tool per **GitHub Actions** und veröffentlicht die Treffer auf dem Branch [`proxy-list`](../../tree/proxy-list) – jeder Eintrag hat beim letzten Lauf wirklich funktioniert, schnellste zuerst.

<div align="center">

[![Proxys](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Ftotal.json&style=for-the-badge)](../../tree/proxy-list)
[![HTTP](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Fhttp.json&style=for-the-badge)](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/http.txt)
[![SOCKS4](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Fsocks4.json&style=for-the-badge)](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks4.txt)
[![SOCKS5](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Fsocks5.json&style=for-the-badge)](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks5.txt)
[![Stand](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Fupdated.json&style=for-the-badge)](../../actions/workflows/proxy-list.yml)

</div>

| Liste | Format | Link |
|---|---|---|
| Alle | `socks5://1.2.3.4:1080` | [all.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/all.txt) |
| HTTP · SOCKS4 · SOCKS5 | `1.2.3.4:8080` | [http.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/http.txt) · [socks4.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks4.txt) · [socks5.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks5.txt) |
| Nur HTTPS-fähige | `typ://ip:port` | [https.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/https.txt) |
| Nur Elite | `typ://ip:port` | [elite.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/elite.txt) |
| Mit allen Details | Latenz, Land, HTTPS, Anonymität, Exit-IP | [proxies.json](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/proxies.json) · [proxies.csv](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/proxies.csv) |

```bash
curl -s https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks5.txt | head
```

<a id="features"></a>

## ✨ Features

<table>
<tr>
<td width="50%" valign="top">

**🧭 Einrichtungsassistent**<br>
Ohne Argumente gestartet fragt das Tool per Pfeiltasten, was du suchst – Schnellauswahl oder Schritt für Schritt. Am Ende steht die passende Kommandozeile da.

</td>
<td width="50%" valign="top">

**⚡ Schnell**<br>
Über 700 Quellen parallel geladen, große Listen auf allen CPU-Kernen geparst, eigene HTTP/SOCKS-Handshakes direkt auf `asyncio` mit 2000+ Prüfungen gleichzeitig.

</td>
</tr>
<tr>
<td valign="top">

**🔐 Echte Detailprüfung**<br>
Jeder Treffer muss zwei unabhängige Seiten abrufen – das sortiert **Honeypots** aus, die nur auf Prüfanfragen antworten (in manchen Läufen 5 von 6 „Treffern“). Dazu: HTTPS über einen Tunnel mit **verifiziertem TLS**, Anonymitätsstufe *elite / anonymous / transparent* und das Land der Exit-IP.

</td>
<td valign="top">

**🧠 Lernt mit jedem Lauf**<br>
Trefferquote pro Quelle, Verlauf funktionierender Proxys, automatisches Aussortieren toter und veralteter Listen. Mit `-l 5000` bekommst du die *besten* 5000 Kandidaten, nicht irgendwelche.

</td>
</tr>
<tr>
<td valign="top">

**🔎 Findet neue Quellen selbst**<br>
Durchsucht GitHub nach aktiv gepflegten Proxy-Listen und liest fremd gepflegte Quellenlisten ein. Spam-Klonfarmen und reine Spiegel werden erkannt.

</td>
<td valign="top">

**🎯 Filter & Zielseiten**<br>
Mit `--target google.com` zählt ein Proxy nur, wenn er die Seite wirklich erreicht – viele öffentliche Proxys sind bei Google, Discord & Co. gesperrt. Dazu nach Land, HTTPS, Anonymität und Latenz filtern – und mit `--want 50` aufhören, sobald genug passende Proxys gefunden sind. Filter machen die Suche sogar schneller: Mit `--max-latency 1000` gibt das Tool langsame Proxys nach 1 s auf statt nach 8 s.

</td>
</tr>
<tr>
<td valign="top">

**📊 Live-Dashboard**<br>
Tempo-Verlauf, Latenz-Histogramm, Protokolle, Länder und die letzten Treffer in Echtzeit. <kbd>Strg</kbd>+<kbd>C</kbd> beendet jederzeit und speichert alles.

</td>
<td valign="top">

**🔁 Rotierender Proxy-Server**<br>
`--serve` macht aus den Treffern einen lokalen Proxy, der jede Verbindung über einen anderen schickt – mit automatischem Wechsel, wenn einer hängt.

</td>
</tr>
<tr>
<td valign="top">

**💻 Läuft überall**<br>
macOS, Linux und Windows, Python 3.9 bis 3.13. Einzige Abhängigkeiten: `rich` und `certifi`. Erkennt sogar, wenn eine Firewall Proxys blockiert.

</td>
<td valign="top">

**🧪 Gründlich getestet**<br>
240+ Tests laufen ohne Internet gegen echte Mini-Proxys und Honeypots auf `localhost` – auf Linux, macOS und Windows mit Python 3.9, 3.11 und 3.13.

</td>
</tr>
</table>

<a id="schnellstart"></a>

## 🚀 Installation

**Mit [pipx](https://pipx.pypa.io/)** (empfohlen – ergibt den Befehl `proxy-scraper` in einer eigenen Umgebung):

```bash
pipx install git+https://github.com/maximilianfeix/proxy-scraper.git
proxy-scraper
```

<details>
<summary><b>Andere Wege: pip, schnellere Event-Loop oder direkt aus dem Repo</b></summary>
<br>

```bash
# mit pip in die aktuelle Umgebung
pip install git+https://github.com/maximilianfeix/proxy-scraper.git

# optional: schnellere Event-Loop unter macOS/Linux
pipx install "proxy-scraper[fast] @ git+https://github.com/maximilianfeix/proxy-scraper.git"

# ganz ohne Installation
git clone https://github.com/maximilianfeix/proxy-scraper.git
cd proxy-scraper
pip install -r requirements.txt
python3 proxy_scraper.py
```

Zu jedem [Release](https://github.com/maximilianfeix/proxy-scraper/releases/latest) gibt es außerdem ein Wheel für `pip install <datei>.whl`.

Installiert liegt der gelernte Zustand im Benutzerordner (`~/Library/Application Support/proxy-scraper`, `%LOCALAPPDATA%\proxy-scraper` bzw. `~/.local/share/proxy-scraper`; änderbar mit `PROXY_SCRAPER_HOME`), Ergebnisse landen in `./results`. Aus einem Klon gestartet bleibt beides im Projekt.

</details>

Ohne Argumente gestartet fragt ein Assistent, was du brauchst:

<div align="center">
<img src="docs/wizard.svg" alt="Einrichtungsassistent" width="760">
</div>

| Schnellauswahl | Was passiert |
|---|---|
| **Alles finden** | alle Protokolle, maximale Ausbeute |
| **Surfen & Web** | HTTP + SOCKS5, HTTPS-fähig, mindestens anonym, unter 3 s |
| **Maximal anonym** | nur Elite-SOCKS5 mit HTTPS |
| **Schnell & stabil** | nur Proxys unter 1 s |
| **Sofort ein paar** | stoppt nach 25 Treffern |
| **Letzte Treffer neu prüfen** | ohne Sammeln, dauert Sekunden |
| **Wie letztes Mal** | deine letzte Auswahl |
| **Eigene Auswahl …** | Protokolle, Länder, Anonymität, HTTPS, Zielseite, Latenz, Menge, Prüfmodus |

Bedienung: <kbd>↑</kbd><kbd>↓</kbd> auswählen · <kbd>Leertaste</kbd> an/aus · <kbd>1</kbd>–<kbd>9</kbd> direkt · <kbd>Enter</kbd> weiter · <kbd>Esc</kbd> zurück · <kbd>q</kbd> beenden. In Skripten und Cronjobs kommt der Assistent nie – dort einfach Optionen angeben oder `-y`.

## 💡 Beispiele

```bash
# 50 Proxys, die HTTPS können – danach Schluss
proxy-scraper --want 50 --https-only

# nur Deutschland, Österreich und die Schweiz, die 20.000 vielversprechendsten Kandidaten
proxy-scraper --country DE,AT,CH -l 20000

# schnelle Elite-SOCKS5-Proxys
proxy-scraper --types socks5 --anonymity elite --max-latency 1500

# 20 Proxys, die Google UND Discord wirklich erreichen
proxy-scraper --target google.com --target discord.com --want 20

# nur die Treffer vom letzten Mal (plus Verlauf) neu prüfen – dauert Sekunden
proxy-scraper --recheck

# Assistent mit Startwerten – er übernimmt, was du schon angegeben hast
proxy-scraper -i --country DE

# welche Quellen liefern am meisten?
proxy-scraper --list-sources
```

Aus einem Klon gestartet? Statt `proxy-scraper` einfach `python3 proxy_scraper.py`.

<a id="proxy-server"></a>

## 🔁 Rotierender Proxy-Server

Eine Liste ist nett – aber meistens will man einfach **einen** Proxy eintragen, der immer funktioniert:

```bash
proxy-scraper --recheck --serve     # letzte Treffer prüfen, dann los – dauert Sekunden
```

```bash
curl -x http://127.0.0.1:8899 https://api.ipify.org     # jedes Mal eine andere IP
```

- jede Verbindung läuft über einen anderen gefundenen Proxy, schnelle und bewährte werden bevorzugt
- `CONNECT` für HTTPS und normale HTTP-Anfragen; dahinter können HTTP-, SOCKS4- und SOCKS5-Proxys stecken (SOCKS5 mit DNS über den Proxy)
- für HTTPS nur Proxys, die den Test mit **verifiziertem TLS** bestanden haben – keine aufgebrochene Verschlüsselung
- bleibt ein Proxy im Tunnel stumm oder liefert statt TLS eine Fehlerseite, geht dasselbe erste Paket unbemerkt an den nächsten
- wer dreimal hintereinander scheitert, fliegt aus der Rotation
- lauscht nur auf `127.0.0.1`; Live-Ansicht mit Anfragen, Erfolgsquote, Pool und den letzten Verbindungen

Im Test: 20 von 20 HTTPS-Anfragen erfolgreich, über 15 verschiedene Exit-IPs. Im Assistenten gibt es dafür **Sofort als Proxy-Server**.

<a id="so-funktionierts"></a>

## 🔬 So funktioniert's

```mermaid
flowchart LR
    A[sources.json<br/>Meta-Listen<br/>GitHub-Discovery] --> B[Laden & Parsen<br/>parallel auf allen Kernen]
    B --> C[Priorisieren<br/>Verlauf → gute Quellen → Rest]
    C --> D[Prüfen<br/>HTTP · SOCKS4 · SOCKS5]
    D --> E[Details<br/>HTTPS · Anonymität · Land]
    E --> F[results/]
    D -. Trefferquote pro Quelle .-> G[(data/)]
    G -. nächster Lauf .-> C
```

1. **Quellen** – die kuratierte Liste in [`sources.json`](proxyscraper/sources.json), Meta-Quellen (andere Projekte, die selbst Listen von Proxy-Quellen pflegen) und alle drei Tage eine Suche auf GitHub nach aktiv gepflegten Repos.
2. **Sammeln** – Text, HTML-Tabellen, JSON-APIs und `typ://ip:port`-Zeilen werden erkannt, private und reservierte Adressbereiche verworfen.
3. **Priorisieren** – bekannte funktionierende Proxys zuerst, dann nach gelernter Trefferquote ihrer Quellen.
4. **Prüfen** – jeder Proxy muss `checkip.amazonaws.com` abrufen und eine gültige, *fremde* IP zurückliefern. Wer deine IP durchreicht, fliegt raus. Danach die **Bestätigung** über `httpbin.org`: Fake-Proxys, die nur auf die erste Prüfanfrage mit „200 + IP“ antworten, scheitern hier.
5. **Lernen** – Trefferquoten und Verlauf landen in `data/`. Quellen ohne Treffer, mit seit einer Woche unverändertem Inhalt oder dauerhaft unerreichbar werden übersprungen.

<details>
<summary><b>📸 Live-Dashboard und Abschlussbericht ansehen</b></summary>
<br>
<div align="center">
<img src="docs/dashboard.svg" alt="Live-Dashboard während der Prüfung" width="860">
<br><br>
<img src="docs/summary.svg" alt="Abschlussbericht nach einem Lauf" width="860">
</div>
</details>

## 📦 Ausgabe

Jeder Lauf bekommt einen eigenen Ordner, `results/latest.txt` nennt immer den neuesten (unter macOS/Linux zusätzlich der Symlink `results/latest`):

```
results/2026-09-24_18-42-07/
├── all.txt        socks5://203.0.113.10:1080   (schnellste zuerst)
├── http.txt       203.0.113.20:8080            (reine ip:port-Listen pro Typ)
├── socks4.txt
├── socks5.txt
├── proxies.json   Latenz, Land, HTTPS, Anonymität, Exit-IP
└── proxies.csv
```

<a id="optionen"></a>

## ⚙️ Optionen

<details>
<summary><b>Alle Optionen anzeigen</b></summary>
<br>

| Option | Beschreibung |
|---|---|
| `-i`, `--interactive` | Einrichtungsassistent (kommt ohne Argumente automatisch) |
| `-y`, `--yes` | ohne Assistent sofort starten |
| `--types http socks5` | nur bestimmte Protokolle |
| `-l`, `--limit N` | nur die *N* vielversprechendsten Proxys prüfen |
| `--want N` | beenden, sobald *N* passende Proxys gefunden sind |
| `--country DE,AT` | nur diese Länder |
| `--https-only` | nur Proxys, die HTTPS tunneln können |
| `--anonymity elite` | Mindest-Anonymität (`anonymous` oder `elite`) |
| `--max-latency MS` | maximale Latenz |
| `--target URL` | nur Proxys, die diese Seite erreichen (mehrfach möglich) |
| `--recheck [DATEI]` | nur Proxys aus einer Datei bzw. vom letzten Lauf prüfen |
| `--fast` | ohne HTTPS-Test (Bestätigung und Anonymität laufen trotzdem) |
| `--no-geo` | ohne Länder-Lookup |
| `-c`, `--concurrency N` | gleichzeitige Prüfungen (Standard: 2000) |
| `-t`, `--timeout S` | Timeout pro Proxy (Standard: 8 s) |
| `--discover` | sofort neue Quellen auf GitHub suchen |
| `--list-sources [N]` | Rangliste der Quellen anzeigen |
| `--serve [PORT]` | danach als rotierender Proxy auf `127.0.0.1:PORT` bereitstellen (Standard: 8899) |
| `-o DATEI` | zusätzlich alle Treffer in diese Datei schreiben |
| `-V`, `--version` | Version anzeigen |

Alles Weitere: `proxy-scraper --help`

</details>

> [!TIP]
> Für die GitHub-Suche reicht ein eingeloggtes [`gh`](https://cli.github.com/) oder die Umgebungsvariable `GITHUB_TOKEN`. Ohne Token gilt das API-Limit von 60 Anfragen pro Stunde, dann werden nur 40 Repos durchsucht.

## 🤖 GitHub Actions

Das Repo arbeitet selbst mit:

| Workflow | Was er macht |
|---|---|
| [**tests**](../../actions/workflows/tests.yml) | 3 Betriebssysteme × 3 Python-Versionen, dazu ein gebautes und installiertes Paket – bei jedem Push und Pull Request |
| [**lint**](../../actions/workflows/lint.yml) | `ruff` mit fest gepinnter Version – lokal und in der CI dieselben Regeln |
| [**codeql**](../../actions/workflows/codeql.yml) | Sicherheitsanalyse bei jedem Push und einmal pro Woche |
| [**proxy list**](../../actions/workflows/proxy-list.yml) | alle 6 Stunden: sammeln, prüfen, auf `proxy-list` veröffentlichen. Die gelernte Statistik liegt im Actions-Cache – das Tool wird also auch in der Cloud mit jedem Lauf besser |
| [**release**](../../actions/workflows/release.yml) | bei einem Versions-Tag: testen, bauen, Probestart und GitHub-Release mit Wheel |
| **Dependabot** | hält die Versionen der Actions aktuell |

<a id="faq"></a>

## ❓ FAQ

<details>
<summary><b>Es kommt (fast) nichts durch.</b></summary>
<br>

Viele Firmen-, Schul- und Uni-Netze blockieren Proxy-Verbindungen. Das Tool erkennt das an einer Trefferquote unter 0,2 % und warnt dann – in dem Fall hilft ein anderes Netz, z. B. ein Handy-Hotspot. Die gelernten Statistiken werden bei so einem Lauf nicht abgewertet.

</details>

<details>
<summary><b>Läuft es unter Windows?</b></summary>
<br>

Ja, in PowerShell und Windows Terminal. `uvloop` gibt es dort nicht und wird automatisch übersprungen. Im alten `cmd.exe`-Fenster fehlen je nach Schriftart einzelne Symbole.

</details>

<details>
<summary><b>Warum findet es weniger Proxys, als andere Listen versprechen?</b></summary>
<br>

Weil nur Proxys bleiben, die jede Prüfung bestehen. Viele Listen zählen alles, was eine TCP-Verbindung annimmt; hier muss ein Proxy zwei unabhängige Seiten abrufen und eine fremde IP zeigen. Das sind meist ein paar Hundert von einer Million Kandidaten – aber die funktionieren.

</details>

<details>
<summary><b>Wie aktuell ist die Live-Liste?</b></summary>
<br>

Sie wird alle 6 Stunden neu gebaut, das Badge „Stand“ zeigt den letzten Lauf. Freie Proxys kommen und gehen schnell – für Wichtiges direkt vorher `proxy-scraper --recheck` laufen lassen.

</details>

## 🗺️ Roadmap

Was als Nächstes kommt, steht in den Meilensteinen [**v1.3**](../../milestone/3) und [**v1.1**](../../milestone/1) – Ideen und Wünsche gerne als [Issue](../../issues/new/choose).

- [ ] [Proxys mit Zugangsdaten](../../issues/7) · [Zweites Prüfziel](../../issues/8) · [ETag-Cache](../../issues/9)
- [ ] [Export für proxychains, Clash & Co.](../../issues/4) · [Docker-Image](../../issues/5) · [IPv6-Proxys](../../issues/1)

## 🤝 Mitmachen

Fehlerberichte, neue Quellen und Pull Requests sind sehr willkommen – Details in [CONTRIBUTING.md](CONTRIBUTING.md). Kurzfassung:

```bash
pip install -e ".[dev]"
python3 -m pytest          # läuft ohne Internet – Fake-Proxys auf localhost
ruff check .
python3 docs/make_demo.py  # Bilder für diese README neu erzeugen
```

<details>
<summary><b>Projektstruktur</b></summary>

```
proxy_scraper.py        Einstiegspunkt beim Start aus dem Klon
proxyscraper/
├── cli.py              Argumente, Assistent oder direkter Start
├── app.py              ein Lauf in Phasen: Netz → Jobs → Prüfen → Lernen & Bericht
├── options.py          RunOptions + Filters – alle Einstellungen an einer Stelle
├── pipeline.py         Quellen sammeln, priorisieren, Prüfschleife
├── checker.py          HTTP/SOCKS-Handshakes, Bestätigung gegen Honeypots, HTTPS-Test
├── sources.py          Quellenlisten, Meta-Quellen, GitHub-Discovery, Statistik
├── sources.json        kuratierte Quellen
├── parsing.py          Proxys in Text, HTML und JSON finden
├── history.py          Verlauf funktionierender Proxys
├── geo.py              Länder über ip-api.com (Batch, mit Cache)
├── targets.py          Zielseiten für --target
├── output.py           Ergebnisdateien
├── server.py           rotierender Proxy-Server (--serve)
├── publish.py          Live-Liste für GitHub Actions aufbereiten
├── paths.py            wo Zustand und Ergebnisse liegen
├── compat.py           Unterschiede zwischen Unix und Windows
├── netio.py            schlanker HTTP-Client auf asyncio
└── ui/                 widgets · dashboard · report · wizard · serve · keys
```

</details>

## ⚠️ Hinweis

Öffentliche Proxys werden von Unbekannten betrieben, die alles mitlesen können, was unverschlüsselt durchgeht. Keine Passwörter oder persönlichen Daten darüber schicken und nur für legale Zwecke nutzen.

<div align="center">

---

[MIT-Lizenz](LICENSE) · [Changelog](CHANGELOG.md) · [Sicherheit](SECURITY.md)

Wenn dir das Tool hilft, freut sich das Repo über einen ⭐

</div>
