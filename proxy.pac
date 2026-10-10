// proxy-scraper, 2026-10-10 19:32, 30 proxies, best first.
// The browser tries them in order. Local names and private IPv4 addresses go direct; no DIRECT fallback.
var PROXIES = "PROXY 138.68.60.8:3128; SOCKS5 193.25.215.182:22222; PROXY 209.97.150.167:3128; PROXY 198.199.86.11:3128; SOCKS5 52.128.241.106:1080; PROXY 159.203.61.169:3128; SOCKS5 83.147.217.103:1080; PROXY 139.162.78.109:8080; PROXY 134.209.29.120:3128; PROXY 161.35.70.249:80; SOCKS5 129.153.11.56:1080; PROXY 128.199.202.122:8080; PROXY 103.237.102.191:11111; PROXY 139.59.1.14:8080; PROXY 103.88.234.239:40005; SOCKS5 47.252.47.39:1080; PROXY 116.196.150.180:17981; PROXY 103.88.234.239:40017; PROXY 27.185.218.213:17981; PROXY 120.232.115.170:17981; PROXY 103.88.234.239:40002; SOCKS5 164.68.114.118:1080; PROXY 167.99.8.113:8011; SOCKS5 185.197.251.16:9050; SOCKS5 5.255.117.127:1080; SOCKS5 183.106.215.208:1080; SOCKS5 103.88.234.239:40005; SOCKS5 103.88.234.239:40017; PROXY 39.106.170.168:8080; SOCKS5 103.75.118.84:1080";

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
