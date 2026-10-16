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

**Verificações de proxy que você pode inspecionar: o que passou, o que falhou e quando.** O proxy-scraper coleta proxies HTTP, SOCKS4 e SOCKS5 públicos de centenas de listas, roda até quatro verificações em cada um e guarda o resultado de cada verificação para os proxies que ele lista (para os demais, conta como cada verificação terminou). Assim, "funciona" passa a ser algo que você pode conferir, e não um rótulo em que precisa confiar.

<div align="center">
<img src="docs/demo/checks.gif" alt="Gravação de terminal: proxy-scraper --pick 2 --verify --https-only imprime dois proxies e diz no stderr por que os outros quatro ficaram de fora; proxy-scraper --diagnose mostra cada verificação de um proxy com o resultado" width="880">
</div>

<sub>Uma gravação real de terminal, feita com seis proxies simulados em localhost ([reproduza](docs/demo/)). Ela mostra como os resultados são apresentados. Não mede nada sobre proxies públicos.</sub>

**Experimente** – sem instalar nada, o `uvx` vem com o [uv](https://docs.astral.sh/uv/) (`pipx run` faz o mesmo):

```bash
uvx proxy-scraper-cli --pick 3 --verify               # até 3 proxies da lista de hora em hora que passam agora, a partir da sua rede
uvx proxy-scraper-cli --diagnose socks5://HOST:PORT   # um proxy, verificação por verificação: o que ele fez e o que não fez
```

No PyPI o pacote se chama `proxy-scraper-cli` (o nome simples já estava ocupado). Depois de [instalado](#install), o comando é `proxy-scraper`. `--verify` e `--diagnose` exigem a versão 1.30 ou mais recente.

**Três formas de obter proxies, e o que "verificado" significa em cada uma:**

| Comando | De onde vêm os proxies | Verificados | Demora |
|---|---|---|---|
| `proxy-scraper --pick 5` | da [lista publicada](#live-list) | a partir dos servidores do GitHub, quando a lista foi gerada, mais ou menos a cada hora | menos de um segundo |
| `proxy-scraper --pick 5 --verify` | da lista publicada | **agora, a partir da sua rede** | de segundos a um minuto e meio, no máximo |
| `proxy-scraper -y` | de todas as listas que a ferramenta conhece | agora, a partir da sua rede | minutos (cerca de três nas execuções de hora em hora) |

**O que você recebe**

- **Cada verificação tem um resultado que dá para ler.** `passed`, `failed`, `unavailable` ou `skipped` (passou, falhou, indisponível, pulada), com um código de motivo, o alvo e o horário, no terminal, em JSON e em Python. Uma verificação que não rodou nunca aparece como aprovada, e um alvo de verificação fora do ar não transforma em falha os proxies verificados contra ele. → [Estados das verificações (em inglês)](docs/check-states.md)
- **Recente quando importa.** `--pick --verify` verifica alguns proxies a partir da sua própria rede, em geral em segundos. `--recheck` faz o mesmo com [uma lista sua](README.md#examples), e `--diagnose` diz por que um proxy não funciona.
- **Mais que uma lista.** Um [servidor proxy rotativo local](#proxy-server), uma [API Python](#python), um [servidor MCP](#mcp) para agentes de IA, Docker e exportações para curl, proxychains, Clash e sing-box.

**O que ele não faz.** Proxies gratuitos são mantidos por desconhecidos, e da lista de uma hora só cerca de um quarto está de novo na lista um dia depois. Passar em uma verificação é uma medição, feita de uma rede, contra alvos de teste: não é promessa para a próxima hora nem para o site que interessa a você. A verificação de HTTPS é uma conexão TLS verificada com um único host de teste, não uma nota de segurança. Use proxies gratuitos para dados públicos e testes, nunca para logins, pagamentos ou qualquer coisa pessoal. → [O que os números mostram e o que não mostram (em inglês)](docs/free-proxies-in-numbers.md) · [Comparação com outros projetos (em inglês)](docs/comparison.md) · [Quem mantém proxies gratuitos](#faq)

**Só quer as listas?** Você não precisa desta ferramenta: o [free-proxy-list](https://github.com/maximilianfeix/free-proxy-list) tem todas em arquivos simples por protocolo e por país, refeitos mais ou menos a cada hora. Ou direto daqui: [all.txt](https://maximilianfeix.github.io/proxy-scraper/all.txt) · [http.txt](https://maximilianfeix.github.io/proxy-scraper/http.txt) · [socks4.txt](https://maximilianfeix.github.io/proxy-scraper/socks4.txt) · [socks5.txt](https://maximilianfeix.github.io/proxy-scraper/socks5.txt) · [proxies.json](https://maximilianfeix.github.io/proxy-scraper/proxies.json) · [mais formatos](#live-list)

**Quem usa:** a lista de hora em hora é fonte embutida do [monosans/proxy-scraper-checker](https://github.com/monosans/proxy-scraper-checker) e do [gfpcom/free-proxy-list](https://github.com/gfpcom/free-proxy-list).

## As verificações que todo proxy precisa passar

| Verificação | O que significa |
|---|---|
| Handshake de verdade | O proxy precisa completar de fato o protocolo HTTP, SOCKS4 ou SOCKS5 |
| Segunda requisição, o mesmo IP de saída | Uma segunda requisição, a outro site, precisa mostrar o mesmo IP de saída. Proxies que só respondem à primeira verificação, os instáveis e os que trocam de saída falham aqui |
| Conteúdo intacto | Uma página de teste estática precisa chegar byte a byte. O motivo de uma diferença não é determinado |
| HTTPS com certificado verificado | Um proxy só conta como capaz de HTTPS se o certificado TLS recebido pelo túnel dele for válido para o host de teste |
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

Não quer escanear você mesmo? O GitHub Actions roda a ferramenta mais ou menos a cada hora e publica os acertos. Cada proxy da lista passou na primeira requisição, na segunda requisição e na verificação de conteúdo na última execução (o teste de HTTPS é registrado por entrada, mas não é exigido), ordenado por "melhores primeiro": os rápidos, que provavelmente ainda estão no ar, ficam no topo.

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

A verificação é feita dos servidores do GitHub nos EUA. `proxy-scraper --recheck live` baixa a lista e verifica tudo de novo a partir da **sua** rede – bem menos de um minuto em vez de um scan completo. Quantos ainda funcionam a partir da sua rede difere muito do número da própria lista, e é por isso que vale verificar de novo. Acrescente `--serve` e o resultado vira um proxy rotativo.

<a id="pool-api"></a>

## API de pool de proxies: compatível com o jhao104/proxy_pool

Usa o [jhao104/proxy_pool](https://github.com/jhao104/proxy_pool)? Os endpoints, o parâmetro `type=https` e a maioria dos campos JSON (`proxy`, `https`, `region`, `check_count`, `fail_count`, …) são os mesmos – aponte seu código para a porta 8899 e quase tudo continua funcionando (três diferenças: não existe `last_time`, `anonymous` é true/false, não uma string, e `source` é sempre `proxy-scraper`). **Sem Redis**, e cada proxy passou na verificação da segunda requisição e na de conteúdo; os marcados como HTTPS passaram também na de TLS.

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
| `get_proxies` | proxies da lista de hora em hora, como foram verificados na última execução dela – filtráveis por protocolo, país, HTTPS, elite, datacenter, estabilidade, latência |
| `check_proxies` | verifica proxies a partir da sua rede, para que funcionem onde seu código roda |
| `fetch_url` | carrega uma página por um proxy da lista verificada, troca sozinho em caso de erro e devolve texto legível |

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
Quase ninguém mantém um proxy gratuito para você. O que aparece nas listas públicas costuma ser: servidores mal configurados com uma porta aberta sem querer; alguns proxies abertos de propósito; computadores e dispositivos IoT infectados, sem que os donos saibam; e armadilhas – honeypots que registram o tráfego e proxies que reescrevem páginas. Isso é contexto geral, não algo que este projeto mediu: uma verificação não enxerga quem mantém um proxy nem por quê. O proxy-scraper não distingue um roteador doméstico infectado de um proxy de escritório aberto, mas filtra o que dá para medir: duas requisições independentes precisam mostrar o mesmo IP de saída, uma página conhecida precisa chegar byte a byte, e HTTPS só conta com um certificado válido para o host de teste. Bom para dados públicos, para ver um site a partir de outro país, para testar os próprios bloqueios e para pesquisa. Nunca envie senhas, cookies, dados de pagamento ou pessoais por um proxy gratuito.

**Por que encontra menos proxies do que outras listas prometem?**
Porque só ficam os proxies que passam em todas as verificações: duas requisições independentes que mostram o mesmo IP de saída, diferente do seu, e uma página de teste que chega sem alterações. Nas execuções de hora em hora, isso dá cerca de 1 % dos 150.000 candidatos verificados. Eles passaram a partir da rede que os verificou, naquele momento.

**Quase nada passa?**
Muitas redes de empresas, escolas e universidades bloqueiam conexões de proxy. A ferramenta nota uma taxa de acerto abaixo de 0,2 % e avisa – outra rede, como o hotspot do celular, ajuda.

**Funciona no Windows?**
Sim, no PowerShell e no Windows Terminal. O `uvloop` não existe lá e é pulado automaticamente.

**Quão recente é a lista?**
É refeita mais ou menos a cada hora. Proxies gratuitos vêm e vão rápido – para qualquer coisa importante, rode `proxy-scraper --recheck` logo antes de usar.

**Proxies gratuitos são seguros?**
Só para o que não importa. Proxies públicos são mantidos por desconhecidos, que podem ler tudo o que não está criptografado. Não envie senhas nem dados pessoais por eles, e use só onde for permitido.

## Contribuindo

Issues e pull requests são bem-vindos, em português ou inglês. Há [issues para iniciantes](https://github.com/maximilianfeix/proxy-scraper/issues?q=is%3Aopen+label%3A%22good+first+issue%22). Se o proxy-scraper economiza o seu tempo, uma ⭐ ajuda outras pessoas a encontrá-lo.

## Aviso legal

Esta ferramenta só coleta proxies listados publicamente e verifica se funcionam. O uso é responsabilidade sua – respeite os termos dos sites que visita e as leis que valem para você. [Licença MIT](LICENSE).
