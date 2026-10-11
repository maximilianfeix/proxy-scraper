<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/banner-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/banner-light.svg">
  <img src="docs/banner-dark.svg" alt="proxy-scraper – proxies gratuitos que realmente funcionam" width="100%">
</picture>

[![tests](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/tests.yml/badge.svg)](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/maximilianfeix/proxy-scraper?style=flat-square&color=D4F77A&labelColor=121113)](https://github.com/maximilianfeix/proxy-scraper/releases/latest)
[![Live proxies](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Ftotal.json&style=flat-square&labelColor=121113)](#live-list)
[![PyPI](https://img.shields.io/pypi/v/proxy-scraper-cli?style=flat-square&color=D4F77A&labelColor=121113&label=pypi)](https://pypi.org/project/proxy-scraper-cli/)
[![Downloads](https://img.shields.io/pepy/dt/proxy-scraper-cli?style=flat-square&color=D4F77A&labelColor=121113&label=downloads)](https://pepy.tech/projects/proxy-scraper-cli)
[![Stars](https://img.shields.io/github/stars/maximilianfeix/proxy-scraper?style=flat-square&color=D4F77A&labelColor=121113)](https://github.com/maximilianfeix/proxy-scraper/stargazers)
[![License](https://img.shields.io/badge/license-MIT-D4F77A?style=flat-square&labelColor=121113)](LICENSE)

[English](README.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Deutsch](README.de.md) · [Русский](README.ru.md) · **Português (Brasil)** · [Français](README.fr.md)

[Instalação](#install) · [Lista de proxies de hora em hora](#live-list) · [API de pool de proxies](#pool-api) · [Servidor proxy rotativo](#proxy-server) · [Python](#python) · [Agentes de IA (MCP)](#mcp) · [FAQ](#faq)

</div>

---

A maioria das listas de proxies gratuitos está 95 % morta, e boa parte do resto são honeypots ou proxies que injetam scripts nas suas páginas. O **proxy-scraper** coleta proxies HTTP, SOCKS4 e SOCKS5 públicos de mais de 700 fontes e mantém só os que passam em todas as verificações. A cada execução ele aprende quais fontes valem a pena, e pode transformar o resultado em um único proxy rotativo.

**Em números:** em um dia ele fez 3,6 milhões de verificações de proxies gratuitos – 1,1 % passaram, e mais da metade dos que responderam falhou na segunda requisição. [O que realmente existe por aí (em inglês) →](docs/free-proxies-in-numbers.md)

**Quem usa:** a lista de hora em hora é fonte embutida do [monosans/proxy-scraper-checker](https://github.com/monosans/proxy-scraper-checker) e do [gfpcom/free-proxy-list](https://github.com/gfpcom/free-proxy-list).

**Experimente – sem instalar, uns cinco segundos:**

```bash
uvx proxy-scraper-cli --pick 5 --types socks5     # 5 proxies verificados

# ou só a lista
curl -s https://maximilianfeix.github.io/proxy-scraper/socks5.txt | head
```

O `uvx` vem com o [uv](https://docs.astral.sh/uv/); `pipx run proxy-scraper-cli --pick 5` faz o mesmo.

<div align="center">
<img src="docs/demo.svg" alt="Demonstração: o painel ao vivo durante uma verificação, o relatório, o assistente de configuração e a coleta" width="880">
</div>

## As verificações que todo proxy precisa passar

| Verificação | O que significa |
|---|---|
| Handshake de verdade | O proxy precisa completar de fato o protocolo HTTP, SOCKS4 ou SOCKS5 |
| Dois sites independentes, o mesmo IP de saída | Uma segunda requisição independente precisa devolver o mesmo IP de saída – honeypots que só respondem a scanners caem aqui |
| Conteúdo intacto | Uma página conhecida precisa chegar byte a byte; proxies que injetam scripts ou anúncios são descartados |
| HTTPS com TLS verificado | Só proxies cujo certificado é verificado de ponta a ponta contam como capazes de HTTPS |
| Detalhes | Anonimato (elite / anonymous / transparent), país, ASN e provedor, datacenter ou não, latência, velocidade de download |

<a id="install"></a>

## Instalação

```bash
pipx install proxy-scraper-cli
proxy-scraper
```

No PyPI o pacote se chama `proxy-scraper-cli` (o nome simples já estava ocupado), o comando é `proxy-scraper`. Roda em Python 3.9–3.14 no macOS, Linux e Windows e só depende de `rich` e `certifi`.

No macOS e Linux também com [Homebrew](https://brew.sh):

```bash
brew install maximilianfeix/tap/proxy-scraper
```

Ou com Docker (`linux/amd64` e `linux/arm64`):

```bash
docker run --rm ghcr.io/maximilianfeix/proxy-scraper --want 50 --https-only
```

Iniciado sem argumentos, um assistente pergunta o que você procura: com as setas você escolhe um preset (encontrar tudo, navegação e web, anonimato máximo, rápidos e estáveis …) e no fim recebe a linha de comando correspondente.

<a id="live-list"></a>

## Lista de proxies de hora em hora

Não quer escanear você mesmo? O GitHub Actions roda a ferramenta a cada hora e publica os acertos. Cada proxy da lista passou em todas as verificações na última execução, ordenado por "melhores primeiro": os rápidos, que provavelmente ainda estão no ar, ficam no topo (um proxy que está há um dia no ar tem 99 % de chance de estar lá daqui a uma hora; um recém-chegado, só 25 %).

- **Site** (filtre por protocolo, país, HTTPS, provedor, latência): https://maximilianfeix.github.io/proxy-scraper/
- **Só as listas** (TXT por protocolo, país e site, mais JSON/CSV): [maximilianfeix/free-proxy-list](https://github.com/maximilianfeix/free-proxy-list)

| Lista | Formato | Endereço |
|---|---|---|
| Todos | `socks5://1.2.3.4:1080` | `https://maximilianfeix.github.io/proxy-scraper/all.txt` |
| HTTP · SOCKS4 · SOCKS5 | `1.2.3.4:8080` | `…/http.txt` · `…/socks4.txt` · `…/socks5.txt` |
| Só os capazes de HTTPS | `type://ip:port` | `…/https.txt` |
| Só elite | `type://ip:port` | `…/elite.txt` |
| Passam no Google · Reddit · Amazon · Instagram · TikTok · Discord | `type://ip:port` | `…/works-with/google.txt` · `…/works-with/reddit.txt` · … |
| Estáveis (em 90 %+ das execuções desta semana) | `type://ip:port` | `…/stable.txt` |
| Com todos os detalhes | latência, país, HTTPS, anonimato, IP de saída, uptime | `…/proxies.json` · `…/proxies.csv` |

Cada protocolo e cada país também tem a própria página com download direto, por exemplo [SOCKS5](https://maximilianfeix.github.io/proxy-scraper/socks5/) ou [Brasil](https://maximilianfeix.github.io/proxy-scraper/country/br/) (`country/br/proxies.txt`).

```bash
curl -s https://maximilianfeix.github.io/proxy-scraper/socks5.txt | head
```

> [!TIP]
> Os arquivos também estão no GitHub Pages, atrás de uma CDN – sem o limite de taxa do `raw.githubusercontent.com` e com cabeçalhos CORS, ou seja, funcionam direto do navegador. O [jsDelivr](https://cdn.jsdelivr.net/gh/maximilianfeix/proxy-scraper@proxy-list/) também funciona, mas pode atrasar algumas horas.

A verificação é feita dos servidores do GitHub nos EUA. `proxy-scraper --recheck live` baixa a lista e verifica tudo de novo a partir da **sua** rede – uns 30 segundos em vez de um scan completo. Com `--serve` você tem um proxy rotativo em menos de um minuto.

<a id="pool-api"></a>

## API de pool de proxies: substituto direto do jhao104/proxy_pool

Usa o [jhao104/proxy_pool](https://github.com/jhao104/proxy_pool)? Os endpoints, o parâmetro `type=https` e os campos JSON (`proxy`, `https`, `region`, `anonymous`, `check_count`, `fail_count`, …) são os mesmos – aponte seu código para a porta 8899 e ele continua funcionando. **Sem Redis**, e cada proxy passou nas verificações de honeypot e de adulteração; os marcados como HTTPS passaram também na de TLS.

```bash
proxy-scraper --recheck live --serve   # começa com a lista de hora em hora, pronto em ~30 s
```

```bash
curl http://127.0.0.1:8899/get                                    # um proxy em JSON
curl "http://127.0.0.1:8899/get?country=BR&https=1&format=txt"    # → http://203.0.113.7:8080
curl "http://127.0.0.1:8899/all?protocol=socks5&limit=20"         # os 20 melhores SOCKS5
curl "http://127.0.0.1:8899/report?proxy=203.0.113.7:8080&ok=0"   # falhou com você – três vezes e sai
```

| Endpoint | O que faz |
|---|---|
| `/get` | um proxy, escolhido pela estratégia `--rotate` |
| `/pop` | como `/get`, e o proxy sai do pool |
| `/all` | todos os proxies utilizáveis, melhores primeiro (`limit=N`) |
| `/count` | totais por tipo e país |
| `/delete?proxy=IP:PORT` | remove um proxy |
| `/report?proxy=IP:PORT&ok=0` | feedback das suas próprias requisições |

Os filtros valem para `/get`, `/pop` e `/all`: `country=BR,PT`, `protocol=socks5`, `https=1`, `anonymity=elite`, `max_latency=1500`, e `format=txt` devolve só a URL.

```python
import requests
proxy = requests.get("http://127.0.0.1:8899/get?type=https").json()["url"]   # ex. socks5://…, tipo incluído
requests.get("https://example.com", proxies={"http": proxy, "https": proxy})
```

<a id="proxy-server"></a>

## Servidor proxy rotativo

A mesma porta também é um proxy local: cada conexão sai por um proxy diferente, e se um falha, o próximo assume.

```bash
curl -x http://127.0.0.1:8899 https://api.ipify.org                  # um IP diferente a cada vez
curl -x socks5h://127.0.0.1:8899 https://api.ipify.org               # SOCKS5 na mesma porta
curl -x http://country-br:x@127.0.0.1:8899 https://api.ipify.org     # só saídas brasileiras
curl -x http://session-cart42:x@127.0.0.1:8899 https://shop.example  # o mesmo proxy para esta sessão
```

Como nos proxies rotativos comerciais, o pedido vai no **nome de usuário**: `country-XX`, `type-http|socks4|socks5` e `session-NOME`, combináveis. HTTPS prefere proxies com TLS verificado; se nenhum serve no momento (nenhum atende a um pedido como `country-br`, ou todos caíram), o servidor usa os outros – a verificação de certificado do seu cliente ainda pega qualquer proxy que quebre a criptografia, então deixe-a ligada. Três falhas seguidas e o proxy sai da rotação; a cada cinco minutos é verificado de novo e volta se funcionar. Por padrão o servidor só escuta em `127.0.0.1`; para acesso de outras máquinas, defina uma senha com `PROXY_SCRAPER_SERVE_PASSWORD`. Todas as opções no [README em inglês](README.md#proxy-server).

**Painel ao vivo:** `http://127.0.0.1:8899/__proxy-scraper/` no navegador mostra o pool, a taxa de sucesso, o tráfego, os países, os melhores proxies e as últimas conexões – atualizado a cada dois segundos.

<a id="python"></a>

## Em Python

```python
from proxyscraper import ProxyRotator, live_proxies

# a lista de hora em hora, sem verificação, em cerca de um segundo
proxies = live_proxies(types=["socks5"], https=True, min_uptime=90)

# repetição automática e troca de proxy
with ProxyRotator(country="BR") as rotator:
    r = rotator.get("https://httpbin.org/ip")
    print(r.status, r.text, "via", r.via)

# um endereço de proxy local para requests / httpx / Playwright / Scrapy, rotação nos bastidores
with ProxyRotator() as rotator:
    proxy = rotator.proxy_url()
```

Para uma verificação nova a partir da sua rede há `find_proxies()` e `check_proxies()`. A descrição completa está no [README em inglês](README.md#from-python).

## Comandos frequentes

```bash
proxy-scraper --want 50 --https-only                   # parar assim que achar 50 capazes de HTTPS
proxy-scraper --types socks5 --anonymity elite         # só SOCKS5 elite
proxy-scraper --country BR,PT,AR --max-latency 1500    # países específicos, latência máxima
proxy-scraper --target www.google.com --want 20        # só proxies que alcançam o site alvo
proxy-scraper --pick 5 --types socks5                  # 5 da lista de hora em hora, sem scan
proxy-scraper --export clash                           # configuração do Clash (também proxychains, sing-box, curl)
```

Todas as opções: `proxy-scraper --help` ou o [README em inglês](README.md#options).

<a id="mcp"></a>

## Agentes de IA (MCP)

`proxy-scraper-mcp` é um servidor [MCP](https://modelcontextprotocol.io): Claude Code, Claude Desktop, Cursor, VS Code, Codex e qualquer outro cliente MCP podem pedir proxies funcionando e carregar páginas por eles.

[![proxy-scraper MCP server on Glama](https://glama.ai/mcp/servers/maximilianfeix/proxy-scraper/badges/score.svg)](https://glama.ai/mcp/servers/maximilianfeix/proxy-scraper)

| Ferramenta | O que faz |
|---|---|
| `get_proxies` | proxies funcionando da lista de hora em hora – filtráveis por protocolo, país, HTTPS, elite, datacenter, estabilidade, latência |
| `check_proxies` | verifica proxies a partir da sua rede, para que funcionem onde seu código roda |
| `fetch_url` | carrega uma página por um proxy verificado, troca sozinho em caso de erro e devolve texto legível |

**Claude Code:**

```bash
claude mcp add proxy-scraper -- uvx --python ">=3.10" --from "proxy-scraper-cli[mcp]" proxy-scraper-mcp
```

**Claude Desktop, Cursor e a maioria dos outros clientes** – adicione à configuração MCP:

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

Não quer Python? A imagem Docker traz tudo: `"command": "docker"`, `"args": ["run", "-i", "--rm", "ghcr.io/maximilianfeix/proxy-scraper", "--mcp"]`. O servidor também está no [registro oficial do MCP](https://registry.modelcontextprotocol.io) como `io.github.maximilianfeix/proxy-scraper`.

<a id="faq"></a>

## FAQ

**Quem mantém proxies gratuitos – e dá para usá-los?**
Quase ninguém mantém um proxy gratuito para você. O que aparece nas listas públicas costuma ser: servidores mal configurados com uma porta aberta sem querer; alguns proxies abertos de propósito; computadores e dispositivos IoT infectados, sem que os donos saibam; e armadilhas que registram o tráfego ou reescrevem páginas. O proxy-scraper não distingue um roteador doméstico infectado de um proxy de escritório aberto, mas filtra o que dá para medir: duas requisições independentes precisam devolver o mesmo IP de saída (honeypots que só respondem a scanners caem), uma página conhecida precisa chegar byte a byte (injetores caem), e HTTPS só conta com certificado verificado de ponta a ponta. Bom para dados públicos, para ver um site a partir de outro país, para testar os próprios bloqueios e para pesquisa. Nunca envie senhas, cookies, dados de pagamento ou pessoais por um proxy gratuito.

**Por que encontra menos proxies do que outras listas prometem?**
Porque só ficam os proxies que passam em todas as verificações. Muitas listas contam qualquer coisa que aceite uma conexão TCP; aqui um proxy precisa carregar duas páginas independentes e mostrar um IP estranho. Costuma dar algumas centenas ou milhares em um milhão de candidatos – mas funcionam.

**Quase nada passa?**
Muitas redes de empresas, escolas e universidades bloqueiam conexões de proxy. A ferramenta nota uma taxa de acerto abaixo de 0,2 % e avisa – outra rede, como o hotspot do celular, ajuda.

**Funciona no Windows?**
Sim, no PowerShell e no Windows Terminal. O `uvloop` não existe lá e é pulado automaticamente.

**Quão recente é a lista?**
É refeita a cada hora. Proxies gratuitos vêm e vão rápido – para qualquer coisa importante, rode `proxy-scraper --recheck` logo antes de usar.

**Proxies gratuitos são seguros?**
Só para o que não importa. Proxies públicos são mantidos por desconhecidos, que podem ler tudo o que não está criptografado. Não envie senhas nem dados pessoais por eles, e use só onde for permitido.

## Contribuindo

Issues e pull requests são bem-vindos, em português ou inglês. Há [issues para iniciantes](https://github.com/maximilianfeix/proxy-scraper/issues?q=is%3Aopen+label%3A%22good+first+issue%22). Se o proxy-scraper economiza o seu tempo, uma ⭐ ajuda outras pessoas a encontrá-lo.

## Aviso legal

Esta ferramenta só coleta proxies listados publicamente e verifica se funcionam. O uso é responsabilidade sua – respeite os termos dos sites que visita e as leis que valem para você. [Licença MIT](LICENSE).
