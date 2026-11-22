"""IndexNow pour Parole de RH (Bing, Yandex, Seznam, Naver...).

Deux commandes :
  python3 indexnow.py diff public urls.txt [--all]
      Compare le sitemap en ligne (avant deploiement) avec celui qui vient d'etre
      genere dans public/ et ecrit dans urls.txt les adresses nouvelles, modifiees
      (lastmod different) ou supprimees. --all ecrit toutes les adresses.
  python3 indexnow.py submit urls.txt
      Envoie la liste a IndexNow (a lancer APRES le deploiement).
"""
import json
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

SITE = "https://parole-de-rh.fr"
HOST = "parole-de-rh.fr"
KEY = "6b447744029c68dba158dc292452d414"
ENDPOINT = "https://api.indexnow.org/indexnow"
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def parse(xml_bytes):
    root = ET.fromstring(xml_bytes)
    return root


def read_live(path):
    url = f"{SITE}{path}?nocache={int(time.time())}"
    req = urllib.request.Request(url, headers={"User-Agent": "parole-de-rh-indexnow"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def read_local(public, path):
    with open(os.path.join(public, path.lstrip("/")), "rb") as f:
        return f.read()


def collect(reader):
    """Renvoie {url: lastmod} en suivant l'index de sitemaps."""
    pages = {}
    index = parse(reader("/sitemap.xml"))
    children = [s.findtext(f"{NS}loc") for s in index.findall(f"{NS}sitemap")]
    if not children:  # sitemap simple, sans index
        trees = [index]
    else:
        trees = [parse(reader(urlparse(loc).path)) for loc in children]
    for tree in trees:
        for u in tree.findall(f"{NS}url"):
            loc = (u.findtext(f"{NS}loc") or "").strip()
            if loc:
                pages[loc] = (u.findtext(f"{NS}lastmod") or "").strip()
    return pages


def diff(public, out, submit_all):
    new = collect(lambda p: read_local(public, p))
    if submit_all:
        urls = sorted(new)
    else:
        try:
            old = collect(read_live)
        except Exception as e:  # site injoignable : on n'envoie rien plutot que tout
            print(f"Sitemap en ligne illisible ({e}), aucune adresse envoyee.")
            old = None
        if old is None:
            urls = []
        else:
            changed = [u for u, m in new.items() if old.get(u) != m]
            removed = [u for u in old if u not in new]
            urls = sorted(set(changed + removed))
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(urls))
    print(f"{len(urls)} adresse(s) a envoyer a IndexNow :")
    for u in urls[:50]:
        print("  " + u)


def submit(path):
    with open(path, encoding="utf-8") as f:
        urls = [l.strip() for l in f if l.strip().startswith(SITE)]
    if not urls:
        print("Rien a envoyer.")
        return
    for i in range(0, len(urls), 10000):
        body = json.dumps({
            "host": HOST,
            "key": KEY,
            "keyLocation": f"{SITE}/{KEY}.txt",
            "urlList": urls[i:i + 10000],
        }).encode("utf-8")
        req = urllib.request.Request(
            ENDPOINT, data=body, method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                print(f"IndexNow : HTTP {r.status} pour {len(urls[i:i + 10000])} adresse(s)")
        except urllib.error.HTTPError as e:
            # 200/202 = recu. 403 = cle non trouvee, 422 = adresses hors du domaine, 429 = trop d'envois
            print(f"IndexNow : HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}")
            sys.exit(1)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "diff":
        diff(sys.argv[2], sys.argv[3], "--all" in sys.argv)
    elif cmd == "submit":
        submit(sys.argv[2])
