// proxy-scraper, 2026-10-31 22:26, 30 proxies, best first.
// The browser tries them in order. Local names and private IPv4 addresses go direct; no DIRECT fallback.
var PROXIES = "SOCKS5 107.174.30.92:1080; SOCKS5 45.61.188.134:44499; PROXY 103.237.102.191:11111; SOCKS5 193.25.215.182:22222; SOCKS5 67.207.92.87:1088; PROXY 184.75.221.82:3118; PROXY 34.43.46.91:80; SOCKS5 184.182.240.12:4145; PROXY 120.232.115.170:17981; SOCKS5 184.185.2.12:4145; SOCKS5 184.182.240.211:4145; SOCKS5 216.105.143.146:4145; SOCKS5 72.49.49.11:31034; SOCKS5 216.68.128.121:4145; SOCKS5 66.42.224.229:41679; SOCKS5 208.102.51.6:58208; PROXY 120.232.115.57:17981; SOCKS5 216.105.130.131:4145; SOCKS5 199.66.183.226:4145; PROXY 103.133.26.11:8080; SOCKS5 69.61.200.104:36181; PROXY 103.133.26.73:3128; SOCKS5 217.71.230.103:1080; PROXY 103.133.26.72:8080; PROXY 27.185.218.213:17981; SOCKS5 47.238.126.208:1080; SOCKS5 199.66.183.251:4145; PROXY 103.133.26.119:8080; PROXY 80.74.30.136:31286; SOCKS5 45.74.31.47:15943";

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
