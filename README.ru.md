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

**Проверки прокси, которые можно разобрать: что прошло, что нет и когда.** proxy-scraper собирает публичные HTTP-, SOCKS4- и SOCKS5-прокси из сотен списков, для каждого выполняет до четырёх проверок и сохраняет итог каждой проверки у прокси, попавших в список (для остальных считает, чем каждая проверка закончилась). «Работает» — это то, что можно посмотреть самому, а не ярлык, которому приходится верить на слово.

<div align="center">
<img src="docs/demo/checks.gif" alt="Запись терминала: proxy-scraper --pick 2 --verify --https-only выводит два прокси и сообщает в stderr, почему остальные четыре не попали в вывод; proxy-scraper --diagnose показывает каждую проверку одного прокси с её результатом" width="880">
</div>

<sub>Реальная запись терминала на шести имитированных прокси на localhost ([как воспроизвести](docs/demo/)). Показывает, как выглядят результаты; про публичные прокси ничего не измеряет.</sub>

**Попробовать** — установка не нужна, `uvx` входит в [uv](https://docs.astral.sh/uv/) (`pipx run` делает то же самое):

```bash
uvx proxy-scraper-cli --pick 3 --verify               # до 3 прокси из ежечасного списка, которые проходят проверку прямо сейчас из вашей сети
uvx proxy-scraper-cli --diagnose socks5://HOST:PORT   # один прокси, проверка за проверкой: что прошло, а что нет
```

Пакет на PyPI называется `proxy-scraper-cli` (короткое имя занято). После [установки](#install) команда — `proxy-scraper`. Для `--verify` и `--diagnose` нужна версия 1.30 или новее.

**Три способа получить прокси — и что в каждом случае значит «проверен»:**

| Команда | Откуда берутся прокси | Когда и откуда проверены | Сколько занимает |
|---|---|---|---|
| `proxy-scraper --pick 5` | из [опубликованного списка](#live-list) | на серверах GitHub при сборке списка, примерно раз в час | меньше секунды |
| `proxy-scraper --pick 5 --verify` | из опубликованного списка | **сейчас, из вашей сети** | от нескольких секунд до полутора минут |
| `proxy-scraper -y` | из всех списков, которые знает инструмент | сейчас, из вашей сети | минуты (в ежечасных запусках — около трёх) |

**Что вы получаете**

- **У каждой проверки есть читаемый итог.** `passed`, `failed`, `unavailable` или `skipped` (пройдена, не пройдена, недоступна, пропущена) — с кодом причины, целью и временем; в терминале, в JSON и из Python. Проверка, которую не запускали, никогда не показывается как пройденная; если цель проверки недоступна, прокси из‑за этого не считаются провалившимися. → [Состояния проверок (англ.)](docs/check-states.md)
- **Свежесть, когда она нужна.** `--pick --verify` проверяет несколько прокси из вашей сети, обычно за секунды. `--recheck` делает то же с [вашим списком](README.md#examples), а `--diagnose` объясняет, почему конкретный прокси не работает.
- **Больше, чем список.** [Локальный ротирующий прокси-сервер](#proxy-server), [Python API](#python), [MCP-сервер](#mcp) для ИИ-агентов, Docker и экспорт для curl, proxychains, Clash и sing-box.

**Чего он не умеет.** Бесплатные прокси держат незнакомцы, и из часового списка через сутки снова в списке оказывается лишь около четверти. Пройденная проверка — одно измерение из одной сети по тестовым целям: она ничего не обещает ни на следующий час, ни для сайта, который вам нужен. Проверка HTTPS — это проверенное TLS-соединение с одним тестовым хостом, а не оценка безопасности. Используйте бесплатные прокси для публичных данных и тестов — и никогда для входа в аккаунты, платежей и всего личного. → [Что показывают цифры и чего не показывают (англ.)](docs/free-proxies-in-numbers.md) · [Сравнение с другими проектами (англ.)](docs/comparison.md) · [Кто держит бесплатные прокси](#faq)

**Нужны только списки?** Тогда этот инструмент не обязателен: в [free-proxy-list](https://github.com/maximilianfeix/free-proxy-list) они лежат обычными файлами по протоколам и странам и пересобираются примерно раз в час. Или прямо отсюда: [all.txt](https://maximilianfeix.github.io/proxy-scraper/all.txt) · [http.txt](https://maximilianfeix.github.io/proxy-scraper/http.txt) · [socks4.txt](https://maximilianfeix.github.io/proxy-scraper/socks4.txt) · [socks5.txt](https://maximilianfeix.github.io/proxy-scraper/socks5.txt) · [proxies.json](https://maximilianfeix.github.io/proxy-scraper/proxies.json) · [другие форматы](#live-list)

**Кто использует:** ежечасный список — встроенный источник в [monosans/proxy-scraper-checker](https://github.com/monosans/proxy-scraper-checker) и [gfpcom/free-proxy-list](https://github.com/gfpcom/free-proxy-list).

## Проверки, которые проходит каждый прокси

| Проверка | Что значит |
|---|---|
| Настоящий handshake | Прокси должен реально пройти протокол HTTP, SOCKS4 или SOCKS5 |
| Второй запрос, тот же exit-IP | Второй запрос к другому сайту должен показать тот же exit-IP. Здесь отсеиваются прокси, которые отвечают только на первую проверку, нестабильные и те, у которых меняется выход |
| Содержимое не изменено | Статическая тестовая страница должна прийти байт в байт. Почему она отличается — не разбирается |
| HTTPS с проверенным сертификатом | Прокси считается HTTPS-совместимым, только если TLS-сертификат через его туннель проходит проверку для тестового хоста |
| Метаданные | Анонимность (elite / anonymous / transparent), страна, ASN и провайдер, дата-центр или нет, задержка, скорость загрузки |

<a id="install"></a>

## Установка

```bash
pipx install proxy-scraper-cli
proxy-scraper
```

Пакет на PyPI называется `proxy-scraper-cli` (короткое имя занято), команда — `proxy-scraper`. Работает на Python 3.9–3.14 в macOS, Linux и Windows; из зависимостей нужны только `rich` и `certifi`.

На macOS и Linux также через [Homebrew](https://brew.sh):

```bash
brew install maximilianfeix/tap/proxy-scraper
```

Или через Docker (`linux/amd64` и `linux/arm64`):

```bash
docker run --rm ghcr.io/maximilianfeix/proxy-scraper --want 50 --https-only
```

Если запустить без аргументов, мастер спросит, что вам нужно: стрелками выбираете пресет (найти всё, просмотр сайтов, максимальная анонимность, быстрые и стабильные…) и в конце получаете готовую командную строку.

<a id="live-list"></a>

## Ежечасный список прокси

Не хотите сканировать сами? GitHub Actions запускает инструмент примерно раз в час и публикует результат. Каждый прокси в списке в последнем запуске прошёл первый запрос, второй запрос и проверку содержимого (тест HTTPS для каждой записи пишется, но не обязателен); список отсортирован «лучшие сверху»: быстрые и с большей вероятностью ещё живые — в начале.

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
| Со всеми полями | задержка, страна, HTTPS, анонимность, exit-IP, аптайм | `…/proxies.json` · `…/proxies.csv` |

У каждого протокола и каждой страны есть своя страница с удобной загрузкой, например [SOCKS5](https://maximilianfeix.github.io/proxy-scraper/socks5/) или [Россия](https://maximilianfeix.github.io/proxy-scraper/country/ru/) (`country/ru/proxies.txt`).

```bash
curl -s https://maximilianfeix.github.io/proxy-scraper/socks5.txt | head
```

> [!TIP]
> Файлы также лежат на GitHub Pages за CDN — без лимитов `raw.githubusercontent.com` и с CORS-заголовками, так что их можно читать прямо из браузера. [jsDelivr](https://cdn.jsdelivr.net/gh/maximilianfeix/proxy-scraper@proxy-list/) тоже подходит, но может отставать на несколько часов.

Проверка идёт с серверов GitHub в США. `proxy-scraper --recheck live` скачивает список и перепроверяет его из **вашей** сети — заметно меньше минуты вместо полного скана. Сколько прокси ещё живы именно из вашей сети, сильно отличается от числа в самом списке — ради этого и стоит перепроверять. Добавьте `--serve`, и результат станет ротирующим прокси.

<a id="pool-api"></a>

## API пула прокси: совместим с jhao104/proxy_pool

Пользуетесь [jhao104/proxy_pool](https://github.com/jhao104/proxy_pool)? Эндпоинты, параметр `type=https` и большинство полей JSON (`proxy`, `https`, `region`, `check_count`, `fail_count`, …) те же — направьте код на порт 8899, и почти всё продолжит работать (три отличия: поля `last_time` нет, `anonymous` — это true/false, а не строка, а `source` всегда `proxy-scraper`). **Без Redis**, и каждый прокси прошёл проверку вторым запросом и проверку содержимого; помеченные как HTTPS — ещё и проверку TLS.

```bash
proxy-scraper --recheck live --serve   # стартует с ежечасного списка, готов примерно через 30 секунд
```

```bash
curl http://127.0.0.1:8899/get                                    # один прокси в JSON
curl "http://127.0.0.1:8899/get?country=RU&https=1&format=txt"    # → http://203.0.113.7:8080
curl "http://127.0.0.1:8899/all?protocol=socks5&limit=20"         # 20 лучших SOCKS5
curl "http://127.0.0.1:8899/report?proxy=203.0.113.7:8080&ok=0"   # не сработал — три раза, и он выпадает из пула
```

| Эндпоинт | Что делает |
|---|---|
| `/get` | один прокси по стратегии `--rotate` |
| `/pop` | как `/get`, но прокси сразу убирается из пула |
| `/all` | все рабочие прокси, сначала лучшие (`limit=N`) |
| `/count` | количество по типу и стране |
| `/delete?proxy=IP:PORT` | убрать прокси |
| `/report?proxy=IP:PORT&ok=0` | сообщить, сработал ли прокси в вашем коде |

Фильтры работают для `/get`, `/pop` и `/all`: `country=RU,KZ`, `protocol=socks5`, `https=1`, `anonymity=elite`, `max_latency=1500`; `format=txt` возвращает просто URL.

```python
import requests
proxy = requests.get("http://127.0.0.1:8899/get?type=https").json()["url"]   # например socks5://… — тип уже в URL
requests.get("https://example.com", proxies={"http": proxy, "https": proxy})
```

<a id="proxy-server"></a>

## Ротирующий прокси-сервер

Тот же порт — ещё и локальный прокси: каждое соединение идёт через другой выход, а если один падает, берётся следующий.

```bash
curl -x http://127.0.0.1:8899 https://api.ipify.org                  # каждый раз другой IP
curl -x socks5h://127.0.0.1:8899 https://api.ipify.org               # SOCKS5 на том же порту
curl -x http://country-ru:x@127.0.0.1:8899 https://api.ipify.org     # только российские выходы
curl -x http://session-cart42:x@127.0.0.1:8899 https://shop.example  # один и тот же прокси для этой сессии
```

Как у коммерческих ротирующих прокси, фильтр задаётся в **имени пользователя**: `country-XX`, `type-http|socks4|socks5` и `session-ИМЯ` — можно комбинировать. Для HTTPS сервер предпочитает прокси с проверенным TLS; если подходящего сейчас нет (нет выходов под фильтр вроде `country-ru`, или все выбыли), берутся остальные — проверка сертификата вашим клиентом всё равно поймает прокси, ломающий шифрование, поэтому не отключайте её. Три ошибки подряд — и прокси выбывает из ротации; каждые пять минут он перепроверяется и возвращается, если снова работает. По умолчанию сервер слушает только `127.0.0.1`; для доступа с других машин задайте пароль через `PROXY_SCRAPER_SERVE_PASSWORD`. Все опции — в [английском README](README.md#proxy-server).

**Живая панель:** `http://127.0.0.1:8899/__proxy-scraper/` в браузере показывает пул, долю успешных запросов, трафик, страны, лучшие прокси и последние соединения — обновляется каждые две секунды.

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

# один локальный адрес прокси для requests / httpx / Playwright / Scrapy; ротация под капотом
with ProxyRotator() as rotator:
    proxy = rotator.proxy_url()
```

Для свежей проверки из вашей сети есть `find_proxies()` и `check_proxies()`. Полное описание — в [английском README](README.md#from-python).

## Частые команды

```bash
proxy-scraper --want 50 --https-only                   # остановиться, когда найдено 50 HTTPS-прокси
proxy-scraper --types socks5 --anonymity elite         # только elite SOCKS5
proxy-scraper --country RU,KZ,BY --max-latency 1500    # нужные страны и потолок задержки
proxy-scraper --target www.google.com --want 20        # только прокси, которые доходят до целевого сайта
proxy-scraper --pick 5 --types socks5                  # 5 из ежечасного списка, без сканирования
proxy-scraper --export clash                           # конфиг Clash (также proxychains, sing-box, curl)
```

Все опции — в `proxy-scraper --help` или в [английском README](README.md#options).

<a id="mcp"></a>

## ИИ-агенты (MCP)

`proxy-scraper-mcp` — это [MCP](https://modelcontextprotocol.io)-сервер: Claude Code, Claude Desktop, Cursor, VS Code, Codex и любой другой MCP-клиент могут получать рабочие прокси и загружать через них страницы.

[![proxy-scraper MCP server on Glama](https://glama.ai/mcp/servers/maximilianfeix/proxy-scraper/badges/score.svg)](https://glama.ai/mcp/servers/maximilianfeix/proxy-scraper)

| Инструмент | Что делает |
|---|---|
| `get_proxies` | прокси из ежечасного списка в том виде, в каком их проверили в последнем запуске — фильтры по протоколу, стране, HTTPS, elite, дата-центру, стабильности, задержке |
| `check_proxies` | проверяет прокси из вашей сети — чтобы они работали там же, где и ваш код |
| `fetch_url` | загружает страницу через прокси из проверенного списка, при ошибке сам переключается и возвращает читаемый текст |

**Claude Code:**

```bash
claude mcp add proxy-scraper -- uvx --python ">=3.10" --from "proxy-scraper-cli[mcp]" proxy-scraper-mcp
```

**Claude Desktop, Cursor и большинство других клиентов** — добавьте в конфигурацию MCP:

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

Не хотите ставить Python? В Docker-образе уже всё есть: `"command": "docker"`, `"args": ["run", "-i", "--rm", "ghcr.io/maximilianfeix/proxy-scraper", "--mcp"]`. Сервер также есть в [официальном реестре MCP](https://registry.modelcontextprotocol.io) под именем `io.github.maximilianfeix/proxy-scraper`.

<a id="faq"></a>

## FAQ

**Кто держит бесплатные прокси — и можно ли ими пользоваться?**
Почти никто не поднимает бесплатный прокси специально для вас. В публичные списки обычно попадают: неправильно настроенные серверы с открытым портом; немного намеренно открытых прокси; заражённые компьютеры и IoT-устройства, о чём владельцы не знают; и ловушки — honeypot'ы, которые логируют трафик, и прокси, которые переписывают страницы. Это общие сведения, а не то, что измерил этот проект: проверка не видит, кто держит прокси и зачем. proxy-scraper не отличит заражённый домашний роутер от открытого офисного прокси, но отсекает то, что можно измерить: два независимых запроса должны показать один exit-IP, известная страница должна прийти байт в байт, а HTTPS засчитывается только с сертификатом, прошедшим проверку для тестового хоста. Подходит для публичных данных, просмотра сайта из другой страны, проверки своих блокировок и исследований. Никогда не отправляйте пароли, cookies, платёжные или личные данные через бесплатный прокси.

**Почему находит меньше прокси, чем обещают другие списки?**
Потому что остаются только прокси, прошедшие каждую проверку: два независимых запроса с одним и тем же чужим exit-IP и тестовая страница без изменений. В ежечасных запусках это около 1 % из 150 000 проверенных кандидатов. Они прошли проверку из той сети, которая их проверяла, и в тот момент.

**Почти ничего не проходит?**
Многие корпоративные, школьные и университетские сети блокируют прокси-соединения. Инструмент замечает долю успешных ниже 0,2 % и предупреждает — поможет другая сеть, например раздача с телефона.

**Работает ли в Windows?**
Да, в PowerShell и Windows Terminal. `uvloop` там недоступен и автоматически пропускается.

**Насколько свеж список?**
Он пересобирается примерно раз в час. Бесплатные прокси быстро появляются и исчезают — для всего важного запускайте `proxy-scraper --recheck` прямо перед использованием.

**Безопасны ли бесплатные прокси?**
Только для того, что не жалко потерять. Публичные прокси держат незнакомцы и могут читать всё незашифрованное. Не отправляйте через них пароли и личные данные — и пользуйтесь ими только там, где это разрешено.

## Участие

Issues и pull request приветствуются — на русском или английском. Есть [задачи для новичков](https://github.com/maximilianfeix/proxy-scraper/issues?q=is%3Aopen+label%3A%22good+first+issue%22). Если proxy-scraper экономит вам время, ⭐ поможет другим его найти.

## Отказ от ответственности

Этот инструмент только собирает публично опубликованные прокси и проверяет, работают ли они. За их использование отвечаете вы — соблюдайте условия сайтов, которые посещаете, и законы, которые к вам применяются. [Лицензия MIT](LICENSE).
