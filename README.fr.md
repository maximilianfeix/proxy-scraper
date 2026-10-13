<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/banner-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/banner-light.svg">
  <img src="docs/banner-dark.svg" alt="proxy-scraper – des proxys gratuits qui fonctionnent vraiment" width="100%">
</picture>

[![tests](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/tests.yml/badge.svg)](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/maximilianfeix/proxy-scraper?style=flat-square&color=D4F77A&labelColor=121113)](https://github.com/maximilianfeix/proxy-scraper/releases/latest)
[![Live proxies](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Ftotal.json&style=flat-square&labelColor=121113)](#live-list)
[![PyPI](https://img.shields.io/pypi/v/proxy-scraper-cli?style=flat-square&color=D4F77A&labelColor=121113&label=pypi)](https://pypi.org/project/proxy-scraper-cli/)
[![Downloads](https://img.shields.io/pepy/dt/proxy-scraper-cli?style=flat-square&color=D4F77A&labelColor=121113&label=downloads)](https://pepy.tech/projects/proxy-scraper-cli)
[![Stars](https://img.shields.io/github/stars/maximilianfeix/proxy-scraper?style=flat-square&color=D4F77A&labelColor=121113)](https://github.com/maximilianfeix/proxy-scraper/stargazers)
[![License](https://img.shields.io/badge/license-MIT-D4F77A?style=flat-square&labelColor=121113)](LICENSE)

[English](README.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Deutsch](README.de.md) · [Русский](README.ru.md) · [Português (Brasil)](README.pt-BR.md) · **Français**

[Installation](#install) · [Liste de proxys horaire](#live-list) · [API de pool de proxys](#pool-api) · [Serveur proxy rotatif](#proxy-server) · [Python](#python) · [Agents IA (MCP)](#mcp) · [FAQ](#faq)

</div>

---

**Des vérifications de proxys que vous pouvez inspecter : ce qui a réussi, ce qui a échoué, et quand.** proxy-scraper collecte des proxys HTTP, SOCKS4 et SOCKS5 publics dans des centaines de listes, fait passer jusqu'à quatre vérifications à chacun et conserve le résultat de chaque vérification pour les proxys qu'il liste (pour les autres, il compte comment chaque vérification s'est terminée). « Fonctionne » devient ainsi quelque chose que vous pouvez regarder, et non une étiquette à croire sur parole.

<div align="center">
<img src="docs/demo/checks.gif" alt="Enregistrement de terminal : proxy-scraper --pick 2 --verify --https-only affiche deux proxys et indique sur stderr pourquoi les quatre autres ont été écartés ; proxy-scraper --diagnose montre chaque vérification d'un proxy avec son résultat" width="880">
</div>

<sub>Un véritable enregistrement de terminal, réalisé avec six proxys simulés sur localhost ([pour le reproduire](docs/demo/)). Il montre comment les résultats sont présentés. Il ne mesure rien sur les proxys publics.</sub>

**Essayez** – sans installation, `uvx` est fourni avec [uv](https://docs.astral.sh/uv/) (`pipx run` fait la même chose) :

```bash
uvx proxy-scraper-cli --pick 3 --verify               # jusqu'à 3 proxys de la liste horaire qui passent maintenant, depuis votre réseau
uvx proxy-scraper-cli --diagnose socks5://HOST:PORT   # un proxy, vérification par vérification : ce qu'il a réussi et ce qu'il n'a pas réussi
```

Sur PyPI, le paquet s'appelle `proxy-scraper-cli` (le nom simple était pris). Une fois [installé](#install), la commande est `proxy-scraper`. `--verify` et `--diagnose` demandent la version 1.29 ou une version plus récente.

**Trois façons d'obtenir des proxys, et ce que « vérifié » veut dire pour chacune :**

| Commande | D'où viennent les proxys | Vérifiés | Durée |
|---|---|---|---|
| `proxy-scraper --pick 5` | de la [liste publiée](#live-list) | depuis les serveurs de GitHub, au moment où la liste a été construite, environ toutes les heures | moins d'une seconde |
| `proxy-scraper --pick 5 --verify` | de la liste publiée | **maintenant, depuis votre réseau** | de quelques secondes à une minute et demie au maximum |
| `proxy-scraper -y` | de toutes les listes que l'outil connaît | maintenant, depuis votre réseau | quelques minutes (environ trois dans les exécutions horaires) |

**Ce que vous obtenez**

- **Chaque vérification a un résultat lisible.** `passed`, `failed`, `unavailable` ou `skipped` (réussie, échouée, indisponible, ignorée), avec un code de raison, la cible et l'heure, dans le terminal, en JSON et depuis Python. Une vérification qui n'a pas eu lieu n'est jamais affichée comme réussie, et une cible de vérification en panne ne fait pas échouer les proxys vérifiés contre elle. → [États des vérifications (en anglais)](docs/check-states.md)
- **Frais quand ça compte.** `--pick --verify` vérifie quelques proxys depuis votre propre réseau, en général en quelques secondes. `--recheck` fait la même chose pour [une liste à vous](README.md#examples), et `--diagnose` vous dit pourquoi un proxy ne fonctionne pas.
- **Plus qu'une liste.** Un [serveur proxy rotatif local](#proxy-server), une [API Python](#python), un [serveur MCP](#mcp) pour les agents IA, Docker, et des exports pour curl, proxychains, Clash et sing-box.

**Ce qu'il ne peut pas faire.** Les proxys gratuits sont tenus par des inconnus, et de la liste d'une heure donnée, un quart environ seulement figure encore sur la liste un jour plus tard. Une vérification réussie est une mesure, depuis un réseau, contre des cibles de test : ce n'est pas une promesse pour l'heure qui suit ni pour le site qui vous intéresse. La vérification HTTPS est une connexion TLS vérifiée vers un seul hôte de test, pas une évaluation de sécurité. Utilisez les proxys gratuits pour des données publiques et des tests, jamais pour des connexions à un compte, des paiements ou quoi que ce soit de personnel. → [Ce que les chiffres montrent et ce qu'ils ne montrent pas (en anglais)](docs/free-proxies-in-numbers.md) · [Comparaison avec d'autres projets (en anglais)](docs/comparison.md) · [Qui fait tourner les proxys gratuits](#faq)

**Vous ne voulez que les listes ?** Vous n'avez pas besoin de cet outil : [free-proxy-list](https://github.com/maximilianfeix/free-proxy-list) les propose en fichiers bruts par protocole et par pays, reconstruits environ toutes les heures. Ou directement d'ici : [all.txt](https://maximilianfeix.github.io/proxy-scraper/all.txt) · [http.txt](https://maximilianfeix.github.io/proxy-scraper/http.txt) · [socks4.txt](https://maximilianfeix.github.io/proxy-scraper/socks4.txt) · [socks5.txt](https://maximilianfeix.github.io/proxy-scraper/socks5.txt) · [proxies.json](https://maximilianfeix.github.io/proxy-scraper/proxies.json) · [autres formats](#live-list)

**Qui l'utilise :** la liste horaire est une source intégrée de [monosans/proxy-scraper-checker](https://github.com/monosans/proxy-scraper-checker) et de [gfpcom/free-proxy-list](https://github.com/gfpcom/free-proxy-list).

## Les vérifications que chaque proxy doit passer

| Vérification | Ce que ça veut dire |
|---|---|
| Vraie poignée de main | Le proxy doit réellement dérouler le protocole HTTP, SOCKS4 ou SOCKS5 |
| Seconde requête, la même IP de sortie | Une seconde requête, vers un autre site, doit montrer la même IP de sortie. Les proxys qui ne répondent qu'à la première vérification, les instables et ceux dont la sortie change échouent ici |
| Contenu intact | Une page de test statique doit arriver octet pour octet. La raison d'une différence n'est pas déterminée |
| HTTPS avec certificat vérifié | Un proxy ne compte comme compatible HTTPS que si le certificat TLS reçu à travers son tunnel est valide pour l'hôte de test |
| Détails | Anonymat (elite / anonymous / transparent), pays, ASN et fournisseur, datacenter ou non, latence, vitesse de téléchargement |

<a id="install"></a>

## Installation

```bash
pipx install proxy-scraper-cli
proxy-scraper
```

Sur PyPI, le paquet s'appelle `proxy-scraper-cli` (le nom simple était pris), la commande est `proxy-scraper`. Fonctionne avec Python 3.9–3.14 sous macOS, Linux et Windows, et ne dépend que de `rich` et `certifi`.

Sous macOS et Linux, aussi avec [Homebrew](https://brew.sh) :

```bash
brew install maximilianfeix/tap/proxy-scraper
```

Ou avec Docker (`linux/amd64` et `linux/arm64`) :

```bash
docker run --rm ghcr.io/maximilianfeix/proxy-scraper --want 50 --https-only
```

Lancé sans argument, un assistant demande ce que vous cherchez : avec les flèches, vous choisissez un préréglage (tout trouver, navigation et web, anonymat maximal, rapides et stables …) et vous obtenez à la fin la ligne de commande correspondante.

<a id="live-list"></a>

## Liste de proxys horaire

Pas envie de scanner vous-même ? GitHub Actions lance l'outil environ toutes les heures et publie les résultats. Chaque proxy de la liste a passé la première requête, la seconde requête et la vérification du contenu lors de la dernière exécution (le test HTTPS est enregistré pour chaque entrée, mais n'est pas exigé), trié « les meilleurs d'abord » : les rapides, qui ont de bonnes chances d'être encore en ligne, sont en haut.

- **Site web** (filtres par protocole, pays, HTTPS, fournisseur, latence) : https://maximilianfeix.github.io/proxy-scraper/
- **Rien que les listes** (TXT par protocole, pays et site, plus JSON/CSV) : [maximilianfeix/free-proxy-list](https://github.com/maximilianfeix/free-proxy-list)

| Liste | Format | Adresse |
|---|---|---|
| Tous | `socks5://1.2.3.4:1080` | `https://maximilianfeix.github.io/proxy-scraper/all.txt` |
| HTTP · SOCKS4 · SOCKS5 | `1.2.3.4:8080` | `…/http.txt` · `…/socks4.txt` · `…/socks5.txt` |
| Compatibles HTTPS seulement | `type://ip:port` | `…/https.txt` |
| Elite seulement | `type://ip:port` | `…/elite.txt` |
| Passent chez Google · Reddit · Amazon · Instagram · TikTok · Discord | `type://ip:port` | `…/works-with/google.txt` · `…/works-with/reddit.txt` · … |
| Stables (présents dans 90 %+ des exécutions de la semaine) | `type://ip:port` | `…/stable.txt` |
| Avec tous les détails | latence, pays, HTTPS, anonymat, IP de sortie, disponibilité | `…/proxies.json` · `…/proxies.csv` |

Chaque protocole et chaque pays a aussi sa page avec un téléchargement direct, par exemple [SOCKS5](https://maximilianfeix.github.io/proxy-scraper/socks5/) ou [France](https://maximilianfeix.github.io/proxy-scraper/country/fr/) (`country/fr/proxies.txt`).

```bash
curl -s https://maximilianfeix.github.io/proxy-scraper/socks5.txt | head
```

> [!TIP]
> Les fichiers sont aussi sur GitHub Pages, derrière un CDN – sans la limite de débit de `raw.githubusercontent.com` et avec des en-têtes CORS, donc utilisables directement depuis le navigateur. [jsDelivr](https://cdn.jsdelivr.net/gh/maximilianfeix/proxy-scraper@proxy-list/) fonctionne aussi, avec parfois quelques heures de retard.

La vérification se fait depuis les serveurs de GitHub aux États-Unis. `proxy-scraper --recheck live` télécharge la liste et la revérifie depuis **votre** réseau – bien moins d'une minute au lieu d'un scan complet. Le nombre de proxys qui fonctionnent encore depuis votre réseau s'écarte beaucoup du chiffre de la liste, et c'est tout l'intérêt de revérifier. Ajoutez `--serve` et le résultat devient un proxy rotatif.

<a id="pool-api"></a>

## API de pool de proxys : compatible avec jhao104/proxy_pool

Vous utilisez [jhao104/proxy_pool](https://github.com/jhao104/proxy_pool) ? Les endpoints, le paramètre `type=https` et la plupart des champs JSON (`proxy`, `https`, `region`, `check_count`, `fail_count`, …) sont les mêmes – pointez votre code vers le port 8899 et l'essentiel continue de fonctionner (trois différences : il n'y a pas de `last_time`, `anonymous` vaut true/false et n'est pas une chaîne, et `source` vaut toujours `proxy-scraper`). **Sans Redis**, et chaque proxy a passé la vérification de la seconde requête et celle du contenu ; ceux marqués HTTPS ont aussi passé celle du TLS.

```bash
proxy-scraper --recheck live --serve   # démarre avec la liste horaire, prêt en ~30 s
```

```bash
curl http://127.0.0.1:8899/get                                    # un proxy en JSON
curl "http://127.0.0.1:8899/get?country=FR&https=1&format=txt"    # → http://203.0.113.7:8080
curl "http://127.0.0.1:8899/all?protocol=socks5&limit=20"         # les 20 meilleurs SOCKS5
curl "http://127.0.0.1:8899/report?proxy=203.0.113.7:8080&ok=0"   # il vous a lâché – trois fois et il sort
```

| Endpoint | Rôle |
|---|---|
| `/get` | un proxy, choisi selon la stratégie `--rotate` |
| `/pop` | comme `/get`, et le proxy quitte le pool |
| `/all` | tous les proxys utilisables, les meilleurs d'abord (`limit=N`) |
| `/count` | totaux par type et par pays |
| `/delete?proxy=IP:PORT` | retirer un proxy |
| `/report?proxy=IP:PORT&ok=0` | retour de vos propres requêtes |

Les filtres s'appliquent à `/get`, `/pop` et `/all` : `country=FR,BE`, `protocol=socks5`, `https=1`, `anonymity=elite`, `max_latency=1500`, et `format=txt` pour une URL brute.

```python
import requests
proxy = requests.get("http://127.0.0.1:8899/get?type=https").json()["url"]   # p. ex. socks5://…, type inclus
requests.get("https://example.com", proxies={"http": proxy, "https": proxy})
```

<a id="proxy-server"></a>

## Serveur proxy rotatif

Le même port est aussi un proxy local : chaque connexion sort par un proxy différent, et si l'un tombe, le suivant prend le relais.

```bash
curl -x http://127.0.0.1:8899 https://api.ipify.org                  # une IP différente à chaque fois
curl -x socks5h://127.0.0.1:8899 https://api.ipify.org               # SOCKS5 sur le même port
curl -x http://country-fr:x@127.0.0.1:8899 https://api.ipify.org     # sorties françaises seulement
curl -x http://session-cart42:x@127.0.0.1:8899 https://shop.example  # le même proxy pour cette session
```

Comme chez les proxys rotatifs commerciaux, la demande passe par le **nom d'utilisateur** : `country-XX`, `type-http|socks4|socks5` et `session-NOM`, combinables. HTTPS préfère les proxys au TLS vérifié ; si aucun ne convient sur le moment (aucun ne répond à une demande comme `country-fr`, ou ils sont tous tombés), le serveur prend les autres – la vérification du certificat par votre client attrape de toute façon un proxy qui casse le chiffrement, alors laissez-la activée. Trois échecs d'affilée et un proxy quitte la rotation ; toutes les cinq minutes il est revérifié et revient s'il fonctionne de nouveau. Par défaut, le serveur n'écoute que sur `127.0.0.1` ; pour y accéder depuis d'autres machines, définissez un mot de passe avec `PROXY_SCRAPER_SERVE_PASSWORD`. Toutes les options dans le [README anglais](README.md#proxy-server).

**Tableau de bord en direct :** `http://127.0.0.1:8899/__proxy-scraper/` dans le navigateur montre le pool, le taux de réussite, le trafic, les pays, les meilleurs proxys et les dernières connexions – rafraîchi toutes les deux secondes.

<a id="python"></a>

## Depuis Python

```python
from proxyscraper import ProxyRotator, live_proxies

# la liste horaire, sans vérification, en une seconde environ
proxies = live_proxies(types=["socks5"], https=True, min_uptime=90)

# nouvelles tentatives et changement de proxy automatiques
with ProxyRotator(country="FR") as rotator:
    r = rotator.get("https://httpbin.org/ip")
    print(r.status, r.text, "via", r.via)

# une adresse de proxy locale pour requests / httpx / Playwright / Scrapy, rotation en coulisses
with ProxyRotator() as rotator:
    proxy = rotator.proxy_url()
```

Pour une vérification fraîche depuis votre réseau, il y a `find_proxies()` et `check_proxies()`. La description complète est dans le [README anglais](README.md#from-python).

## Commandes courantes

```bash
proxy-scraper --want 50 --https-only                   # s'arrêter dès que 50 compatibles HTTPS sont trouvés
proxy-scraper --types socks5 --anonymity elite         # SOCKS5 elite seulement
proxy-scraper --country FR,BE,CH --max-latency 1500    # certains pays, latence maximale
proxy-scraper --target www.google.com --want 20        # seulement les proxys qui atteignent le site cible
proxy-scraper --pick 5 --types socks5                  # 5 depuis la liste horaire, sans scan
proxy-scraper --export clash                           # configuration Clash (aussi proxychains, sing-box, curl)
```

Toutes les options : `proxy-scraper --help` ou le [README anglais](README.md#options).

<a id="mcp"></a>

## Agents IA (MCP)

`proxy-scraper-mcp` est un serveur [MCP](https://modelcontextprotocol.io) : Claude Code, Claude Desktop, Cursor, VS Code, Codex et tout autre client MCP peuvent demander des proxys fonctionnels et charger des pages à travers eux.

[![proxy-scraper MCP server on Glama](https://glama.ai/mcp/servers/maximilianfeix/proxy-scraper/badges/score.svg)](https://glama.ai/mcp/servers/maximilianfeix/proxy-scraper)

| Outil | Rôle |
|---|---|
| `get_proxies` | des proxys de la liste horaire, tels que vérifiés lors de sa dernière exécution – filtrables par protocole, pays, HTTPS, elite, datacenter, stabilité, latence |
| `check_proxies` | vérifie des proxys depuis votre réseau, pour qu'ils fonctionnent là où tourne votre code |
| `fetch_url` | charge une page via un proxy de la liste vérifiée, change de proxy tout seul en cas d'erreur et renvoie un texte lisible |

**Claude Code :**

```bash
claude mcp add proxy-scraper -- uvx --python ">=3.10" --from "proxy-scraper-cli[mcp]" proxy-scraper-mcp
```

**Claude Desktop, Cursor et la plupart des autres clients** – à ajouter à la configuration MCP :

```json
{
  "mcpServers": {
    "proxy-scraper": {
      "command": "uvx",
      "args": ["--python", ">=3.10", "--from", "proxy-scraper-cli[mcp]", "proxy-scraper-mcp"]
    }
  }
}
```

Pas de Python ? L'image Docker contient tout : `"command": "docker"`, `"args": ["run", "-i", "--rm", "ghcr.io/maximilianfeix/proxy-scraper", "--mcp"]`. Le serveur est aussi dans le [registre MCP officiel](https://registry.modelcontextprotocol.io) sous le nom `io.github.maximilianfeix/proxy-scraper`.

<a id="faq"></a>

## FAQ

**Qui fait tourner les proxys gratuits – et peut-on les utiliser ?**
Presque personne ne fait tourner un proxy gratuit pour vous. Ce qui atterrit sur les listes publiques, c'est généralement : des serveurs mal configurés avec un port ouvert par erreur ; quelques proxys ouverts volontairement ; des ordinateurs et objets connectés infectés, à l'insu de leurs propriétaires ; et des pièges – des honeypots qui journalisent le trafic et des proxys qui réécrivent les pages. C'est un rappel général, pas quelque chose que ce projet a mesuré : une vérification ne voit pas qui fait tourner un proxy ni pourquoi. proxy-scraper ne distingue pas un routeur domestique infecté d'un proxy de bureau ouvert, mais il filtre ce qui est mesurable : deux requêtes indépendantes doivent montrer la même IP de sortie, une page connue doit arriver octet pour octet, et le HTTPS ne compte qu'avec un certificat valide pour l'hôte de test. Bien pour les données publiques, pour voir un site depuis un autre pays, pour tester ses propres blocages et pour la recherche. N'envoyez jamais de mots de passe, cookies, données de paiement ou personnelles à travers un proxy gratuit.

**Pourquoi trouve-t-il moins de proxys que d'autres listes n'en promettent ?**
Parce que seuls restent les proxys qui passent chaque vérification : deux requêtes indépendantes qui montrent la même IP de sortie étrangère, et une page de test qui arrive inchangée. Dans les exécutions horaires, cela représente environ 1 % des 150 000 candidats vérifiés. Ils ont réussi depuis le réseau qui les a vérifiés, à ce moment-là.

**Presque rien ne passe ?**
Beaucoup de réseaux d'entreprise, d'école et d'université bloquent les connexions proxy. L'outil remarque un taux de réussite sous 0,2 % et vous prévient – un autre réseau, comme le partage de connexion du téléphone, aide.

**Ça marche sous Windows ?**
Oui, dans PowerShell et Windows Terminal. `uvloop` n'existe pas là-bas et est ignoré automatiquement.

**La liste est fraîche à quel point ?**
Elle est reconstruite environ toutes les heures. Les proxys gratuits vont et viennent vite – pour tout ce qui compte, lancez `proxy-scraper --recheck` juste avant de les utiliser.

**Les proxys gratuits sont-ils sûrs ?**
Seulement pour ce qui n'a pas d'importance. Les proxys publics sont tenus par des inconnus qui peuvent lire tout ce qui n'est pas chiffré. N'y faites passer ni mots de passe ni données personnelles, et ne les utilisez que là où c'est permis.

## Contribuer

Issues et pull requests sont les bienvenus, en français ou en anglais. Il y a des [issues pour débuter](https://github.com/maximilianfeix/proxy-scraper/issues?q=is%3Aopen+label%3A%22good+first+issue%22). Si proxy-scraper vous fait gagner du temps, une ⭐ aide les autres à le trouver.

## Avertissement

Cet outil ne fait que collecter des proxys listés publiquement et vérifier s'ils fonctionnent. Vous êtes responsable de l'usage que vous en faites – respectez les conditions des sites que vous visitez et les lois qui s'appliquent à vous. [Licence MIT](LICENSE).
