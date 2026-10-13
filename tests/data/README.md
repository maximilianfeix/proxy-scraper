Self-signed certificate for `localhost` / `127.0.0.1` – **for the tests only** (local HTTPS target server).
It isn't trusted anywhere and protects nothing, which is why the key is deliberately in the repo.

A second pair, `untrusted-*.pem`, is the same thing with one difference: no test trusts it. It plays a proxy
that breaks up TLS (a certificate that does not verify).
