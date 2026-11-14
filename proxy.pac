// proxy-scraper, 2026-11-14 19:29, 30 proxies, best first.
// The browser tries them in order. Local names and private IPv4 addresses go direct; no DIRECT fallback.
var PROXIES = "SOCKS5 107.174.30.93:1080; SOCKS5 107.174.30.92:1080; SOCKS5 107.174.30.94:1080; SOCKS5 193.25.215.182:22222; SOCKS5 199.66.182.243:4145; SOCKS5 216.105.143.146:4145; SOCKS5 216.105.130.131:4145; PROXY 103.237.102.191:11111; PROXY 106.14.104.209:8080; SOCKS5 208.102.51.6:58208; SOCKS5 216.68.128.121:4145; PROXY 188.166.178.163:3129; SOCKS5 184.182.240.211:4145; SOCKS5 66.42.224.229:41679; SOCKS5 113.249.111.67:1080; SOCKS5 199.66.183.226:4145; SOCKS5 199.66.183.251:4145; SOCKS5 199.66.182.232:4145; SOCKS5 72.49.49.11:31034; SOCKS5 91.199.137.149:2000; SOCKS5 68.233.127.229:1080; SOCKS5 45.74.31.47:4738; SOCKS5 201.34.153.217:1080; SOCKS5 45.74.31.47:4691; SOCKS5 202.61.239.148:8383; SOCKS5 184.185.2.12:4145; SOCKS5 47.103.30.64:1080; SOCKS5 39.106.170.168:1080; SOCKS5 45.74.31.47:4773; SOCKS5 39.106.165.196:1080";

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
