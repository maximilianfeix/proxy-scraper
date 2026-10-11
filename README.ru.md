<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/banner-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/banner-light.svg">
  <img src="docs/banner-dark.svg" alt="proxy-scraper – бесплатные прокси, которые действительно работают" width="100%">
</picture>

[![tests](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/tests.yml/badge.svg)](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/maximilianfeix/proxy-scraper?style=flat-square&color=D4F77A&labelColor=121113)](https://github.com/maximilianfeix/proxy-scraper/releases/latest)
[![Live proxies](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Ftotal.json&style=flat-square&labelColor=121113)](#live-list)
[![PyPI](https://img.shields.io/pypi/v/proxy-scraper-cli?style=flat-square&color=D4F77A&labelColor=121113&label=pypi)](https://pypi.org/project/proxy-scraper-cli/)
[![Downloads](https://img.shields.io/pepy/dt/proxy-scraper-cli?style=flat-square&color=D4F77A&labelColor=121113&label=downloads)](https://pepy.tech/projects/proxy-scraper-cli)
[![Stars](https://img.shields.io/github/stars/maximilianfeix/proxy-scraper?style=flat-square&color=D4F77A&labelColor=121113)](https://github.com/maximilianfeix/proxy-scraper/stargazers)
[![License](https://img.shields.io/badge/license-MIT-D4F77A?style=flat-square&labelColor=121113)](LICENSE)

[English](README.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Deutsch](README.de.md) · **Русский** · [Português (Brasil)](README.pt-BR.md) · [Français](README.fr.md)

[Установка](#install) · [Ежечасный список прокси](#live-list) · [API пула прокси](#pool-api) · [Ротирующий прокси-сервер](#proxy-server) · [Python](#python) · [ИИ-агенты (MCP)](#mcp) · [FAQ](#faq)

</div>

---

Большинство бесплатных списков прокси на 95 % мертвы, а заметная часть остального – honeypot'ы или прокси, которые внедряют скрипты в ваши страницы. **proxy-scraper** собирает публичные HTTP-, SOCKS4- и SOCKS5-прокси из более чем 700 источников и оставляет только те, что проходят каждую проверку. С каждым запуском он учится, какие источники того стоят, и может превратить результат в один ротирующий прокси.

**В цифрах:** за один день он выполнил 3,6 миллиона проверок бесплатных прокси – 1,1 % прошли, а больше половины ответивших провалили второй запрос. [Что на самом деле есть в сети (англ.) →](docs/free-proxies-in-numbers.md)

**Кто использует:** ежечасный список – встроенный источник [monosans/proxy-scraper-checker](https://github.com/monosans/proxy-scraper-checker) и [gfpcom/free-proxy-list](https://github.com/gfpcom/free-proxy-list).

**Попробовать – без установки, около пяти секунд:**

```bash
uvx proxy-scraper-cli --pick 5 --types socks5     # 5 проверенных прокси

# или просто список
curl -s https://maximilianfeix.github.io/proxy-scraper/socks5.txt | head
```

`uvx` входит в [uv](https://docs.astral.sh/uv/); `pipx run proxy-scraper-cli --pick 5` делает то же самое.

<div align="center">
<img src="docs/demo.svg" alt="Демо: живая панель во время проверки, отчёт, мастер настройки и сбор" width="880">
</div>

## Проверки, которые проходит каждый прокси

| Проверка | Что значит |
|---|---|
| Настоящее рукопожатие | Прокси должен по-настоящему выполнить протокол HTTP, SOCKS4 или SOCKS5 |
| Два независимых сайта, один exit-IP | Второй, независимый запрос должен вернуть тот же exit-IP – honeypot'ы, которые отвечают только сканерам, отсеиваются здесь |
| Содержимое не изменено | Известная страница должна прийти байт в байт; прокси, внедряющие скрипты или рекламу, отбрасываются |
| HTTPS с проверенным TLS | Только прокси, у которых сертификат проверяется насквозь, считаются поддерживающими HTTPS |
| Подробности | Анонимность (elite / anonymous / transparent), страна, ASN и провайдер, дата-центр или нет, задержка, скорость загрузки |

<a id="install"></a>

## Установка

```bash
pipx install proxy-scraper-cli
proxy-scraper
```

Пакет на PyPI называется `proxy-scraper-cli` (простое имя занято), команда – `proxy-scraper`. Работает на Python 3.9–3.14 в macOS, Linux и Windows, зависит только от `rich` и `certifi`.

На macOS и Linux также через [Homebrew](https://brew.sh):

```bash
brew install maximilianfeix/tap/proxy-scraper
```

Или через Docker (`linux/amd64` и `linux/arm64`):

```bash
docker run --rm ghcr.io/maximilianfeix/proxy-scraper --want 50 --https-only
```

Запущенный без аргументов, мастер спрашивает, что вы ищете: стрелками выбираете пресет (найти всё, браузинг и веб, максимальная анонимность, быстрые и стабильные …) и в конце получаете готовую командную строку.

<a id="live-list"></a>

## Ежечасный список прокси

Не хотите сканировать сами? GitHub Actions запускает инструмент каждый час и публикует результат. Каждый прокси в списке прошёл все проверки в последнем запуске, отсортирован «лучшие первыми»: быстрые, которые скорее всего ещё живы, стоят сверху (прокси, живущий уже сутки, через час доступен в 99 % случаев; новый – только в 25 %).

- **Сайт** (фильтры по протоколу, стране, HTTPS, провайдеру, задержке): https://maximilianfeix.github.io/proxy-scraper/
- **Только списки** (TXT по протоколу, стране и сайту, плюс JSON/CSV): [maximilianfeix/free-proxy-list](https://github.com/maximilianfeix/free-proxy-list)

| Список | Формат | Адрес |
|---|---|---|
| Все | `socks5://1.2.3.4:1080` | `https://maximilianfeix.github.io/proxy-scraper/all.txt` |
| HTTP · SOCKS4 · SOCKS5 | `1.2.3.4:8080` | `…/http.txt` · `…/socks4.txt` · `…/socks5.txt` |
| Только с поддержкой HTTPS | `type://ip:port` | `…/https.txt` |
| Только elite | `type://ip:port` | `…/elite.txt` |
| Проходят к Google · Reddit · Amazon · Instagram · TikTok · Discord | `type://ip:port` | `…/works-with/google.txt` · `…/works-with/reddit.txt` · … |
| Стабильные (в 90 %+ запусков этой недели) | `type://ip:port` | `…/stable.txt` |
| Со всеми подробностями | задержка, страна, HTTPS, анонимность, exit-IP, аптайм | `…/proxies.json` · `…/proxies.csv` |

У каждого протокола и каждой страны есть своя страница с простой загрузкой, например [SOCKS5](https://maximilianfeix.github.io/proxy-scraper/socks5/) или [Россия](https://maximilianfeix.github.io/proxy-scraper/country/ru/) (`country/ru/proxies.txt`).

```bash
curl -s https://maximilianfeix.github.io/proxy-scraper/socks5.txt | head
```

> [!TIP]
> Файлы лежат и на GitHub Pages за CDN – без лимитов `raw.githubusercontent.com` и с CORS-заголовками, то есть работают прямо из браузера. [jsDelivr](https://cdn.jsdelivr.net/gh/maximilianfeix/proxy-scraper@proxy-list/) тоже работает, но может отставать на несколько часов.

Проверка идёт с серверов GitHub в США. `proxy-scraper --recheck live` скачивает список и перепроверяет его из **вашей** сети – около 30 секунд вместо полного сканирования. С `--serve` у вас меньше чем за минуту есть ротирующий прокси.

<a id="pool-api"></a>

## API пула прокси: замена jhao104/proxy_pool

Пользуетесь [jhao104/proxy_pool](https://github.com/jhao104/proxy_pool)? Эндпоинты, параметр `type=https` и поля JSON (`proxy`, `https`, `region`, `anonymous`, `check_count`, `fail_count`, …) те же – направьте код на порт 8899, и он продолжит работать. **Без Redis**, и каждый прокси прошёл проверку на honeypot и подмену содержимого; помеченные как HTTPS – ещё и проверку TLS.

```bash
proxy-scraper --recheck live --serve   # стартует с ежечасного списка, готов примерно через 30 с
```

```bash
curl http://127.0.0.1:8899/get                                    # один прокси в JSON
curl "http://127.0.0.1:8899/get?country=RU&https=1&format=txt"    # → http://203.0.113.7:8080
curl "http://127.0.0.1:8899/all?protocol=socks5&limit=20"         # 20 лучших SOCKS5
curl "http://127.0.0.1:8899/report?proxy=203.0.113.7:8080&ok=0"   # не сработал – три раза, и он вылетает
```

| Эндпоинт | Что делает |
|---|---|
| `/get` | один прокси, выбранный по стратегии `--rotate` |
| `/pop` | как `/get`, но прокси покидает пул |
| `/all` | все рабочие прокси, лучшие первыми (`limit=N`) |
| `/count` | количество по типу и стране |
| `/delete?proxy=IP:PORT` | убрать прокси |
| `/report?proxy=IP:PORT&ok=0` | обратная связь по вашим собственным запросам |

Фильтры работают для `/get`, `/pop` и `/all`: `country=RU,KZ`, `protocol=socks5`, `https=1`, `anonymity=elite`, `max_latency=1500`, а `format=txt` возвращает просто URL.

```python
import requests
proxy = requests.get("http://127.0.0.1:8899/get?type=https").json()["url"]   # например socks5://…, тип уже включён
requests.get("https://example.com", proxies={"http": proxy, "https": proxy})
```

<a id="proxy-server"></a>

## Ротирующий прокси-сервер

Тот же порт – ещё и локальный прокси: каждое соединение идёт через другой прокси, а если один падает, берётся следующий.

```bash
curl -x http://127.0.0.1:8899 https://api.ipify.org                  # каждый раз другой IP
curl -x socks5h://127.0.0.1:8899 https://api.ipify.org               # SOCKS5 на том же порту
curl -x http://country-ru:x@127.0.0.1:8899 https://api.ipify.org     # только российские выходы
curl -x http://session-cart42:x@127.0.0.1:8899 https://shop.example  # один и тот же прокси для этой сессии
```

Как у коммерческих ротирующих прокси, пожелание передаётся в **имени пользователя**: `country-XX`, `type-http|socks4|socks5` и `session-ИМЯ`, их можно комбинировать. HTTPS предпочитает прокси с проверенным TLS; если сейчас подходящего нет (никто не отвечает пожеланию вроде `country-ru`, или все выбыли), сервер берёт остальные – проверка сертификата вашим клиентом всё равно поймает прокси, ломающий шифрование, так что не отключайте её. Три ошибки подряд – и прокси выбывает из ротации; каждые пять минут он перепроверяется и возвращается, если снова работает. По умолчанию сервер слушает только `127.0.0.1`; для доступа с других машин задайте пароль через `PROXY_SCRAPER_SERVE_PASSWORD`. Все опции – в [английском README](README.md#proxy-server).

**Живая панель:** `http://127.0.0.1:8899/__proxy-scraper/` в браузере показывает пул, долю успешных запросов, трафик, страны, лучшие прокси и последние соединения – обновляется каждые две секунды.

<a id="python"></a>

## Из Python

```python
from proxyscraper import ProxyRotator, live_proxies

# ежечасный список, без проверки, примерно за секунду
proxies = live_proxies(types=["socks5"], https=True, min_uptime=90)

# автоматические повторы и смена прокси
with ProxyRotator(country="RU") as rotator:
    r = rotator.get("https://httpbin.org/ip")
    print(r.status, r.text, "via", r.via)

# один локальный адрес прокси для requests / httpx / Playwright / Scrapy, ротация за кулисами
with ProxyRotator() as rotator:
    proxy = rotator.proxy_url()
```

Для свежей проверки из вашей сети есть `find_proxies()` и `check_proxies()`. Полное описание – в [английском README](README.md#from-python).

## Частые команды

```bash
proxy-scraper --want 50 --https-only                   # остановиться, когда найдено 50 с поддержкой HTTPS
proxy-scraper --types socks5 --anonymity elite         # только elite SOCKS5
proxy-scraper --country RU,KZ,BY --max-latency 1500    # нужные страны, максимальная задержка
proxy-scraper --target www.google.com --want 20        # только прокси, которые достигают целевого сайта
proxy-scraper --pick 5 --types socks5                  # 5 из ежечасного списка, без сканирования
proxy-scraper --export clash                           # конфиг Clash (также proxychains, sing-box, curl)
```

Все опции: `proxy-scraper --help` или [английский README](README.md#options).

<a id="mcp"></a>

## ИИ-агенты (MCP)

`proxy-scraper-mcp` – это [MCP](https://modelcontextprotocol.io)-сервер: Claude Code, Claude Desktop, Cursor, VS Code, Codex и любой другой MCP-клиент могут получать рабочие прокси и загружать через них страницы.

[![proxy-scraper MCP server on Glama](https://glama.ai/mcp/servers/maximilianfeix/proxy-scraper/badges/score.svg)](https://glama.ai/mcp/servers/maximilianfeix/proxy-scraper)

| Инструмент | Что делает |
|---|---|
| `get_proxies` | рабочие прокси из ежечасного списка – фильтры по протоколу, стране, HTTPS, elite, дата-центру, стабильности, задержке |
| `check_proxies` | проверяет прокси из вашей сети, чтобы они работали там, где работает ваш код |
| `fetch_url` | загружает страницу через проверенный прокси, сам переключается при ошибке и возвращает читаемый текст |

**Claude Code:**

```bash
claude mcp add proxy-scraper -- uvx --python ">=3.10" --from "proxy-scraper-cli[mcp]" proxy-scraper-mcp
```

**Claude Desktop, Cursor и большинство других клиентов** – добавьте в конфигурацию MCP:

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

Не хотите Python? В Docker-образе есть всё: `"command": "docker"`, `"args": ["run", "-i", "--rm", "ghcr.io/maximilianfeix/proxy-scraper", "--mcp"]`. Сервер есть и в [официальном реестре MCP](https://registry.modelcontextprotocol.io) под именем `io.github.maximilianfeix/proxy-scraper`.

<a id="faq"></a>

## FAQ

**Кто держит бесплатные прокси – и можно ли ими пользоваться?**
Почти никто не держит бесплатный прокси для вас. В публичные списки обычно попадают: неправильно настроенные серверы с открытым портом; немного намеренно открытых прокси; заражённые компьютеры и IoT-устройства, о чём их владельцы не знают; и ловушки, которые логируют трафик или переписывают страницы. proxy-scraper не отличит заражённый домашний роутер от открытого офисного прокси, но отфильтровывает то, что можно измерить: два независимых запроса должны вернуть один exit-IP (honeypot'ы, отвечающие только сканерам, вылетают), известная страница должна прийти байт в байт (инжекторы вылетают), а HTTPS засчитывается только с насквозь проверенным сертификатом. Подходит для публичных данных, взгляда на сайт из другой страны, тестирования своих блокировок и исследований. Никогда не отправляйте пароли, cookies, платёжные или личные данные через бесплатный прокси.

**Почему находит меньше прокси, чем обещают другие списки?**
Потому что остаются только прокси, прошедшие каждую проверку. Многие списки считают всё, что принимает TCP-соединение; здесь прокси должен загрузить две независимые страницы и показать чужой IP. Обычно это несколько сотен или тысяч из миллиона кандидатов – но они работают.

**Почти ничего не проходит?**
Многие корпоративные, школьные и университетские сети блокируют прокси-соединения. Инструмент замечает долю попаданий ниже 0,2 % и предупреждает – поможет другая сеть, например точка доступа с телефона.

**Работает ли в Windows?**
Да, в PowerShell и Windows Terminal. `uvloop` там нет, и он автоматически пропускается.

**Насколько свеж список?**
Он пересобирается каждый час. Бесплатные прокси быстро появляются и исчезают – для всего важного запускайте `proxy-scraper --recheck` непосредственно перед использованием.

**Безопасны ли бесплатные прокси?**
Только для того, что не имеет значения. Публичные прокси держат незнакомцы, которые могут читать всё незашифрованное. Не отправляйте через них пароли и личные данные и используйте только там, где это разрешено.

## Участие

Issues и pull request'ы приветствуются, на русском или английском. Есть [задачи для новичков](https://github.com/maximilianfeix/proxy-scraper/issues?q=is%3Aopen+label%3A%22good+first+issue%22). Если proxy-scraper экономит вам время, ⭐ поможет другим его найти.

## Отказ от ответственности

Этот инструмент только собирает публично опубликованные прокси и проверяет, работают ли они. За их использование отвечаете вы – соблюдайте условия сайтов, которые посещаете, и законы, которые к вам применяются. [Лицензия MIT](LICENSE).
