// proxy-scraper, 2026-11-07 20:25, 30 proxies, best first.
// The browser tries them in order. Local names and private IPv4 addresses go direct; no DIRECT fallback.
var PROXIES = "SOCKS5 45.76.66.251:11080; PROXY 47.254.31.207:1080; SOCKS5 193.25.215.182:22222; PROXY 162.35.110.218:8080; PROXY 103.237.102.191:11111; PROXY 158.173.80.27:8888; SOCKS5 216.105.143.146:4145; SOCKS5 158.173.80.27:8888; PROXY 103.133.26.73:3128; PROXY 103.133.26.50:8080; PROXY 103.133.26.11:8080; SOCKS5 199.66.183.226:4145; SOCKS5 199.66.182.232:4145; SOCKS5 212.77.75.25:1088; SOCKS5 66.42.224.229:41679; SOCKS5 208.102.51.6:58208; SOCKS5 69.61.200.104:36181; SOCKS5 3.147.12.96:1080; SOCKS5 107.174.30.92:1080; SOCKS5 184.182.240.211:4145; PROXY 103.133.26.72:8080; PROXY 103.133.26.119:8080; SOCKS5 216.105.128.144:4145; SOCKS5 199.66.183.251:4145; SOCKS5 72.49.49.11:31034; SOCKS5 216.68.128.121:4145; SOCKS5 69.206.61.125:1080; SOCKS5 209.50.255.91:1080; SOCKS5 45.74.31.42:6801; SOCKS5 5.255.117.127:1080";

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
