<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/banner-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/banner-light.svg">
  <img src="docs/banner-dark.svg" alt="proxy-scraper – proxies gratuitos que de verdad funcionan" width="100%">
</picture>

[![tests](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/tests.yml/badge.svg)](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/tests.yml)
[![Versión](https://img.shields.io/github/v/release/maximilianfeix/proxy-scraper?style=flat-square&color=D4F77A&labelColor=121113)](https://github.com/maximilianfeix/proxy-scraper/releases/latest)
[![Proxies activos](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Ftotal.json&style=flat-square&labelColor=121113)](#live-list)
[![PyPI](https://img.shields.io/pypi/v/proxy-scraper-cli?style=flat-square&color=D4F77A&labelColor=121113&label=pypi)](https://pypi.org/project/proxy-scraper-cli/)
[![Descargas](https://img.shields.io/pepy/dt/proxy-scraper-cli?style=flat-square&color=D4F77A&labelColor=121113&label=downloads)](https://pepy.tech/projects/proxy-scraper-cli)
[![Python](https://img.shields.io/badge/python-3.9–3.14-D4F77A?style=flat-square&labelColor=121113)](pyproject.toml)
[![Estrellas](https://img.shields.io/github/stars/maximilianfeix/proxy-scraper?style=flat-square&color=D4F77A&labelColor=121113)](https://github.com/maximilianfeix/proxy-scraper/stargazers)
[![Licencia](https://img.shields.io/badge/license-MIT-D4F77A?style=flat-square&labelColor=121113)](LICENSE)

<a href="https://maximilianfeix.github.io/proxy-scraper/"><img src="https://img.shields.io/badge/Browse_the_live_list-D4F77A?style=for-the-badge&labelColor=121113" alt="Explorar la lista en vivo"></a>
<a href="https://github.com/maximilianfeix/free-proxy-list"><img src="https://img.shields.io/badge/Just_the_lists-121113?style=for-the-badge" alt="Solo las listas: free-proxy-list"></a>
<a href="#install"><img src="https://img.shields.io/badge/Install-121113?style=for-the-badge" alt="Instalar"></a>
<a href="#from-python"><img src="https://img.shields.io/badge/Python_API-121113?style=for-the-badge" alt="API de Python"></a>
<a href="#mcp"><img src="https://img.shields.io/badge/MCP_server-121113?style=for-the-badge" alt="Servidor MCP para agentes de IA"></a>
<a href="bot/"><img src="https://img.shields.io/badge/Discord_bot-121113?style=for-the-badge" alt="Bot de Discord"></a>

[English](README.md) · [简体中文](README.zh-CN.md) · **Español**

[Instalación](#install) · [Lista en vivo](#live-list) · [Para agentes de IA](#mcp) · [Servidor proxy](#proxy-server) · [Cómo funciona](#how-it-works) · [Recetas](#recipes) · [Opciones](#options) · [Preguntas frecuentes](#faq)

</div>

---

Traducción del README en inglés; si algo no coincide, la versión inglesa es la de referencia.

La mayoría de las listas de proxies gratuitos están muertas en un 95 %, y buena parte del resto son honeypots o proxies que inyectan scripts en tus páginas. **proxy-scraper** recopila proxies públicos HTTP, SOCKS4 y SOCKS5 de más de 700 fuentes y se queda solo con los que superan todas las comprobaciones. Aprende en cada ejecución qué fuentes merecen la pena y puede convertir el resultado en un único proxy rotativo.

**En cifras:** en un solo día comprobó 3,6 millones de proxies gratuitos: el 1,1 % funcionaba, y más de la mitad de los que respondieron fallaron en una segunda petición. [Qué hay realmente por ahí →](docs/free-proxies-in-numbers.md)

**Usado por:** la lista horaria es una fuente integrada de [monosans/proxy-scraper-checker](https://github.com/monosans/proxy-scraper-checker) y [gfpcom/free-proxy-list](https://github.com/gfpcom/free-proxy-list).

**Pruébalo: sin instalar nada, en unos cinco segundos:**

```bash
uvx proxy-scraper-cli --pick 5 --types socks5     # 5 proxies comprobados

# o solo la lista simple
curl -s https://maximilianfeix.github.io/proxy-scraper/socks5.txt | head
```

`uvx` viene con [uv](https://docs.astral.sh/uv/); `pipx run proxy-scraper-cli --pick 5` hace lo mismo.

<div align="center">
<img src="docs/demo.svg" alt="Demo animada: el panel en vivo durante una comprobación, el informe, el asistente de configuración y la recopilación" width="880">
</div>

> **¿Quién gestiona los proxies gratuitos y es seguro usarlos?** Casi nadie lo hace a propósito: servidores mal configurados con un puerto abierto, unos pocos abiertos deliberadamente, máquinas infectadas y trampas que registran o reescriben tu tráfico. Por eso cada proxy de aquí tiene que superar [cinco comprobaciones](#how-it-works), y por eso sirven para datos públicos y pruebas, nunca para inicios de sesión, pagos ni nada personal. [Más sobre su origen →](#who-runs-free-proxies)

<details>
<summary><b>Tabla de contenidos</b></summary>

- [Instalación](#install)
- [Lista de proxies en vivo](#live-list)
- [Para agentes de IA (MCP)](#mcp)
- [Características](#features) · [¿Por qué no descargar simplemente una lista?](#why-not-just-download-a-list)
- [Ejemplos](#examples)
- [Recetas](#recipes)
- [Servidor proxy rotativo](#proxy-server)
- [Bot de Discord y Telegram](#discord-bot)
- [Cómo funciona](#how-it-works)
- [Salida](#output)
- [Opciones](#options)
- [GitHub Actions](#github-actions)
- [Preguntas frecuentes](#faq)
- [Hoja de ruta](#roadmap) · [Contribuir](#contributing) · [Comunidad](#community) · [Agradecimientos](#acknowledgements)

</details>

<a id="install"></a>

## Instalación

**Con [pipx](https://pipx.pypa.io/)** (recomendado: te da un comando `proxy-scraper` en su propio entorno):

```bash
pipx install proxy-scraper-cli
proxy-scraper
```

El paquete se llama `proxy-scraper-cli` en PyPI (el nombre simple ya está ocupado); el comando es `proxy-scraper`.

**Con [Homebrew](https://brew.sh)** en macOS y Linux:

```bash
brew install maximilianfeix/tap/proxy-scraper
```

La fórmula sigue cada versión en aproximadamente un día.

<details>
<summary><b>Otras formas: Docker, pip, un bucle de eventos más rápido o directamente desde el repositorio</b></summary>
<br>

```bash
# Docker: el estado aprendido y los resultados se quedan en dos carpetas junto a ti
mkdir -p proxy-data results
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/proxy-data:/data" -v "$PWD/results:/work/results" \
  ghcr.io/maximilianfeix/proxy-scraper --want 50 --https-only

# pip en el entorno actual
pip install proxy-scraper-cli

# opcional: bucle de eventos más rápido en macOS/Linux
pipx install "proxy-scraper-cli[fast]"

# la última versión de main en lugar de la última release
pipx install git+https://github.com/maximilianfeix/proxy-scraper.git

# sin instalar nada
git clone https://github.com/maximilianfeix/proxy-scraper.git
cd proxy-scraper
pip install -r requirements.txt
python3 proxy_scraper.py
```

Cada [release](https://github.com/maximilianfeix/proxy-scraper/releases/latest) incluye además un wheel que puedes instalar con `pip install <file>.whl`, y una imagen multiarquitectura (amd64/arm64) en `ghcr.io`. En el contenedor el asistente nunca aparece: se ejecuta directamente. Para el servidor proxy usa `--serve --serve-host 0.0.0.0` con `-p 127.0.0.1:8899:8899`, de modo que el puerto solo esté abierto en tu propia máquina.

Autocompletado con tabulador para bash, zsh, fish y PowerShell:

```bash
eval "$(proxy-scraper --completion zsh)"     # en ~/.zshrc (después de compinit); lo mismo para bash en ~/.bashrc
proxy-scraper --completion fish > ~/.config/fish/completions/proxy-scraper.fish
proxy-scraper --completion powershell | Out-String | Invoke-Expression   # en $PROFILE
```

Una vez instalado, el estado aprendido vive en la carpeta de datos de tu usuario (`~/Library/Application Support/proxy-scraper`, `%LOCALAPPDATA%\proxy-scraper` o `~/.local/share/proxy-scraper`; se puede cambiar con `PROXY_SCRAPER_HOME`) y los resultados van a `./results`. Si se ejecuta desde un clon, ambos se quedan dentro del proyecto. Tras la segunda ejecución que encuentre proxies, pide una sola vez una estrella en GitHub; `PROXY_SCRAPER_NO_STAR_HINT=1` lo desactiva (nunca aparece en CI).

</details>

Si se inicia sin argumentos, un asistente te pregunta qué estás buscando:

<div align="center">
<img src="docs/wizard.svg" alt="Asistente de configuración" width="760">
</div>

| Preajuste | Qué hace |
|---|---|
| **Encontrar todo** | todos los protocolos, máximo rendimiento |
| **Navegación y web** | HTTP + SOCKS5, compatibles con HTTPS, al menos anónimos, menos de 3 s |
| **Máximo anonimato** | solo SOCKS5 elite con HTTPS |
| **Rápido y estable** | solo proxies de menos de 1 s |
| **Unos pocos ahora mismo** | se detiene tras 25 aciertos |
| **Volver a comprobar los últimos aciertos** | sin recopilar, tarda segundos |
| **Servidor proxy al instante** | vuelve a comprobar los últimos aciertos y luego los sirve en :8899 |
| **Igual que la última vez** | tu elección anterior |
| **Personalizado …** | protocolos, países, anonimato, HTTPS, sitio objetivo, latencia, cantidad, modo de comprobación |

Teclas: <kbd>↑</kbd><kbd>↓</kbd> seleccionar · <kbd>Espacio</kbd> marcar/desmarcar · <kbd>1</kbd>–<kbd>9</kbd> saltar · <kbd>Enter</kbd> siguiente · <kbd>Esc</kbd> atrás · <kbd>q</kbd> salir. En scripts y tareas cron el asistente nunca aparece: pasa opciones o `-y`.

<a id="live-list"></a>

## Lista de proxies en vivo

¿No quieres escanear tú mismo? Cada hora **GitHub Actions** ejecuta la herramienta y publica los aciertos en la rama [`proxy-list`](../../tree/proxy-list): cada entrada funcionó en la última ejecución y van ordenadas de mejor a peor: los rápidos que probablemente sigan activos aparecen arriba.

> **¿Solo quieres las listas?** También viven en un repositorio propio, **[maximilianfeix/free-proxy-list](https://github.com/maximilianfeix/free-proxy-list)**: una lista por protocolo, por país y por sitio, actualizadas cada hora, con las cifras de la última ejecución en la portada. Sigue el repositorio o dale una estrella para tenerlo a mano. Otras herramientas también lo consultan: [monosans/proxy-scraper-checker](https://github.com/monosans/proxy-scraper-checker) y [gfpcom/free-proxy-list](https://github.com/gfpcom/free-proxy-list) lo usan como fuente integrada.

<a href="https://maximilianfeix.github.io/proxy-scraper/"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://maximilianfeix.github.io/proxy-scraper/chart-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://maximilianfeix.github.io/proxy-scraper/chart-light.svg">
  <img src="https://maximilianfeix.github.io/proxy-scraper/chart-dark.svg" alt="Proxies que funcionan en los últimos días, apilados por protocolo; se redibuja en cada ejecución" width="100%">
</picture></a>

**→ [Explórala en el sitio web](https://maximilianfeix.github.io/proxy-scraper/)**: busca, filtra por tipo, país, HTTPS, proveedor y latencia, mira cuánto tiempo lleva activo cada proxy y con qué frecuencia estuvo en la lista esta semana, y copia o descarga exactamente los proxies que necesitas.

Cada protocolo y cada país tiene además su propia página con una descarga simple, p. ej. [SOCKS5](https://maximilianfeix.github.io/proxy-scraper/socks5/) o [Alemania](https://maximilianfeix.github.io/proxy-scraper/country/de/) (`country/de/proxies.txt`).

<div align="center"><a href="https://maximilianfeix.github.io/proxy-scraper/"><img src="docs/website.png" alt="El sitio web de la lista en vivo" width="860"></a></div>

<div align="center">

[![Proxies](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Ftotal.json&style=for-the-badge)](../../tree/proxy-list)
[![HTTP](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Fhttp.json&style=for-the-badge)](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/http.txt)
[![SOCKS4](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Fsocks4.json&style=for-the-badge)](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks4.txt)
[![SOCKS5](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Fsocks5.json&style=for-the-badge)](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks5.txt)
[![Actualizado](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Fupdated.json&style=for-the-badge)](../../actions/workflows/proxy-list.yml)

</div>

| Lista | Formato | Enlace |
|---|---|---|
| Todos | `socks5://1.2.3.4:1080` | [all.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/all.txt) |
| HTTP · SOCKS4 · SOCKS5 | `1.2.3.4:8080` | [http.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/http.txt) · [socks4.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks4.txt) · [socks5.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks5.txt) |
| Solo compatibles con HTTPS | `type://ip:port` | [https.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/https.txt) |
| Solo elite | `type://ip:port` | [elite.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/elite.txt) |
| Llegan a Google · Reddit · Amazon · Instagram · TikTok · Discord (sin captcha ni bloqueo en la última ejecución) | `type://ip:port` | [google.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/works-with/google.txt) · [reddit.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/works-with/reddit.txt) · [amazon.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/works-with/amazon.txt) · [instagram.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/works-with/instagram.txt) · [tiktok.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/works-with/tiktok.txt) · [discord.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/works-with/discord.txt) |
| Estables, presentes en el 90 % o más de las ejecuciones de esta semana | `type://ip:port` | [stable.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/stable.txt) |
| Con todos los detalles | latencia, país, HTTPS, anonimato, IP de salida, uptime, sitios | [proxies.json](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/proxies.json) · [proxies.csv](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/proxies.csv) |

<a href="https://maximilianfeix.github.io/proxy-scraper/"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://maximilianfeix.github.io/proxy-scraper/countries-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://maximilianfeix.github.io/proxy-scraper/countries-light.svg">
  <img src="https://maximilianfeix.github.io/proxy-scraper/countries-dark.svg" alt="Países con más proxies funcionando ahora mismo" width="100%">
</picture></a>

```bash
curl -s https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks5.txt | head
```

**Con el tiempo:** cada día el `proxies.json` de la primera ejecución se conserva de forma permanente como un recurso comprimido en gzip de la release de ese año, como [snapshots-2026](../../releases/tag/snapshots-2026): `proxies-2026-09-28.json.gz` y así sucesivamente, para quien quiera estudiar los proxies gratuitos a lo largo de semanas y meses.

Cada archivo está también en GitHub Pages, que va detrás de una CDN, no tiene límite de peticiones como raw.githubusercontent y envía cabeceras CORS, así que funciona directamente desde el navegador: `https://maximilianfeix.github.io/proxy-scraper/socks5.txt`. [jsDelivr](https://cdn.jsdelivr.net/gh/maximilianfeix/proxy-scraper@proxy-list/) también sirve, pero puede ir con unas horas de retraso.

O deja que la herramienta parta de ella: `proxy-scraper --recheck live` descarga la lista y la vuelve a comprobar desde **tu** red: unos 30 segundos en lugar de un escaneo completo (desde aquí funcionaron 517 de 1.169). Con `--serve` tienes un proxy rotativo en menos de un minuto.

<a id="mcp"></a>

## Para agentes de IA (MCP)

<!-- mcp-name: io.github.maximilianfeix/proxy-scraper -->

`proxy-scraper-mcp` es un servidor [MCP](https://modelcontextprotocol.io): Claude Code, Claude Desktop, Cursor, VS Code, Codex y cualquier otro cliente MCP pueden pedir proxies que funcionen y cargar páginas a través de ellos.

| Herramienta | Qué hace |
|---|---|
| `get_proxies` | proxies que funcionan ahora mismo, de la lista horaria: filtra por protocolo, país, HTTPS, elite, sin datacenter, fuera de listas negras, estables, uptime, latencia, y por si llegan a Google/Reddit/Amazon |
| `check_proxies` | comprueba proxies desde tu propia red, para que funcionen desde donde se ejecuta tu código (30–90 s, informa del progreso) |
| `fetch_url` | carga una página a través de un proxy verificado, cambia de proxy por sí solo cuando uno falla y devuelve texto legible; HTTPS solo a través de proxies con TLS verificado |

Cosas que puedes pedirle a tu agente: *"Carga bbc.com/news tal como se ve desde el Reino Unido"*, *"Dame 5 proxies SOCKS5 de Alemania que no estén en un datacenter"*, *"Comprueba cuáles de estos sitios bloquean los proxies gratuitos"*.

Requiere [uv](https://docs.astral.sh/uv/), que descarga por sí mismo un Python adecuado si el tuyo es anterior a la 3.10. **Claude Code:**

```bash
claude mcp add proxy-scraper -- uvx --python ">=3.10" --from "proxy-scraper-cli[mcp]" proxy-scraper-mcp
```

**Claude Desktop, Cursor y la mayoría de los demás clientes**: añade esto a la configuración de MCP (Claude Desktop: Settings → Developer → Edit Config, Cursor: `~/.cursor/mcp.json`):

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

<details>
<summary><b>VS Code, Codex, Docker o sin uv</b></summary>

**VS Code** – `.vscode/mcp.json`:

```json
{
  "servers": {
    "proxy-scraper": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--python", ">=3.10", "--from", "proxy-scraper-cli[mcp]", "proxy-scraper-mcp"]
    }
  }
}
```

**Codex** – `~/.codex/config.toml`:

```toml
[mcp_servers.proxy-scraper]
command = "uvx"
args = ["--python", ">=3.10", "--from", "proxy-scraper-cli[mcp]", "proxy-scraper-mcp"]
```

**Sin uv:** `pipx install --python python3.12 "proxy-scraper-cli[mcp]"` (cualquier Python 3.10+), y luego usa `proxy-scraper-mcp` como comando.

**Docker** – no hace falta Python, la imagen lo trae todo:

```json
{
  "mcpServers": {
    "proxy-scraper": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "ghcr.io/maximilianfeix/proxy-scraper", "--mcp"]
    }
  }
}
```

También está en el [registro oficial de MCP](https://registry.modelcontextprotocol.io) como `io.github.maximilianfeix/proxy-scraper`, así que los clientes que exploran el registro pueden instalarlo desde ahí.

</details>

El servidor les dice a los agentes lo mismo que te dice a ti: los proxies gratuitos los gestionan desconocidos, así que nada de inicios de sesión, cookies ni datos personales a través de ellos. Se rechazan las direcciones locales y privadas, y los resultados van a la carpeta de datos de proxy-scraper, no al proyecto en el que estás trabajando.

<a id="features"></a>

## Características

<table>
<tr>
<td width="50%" valign="top">

**Asistente de configuración**<br>
Si se inicia sin argumentos, la herramienta te pregunta qué necesitas con las teclas de flecha: un preajuste o paso a paso. Al final muestra la línea de comandos equivalente.

</td>
<td width="50%" valign="top">

**Rápido**<br>
Más de 700 fuentes descargadas en paralelo, listas grandes analizadas en todos los núcleos de la CPU, handshakes HTTP/SOCKS escritos a mano directamente sobre `asyncio` con más de 2000 comprobaciones a la vez.

</td>
</tr>
<tr>
<td valign="top">

**Verificación real**<br>
Cada acierto tiene que descargar dos páginas independientes: eso elimina los **honeypots** que solo responden a las peticiones de comprobación; en más de 3,6 millones de comprobaciones, el 54 % de los proxies que respondieron a la primera petición fallaron en la segunda. Una tercera petición detecta los proxies que **manipulan el contenido**: aproximadamente uno de cada 40 proxies que funcionaban modificó una página conocida, normalmente inyectando un script ([las cifras](docs/free-proxies-in-numbers.md)). Además: HTTPS a través de un túnel con **TLS verificado**, nivel de anonimato *elite / anonymous / transparent* y el país de la IP de salida.

</td>
<td valign="top">

**Aprende en cada ejecución**<br>
Tasa de aciertos por fuente, historial de proxies que funcionan, eliminación automática de listas muertas o desactualizadas. Con `-l 5000` obtienes los *mejores* 5000 candidatos, no unos cualquiera.

</td>
</tr>
<tr>
<td valign="top">

**Encuentra fuentes nuevas por sí mismo**<br>
Busca en GitHub listas de proxies mantenidas activamente y lee listas de fuentes mantenidas por otros. Se detectan las granjas de clones spam y los simples espejos.

</td>
<td valign="top">

**Filtros y sitios objetivo**<br>
Con `--target google.com` un proxy solo cuenta si realmente llega al sitio: muchos proxies públicos están bloqueados por Google, Discord y compañía. Filtra por país, HTTPS, anonimato y latencia, y detente con `--want 50` en cuanto se hayan encontrado suficientes proxies que cumplan. Los filtros incluso aceleran el proceso: con `--max-latency 1000` los proxies lentos se descartan tras 1 s en lugar de 8 s.

</td>
</tr>
<tr>
<td valign="top">

**Panel en vivo**<br>
Gráfico de velocidad, histograma de latencia, protocolos, países y los últimos aciertos en tiempo real. <kbd>Ctrl</kbd>+<kbd>C</kbd> detiene la ejecución en cualquier momento y lo guarda todo.

</td>
<td valign="top">

**Servidor proxy rotativo**<br>
`--serve` convierte los aciertos en un proxy local que envía cada conexión por uno distinto, con conmutación automática cuando uno se cuelga.

</td>
</tr>
<tr>
<td valign="top">

**Funciona en todas partes**<br>
macOS, Linux y Windows, Python 3.9 a 3.14. Solo dos dependencias: `rich` y `certifi`. Incluso se da cuenta cuando un firewall bloquea los proxies.

</td>
<td valign="top">

**Probado a fondo**<br>
Más de 760 tests se ejecutan sin conexión contra mini proxies y honeypots reales en `localhost`, en Linux, macOS y Windows con Python 3.9, 3.11, 3.13 y 3.14.

</td>
</tr>
</table>

<a id="why-not-just-download-a-list"></a>

### ¿Por qué no descargar simplemente una lista?

| | Repositorio típico de listas de proxies | **proxy-scraper** |
|---|:---:|:---:|
| Proxies comprobados justo antes de usarlos | ❌ | ✅ |
| Honeypots que simulan una comprobación correcta, filtrados | ❌ | ✅ |
| Proxies que inyectan scripts o anuncios, filtrados | ❌ | ✅ |
| HTTPS probado con TLS verificado | rara vez | ✅ |
| Nivel de anonimato y país por proxy | a veces | ✅ |
| Solo proxies que llegan a *tu* sitio objetivo | ❌ | ✅ `--target` |
| Aprende qué fuentes merecen la pena | ❌ | ✅ |
| Utilizable como un único proxy rotativo | ❌ | ✅ `--serve` |
| API para obtener un proxy (compatible con proxy_pool) | ❌ | ✅ [`/get`](#pool-api) |
| Lista lista para usar sin ejecutar nada | ✅ | ✅ [lista en vivo](#live-list) |

<a id="examples"></a>

## Ejemplos

```bash
# 50 proxies que soportan HTTPS, y luego parar
proxy-scraper --want 50 --https-only

# solo Alemania, Austria y Suiza, los 20.000 candidatos más prometedores
proxy-scraper --country DE,AT,CH -l 20000

# proxies SOCKS5 elite rápidos
proxy-scraper --types socks5 --anonymity elite --max-latency 1500

# 20 proxies que de verdad llegan a Google Y a Discord
proxy-scraper --target google.com --target discord.com --want 20

# volver a comprobar solo los últimos aciertos (más el historial): tarda segundos
proxy-scraper --recheck

# asistente con valores por defecto: conserva lo que ya pasaste
proxy-scraper -i --country DE

# ¿qué fuentes aportan más?
proxy-scraper --list-sources
```

¿Lo ejecutas desde un clon? Sustituye `proxy-scraper` por `python3 proxy_scraper.py`.

<a id="from-python"></a>

### Desde Python

```python
from proxyscraper import check_proxies, find_proxies

if __name__ == "__main__":  # necesario en macOS/Windows: el analizador usa un pool de procesos
    for p in find_proxies(want=20, https=True, countries=["DE", "NL"], no_datacenter=True):
        print(p.url, p.latency, p.country, p.org)

    alive = check_proxies(["socks5://1.2.3.4:1080", "5.6.7.8:3128"])  # tu propia lista
```

La misma ejecución que en la línea de comandos (fuentes, aprendizaje, todas las comprobaciones, archivos de resultados), solo que sin salida por terminal. Cada resultado tiene `url`, `latency`, `exit_ip`, `https`, `anonymity`, `country`, `asn`, `org` y `hosting`. Existe una versión asíncrona de ambas (`find_proxies_async`, `check_proxies_async`).

¿No necesitas un escaneo nuevo? `live_proxies` toma la [lista en vivo](#live-list): sin comprobaciones, una descarga, listo en aproximadamente un segundo:

```python
import itertools, requests
from proxyscraper import live_proxies

proxies = live_proxies(types=["socks5"], https=True, min_uptime=90)  # los fiables de esta semana
pool = itertools.cycle(p.url for p in proxies)
r = requests.get("https://api.ipify.org", proxies={"https": next(pool)}, timeout=15)  # pip install "requests[socks]"
```

Mismos filtros que `find_proxies`, más `min_uptime`, `works_on` (`["google"]`, `"reddit"`, `"amazon"`, `"instagram"`, `"tiktok"`, `"discord"`) y `limit`. Cada resultado tiene además `uptime_24h`, `uptime_7d`, `first_seen`, `up_for_hours` y `sites`.

O deja que la biblioteca se encargue de los reintentos: `ProxyRotator` carga una URL a través de la lista y pasa al siguiente proxy cuando uno falla; HTTPS solo a través de proxies con TLS verificado.

```python
from proxyscraper import ProxyRotator

with ProxyRotator(country="DE") as rotator:
    r = rotator.get("https://httpbin.org/ip")
    print(r.status, r.text, "via", r.via)
```

Normalmente tarda unos segundos; cuando caen muchos proxies seguidos puede tardar un minuto (`timeout=` es por intento). Existe `aget()` con `async with` para código asyncio.

¿Ya usas requests, httpx, Playwright o Scrapy? `proxy_url()` te da una única dirección de proxy local que rota entre bastidores: cada conexión sale por otro proxy de la lista, los mejores primero, y se saltan los que están caídos:

```python
import requests
from proxyscraper import ProxyRotator

with ProxyRotator(country="DE") as rotator:
    proxy = rotator.proxy_url()          # http://country-de:…@127.0.0.1:…
    requests.get("https://api.ipify.org", proxies={"http": proxy, "https": proxy})
    # httpx.Client(proxy=proxy) · scrapy: meta={"proxy": proxy} · curl -x "$proxy"
    # Playwright quiere las credenciales por separado: chromium.launch(proxy=rotator.playwright_proxy())
```

Se ejecuta en 127.0.0.1 con una contraseña aleatoria, adopta por sí solo cada nueva lista horaria y se detiene al terminar el bloque `with`.

<a id="proxy-server"></a>

## Servidor proxy rotativo

Una lista está bien, pero normalmente lo que quieres es introducir **un** proxy que siempre funcione:

```bash
proxy-scraper --recheck --serve     # vuelve a comprobar los últimos aciertos y arranca: tarda segundos
```

```bash
curl -x http://127.0.0.1:8899 https://api.ipify.org              # una IP distinta cada vez
curl -x socks5h://127.0.0.1:8899 https://api.ipify.org           # SOCKS5 en el mismo puerto
curl -x http://country-de:x@127.0.0.1:8899 https://api.ipify.org # solo salidas alemanas
curl -x http://session-cart42:x@127.0.0.1:8899 https://shop.example  # el mismo proxy durante esta sesión
curl http://127.0.0.1:8899/__proxy-scraper/status                # pool y contadores en JSON
curl http://127.0.0.1:8899/__proxy-scraper/metrics               # lo mismo para Prometheus/Grafana
```

Como los proxies rotativos comerciales, el **nombre de usuario** lleva lo que quieres: `country-XX`, `type-http|socks4|socks5` y `session-NAME`, combinables (`country-us-type-socks5-session-a`). Funciona con HTTP (`Proxy-Authorization`) y SOCKS5 (autenticación de usuario/contraseña). Por defecto la contraseña se ignora y el servidor solo escucha en `127.0.0.1`.

Para acceder desde otras máquinas, ponle una contraseña: todos los clientes tendrán que enviarla, tanto por HTTP como por SOCKS5, y la página de estado la pedirá como autenticación Basic:

```bash
export PROXY_SCRAPER_SERVE_PASSWORD=$(openssl rand -hex 16)   # la variable de entorno la mantiene fuera de `ps`
proxy-scraper --recheck --serve --serve-host 0.0.0.0
curl -x "http://country-de:$PROXY_SCRAPER_SERVE_PASSWORD@your-server:8899" https://api.ipify.org
```

Sin contraseña, `--serve-host` significa que **cualquiera que llegue al puerto puede usarlo**. El [`compose.yaml`](compose.yaml) incluido inicia el servidor en Docker a partir de la lista en vivo, con contraseña, comprobación de estado y el estado aprendido en un volumen: pon `PROXY_PASSWORD=…` en `.env` y luego ejecuta `docker compose up -d`.

| Opción | Qué hace |
|---|---|
| `--rotate weighted` | por defecto: los proxies rápidos y probados salen más a menudo, y todos tienen su oportunidad |
| `--rotate random` / `round-robin` | de forma uniforme, al azar o por turnos |
| `--rotate fastest` | siempre el más rápido que no esté ocupado |
| `--sticky 300` | el mismo sitio conserva su proxy durante 5 minutos (inicios de sesión, carritos) |

- cada conexión pasa por un proxy distinto (salvo con sticky); se prefieren los rápidos y probados
- `CONNECT` para HTTPS y peticiones HTTP simples; detrás pueden estar proxies HTTP, SOCKS4 y SOCKS5 (SOCKS5 con DNS a través del proxy)
- HTTPS prefiere los proxies que pasaron la prueba con **TLS verificado**; cuando ahora mismo no hay ninguno que encaje (ninguno cumple una petición como `country-de`, o todos han salido de la rotación) usa los demás; la comprobación de certificados de tu propio cliente sigue detectando un proxy que rompe el cifrado, así que déjala activada
- si un proxy se queda en silencio dentro del túnel o devuelve una página de error en lugar de TLS, el mismo primer paquete pasa discretamente al siguiente
- tres fallos seguidos y un proxy sale de la rotación; cada 5 minutos se vuelven a comprobar y regresan si vuelven a funcionar
- `--serve-refill 6` comprueba proxies nuevos cada 6 horas en segundo plano (la lista en vivo con `--recheck live`, o si no la última ejecución + historial) con las mismas comprobaciones y filtros, y añade los aciertos: un servidor que lleva días en marcha no se queda sin proxies
- escucha solo en `127.0.0.1` (salvo que `--serve-host` diga otra cosa), opcionalmente con contraseña; vista en vivo con peticiones, tasa de éxito, pool y las últimas conexiones

En las pruebas: 20 de 20 peticiones HTTPS tuvieron éxito, con más de 15 IP de salida distintas. En el asistente esto es **Servidor proxy al instante**.

**Panel en vivo:** abre `http://127.0.0.1:8899/__proxy-scraper/` en un navegador: el pool, la tasa de éxito, el tráfico, un gráfico en vivo de peticiones, países, los mejores proxies y las últimas conexiones, actualizado cada dos segundos. No necesita nada de internet, y `--serve-password` lo protege igual que al resto.

<div align="center"><img src="docs/dashboard-live.png" alt="El panel en vivo del servidor proxy rotativo: proxies utilizables, tasa de éxito, peticiones por segundo, países y las últimas conexiones" width="860"></div>

<a id="pool-api"></a>

### API del pool de proxies

Algunos programas quieren una *dirección* de proxy, no un proxy: para pasársela a un navegador, a un worker o a una cola. El mismo puerto responde a peticiones HTTP simples con una:

```bash
curl http://127.0.0.1:8899/get                          # un proxy en JSON, elegido como se elegiría para una conexión
curl "http://127.0.0.1:8899/get?country=DE&https=1&format=txt"   # → http://203.0.113.7:8080
curl "http://127.0.0.1:8899/all?protocol=socks5&limit=20"        # los 20 mejores proxies SOCKS5
curl "http://127.0.0.1:8899/report?proxy=203.0.113.7:8080&ok=0"  # te falló: a la tercera sale del pool
```

| Endpoint | Qué hace |
|---|---|
| `/get` | un proxy, elegido según la estrategia de `--rotate` |
| `/pop` | como `/get`, y el proxy sale del pool |
| `/all` | todos los proxies utilizables, los mejores primero (`limit=N`) |
| `/count` | totales por tipo y país |
| `/delete?proxy=IP:PORT` | elimina un proxy |
| `/report?proxy=IP:PORT&ok=0` | comentarios sobre el resultado de tus propias peticiones |

Los filtros funcionan en `/get`, `/pop` y `/all`: `country=DE,AT`, `protocol=socks5`, `https=1`, `anonymity=elite`, `max_latency=1500`, y `format=txt` para URLs simples. Con `--serve-password` la API la pide como autenticación Basic, igual que la página de estado.

**¿Vienes de [jhao104/proxy_pool](https://github.com/jhao104/proxy_pool)?** Los endpoints, `type=https` y los campos JSON (`proxy`, `https`, `region`, `anonymous`, `check_count`, `fail_count`, …) son los mismos, así que apunta tu código al puerto 8899 y seguirá funcionando: sin Redis, y con proxies que han superado las comprobaciones de honeypot, manipulación y TLS:

```python
import requests
proxy = requests.get("http://127.0.0.1:8899/get?type=https").json()["url"]   # p. ej. socks5://…, con el tipo incluido
requests.get("https://example.com", proxies={"http": proxy, "https": proxy})
```

<a id="discord-bot"></a>

## Bot de Discord y Telegram

La lista en vivo también puede venir a ti: [`bot/`](bot/) es un bot de Discord que publica cada ejecución en un servidor: un resumen con los proxies más rápidos, las listas completas por protocolo como archivos y comandos slash como `/proxies type:socks5 country:DE https:true`. Configura sus propios canales de solo lectura cuando lo invitas, y una GitHub Action lo despliega en un servidor como servicio de systemd. El mismo proceso responde también en Telegram: `/proxy de socks5` para un proxy con una línea de curl, `/proxies 10 us https` para una lista corta. La configuración está en [bot/README.md](bot/README.md).

<a id="how-it-works"></a>

## Cómo funciona

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/checks-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/checks-light.svg">
  <img src="docs/checks-dark.svg" alt="Las cinco comprobaciones: más de 700 listas, un handshake real, dos sitios con una misma IP, nada inyectado, los detalles" width="100%">
</picture>


```mermaid
flowchart LR
    A[sources.json<br/>metalistas<br/>descubrimiento en GitHub] --> B[Descargar y analizar<br/>en paralelo en todos los núcleos]
    B --> C[Priorizar<br/>historial → buenas fuentes → resto]
    C --> D[Comprobar<br/>HTTP · SOCKS4 · SOCKS5]
    D --> E[Detalles<br/>HTTPS · anonimato · país]
    E --> F[results/]
    D -. tasa de aciertos por fuente .-> G[(estado aprendido)]
    G -. siguiente ejecución .-> C
```

1. **Fuentes**: la lista curada en [`sources.json`](proxyscraper/sources.json), metafuentes (otros proyectos que mantienen listas de fuentes de proxies) y, una vez al día, una búsqueda en GitHub de repositorios mantenidos activamente. Cada búsqueda suma a lo que encontraron las anteriores; una lista que la búsqueda no ha visto en tres semanas se descarta.
2. **Recopilar**: se reconocen texto simple, tablas HTML, APIs JSON y líneas `type://ip:port`; se descartan los rangos de direcciones privadas y reservadas. Las listas que no han cambiado desde la última ejecución responden `304` y salen de una caché local: una segunda ejecución justo después de la primera descarga 0 MB en lugar de ~160 MB.
3. **Priorizar**: primero los proxies que se sabe que funcionan, luego según la tasa de aciertos aprendida de sus fuentes.
4. **Comprobar**: cada proxy tiene que obtener su IP de salida de un objetivo de comprobación (`checkip.amazonaws.com`, con `ifconfig.me`, `ipinfo.io`, `wtfismyip.com` e `ident.me` como reserva; ninguno detrás de Cloudflare) y devolver una IP válida y *ajena*. Si el objetivo se cae a mitad de ejecución, la herramienta cambia de objetivo y vuelve a comprobar los proxies afectados, para que las estadísticas no aprendan de una caída. Quien deje pasar tu propia IP queda fuera. Después llega la **confirmación** mediante `httpbin.org`: los proxies falsos que solo responden a la primera comprobación con “200 + IP” fallan aquí. Por último, una página HTML estática tiene que llegar byte por byte igual que sin proxy; quien inyecte anuncios o scripts queda fuera.
5. **Países y proveedores**: se consultan sin conexión en las bases de datos gratuitas de DB-IP, incluido el proveedor (ASN) y si probablemente es un datacenter (lo son alrededor del 45 % de los proxies que funcionan) (se descargan una vez al mes, ~2 µs por consulta); a ip-api.com solo se le pregunta por las pocas direcciones que no conoce.
6. **Listas negras**: una consulta DNS por IP de salida contra SpamCop, en caché durante la ejecución: alrededor del 29 % de los proxies que funcionan salen por una IP listada, y los sitios que usan esa lista les muestran captchas o los bloquean. `--no-blocklisted` los descarta. Si SpamCop rechaza tu resolutor DNS (los grandes resolutores públicos lo son), la consulta se omite en lugar de adivinar.
7. **Aprender**: se guardan las tasas de aciertos y el historial. Las fuentes sin aciertos, con el contenido sin cambios durante una semana o permanentemente inaccesibles se omiten.

<details>
<summary><b>📸 Mira el panel en vivo y el informe final</b></summary>
<br>
<div align="center">
<img src="docs/dashboard.svg" alt="Panel en vivo durante la comprobación" width="860">
<br><br>
<img src="docs/summary.svg" alt="Informe final tras una ejecución" width="860">
</div>
</details>

### Tus propias listas

```bash
proxy-scraper --source https://example.com/my-list.txt --source socks5=./socks.txt   # además de las más de 700 fuentes
proxy-scraper --only-sources --source bought.txt --want 50                            # solo las tuyas
```

Sirve cualquier texto con `ip:port`; las líneas como `socks5://user:pass@host:port` conservan su tipo, y las simples se prueban como HTTP y SOCKS5 salvo que escribas `http=…`. Para credenciales escritas como las exportan muchas listas de pago, `ip:port:user:pass`, usa `--recheck bought.txt` o pasa la lista por tubería a `--recheck -`; las fuentes dejan esa forma sin tocar, ya que listas como `ip:port:US:elite` tienen el mismo aspecto.

<a id="output"></a>

## Salida

Cada ejecución tiene su propia carpeta; `results/latest.txt` siempre indica la más reciente (en macOS/Linux existe además el enlace simbólico `results/latest`):

```
results/2026-09-24_18-42-07/
├── all.txt        socks5://203.0.113.10:1080   (el más rápido primero)
├── http.txt       203.0.113.20:8080            (listas ip:port simples por tipo)
├── socks4.txt
├── socks5.txt
├── proxies.json   latencia, país, HTTPS, anonimato, IP de salida
└── proxies.csv
```

<a id="recipes"></a>

## Recetas

**Usa el proxy más rápido de la última ejecución**: los proxies gratuitos mueren rápido, así que haz primero `--recheck` si la ejecución tiene más de unos minutos

```bash
proxy-scraper --recheck -y
curl -x "$(head -1 results/latest/all.txt)" http://api.ipify.org
```

Para HTTPS, elige un proxy con `"https": true` en `proxies.json`, como hace el ejemplo de Python que sigue.

**Python `requests`** (`pip install "requests[socks]"` para SOCKS)

```python
import json
from pathlib import Path

import requests

run = Path("results") / Path("results/latest.txt").read_text().strip()   # funciona en todos los sistemas operativos
proxies = json.loads((run / "proxies.json").read_text())   # el más rápido primero

for p in proxies:
    if not p["https"]:
        continue
    try:
        r = requests.get("https://api.ipify.org", proxies={"http": p["url"], "https": p["url"]}, timeout=8)
        print(p["url"], "→", r.text)
        break
    except requests.RequestException:
        continue  # los proxies gratuitos van y vienen: simplemente toma el siguiente
```

**httpx** (`pip install "httpx[socks]"`): directamente desde la lista horaria, sin escaneo

```python
import httpx
from proxyscraper import live_proxies

for p in live_proxies(types=["http", "socks5"], https=True, min_uptime=90, limit=10):  # httpx no soporta SOCKS4
    try:
        with httpx.Client(proxy=p.url, timeout=10) as client:
            print(p.url, "→", client.get("https://api.ipify.org").text)
        break
    except httpx.HTTPError:
        continue  # el siguiente
```

**aiohttp** (`pip install aiohttp aiohttp-socks`: aiohttp por sí solo no soporta SOCKS)

```python
import asyncio

import aiohttp
from aiohttp_socks import ProxyConnector, ProxyError
from proxyscraper import live_proxies_async


async def main():
    for p in await live_proxies_async(https=True, min_uptime=90, limit=10):
        try:
            async with aiohttp.ClientSession(connector=ProxyConnector.from_url(p.url)) as session:
                async with session.get("https://api.ipify.org", timeout=aiohttp.ClientTimeout(total=10)) as r:
                    print(p.url, "→", await r.text())
                    return
        except (aiohttp.ClientError, ProxyError, asyncio.TimeoutError, OSError):
            continue  # los proxies gratuitos van y vienen: simplemente toma el siguiente

asyncio.run(main())
```

**Scrapy**: un middleware de descarga que envía cada petición, reintentos incluidos, por el siguiente proxy. Scrapy solo habla con proxies HTTP; `https=True` elige los que pueden tunelizar páginas `https://`

```python
import itertools

import scrapy
from scrapy.crawler import CrawlerProcess
from proxyscraper import live_proxies

PROXIES = [p.url for p in live_proxies(types="http", https=True, min_uptime=50)]
if not PROXIES:
    raise SystemExit("No proxy matches right now – loosen the filters (e.g. min_uptime)")
POOL = itertools.cycle(PROXIES)


class RotatingProxy:
    def process_request(self, request, spider=None):  # las versiones más recientes de Scrapy omiten spider
        request.meta["proxy"] = next(POOL)


class IpSpider(scrapy.Spider):
    name = "ip"
    start_urls = [f"https://api.ipify.org/?n={i}" for i in range(3)]
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {f"{__name__}.RotatingProxy": 350},
        "RETRY_TIMES": 5, "DOWNLOAD_TIMEOUT": 15,
    }

    def parse(self, response):
        print(response.meta["proxy"], "→", response.text)


if __name__ == "__main__":
    process = CrawlerProcess()
    process.crawl(IpSpider)
    process.start()
```

En un proyecto de Scrapy, pon `RotatingProxy` en `middlewares.py` y añádelo a `DOWNLOADER_MIDDLEWARES` en `settings.py`. Para rastreos largos, recarga el pool de vez en cuando: la lista cambia cada hora.

**proxychains, Clash / Mihomo, sing-box**: configuraciones listas para usar con `--export`

```bash
proxy-scraper --want 30 -y --export proxychains,clash,singbox
proxychains4 -f results/latest/proxychains.conf curl https://api.ipify.org
```

`clash.yaml` contiene todos los proxies HTTP y SOCKS5 más un grupo `url-test` que siempre elige el más rápido. `singbox.json` hace lo mismo para sing-box, SOCKS4 incluido, y abre un proxy local: `sing-box run -c results/latest/singbox.json`, y luego usa `127.0.0.1:2080` como proxy HTTP o SOCKS5. Los tres omiten los proxies HTTP que no pueden tunelizar (`CONNECT`), porque estas herramientas tunelizan todo.

**Navegadores y el sistema operativo**: `--export pac` escribe `proxy.pac`; apunta hacia él Firefox, Chrome (mediante la configuración del sistema), FoxyProxy o la configuración de proxy de macOS/Windows y cada petición pasará por los mejores 30 proxies HTTP y SOCKS5 por orden, y el navegador pasará al siguiente por sí solo cuando uno falle. Los nombres locales y las direcciones IP privadas van directos (un nombre de host como `10.example.com` no cuenta como privado). El archivo en sí no tiene respaldo `DIRECT` y no resuelve nombres de host, y SOCKS4 queda fuera porque haría que el navegador resolviera los nombres con tu propio DNS. Dos ajustes de Firefox importan: activa *Proxy DNS when using SOCKS v5* y pon `network.proxy.failover_direct` en `false` en `about:config`; de lo contrario Firefox va directo cuando todos los proxies han fallado. Sin instalar nada: la lista en vivo publica uno cada hora en `https://maximilianfeix.github.io/proxy-scraper/proxy.pac`.

**Burp Suite, OWASP ZAP, mitmproxy**: pon el servidor rotativo detrás de tu proxy de interceptación, de modo que un escaneo o una prueba de fuerza bruta salga desde muchas IP mientras sigues viendo cada petición. Inícialo con `proxy-scraper --recheck live --serve` y luego:

| Herramienta | Dónde | Configurar |
|---|---|---|
| Burp Suite | *Settings → Network → Connections → Upstream proxy servers* | una regla para el host de destino `*`, host del proxy `127.0.0.1`, puerto `8899`; con `--serve-password` añade autenticación Basic (usuario `any` o una opción como `country-de`, y la contraseña) |
| OWASP ZAP | *Options → Network → Connection → HTTP Proxy* | host `127.0.0.1`, puerto `8899`, y en su autenticación el usuario (`any` o una opción) y la contraseña; usa el ajuste HTTP, no SOCKS: ZAP nunca envía las direcciones loopback por su proxy SOCKS |
| mitmproxy | línea de comandos | `mitmproxy --mode upstream:http://127.0.0.1:8899 --upstream-auth country-us:x` |

Las opciones en el nombre de usuario (`country-us` envía todo por proxies de EE. UU., `session-NAME` mantiene una misma IP de salida durante un flujo de inicio de sesión) llegan al servidor como el login del proxy. mitmproxy lo envía de inmediato; Burp y ZAP pueden esperar a que se les pida, así que inicia el servidor con `--serve-password` cuando dependas de una opción así en ellos. **Mantén activadas las comprobaciones de certificados upstream de tu herramienta** (sin `--ssl-insecure` en mitmproxy, sin “ignorar errores de certificado” upstream en Burp o ZAP): los proxies gratuitos los gestionan desconocidos, y esa comprobación es lo que impide que uno lea o modifique tu tráfico HTTPS. Probado de extremo a extremo con mitmproxy 12, con las comprobaciones de certificados activadas: HTTP y HTTPS a través de mitmproxy y del servidor rotativo, cada petición saliendo por un proxy de EE. UU., y un sitio con un certificado caducado rechazado. Prueba solo lo que tengas permiso para probar.

**En una tubería**: `-o -` imprime los aciertos en stdout, y la interfaz pasa a stderr

```bash
proxy-scraper --recheck live --want 20 -y -o - | grep '^socks5://' > socks.txt
```

**Comprueba una lista que ya tienes**: `--recheck -` la lee de stdin: líneas `ip:port` simples, `type://ip:port`, credenciales (`user:pass@ip:port` o `ip:port:user:pass`), JSON, una exportación CSV o una tabla pegada de un sitio web (HTML o Markdown), en el orden en que llegó. Solo sale lo que funciona desde tu red:

```bash
curl -s https://example.com/proxies.txt | proxy-scraper --recheck - -o - > working.txt
```

Los proxies sin tipo se prueban como HTTP y como SOCKS5, o solo como SOCKS4 con `--types socks4`. Una contraseña con coma, comillas, `|` o corchete no se puede distinguir del texto que la rodea en un pegado; pon esos proxies en un archivo, uno por línea, y usa `--recheck file.txt`.

**Cualquier herramienta, a través del servidor rotativo**

```bash
proxy-scraper --recheck --serve &
export HTTPS_PROXY=http://127.0.0.1:8899 HTTP_PROXY=http://127.0.0.1:8899
pip download requests   # git, pip, npm y compañía ahora pasan por el pool
```

**En un workflow de GitHub**: la action elige proxies que funcionan para los pasos siguientes

```yaml
- id: proxies
  uses: maximilianfeix/proxy-scraper@v1
  with:
    types: socks5
    https: true
    min-uptime: 90        # en la lista el 90 % o más de la semana
    min-speed: 100        # opcional: descargó 100+ KB/s en la última comprobación
    works-on: google      # opcional: google, reddit, amazon
    recheck: true         # opcional: volver a comprobarlos desde el runner
- run: curl -x "${{ steps.proxies.outputs.proxy }}" https://api.ipify.org
```

`proxy` es el más rápido, `file` un archivo de texto con todos (hasta `limit`, por defecto 20) y `count` cuántos hay. Si no hay coincidencias el paso falla, salvo con `fail-if-empty: false`.

**En el shell, sin escaneo**: `--pick` toma proxies de la lista horaria en aproximadamente medio segundo

```bash
curl -x "$(proxy-scraper --pick --https-only --min-uptime 90)" https://api.ipify.org
proxy-scraper --pick 10 --country DE --works-on google > de.txt
proxy-scraper --pick 5 --min-speed 200     # solo los que descargaron 200+ KB/s
```

“El más rápido primero” significa el primero en responder más la velocidad de descarga medida en la última comprobación: en una prueba con páginas reales, los 25 más rápidos en descarga cargaron cuatro veces más páginas que los 25 más rápidos en responder a una petición minúscula.

**Sin instalar nada**: directamente desde la lista en vivo

```bash
curl -s https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/https.txt | head -5
```

Los fragmentos de shell son para macOS y Linux, donde `results/latest` apunta a la ejecución más reciente. En Windows, `results/latest.txt` contiene en su lugar el nombre de la carpeta; en PowerShell:

```powershell
$run = "results\$(Get-Content results\latest.txt)"
curl.exe -x (Get-Content "$run\all.txt" -TotalCount 1) http://api.ipify.org
```

<a id="options"></a>

## Opciones

<details>
<summary><b>Mostrar todas las opciones</b></summary>
<br>

| Opción | Descripción |
|---|---|
| `-i`, `--interactive` | asistente de configuración (se muestra automáticamente sin argumentos) |
| `-y`, `--yes` | empieza de inmediato sin el asistente |
| `--types http socks5` | solo estos protocolos |
| `-l`, `--limit N` | comprueba solo los *N* proxies más prometedores |
| `--want N` | se detiene en cuanto se encuentran *N* proxies que cumplen |
| `--country DE,AT` | solo estos países |
| `--https-only` | solo proxies que pueden tunelizar HTTPS |
| `--anonymity elite` | anonimato mínimo (`anonymous` o `elite`) |
| `--max-latency MS` | latencia máxima |
| `--no-datacenter` | omite proxies cuya salida está (probablemente) en un datacenter: esos se bloquean antes |
| `--no-blocklisted` | omite proxies cuya IP de salida está en la lista negra de SpamCop: esos suelen recibir captchas |
| `--no-dnsbl` | omite la consulta de listas negras |
| `--target URL` | solo proxies que llegan a este sitio (repetible) |
| `--recheck [FILE\|-\|live]` | comprueba solo proxies de un archivo, de stdin (`-`), de la última ejecución o de la lista pública en vivo |
| `--fast` | omite la prueba HTTPS (la confirmación y el anonimato se siguen ejecutando) |
| `--no-geo` | omite la consulta de país |
| `-c`, `--concurrency N` | comprobaciones simultáneas (por defecto: 2000) |
| `-t`, `--timeout S` | tiempo de espera por proxy (por defecto: 8 s) |
| `--discover` | busca nuevas fuentes en GitHub ahora mismo |
| `--no-cache` | descarga de nuevo todas las listas (las que no han cambiado normalmente se omiten mediante ETag) |
| `--list-sources [N]` | muestra el ranking de fuentes (añade `--json` para scripts: url, estado, tasa de aciertos, comprobaciones, último cambio) |
| `--pick [N]` | imprime N proxies (por defecto 1) de la lista horaria ya comprobada y sale: sin escaneo, mismos filtros, más `--min-uptime PERCENT`, `--min-speed KBPS` y `--works-on google,reddit,…` |
| `--serve-host ADDR` | dónde escucha el servidor proxy (por defecto `127.0.0.1`; `0.0.0.0` para Docker, con una advertencia) |
| `--serve-password SECRET` | los clientes deben enviar esta contraseña en el login del proxy; mejor define `PROXY_SCRAPER_SERVE_PASSWORD` |
| `--rotate STRATEGY` · `--sticky SEC` | cómo elige proxies el servidor proxy, véase [arriba](#proxy-server) |
| `--serve-refill HOURS` | mientras sirve, comprueba proxies nuevos cada HOURS y añade los aciertos al pool |
| `--serve [PORT]` | después sirve como proxy rotativo en `127.0.0.1:PORT` (por defecto: 8899) |
| `-o FILE` | escribe además todos los aciertos en este archivo; `-o -` los imprime en stdout |
| `--export FORMATS` | archivos adicionales para otras herramientas: `proxychains`, `clash`, `singbox`, `curl`, `pac` o `all` |
| `-V`, `--version` | imprime la versión |
| `--completion SHELL` | imprime el script de autocompletado para bash, zsh, fish o PowerShell |

Todo lo demás: `proxy-scraper --help`

</details>

> [!TIP]
> Para la búsqueda en GitHub basta con un [`gh`](https://cli.github.com/) con la sesión iniciada o la variable de entorno `GITHUB_TOKEN`. Sin token el límite de la API es de 60 peticiones por hora, y solo se buscan 40 repositorios.

<a id="github-actions"></a>

## GitHub Actions

El repositorio hace parte del trabajo por sí mismo:

| Workflow | Qué hace |
|---|---|
| [**tests**](../../actions/workflows/tests.yml) | 3 sistemas operativos × 3 versiones de Python, más un paquete compilado e instalado, en cada push y pull request |
| [**lint**](../../actions/workflows/lint.yml) | `ruff` con versión fijada: mismas reglas en local y en CI |
| [**codeql**](../../actions/workflows/codeql.yml) | análisis de seguridad en cada push y una vez por semana |
| [**proxy list**](../../actions/workflows/proxy-list.yml) | cada hora: recopila, comprueba y publica en `proxy-list`. Las estadísticas aprendidas viven en la caché de Actions, así que la herramienta sigue mejorando también en la nube |
| [**docker**](../../actions/workflows/docker.yml) | construye la imagen en cada cambio y ejecuta un escaneo real dentro de ella; con una etiqueta de versión publica `linux/amd64` + `linux/arm64` en `ghcr.io` |
| [**release**](../../actions/workflows/release.yml) | con una etiqueta de versión: prueba, compila, hace un smoke test y publica una release de GitHub con el wheel |
| [**discord bot**](../../actions/workflows/bot.yml) | prueba el bot y lo despliega en el servidor en cada cambio en `bot/` |
| **Dependabot** | mantiene al día las versiones de las actions |

<a id="faq"></a>

## Preguntas frecuentes

<a id="who-runs-free-proxies"></a>

<details open>
<summary><b>¿Quién gestiona los proxies gratuitos y deberías usarlos?</b></summary>
<br>

Casi nadie gestiona un proxy gratuito para ti. Lo que acaba en las listas públicas suele ser una de estas cosas:

- **Servidores mal configurados**: un Squid, un router o una aplicación con un puerto de proxy que debía permanecer interno.
- **Proxies abiertos deliberadamente**: unos pocos voluntarios y proyectos de investigación, y servicios que regalan algunos para vender el resto.
- **Máquinas infectadas**: equipos y dispositivos IoT cuyos dueños no saben que retransmiten tráfico. Muchas salidas residenciales son así.
- **Trampas**: honeypots que registran lo que pasa por ellos, y proxies que reescriben las páginas para inyectar anuncios o scripts.

proxy-scraper no puede distinguir un router doméstico infectado de un proxy abierto de oficina, pero filtra lo que puede medir: un proxy tiene que responder a dos peticiones independientes con la misma IP de salida (los honeypots que solo responden a los escáneres quedan fuera), entregar una página conocida byte por byte (los inyectores quedan fuera), y HTTPS solo cuenta con un certificado que se verifica de extremo a extremo. Cada acierto indica si su salida está en un datacenter.

Buenos usos: datos públicos, comprobar cómo se ve un sitio desde otro país, probar tus propios bloqueos y límites de tasa, investigación. Nunca envíes contraseñas, cookies, datos de pago ni datos personales a través de un proxy gratuito, y mantén activadas las comprobaciones de certificados HTTPS. Úsalos solo donde tengas permiso.

</details>

<details>
<summary><b>Casi nada pasa las comprobaciones.</b></summary>
<br>

Muchas redes de empresas, colegios y universidades bloquean las conexiones de proxy. La herramienta detecta una tasa de aciertos por debajo del 0,2 % y te avisa: ayuda cambiar a otra red, como el punto de acceso de un teléfono. Las estadísticas aprendidas no se rebajan en una ejecución así.

</details>

<details>
<summary><b>¿Funciona en Windows?</b></summary>
<br>

Sí, en PowerShell y Windows Terminal. `uvloop` no existe allí y se omite automáticamente. En la antigua ventana de `cmd.exe` pueden faltar algunos símbolos según la fuente.

</details>

<details>
<summary><b>¿Por qué encuentra menos proxies de los que dicen tener otras listas?</b></summary>
<br>

Porque solo se conservan los proxies que superan todas las comprobaciones. Muchas listas cuentan cualquier cosa que acepte una conexión TCP; aquí un proxy tiene que descargar dos páginas independientes y mostrar una IP ajena. Suelen ser unos pocos cientos de entre un millón de candidatos, pero funcionan.

</details>

<details>
<summary><b>¿Y los proxies con usuario y contraseña?</b></summary>
<br>

Las líneas como `socks5://user:pass@1.2.3.4:1080` conservan sus credenciales: los proxies HTTP reciben una cabecera `Proxy-Authorization`, SOCKS5 usa autenticación de usuario/contraseña (RFC 1929) y SOCKS4 el ID de usuario. Lo mismo funciona con `--recheck` y tu propia lista. Los archivos de resultados conservan las credenciales; el terminal solo muestra `user:•••`.

</details>

<details>
<summary><b>¿Con qué frecuencia se actualiza la lista en vivo?</b></summary>
<br>

Se reconstruye cada hora; la insignia “actualizado” muestra la última ejecución. Los proxies gratuitos van y vienen rápidamente, así que para cualquier cosa importante ejecuta `proxy-scraper --recheck` justo antes de usarlos.

</details>

<details>
<summary><b>¿Es seguro usar proxies gratuitos?</b></summary>
<br>

Solo para cosas que no importan. Los proxies públicos los gestionan desconocidos que pueden leer todo lo que no esté cifrado. Nunca envíes contraseñas ni datos personales a través de ellos, y úsalos solo con fines legales.

</details>

<a id="roadmap"></a>

## Hoja de ruta

Lo que viene está en las [issues abiertas](../../issues); las ideas y deseos son bienvenidos como [issue](../../issues/new/choose). Durante Hacktoberfest hay [issues aptas para principiantes](../../issues?q=is%3Aopen+label%3Ahacktoberfest) con indicaciones de por dónde empezar.

Publicado de la v1.24 a la v1.26: `--recheck -` para listas que pasas por tubería, qué proxies llegan a Discord, un README que puedes probar en cinco segundos, el servidor MCP en la imagen de Docker, credenciales escritas como `ip:port:user:pass` y un dataset de Hugging Face que se carga en una línea.

Publicado en v1.22 y v1.23: un panel en vivo para el servidor rotativo, `--export pac` y un `proxy.pac` horario, un «mejor primero» que cuenta la probabilidad de que un proxy siga activo, las listas en un repositorio propio ([free-proxy-list](https://github.com/maximilianfeix/free-proxy-list)), snapshots diarios en Hugging Face, `brew install`, un README en chino, Python 3.14 y una receta para Burp Suite, ZAP y mitmproxy.

Publicado en v1.10 a v1.21: velocidad de descarga por proxy y «mejor primero» en todas partes, snapshots diarios, una URL de proxy rotativo para requests, httpx y Playwright, `--pick` para obtener proxies que funcionan sin escaneo, una API de pool de proxies compatible con jhao104/proxy_pool, tus propias listas con `--source`, una GitHub Action, un bot de Telegram y un feed Atom para el informe semanal.

Publicado en v1.8 y v1.9: uptime por proxy y `stable.txt`, qué proxies llegan a Google, Reddit y Amazon, `live_proxies()` en Python, una página por proxy con su semana de comprobaciones, un informe semanal, gráficos en vivo en este README, filtros que se pueden compartir en el sitio web, fuentes extraídas de las listas de otros scrapers, listas sin tipo probadas como HTTP y SOCKS5, `--export singbox`, autocompletado para PowerShell y recetas para httpx, aiohttp y Scrapy.

Publicado en [v1.7](../../milestone/7): un servidor MCP para que los agentes de IA obtengan proxies que funcionan y puedan cargar páginas a través de ellos, 28 fuentes nuevas y una búsqueda en GitHub que se ejecuta a diario y conserva lo que encontró, y un sitio web más limpio.

Publicado en [v1.6](../../milestone/6): comprobación de listas negras de spam para cada IP de salida, una lista en vivo actualizada cada hora, páginas por protocolo y país, una contraseña opcional para el servidor proxy y un pool que se rellena solo mientras funciona, `compose.yaml`, `-o -` para tuberías, un bot de Discord, y un sitio web y un README nuevos: todo en inglés a partir de entonces (el README original).

Publicado en [v1.5](../../milestone/5): comprobación de manipulación de contenido, sitio web de la lista en vivo con tendencia y proxies estables, información de proveedor/datacenter, un servidor proxy mucho más completo (estrategias de rotación, sesiones sticky, entrada SOCKS5, estado y métricas de Prometheus), `--recheck live`, API de Python, autocompletado de shell. Medido y descartado antes: la detección de protocolo con una conexión adicional ([#3](../../issues/3)) e IPv6 ([#1](../../issues/1)).

<a id="contributing"></a>

## Contribuir

Los informes de errores, las nuevas fuentes y los pull requests son muy bienvenidos: consulta [CONTRIBUTING.md](CONTRIBUTING.md), y [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) para ver cómo encajan las piezas. La versión corta:

```bash
pip install -e ".[dev]"
python3 -m pytest          # se ejecuta sin conexión: proxies falsos en localhost
ruff check .
python3 docs/make_demo.py  # regenera las imágenes de este README
```

<details>
<summary><b>Estructura del proyecto</b></summary>

```
proxy_scraper.py        punto de entrada al ejecutar desde un clon
bot/                    bot de Discord para la lista en vivo (requisitos propios, desplegado con GitHub Actions)
proxyscraper/
├── cli.py              argumentos, asistente o inicio directo
├── app.py              una ejecución en fases: red → trabajos → comprobación → aprendizaje e informe
├── options.py          RunOptions + Filters: todos los ajustes en un solo lugar
├── pipeline.py         recopilar fuentes, priorizar, bucle de comprobación
├── checker.py          comprobaciones, confirmación de honeypots, prueba HTTPS
├── handshake.py        handshakes HTTP/SOCKS4/SOCKS5 incluido el login
├── judges.py           objetivos de comprobación, filtro de Cloudflare, conmutación por error
├── sources.py          listas de fuentes, metafuentes, descubrimiento en GitHub, estadísticas
├── sources.json        fuentes curadas
├── fetchcache.py       caché ETag para listas sin cambios
├── parsing.py          encontrar proxies en texto, HTML y JSON
├── history.py          historial de proxies que funcionan
├── geo.py              países: primero sin conexión, ip-api.com como respaldo
├── asndb.py            base de datos de proveedores de DB-IP, heurística de datacenter
├── geodb.py            base de datos de países de DB-IP (mensual, búsqueda binaria)
├── targets.py          sitios objetivo para --target
├── output.py           archivos de resultados
├── exporters.py        formatos proxychains, Clash, sing-box, curl y PAC (--export)
├── server/             servidor proxy rotativo (--serve): pool · http · upstream · socks · status · api · core
├── api.py              find_proxies() / check_proxies() para Python
├── agent.py            herramientas MCP sin el SDK: lista en vivo, filtros, descarga a través de proxies
├── mcp_server.py       servidor MCP (proxy-scraper-mcp) para agentes de IA
├── publish.py          lista en vivo para GitHub Actions
├── mirror.py           las mismas listas en su propio repositorio (free-proxy-list)
├── paths.py            dónde se guardan el estado y los resultados
├── compat.py           diferencias entre Unix y Windows
├── netio.py            pequeño cliente HTTP sobre asyncio
└── ui/                 widgets · dashboard · report · wizard · serve · keys
```

</details>

<a id="community"></a>

## Comunidad

Las preguntas, ideas y lo que hayas construido con ella van a [Discussions](https://github.com/maximilianfeix/proxy-scraper/discussions); los errores, a las [issues](../../issues). Si proxy-scraper te ahorra tiempo, una ⭐ ayuda a que otros lo encuentren.

Gracias a todos los que ayudaron a construirlo: nuevas fuentes, países, Python 3.14, ejemplos y más:

<a href="https://github.com/maximilianfeix/proxy-scraper/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=maximilianfeix/proxy-scraper" alt="Colaboradores de proxy-scraper">
</a>

¿Quieres unirte? Las [issues aptas para principiantes](../../issues?q=is%3Aopen+label%3A%22good+first+issue%22) indican por dónde empezar.

<a href="https://star-history.com/#maximilianfeix/proxy-scraper&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=maximilianfeix/proxy-scraper&type=Date&theme=dark">
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=maximilianfeix/proxy-scraper&type=Date">
    <img alt="Historial de estrellas de proxy-scraper" src="https://api.star-history.com/svg?repos=maximilianfeix/proxy-scraper&type=Date" width="600">
  </picture>
</a>

<a id="acknowledgements"></a>

## Agradecimientos

proxy-scraper se apoya en el trabajo de quienes publican listas de proxies gratuitos. Gracias a todos los que aparecen en [`sources.json`](proxyscraper/sources.json), y en especial a

- [monosans/proxy-scraper-checker](https://github.com/monosans/proxy-scraper-checker) y [gfpcom/free-proxy-list](https://github.com/gfpcom/free-proxy-list), cuyas colecciones curadas de fuentes se leen como metafuentes
- [Textualize/rich](https://github.com/Textualize/rich), que dibuja toda la interfaz de terminal
- [IP Geolocation by DB-IP](https://db-ip.com): la base de datos gratuita de países (CC BY 4.0) usada para las consultas de país sin conexión
- [httpbin](https://httpbin.org), [checkip.amazonaws.com](https://checkip.amazonaws.com), [ifconfig.me](https://ifconfig.me), [ipinfo.io](https://ipinfo.io), [wtfismyip.com](https://wtfismyip.com), [ident.me](https://ident.me) e [ip-api.com](https://ip-api.com), usados como objetivos de comprobación y para las consultas de país

## Aviso legal

Esta herramienta solo recopila proxies listados públicamente y comprueba si funcionan. Tú eres responsable de cómo los uses: respeta los términos de los sitios que visitas y las leyes del lugar donde vives.

<div align="center">

---

<sub>Hecho en Alemania por <a href="https://github.com/maximilianfeix">@maximilianfeix</a> · <a href="LICENSE">Licencia MIT</a> · <a href="CHANGELOG.md">Changelog</a> · <a href="SECURITY.md">Seguridad</a> · <a href="CONTRIBUTING.md">Contribuir</a></sub>

<sub>Si proxy-scraper te ahorra tiempo, una ⭐ ayuda a que otros lo encuentren.</sub>

</div>
