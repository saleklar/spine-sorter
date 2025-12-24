#!/usr/bin/env python3
"""Headless test to fetch Spine versions (no GUI)."""
import ssl
import urllib.request
import urllib.parse
import re

base_urls = [
    'https://hr.esotericsoftware.com/spine-changelog/archive',
    'https://esotericsoftware.com/spine-changelog/archive',
]

def fetch_url(u, timeout=10):
    last_err = None
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(u, timeout=timeout, context=ctx) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception as e1:
        last_err = e1
        try:
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(u, timeout=timeout, context=ctx) as r:
                return r.read().decode('utf-8', errors='ignore')
        except Exception as e2:
            last_err = e2
            if u.startswith('https://'):
                http_u = 'http://' + u[len('https://'):]
                try:
                    with urllib.request.urlopen(http_u, timeout=timeout) as r:
                        return r.read().decode('utf-8', errors='ignore')
                except Exception as e3:
                    last_err = e3
    raise last_err or RuntimeError('fetch failed')

collected = set()
monthly_urls = []
for base in base_urls:
    try:
        html = fetch_url(base)
        if not html:
            continue
        for v in re.findall(r"\b(\d+\.\d+(?:\.\d+)?)\b", html):
            collected.add(v)
        for m in re.findall(r'href=["\']([^"\']*spine-changelog/\d{4}/\d{2}[^"\']*)', html, flags=re.IGNORECASE):
            u = urllib.parse.urljoin(base, m)
            if u not in monthly_urls:
                monthly_urls.append(u)
    except Exception as e:
        print('Archive host fetch failed:', base, '->', e)

for mu in monthly_urls:
    try:
        h = fetch_url(mu)
        if not h:
            continue
        for v in re.findall(r"\b(\d+\.\d+(?:\.\d+)?)\b", h):
            collected.add(v)
    except Exception as e:
        print('Monthly fetch failed:', mu, '->', e)

try:
    root = 'https://hr.esotericsoftware.com/spine-changelog/'
    r = fetch_url(root)
    for v in re.findall(r"\b(\d+\.\d+(?:\.\d+)?)\b", r):
        collected.add(v)
except Exception:
    pass

def ver_key(s):
    parts = [int(x) for x in s.split('.')[:3]]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)

vers = sorted({v for v in collected if re.match(r'^\d+\.\d+(?:\.\d+)?$', v)}, key=ver_key, reverse=True)
print('Found versions:', len(vers))
for v in vers:
    print(v)
