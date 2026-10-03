// proxy-scraper, 2026-10-03 16:47, 30 proxies, best first.
// The browser tries them in order. Local names and private IPv4 addresses go direct; no DIRECT fallback.
var PROXIES = "PROXY 138.68.60.8:3128; PROXY 209.97.150.167:3128; PROXY 198.199.86.11:3128; SOCKS5 107.167.18.122:443; PROXY 147.78.1.156:3128; PROXY 159.203.61.169:3128; SOCKS5 23.95.164.244:1081; PROXY 23.230.253.121:10808; PROXY 134.209.29.120:3128; PROXY 185.73.39.118:9999; PROXY 95.211.174.135:3128; PROXY 54.237.193.47:8888; PROXY 103.237.102.191:11111; SOCKS5 107.174.30.94:1080; PROXY 45.80.37.229:10801; SOCKS5 54.237.193.47:8888; SOCKS5 107.174.30.92:1080; SOCKS5 185.73.39.118:9999; PROXY 161.35.70.249:80; PROXY 184.75.221.82:3118; PROXY 128.199.202.122:8080; SOCKS5 193.25.215.182:22222; PROXY 43.173.120.13:8899; SOCKS5 207.180.207.217:10808; PROXY 186.208.50.105:3128; PROXY 139.59.1.14:8080; SOCKS5 199.102.105.242:4145; SOCKS5 199.116.114.11:4145; SOCKS5 107.181.161.81:4145; SOCKS5 107.181.168.145:4145";

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
