// proxy-scraper, 2026-10-17 21:30, 30 proxies, best first.
// The browser tries them in order. Local names and private IPv4 addresses go direct; no DIRECT fallback.
var PROXIES = "SOCKS5 107.174.30.94:1080; SOCKS5 107.174.30.93:1080; SOCKS5 23.95.164.244:1081; PROXY 103.237.102.191:11111; SOCKS5 107.174.30.92:1080; SOCKS5 38.49.210.79:40000; SOCKS5 45.61.188.134:44499; SOCKS5 93.99.104.47:1080; SOCKS5 62.83.34.101:1080; SOCKS5 193.25.215.182:22222; SOCKS5 148.230.91.52:1080; SOCKS5 62.83.33.70:1080; PROXY 3.211.120.181:443; SOCKS5 192.141.74.246:1088; PROXY 120.232.115.170:17981; SOCKS5 217.142.236.180:1080; SOCKS5 13.90.182.199:3001; PROXY 91.107.247.193:7001; PROXY 106.14.104.209:8080; SOCKS5 172.171.169.205:3000; SOCKS5 47.238.126.208:1080; SOCKS5 43.245.199.34:1080; PROXY 45.125.64.215:443; SOCKS5 144.24.111.128:1088; PROXY 114.55.168.172:8080; SOCKS5 143.198.90.221:1088; PROXY 27.185.218.213:17981; SOCKS5 57.129.182.181:1080; SOCKS5 199.66.182.232:4145; SOCKS5 184.185.2.12:4145";

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
