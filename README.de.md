<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/banner-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/banner-light.svg">
  <img src="docs/banner-dark.svg" alt="proxy-scraper – freie Proxys, die wirklich funktionieren" width="100%">
</picture>

[![tests](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/tests.yml/badge.svg)](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/tests.yml)
[![codeql](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/codeql.yml/badge.svg)](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/codeql.yml)
[![Release](https://img.shields.io/github/v/release/maximilianfeix/proxy-scraper?color=38BDF8)](https://github.com/maximilianfeix/proxy-scraper/releases/latest)
![Python](https://img.shields.io/badge/python-3.9%20–%203.13-3776AB?logo=python&logoColor=white)
![Plattform](https://img.shields.io/badge/macOS%20·%20Linux%20·%20Windows-lightgrey)
[![Lizenz: MIT](https://img.shields.io/badge/lizenz-MIT-green)](LICENSE)
[![Live-Proxys](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Ftotal.json)](#live-liste)

[English](README.md) · **Deutsch**

[Installation](#schnellstart) · [Live-Liste](#live-liste) · [Rezepte](#rezepte) · [Proxy-Server](#proxy-server) · [So funktioniert's](#so-funktionierts) · [Optionen](#optionen) · [FAQ](#faq)

</div>

---

Die meisten freien Proxy-Listen sind zu 95 % tot. **proxy-scraper** probiert nicht stumpf alles durch, sondern lernt dazu: Proxys, die schon einmal funktioniert haben, kommen zuerst dran, danach die aus Quellen mit guter Trefferquote. Tote und nicht mehr gepflegte Listen fliegen automatisch raus, neue findet das Tool selbst auf GitHub – und jeder Treffer wird nicht nur angepingt, sondern muss eine echte Seite abrufen, HTTPS tunneln und zeigen, wie anonym er ist.

<table>
<tr>
<td width="33%" valign="top">

**🔐 Geprüft, nicht angepingt**<br>
Jeder Treffer muss über den Proxy zwei unabhängige Seiten abrufen. Das sortiert Honeypots aus – in manchen Läufen der Großteil der „funktionierenden“ Proxys.

</td>
<td width="33%" valign="top">

**🧠 Mit jedem Lauf besser**<br>
Trefferquoten pro Quelle und der Verlauf funktionierender Proxys bestimmen, was zuerst geprüft wird. Tote Listen fliegen raus, neue findet das Tool auf GitHub.

</td>
<td width="33%" valign="top">

**🔁 Ein Proxy, der immer geht**<br>
`--serve` macht aus den Treffern einen lokalen rotierenden Proxy mit automatischem Wechsel – einfach `127.0.0.1:8899` eintragen.

</td>
</tr>
</table>

<div align="center">
<img src="docs/demo.svg" alt="Animierte Demo: Einrichtungsassistent, Sammeln, Live-Dashboard und Abschlussbericht" width="880">
</div>

<details>
<summary><b>Inhalt</b></summary>

- [Installation](#schnellstart)
- [Live-Proxyliste](#live-liste)
- [Features](#features)
- [Beispiele](#beispiele)
- [Rezepte](#rezepte)
- [Rotierender Proxy-Server](#proxy-server)
- [So funktioniert's](#so-funktionierts)
- [Ausgabe](#ausgabe)
- [Optionen](#optionen)
- [GitHub Actions](#github-actions)
- [FAQ](#faq)
- [Roadmap](#roadmap) · [Mitmachen](#mitmachen) · [Danke](#danke)

</details>

<a id="schnellstart"></a>

## 🚀 Installation

**Mit [pipx](https://pipx.pypa.io/)** (empfohlen – ergibt den Befehl `proxy-scraper` in einer eigenen Umgebung):

```bash
pipx install git+https://github.com/maximilianfeix/proxy-scraper.git
proxy-scraper
```

<details>
<summary><b>Andere Wege: Docker, pip, schnellere Event-Loop oder direkt aus dem Repo</b></summary>
<br>

```bash
# Docker – Gelerntes und Ergebnisse bleiben in zwei Ordnern neben dir
mkdir -p proxy-data results
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/proxy-data:/data" -v "$PWD/results:/work/results" \
  ghcr.io/maximilianfeix/proxy-scraper --want 50 --https-only

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

Zu jedem [Release](https://github.com/maximilianfeix/proxy-scraper/releases/latest) gibt es außerdem ein Wheel für `pip install <datei>.whl` und ein Multi-Arch-Image (amd64/arm64) auf `ghcr.io`. Im Container kommt der Assistent nie, der Lauf startet direkt. Für den Proxy-Server `--serve --serve-host 0.0.0.0` mit `-p 127.0.0.1:8899:8899` – dann ist der Port nur auf dem eigenen Rechner offen.

Tab-Vervollständigung für bash, zsh und fish:

```bash
eval "$(proxy-scraper --completion zsh)"     # in ~/.zshrc (nach compinit), für bash genauso in ~/.bashrc
proxy-scraper --completion fish > ~/.config/fish/completions/proxy-scraper.fish
```

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

<a id="live-liste"></a>

## 📡 Live-Proxyliste

Keine Lust, selbst zu scannen? Alle 6 Stunden läuft das Tool per **GitHub Actions** und veröffentlicht die Treffer auf dem Branch [`proxy-list`](../../tree/proxy-list) – jeder Eintrag hat beim letzten Lauf wirklich funktioniert, schnellste zuerst.

**→ [Auf der Website durchsuchen](https://maximilianfeix.github.io/proxy-scraper/)** – suchen, nach Typ, Land, HTTPS und Latenz filtern, genau die passenden Proxys kopieren oder herunterladen.

<div align="center"><a href="https://maximilianfeix.github.io/proxy-scraper/"><img src="docs/website.png" alt="Die Website der Live-Liste" width="860"></a></div>

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

Oder das Tool startet direkt damit: `proxy-scraper --recheck live` lädt die Liste und prüft sie aus **deinem** Netz noch einmal – etwa 30 Sekunden statt eines kompletten Scans (von hier aus funktionierten 517 von 1.169). Mit `--serve` steht in unter einer Minute ein rotierender Proxy.

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
Jeder Treffer muss zwei unabhängige Seiten abrufen – das sortiert **Honeypots** aus, die nur auf Prüfanfragen antworten (in manchen Läufen 5 von 6 „Treffern“). Eine dritte Anfrage erwischt Proxys, die **Inhalte verändern**: In unseren Messungen schleuste jeder fünfte funktionierende Proxy ein Skript in eine einfache HTML-Seite ein. Dazu: HTTPS über einen Tunnel mit **verifiziertem TLS**, Anonymitätsstufe *elite / anonymous / transparent* und das Land der Exit-IP.

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
360+ Tests laufen ohne Internet gegen echte Mini-Proxys und Honeypots auf `localhost` – auf Linux, macOS und Windows mit Python 3.9, 3.11 und 3.13.

</td>
</tr>
</table>

<a id="beispiele"></a>

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
curl -x http://127.0.0.1:8899 https://api.ipify.org              # jedes Mal eine andere IP
curl -x socks5h://127.0.0.1:8899 https://api.ipify.org           # SOCKS5 auf demselben Port
curl -x http://country-de:x@127.0.0.1:8899 https://api.ipify.org # nur deutsche Exits
curl -x http://session-cart42:x@127.0.0.1:8899 https://shop.example  # derselbe Proxy für diese Session
curl http://127.0.0.1:8899/__proxy-scraper/status                # Pool und Zähler als JSON
```

Wie bei kommerziellen rotierenden Proxys trägt der **Benutzername** die Wünsche: `country-XX`, `type-http|socks4|socks5` und `session-NAME`, kombinierbar (`country-us-type-socks5-session-a`). Das klappt über HTTP (`Proxy-Authorization`) und SOCKS5 (Benutzer/Passwort). Das Passwort ist egal – standardmäßig lauscht der Server nur auf `127.0.0.1`. Mit `--serve-host` geht auch eine andere Adresse, dann kann ihn **jeder benutzen, der ihn erreicht** – also nur hinter einer Firewall oder in Docker mit `-p 127.0.0.1:…`.

| Option | Was sie macht |
|---|---|
| `--rotate weighted` | Standard: schnelle und bewährte Proxys öfter, alle bekommen eine Chance |
| `--rotate random` / `round-robin` | gleichmäßig, zufällig oder reihum |
| `--rotate fastest` | immer der schnellste, der gerade nicht ausgelastet ist |
| `--sticky 300` | dieselbe Seite behält 5 Minuten lang ihren Proxy (Logins, Warenkörbe) |

- jede Verbindung läuft über einen anderen gefundenen Proxy (außer mit Sticky), schnelle und bewährte werden bevorzugt
- `CONNECT` für HTTPS und normale HTTP-Anfragen; dahinter können HTTP-, SOCKS4- und SOCKS5-Proxys stecken (SOCKS5 mit DNS über den Proxy)
- für HTTPS nur Proxys, die den Test mit **verifiziertem TLS** bestanden haben – keine aufgebrochene Verschlüsselung
- bleibt ein Proxy im Tunnel stumm oder liefert statt TLS eine Fehlerseite, geht dasselbe erste Paket unbemerkt an den nächsten
- wer dreimal hintereinander scheitert, fliegt aus der Rotation – alle 5 Minuten werden die nachgeprüft und kommen zurück, wenn sie wieder funktionieren
- lauscht nur auf `127.0.0.1` (außer mit `--serve-host`); Live-Ansicht mit Anfragen, Erfolgsquote, Pool und den letzten Verbindungen

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
2. **Sammeln** – Text, HTML-Tabellen, JSON-APIs und `typ://ip:port`-Zeilen werden erkannt, private und reservierte Adressbereiche verworfen. Listen, die sich seit dem letzten Lauf nicht geändert haben, antworten mit `304` und kommen aus einem lokalen Cache – ein zweiter Lauf direkt danach lädt 0 MB statt ~160 MB.
3. **Priorisieren** – bekannte funktionierende Proxys zuerst, dann nach gelernter Trefferquote ihrer Quellen.
4. **Prüfen** – jeder Proxy muss seine Exit-IP von einem Prüfziel abrufen (`checkip.amazonaws.com`, als Reserve `ifconfig.me`, `ipinfo.io`, `wtfismyip.com` und `ident.me` – keins davon hinter Cloudflare) und eine gültige, *fremde* IP zurückliefern. Fällt das Ziel mitten im Lauf aus, wechselt das Tool und prüft die betroffenen Proxys erneut – die Statistik lernt so nicht aus einem Ausfall. Wer deine IP durchreicht, fliegt raus. Danach die **Bestätigung** über `httpbin.org`: Fake-Proxys, die nur auf die erste Prüfanfrage mit „200 + IP“ antworten, scheitern hier. Zum Schluss muss eine statische HTML-Seite Byte für Byte so ankommen wie ohne Proxy – wer Werbung oder Skripte einschleust, fliegt raus.
5. **Länder und Anbieter** – offline aus den freien DB-IP-Datenbanken, dazu der Anbieter (ASN) und ob es vermutlich ein Rechenzentrum ist (bei etwa 45 % der funktionierenden Proxys) (einmal im Monat geladen, ~2 µs pro Abfrage); ip-api.com wird nur noch für die wenigen Adressen gefragt, die dort fehlen.
6. **Lernen** – Trefferquoten und Verlauf landen in `data/`. Quellen ohne Treffer, mit seit einer Woche unverändertem Inhalt oder dauerhaft unerreichbar werden übersprungen.

<details>
<summary><b>📸 Live-Dashboard und Abschlussbericht ansehen</b></summary>
<br>
<div align="center">
<img src="docs/dashboard.svg" alt="Live-Dashboard während der Prüfung" width="860">
<br><br>
<img src="docs/summary.svg" alt="Abschlussbericht nach einem Lauf" width="860">
</div>
</details>

<a id="ausgabe"></a>

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

<a id="rezepte"></a>

## 🧪 Rezepte

**Den schnellsten Proxy des letzten Laufs nutzen** – freie Proxys sterben schnell, bei älteren Läufen vorher `--recheck`

```bash
proxy-scraper --recheck -y
curl -x "$(head -1 results/latest/all.txt)" http://api.ipify.org
```

Für HTTPS einen Proxy mit `"https": true` aus `proxies.json` nehmen – wie im Python-Beispiel.

**Python `requests`** (für SOCKS: `pip install "requests[socks]"`)

```python
import json
from pathlib import Path

import requests

run = Path("results") / Path("results/latest.txt").read_text().strip()   # works on every OS
proxies = json.loads((run / "proxies.json").read_text())   # schnellste zuerst

for p in proxies:
    if not p["https"]:
        continue
    try:
        r = requests.get("https://api.ipify.org", proxies={"http": p["url"], "https": p["url"]}, timeout=8)
        print(p["url"], "→", r.text)
        break
    except requests.RequestException:
        continue  # freie Proxys kommen und gehen – einfach den nächsten nehmen
```

**proxychains, Clash / Mihomo** – fertige Konfigurationen mit `--export`

```bash
proxy-scraper --want 30 -y --export proxychains,clash
proxychains4 -f results/latest/proxychains.conf curl https://api.ipify.org
```

`clash.yaml` enthält alle HTTP- und SOCKS5-Proxys plus eine `url-test`-Gruppe, die automatisch den schnellsten nimmt. HTTP-Proxys, die nicht tunneln können (`CONNECT`), fehlen in beiden Dateien, weil diese Tools alles tunneln.

**Beliebige Tools über den rotierenden Server**

```bash
proxy-scraper --recheck --serve &
export HTTPS_PROXY=http://127.0.0.1:8899 HTTP_PROXY=http://127.0.0.1:8899
pip download requests   # git, pip, npm & Co. laufen jetzt über den Pool
```

**Ganz ohne Installation** – direkt aus der Live-Liste

```bash
curl -s https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/https.txt | head -5
```

Die Shell-Beispiele sind für macOS und Linux, wo `results/latest` auf den neuesten Lauf zeigt. Unter Windows steht der Ordnername stattdessen in `results/latest.txt` – in PowerShell:

```powershell
$run = "results\$(Get-Content results\latest.txt)"
curl.exe -x (Get-Content "$run\all.txt" -TotalCount 1) http://api.ipify.org
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
| `--no-datacenter` | keine Proxys mit Exit (vermutlich) in einem Rechenzentrum – die werden schneller gesperrt |
| `--target URL` | nur Proxys, die diese Seite erreichen (mehrfach möglich) |
| `--recheck [DATEI\|live]` | nur Proxys aus einer Datei, vom letzten Lauf oder aus der öffentlichen Live-Liste prüfen |
| `--fast` | ohne HTTPS-Test (Bestätigung und Anonymität laufen trotzdem) |
| `--no-geo` | ohne Länder-Lookup |
| `-c`, `--concurrency N` | gleichzeitige Prüfungen (Standard: 2000) |
| `-t`, `--timeout S` | Timeout pro Proxy (Standard: 8 s) |
| `--discover` | sofort neue Quellen auf GitHub suchen |
| `--no-cache` | alle Listen neu laden (unveränderte werden sonst per ETag übersprungen) |
| `--list-sources [N]` | Rangliste der Quellen anzeigen |
| `--serve-host ADRESSE` | wo der Proxy-Server lauscht (Standard `127.0.0.1`; `0.0.0.0` für Docker, mit Warnung) |
| `--rotate STRATEGIE` · `--sticky SEK` | wie der Proxy-Server Proxys auswählt, siehe [oben](#proxy-server) |
| `--serve [PORT]` | danach als rotierender Proxy auf `127.0.0.1:PORT` bereitstellen (Standard: 8899) |
| `-o DATEI` | zusätzlich alle Treffer in diese Datei schreiben |
| `--export FORMATE` | Zusatzdateien für andere Tools: `proxychains`, `clash`, `curl` oder `all` |
| `-V`, `--version` | Version anzeigen |
| `--completion SHELL` | Skript für die Tab-Vervollständigung (bash, zsh oder fish) ausgeben |

Alles Weitere: `proxy-scraper --help`

</details>

> [!TIP]
> Für die GitHub-Suche reicht ein eingeloggtes [`gh`](https://cli.github.com/) oder die Umgebungsvariable `GITHUB_TOKEN`. Ohne Token gilt das API-Limit von 60 Anfragen pro Stunde, dann werden nur 40 Repos durchsucht.

<a id="github-actions"></a>

## 🤖 GitHub Actions

Das Repo arbeitet selbst mit:

| Workflow | Was er macht |
|---|---|
| [**tests**](../../actions/workflows/tests.yml) | 3 Betriebssysteme × 3 Python-Versionen, dazu ein gebautes und installiertes Paket – bei jedem Push und Pull Request |
| [**lint**](../../actions/workflows/lint.yml) | `ruff` mit fest gepinnter Version – lokal und in der CI dieselben Regeln |
| [**codeql**](../../actions/workflows/codeql.yml) | Sicherheitsanalyse bei jedem Push und einmal pro Woche |
| [**proxy list**](../../actions/workflows/proxy-list.yml) | alle 6 Stunden: sammeln, prüfen, auf `proxy-list` veröffentlichen. Die gelernte Statistik liegt im Actions-Cache – das Tool wird also auch in der Cloud mit jedem Lauf besser |
| [**docker**](../../actions/workflows/docker.yml) | baut das Image bei jeder Änderung und lässt darin einen echten Lauf laufen; bei einem Versions-Tag geht `linux/amd64` + `linux/arm64` auf `ghcr.io` |
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
<summary><b>Und Proxys mit Benutzername und Passwort?</b></summary>
<br>

Zeilen wie `socks5://user:pass@1.2.3.4:1080` behalten ihren Login: HTTP-Proxys bekommen einen `Proxy-Authorization`-Header, SOCKS5 nutzt Benutzer/Passwort (RFC 1929), SOCKS4 die User-ID. Das klappt genauso mit `--recheck` und einer eigenen Liste. In den Ergebnisdateien stehen die Zugangsdaten vollständig, im Terminal nur `user:•••`.

</details>

<details>
<summary><b>Wie aktuell ist die Live-Liste?</b></summary>
<br>

Sie wird alle 6 Stunden neu gebaut, das Badge „Stand“ zeigt den letzten Lauf. Freie Proxys kommen und gehen schnell – für Wichtiges direkt vorher `proxy-scraper --recheck` laufen lassen.

</details>

<a id="roadmap"></a>

## 🗺️ Roadmap

Was als Nächstes kommt, steht im Meilenstein [**v1.5**](../../milestone/5) – Ideen und Wünsche gerne als [Issue](../../issues/new/choose).

- [ ] [Auf PyPI veröffentlichen](../../issues/42), damit einfach `pipx install proxy-scraper` reicht
- [ ] [Rotierender Server aus dem Docker-Container erreichbar](../../issues/43)
- [ ] [Protokollerkennung auf derselben Verbindung](../../issues/44)

In [v1.4](../../milestone/4) erschienen: Exporte für proxychains/Clash/curl, Proxys mit Zugangsdaten, ETag-Cache, Ersatz-Prüfziele, Docker-Image, Länder offline. Gemessen und verworfen: Protokollerkennung mit extra Verbindung ([#3](../../issues/3)) und IPv6 ([#1](../../issues/1)).

<a id="mitmachen"></a>

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
├── checker.py          Prüfung, Bestätigung gegen Honeypots, HTTPS-Test
├── handshake.py        HTTP/SOCKS4/SOCKS5-Handshakes inkl. Login
├── judges.py           Prüfziele, Cloudflare-Filter, Wechsel bei Ausfall
├── sources.py          Quellenlisten, Meta-Quellen, GitHub-Discovery, Statistik
├── sources.json        kuratierte Quellen
├── fetchcache.py       ETag-Cache für unveränderte Listen
├── parsing.py          Proxys in Text, HTML und JSON finden
├── history.py          Verlauf funktionierender Proxys
├── geo.py              Länder: erst offline, ip-api.com als Reserve
├── asndb.py            DB-IP-Anbieterdatenbank, Rechenzentrum-Heuristik
├── geodb.py            DB-IP-Länderdatenbank (monatlich, Binärsuche)
├── targets.py          Zielseiten für --target
├── output.py           Ergebnisdateien
├── exporters.py        Formate für proxychains, Clash und curl (--export)
├── server/             rotierender Proxy-Server (--serve): pool · http · upstream · socks · status · core
├── publish.py          Live-Liste für GitHub Actions aufbereiten
├── paths.py            wo Zustand und Ergebnisse liegen
├── compat.py           Unterschiede zwischen Unix und Windows
├── netio.py            schlanker HTTP-Client auf asyncio
└── ui/                 widgets · dashboard · report · wizard · serve · keys
```

</details>

<a id="danke"></a>

## 🙏 Danke

proxy-scraper baut auf der Arbeit der Leute auf, die freie Proxy-Listen veröffentlichen. Danke an alle in [`sources.json`](proxyscraper/sources.json), besonders an

- [monosans/proxy-scraper-checker](https://github.com/monosans/proxy-scraper-checker) und [gfpcom/free-proxy-list](https://github.com/gfpcom/free-proxy-list), deren gepflegte Quellensammlungen als Meta-Quellen eingelesen werden
- [IP Geolocation by DB-IP](https://db-ip.com) – die freie Länder-Datenbank (CC BY 4.0) für die Länder ohne Internet-Dienst
- [Textualize/rich](https://github.com/Textualize/rich), das die komplette Oberfläche zeichnet
- [httpbin](https://httpbin.org), [checkip.amazonaws.com](https://checkip.amazonaws.com), [ifconfig.me](https://ifconfig.me), [ipinfo.io](https://ipinfo.io), [wtfismyip.com](https://wtfismyip.com), [ident.me](https://ident.me) und [ip-api.com](https://ip-api.com) als Prüfziele und für die Länder

## ⚠️ Hinweis

Öffentliche Proxys werden von Unbekannten betrieben, die alles mitlesen können, was unverschlüsselt durchgeht. Keine Passwörter oder persönlichen Daten darüber schicken und nur für legale Zwecke nutzen.

<div align="center">

---

<sub>Gebaut in Deutschland von <a href="https://github.com/maximilianfeix">@maximilianfeix</a> · <a href="LICENSE">MIT-Lizenz</a> · <a href="CHANGELOG.md">Changelog</a> · <a href="SECURITY.md">Sicherheit</a> · <a href="CONTRIBUTING.md">Mitmachen</a></sub>

<sub>Wenn dir proxy-scraper Zeit spart, hilft ein ⭐ anderen, es zu finden.</sub>

</div>
