// proxy-scraper, 2026-11-28 16:28, 30 proxies, best first.
// The browser tries them in order. Local names and private IPv4 addresses go direct; no DIRECT fallback.
var PROXIES = "SOCKS5 69.55.49.177:38182; PROXY 216.125.18.67:3128; PROXY 47.87.9.77:443; SOCKS5 183.106.215.208:1080; SOCKS5 121.169.46.116:1090; PROXY 103.133.26.50:8080; SOCKS5 43.108.84.178:1080; PROXY 103.237.102.191:11111; PROXY 47.98.219.185:8999; SOCKS5 216.105.128.144:4145; SOCKS5 199.66.183.251:4145; SOCKS5 199.66.182.232:4145; SOCKS5 216.105.130.131:4145; PROXY 34.43.46.91:443; PROXY 80.90.178.167:1081; PROXY 103.133.26.73:3128; PROXY 103.133.26.72:8080; SOCKS5 184.182.240.211:4145; SOCKS5 216.105.143.146:4145; PROXY 109.111.179.214:10808; PROXY 103.133.26.119:8080; SOCKS5 208.102.51.6:58208; SOCKS5 45.194.33.12:30001; SOCKS5 45.194.33.12:30002; SOCKS5 216.68.128.121:4145; SOCKS5 72.49.49.11:31034; SOCKS5 109.111.179.214:10808; PROXY 5.252.155.29:3128; SOCKS5 69.61.200.104:36181; SOCKS5 184.178.172.25:15291";

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
