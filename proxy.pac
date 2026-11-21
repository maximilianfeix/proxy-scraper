// proxy-scraper, 2026-11-21 20:30, 30 proxies, best first.
// The browser tries them in order. Local names and private IPv4 addresses go direct; no DIRECT fallback.
var PROXIES = "SOCKS5 69.55.49.177:38182; SOCKS5 193.25.215.182:22222; PROXY 18.222.225.236:3128; SOCKS5 107.174.30.94:1080; PROXY 103.237.102.191:11111; PROXY 140.238.32.108:3128; PROXY 50.238.106.26:3128; SOCKS5 199.66.183.251:4145; SOCKS5 216.105.130.131:4145; SOCKS5 199.66.183.226:4145; SOCKS5 216.105.143.146:4145; SOCKS5 23.191.176.193:1080; SOCKS5 216.105.128.144:4145; SOCKS5 199.66.182.243:4145; SOCKS5 199.66.182.232:4145; SOCKS5 208.102.51.6:58208; PROXY 106.14.104.209:8080; SOCKS5 72.49.49.11:31034; SOCKS5 66.42.224.229:41679; SOCKS5 216.68.128.121:4145; SOCKS5 69.61.200.104:36181; PROXY 216.125.18.67:3128; PROXY 114.55.168.172:8080; SOCKS5 219.78.223.199:5001; SOCKS5 112.74.105.64:10808; SOCKS5 209.50.255.91:1080; SOCKS5 184.182.240.12:4145; SOCKS5 47.76.227.81:6002; PROXY 223.70.110.3:24900; SOCKS5 184.185.2.12:4145";

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
