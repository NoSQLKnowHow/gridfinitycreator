"""Security headers for every response (SEC-6).

The main one is the Content-Security-Policy. It tells the browser to run scripts and load
styles, fonts, images and data from this server only, and to refuse everything else, inline
scripts included. A script that finds its way into the page by mistake (a field that is not
escaped one day, a stored value that is not checked) is then not run. That is why the page has
no inline scripts or event-handler attributes (tests/test_no_inline_code.py), and no inline
styles (tests/test_security_headers.py).

There is deliberately nothing in the policy that the page does not need: no 'unsafe-inline',
no 'unsafe-eval', no other host, and no upgrade-insecure-requests (an instance on a private
network is served over plain http).
"""

CONTENT_SECURITY_POLICY = "; ".join((
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",          # data: because Bootstrap's own icons are data URIs in its stylesheet
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",        # nobody frames this page (X-Frame-Options says the same to old browsers)
))

HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # Same-origin, not no-referrer: over https Flask-WTF checks the Referer of a form submit against the host
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def parse_hsts_max_age(text):
    """GFG_HSTS_MAX_AGE: how many seconds a browser is told to insist on https for this host, or
       nothing (the default, 0) to say nothing about it.

       It is not on by default because it cannot be taken back: a browser that has been told keeps
       refusing http for this host until the time is up, which locks you out of an instance whose
       https is not working yet (or never will be: one on a private network). Where the proxy
       already sends it, leave this alone."""
    if text is None or not text.strip():
        return 0
    try:
        seconds = int(text)
    except ValueError:
        seconds = -1
    if seconds < 0:
        raise ValueError(f"GFG_HSTS_MAX_AGE: {text!r} is not a number of seconds (0 or more)")
    return seconds


def apply(response, secure, hsts_max_age=0):
    """Add the headers to a response, leaving any a route has set itself. Strict-Transport-Security
       is only ever sent over https (and, behind a proxy, only when the proxy is trusted to say so)."""
    for name, value in HEADERS.items():
        response.headers.setdefault(name, value)
    if secure and hsts_max_age:
        response.headers.setdefault("Strict-Transport-Security", f"max-age={hsts_max_age}")
    return response
