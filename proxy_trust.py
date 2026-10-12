"""Which reverse proxies this server believes (SEC-8).

A reverse proxy in front of the app (Traefik, nginx, ...) ends the visitor's HTTPS connection and
talks to the app over plain HTTP, so the app cannot see who the visitor was or how they connected.
The proxy passes that on in X-Forwarded-* headers: the visitor's address, whether it was https,
and the host name that was asked for.

Those headers are only worth believing when the proxy sent them. Anyone who can reach the app
directly can send the same headers and be taken for another address (the log then says whatever
they like), or for a secure connection. So nothing is believed unless GFG_TRUSTED_PROXIES names
the proxy's address (or the network it is on); headers from any other peer are removed before
the app sees them. X-Forwarded-Prefix is never believed: the app does not run under a path prefix.

Waitress has a setting for this too, but it takes a single address and the proxy's address in a
Docker network is not fixed, so the check is made here, against addresses and networks.
"""

import ipaddress

from werkzeug.middleware.proxy_fix import ProxyFix

# The headers the app uses, when they come from a proxy it trusts
HONOURED = ("HTTP_X_FORWARDED_FOR", "HTTP_X_FORWARDED_PROTO", "HTTP_X_FORWARDED_HOST")

# Never used, from anybody; removed so that nothing downstream can mistake them for something
# that was checked. (Waitress throws the others away by itself, but passes X-Forwarded-Prefix on.)
NEVER_HONOURED = ("HTTP_FORWARDED", "HTTP_X_FORWARDED_PORT", "HTTP_X_FORWARDED_PREFIX", "HTTP_X_FORWARDED_BY")


def parse_proxies(text):
    """The addresses and networks in GFG_TRUSTED_PROXIES: a comma-separated list such as
       "172.18.0.2" or "172.18.0.0/16, 10.0.0.5". Nothing (unset, empty) means no proxy is trusted.

       A typo stops the server from starting, rather than being ignored: a proxy that was meant
       to be trusted and is not would show up only as wrong addresses in the log."""
    networks = []
    for item in (text or "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            raise ValueError(f"GFG_TRUSTED_PROXIES: {item!r} is not an IP address or network "
                             "(write something like 172.18.0.2 or 172.18.0.0/16)") from None
    return tuple(networks)


def parse_hops(text):
    """GFG_PROXY_HOPS: how many proxies the request passed through before it reached the app
       (default 1). Each one adds the address it received the request from to X-Forwarded-For;
       only the last this many entries are believed, so what the visitor wrote themselves is not."""
    if text is None or not text.strip():
        return 1
    try:
        hops = int(text)
    except ValueError:
        hops = 0
    if hops < 1:
        raise ValueError(f"GFG_PROXY_HOPS: {text!r} is not a whole number of at least 1")
    return hops


def server_options(trusted):
    """Keyword arguments for waitress.serve(). Waitress removes X-Forwarded-For, -Proto and -Host
       before the app sees them unless told otherwise; with a proxy to believe they have to arrive,
       so that this module can judge them."""
    return {"clear_untrusted_proxy_headers": False} if trusted else {}


class ProxyTrust:
    """WSGI middleware: believe the X-Forwarded-* headers of the trusted proxies, and nobody else's"""

    def __init__(self, app, trusted=(), hops=1):
        self.app = app
        self.configure(trusted, hops)

    def configure(self, trusted, hops=1):
        self.trusted = tuple(trusted)
        self.hops = hops
        self._fix = ProxyFix(self.app, x_for=hops, x_proto=hops, x_host=hops, x_port=0, x_prefix=0)

    def is_trusted(self, address):
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        return any(ip in network for network in self.trusted if network.version == ip.version)

    def __call__(self, environ, start_response):
        if self.is_trusted(environ.get("REMOTE_ADDR", "")):
            for name in NEVER_HONOURED:
                environ.pop(name, None)
            return self._fix(environ, start_response)
        for name in HONOURED + NEVER_HONOURED:
            environ.pop(name, None)
        return self.app(environ, start_response)
