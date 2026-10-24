// proxy-scraper, 2026-10-24 20:33, 30 proxies, best first.
// The browser tries them in order. Local names and private IPv4 addresses go direct; no DIRECT fallback.
var PROXIES = "SOCKS5 69.55.49.177:38182; SOCKS5 129.146.121.2:10808; PROXY 184.75.221.82:3118; SOCKS5 107.174.30.92:1080; SOCKS5 172.245.108.219:11080; PROXY 64.118.155.2:22222; PROXY 167.99.8.113:8008; SOCKS5 193.25.215.182:22222; PROXY 103.237.102.191:11111; PROXY 120.232.115.57:17981; SOCKS5 166.1.90.114:1090; SOCKS5 103.230.142.150:1080; SOCKS5 103.230.142.152:1080; SOCKS5 183.106.215.208:1080; SOCKS5 51.15.20.32:1088; PROXY 103.133.26.50:8080; SOCKS5 209.50.255.91:1080; PROXY 146.190.60.147:8008; PROXY 103.133.26.11:8080; SOCKS5 2.24.117.176:1080; PROXY 114.55.168.172:8080; SOCKS5 216.105.130.131:4145; SOCKS5 103.100.158.115:10809; PROXY 47.104.159.229:8080; SOCKS5 184.182.240.211:4145; SOCKS5 184.185.2.12:4145; SOCKS5 184.182.240.12:4145; SOCKS5 89.58.42.118:3129; SOCKS5 143.198.90.221:1088; SOCKS5 208.102.51.6:58208";

function isLocal(host) {
  if (isPlainHostName(host) || host === "localhost" ||
      shExpMatch(host, "*.localhost") || shExpMatch(host, "*.local")) {
    return true;
  }
  var ip = /^(\d{1,3})\.(\d{1,3})\.\d{1,3}\.\d{1,3}$/.exec(host);
  if (!ip) {
    return false;
  }
  var a = parseInt(ip[1], 10), b = parseInt(ip[2], 10);
  return a === 127 || a === 10 || (a === 192 && b === 168) || (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31);
}

function FindProxyForURL(url, host) {
  return isLocal(host) ? "DIRECT" : PROXIES;
}
