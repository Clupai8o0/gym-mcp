"""Minimal, self-contained HTML for the API-origin system pages (login/consent/errors).

These are the *authorization server's* own pages, not the flagship Next.js app — so they use
a small neutral, dependency-free stylesheet (no external assets) rather than the docs/08
design system. All dynamic values are escaped with :func:`markupsafe.escape`-equivalent
``html.escape`` since some (client name, scopes) originate from a registered client.
"""

from __future__ import annotations

import html

from fastapi.responses import HTMLResponse

_STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  margin: 0; min-height: 100vh; display: grid; place-items: center;
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: #0b0b0c; color: #ededed; padding: 24px;
}
@media (prefers-color-scheme: light) { body { background: #f6f6f7; color: #16161a; } }
main {
  width: 100%; max-width: 27rem; background: rgba(127,127,127,.08);
  border: 1px solid rgba(127,127,127,.22); border-radius: 16px; padding: 28px 26px;
}
h1 { font-size: 1.2rem; margin: 0 0 .5rem; letter-spacing: -.01em; }
p { margin: 0 0 1rem; color: #a9a9ad; }
@media (prefers-color-scheme: light) { p { color: #5b5b60; } }
ul.scopes { list-style: none; padding: 0; margin: 0 0 1.25rem; }
ul.scopes li { padding: 10px 12px; border: 1px solid rgba(127,127,127,.22);
  border-radius: 10px; margin-bottom: 8px; display: flex; gap: 10px; align-items: baseline; }
ul.scopes b { font-weight: 600; }
.actions { display: flex; gap: 10px; margin-top: 4px; }
button {
  font: inherit; font-weight: 600; border-radius: 10px; padding: 11px 16px; cursor: pointer;
  border: 1px solid transparent; flex: 1;
}
button.approve { background: #4f7cff; color: #fff; }
button.approve:hover { background: #3d6bf0; }
button.deny { background: transparent; color: inherit; border-color: rgba(127,127,127,.35); }
button:focus-visible { outline: 2px solid #4f7cff; outline-offset: 2px; }
.brand { font-size: .8rem; text-transform: uppercase; letter-spacing: .12em;
  color: #7a7a80; margin: 0 0 1.25rem; }
""".strip()


def _document(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head>"
        f"<body><main>{body}</main></body></html>"
    )


def error_page(title: str, message: str, *, status: int) -> HTMLResponse:
    """A neutral error page (used for non-redirectable auth/OAuth failures)."""
    body = (
        '<p class="brand">Tempo</p>'
        f"<h1>{html.escape(title)}</h1>"
        f"<p>{html.escape(message)}</p>"
    )
    return HTMLResponse(_document(title, body), status_code=status)


# Human-readable descriptions for each grantable scope (shown on the consent screen).
_SCOPE_DESCRIPTIONS = {
    "workouts.read": "Read your workouts, exercises, and progress",
    "workouts.write": "Log and update workouts, sets, and personal records",
}


def consent_page(*, client_name: str | None, scope: str, approval: str) -> HTMLResponse:
    """The OAuth consent screen: what the client is asking for + approve/deny (docs/05 B3).

    ``approval`` is an opaque HMAC-signed token binding this request to the logged-in user;
    it is the CSRF protection for the consent POST (a forged POST cannot supply a valid one),
    reinforced by the ``SameSite=Lax`` session cookie.
    """
    name = client_name or "An application"
    items = "".join(
        f"<li><b>+</b><span>{html.escape(_SCOPE_DESCRIPTIONS.get(s, s))}</span></li>"
        for s in scope.split()
    )
    body = (
        '<p class="brand">Tempo</p>'
        f"<h1>{html.escape(name)} wants to connect</h1>"
        "<p>Allow it to act on your Tempo account with these permissions?</p>"
        f'<ul class="scopes">{items}</ul>'
        '<form method="post" action="/oauth/authorize/consent">'
        f'<input type="hidden" name="approval" value="{html.escape(approval)}">'
        '<div class="actions">'
        '<button class="deny" type="submit" name="decision" value="deny">Deny</button>'
        '<button class="approve" type="submit" name="decision" value="approve">Allow</button>'
        "</div></form>"
    )
    return HTMLResponse(_document(f"Connect {name} — Tempo", body))
