#!/usr/bin/env python3
"""
Mirrors Studio: the line art and wall art sold on Redbubble and Zazzle, as a
shop on www.mirrorsphoto.com/art (this repo, kirwana/art, served by GitHub
Pages under the domain the main site already has).

Pinterest takes a catalogue only from the website the account has claimed, so
every design gets a page here (d/<id>.html: its pictures, a price from, and
buttons to Redbubble and Zazzle) and catalog.csv is the feed Pinterest reads.
One listing per design, not per product: a mug and a tee of the same drawing
would be near-duplicate pins.

Run from this folder:  /usr/bin/python3 tools/build.py
It reads Print Kit's records of what is live (~/Projects/etsy/print-templates,
redbubble-items.json and zazzle-items.json) and the artwork on the WDBLACK
drive. Pictures already made are kept, so a build without the drive still
works for designs it has seen before; a new design without its artwork waits.
"""
import csv
import hashlib
import html
import json
import os
import re
import shutil

from PIL import Image, ImageDraw

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = os.path.expanduser("~/Projects/etsy/print-templates")
BASE = "https://www.mirrorsphoto.com/art"
MAIN = "https://www.mirrorsphoto.com"
RB_SHOP = "https://www.redbubble.com/people/MirrorsFineArt/shop"
ZZ_SHOP = "https://www.zazzle.com/store/mirrorsfineart"
VERIFY = '<meta name="p:domain_verify" content="db7d2a24295a67bc265e4a4397112539"/>'
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght,SOFT@9..144,300..600,100'
         '&family=Figtree:wght@400;500;600&display=swap">')
CSS_V = hashlib.sha1(open(os.path.join(SITE, "style.css"), "rb").read()).hexdigest()[:8]

# regular prices (not sale prices), read from the sites on 3 Nov 2026: the
# cheapest product of each kind. "From" on the page and the price in the feed.
PRICE = {"line": (3.49, "AUD", "Redbubble sticker"), "wall": (12.82, "AUD", "Redbubble poster"),
         "zz_line": (2.53, "USD", "Zazzle sticker"), "zz_wall": (48.15, "USD", "Zazzle poster")}

# ranges, in the order shown. A design goes in the first range whose words are
# in its title, else in its tags. Whole words only ("star" is not "starfish"),
# and the title's "with Orange Ball" kind of ending is left out: that's the
# colour accent, not the subject.
RANGES = [
    ("wall", "Forest wall art", "#c9d6c3", r"misty (oak|birch|forest)"),
    ("more", "More line art", "#d9d4cb", r"guitar|music|dancing|robot"),     # before their accents' words
    ("christmas", "Christmas", "#e59a8f", r"christmas|holly|stocking|reindeer|snowman|gingerbread|ornament|xmas"),
    ("coastal", "Coastal & ocean", "#a9cbe6", r"coastal|ocean|beach|whale|whale tail|dolphin|shark|turtle|sailboat|anchor|"
                                              r"crab|seahorse|starfish|shell|jellyfish|lighthouse|wave|sand dollar|fish"),
    ("flowers", "Flowers", "#f2b6b0", r"flower|rose|tulip|daisy|daisies|poppy|poppies|lily|lilies|iris|peony|peonies|anemone|"
                                     r"lavender|sunflower|magnolia|cosmos|camellia|orchid|lotus|bluebell|cornflower|"
                                     r"ranunculus|hydrangea|blossom|snowdrop|foxglove"),
    ("celestial", "Celestial & space", "#c4b8e6", r"celestial|moon|sun|star|planet|saturn|rocket|alien|ufo|saucer|telescope|"
                                                  r"comet|eclipse|astronaut|galaxy|zodiac|pisces|rainbow|constellation"),
    ("fruit", "Fruit & food", "#f4d27c", r"fruit|cherry|cherries|pear|apple|banana|strawberry|strawberries|pineapple|orange|"
                                         r"avocado|peach|lemon|coffee|watermelon"),
    ("animals", "Animals & pets", "#b9d9b4", r"cat|kitten|dog|puppy|gecko|chick|elephant|owl|penguin|snail|bunny|rabbit|bird|"
                                            r"songbird|monkey|chimpanzee|ape|gorilla|bee|bumblebee|hummingbird|fox|bear|lion|sea lion|animal|pet"),
    ("more", "More line art", "#d9d4cb", r""),
]
RANGE = {k: (name, colour) for k, name, colour, _ in RANGES}
ORDER = ["flowers", "celestial", "coastal", "animals", "fruit", "christmas", "wall", "more"]   # the shop's chips

PAPER = (245, 246, 241)      # the pictures' background: the page's own paper


# ------------------------------------------------------------------ designs

def _items(key):
    try:
        with open(os.path.join(KIT, "%s-items.json" % key)) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _urls(it):
    urls = it.get("site_urls") or ([it["site_url"]] if it.get("site_url") else [])
    return [u for u in urls if u]


def _zazzle_names():
    # Print Kit's own names for Zazzle's product codes (Mug, Tote Bag...)
    import sys
    sys.path.insert(0, KIT)
    try:
        import art_sites
        import site_zazzle  # noqa: F401  registers the site
        return {c: n for c, n, _ in art_sites.site("zazzle").catalogue}
    except Exception:
        return {}


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:70]


def designs():
    """Every design live on Redbubble or Zazzle, one entry each, keyed by the
    picture Print Kit uploaded (the same file on both sites)."""
    names = _zazzle_names()
    out = {}
    for key in ("redbubble", "zazzle"):
        for p, it in _items(key).items():
            urls = _urls(it)
            if not urls:
                continue
            if "/Line Art/" in p:
                kind, folder = "line", os.path.dirname(os.path.dirname(p))
            elif "/Own Art/" in p:
                kind, folder = "wall", None
            else:
                continue          # Etsy photographs: those are the main site's
            d = out.setdefault(p, {"path": p, "kind": kind, "folder": folder, "rb": None, "zz": []})
            for f in ("title", "description", "keywords"):
                if it.get(f) and not d.get(f):
                    d[f] = it[f]
            if key == "redbubble":
                m = re.search(r"/(\d{6,})", urls[0])
                if m:
                    d["rb"] = "https://www.redbubble.com/shop/ap/%s" % m.group(1)
            else:
                prods = it.get("site_products") or {}
                for u in urls:
                    d["zz"].append({"url": u, "name": names.get(prods.get(u), "Product")})
                d["zz_page"] = it.get("site_page") or urls[0]
    ds = []
    for d in out.values():
        d["title"] = (d.get("title") or os.path.basename(d["path"])).strip()
        d["description"] = (d.get("description") or "").strip().strip('"').strip()
        if d["folder"]:
            base = os.path.basename(d["folder"])
            d["id"] = slug(base)
            js = os.path.join(d["folder"], "design.json")
            try:
                with open(js) as fh:
                    d["created"] = json.load(fh).get("created") or 0
            except (OSError, ValueError):
                d["created"] = 0
        else:
            d["id"] = slug(os.path.splitext(os.path.basename(d["path"]))[0])
            try:
                d["created"] = os.path.getmtime(d["path"])
            except OSError:
                d["created"] = 0
        d["range"] = range_of(d)
        ds.append(d)
    ds.sort(key=lambda d: -d["created"])
    return ds


def range_of(d):
    name, _, rest = d["title"].partition(",")
    name = re.sub(r"\bwith\b.*$", "", name, flags=re.I)
    # the drawing's name, then its set ("Boho Celestial"), then its tags
    for words in (name, rest, d.get("keywords") or ""):
        for k, _, _, rx in RANGES:
            if rx and re.search(r"\b(%s)s?\b" % rx, words, re.I):
                return k
    return "more"


def name_of(d):
    """The drawing's name, and the rest of the title (its set)."""
    t = re.sub(r"\s+(minimalist\s+)?(one[- ]line art|line art)\b", "", d["title"], flags=re.I)
    head, _, rest = t.partition(",")
    return head.strip(), rest.strip()


def price(d):
    if d["kind"] == "wall":
        return PRICE["wall"] if d["rb"] else PRICE["zz_wall"]
    return PRICE["line"] if d["rb"] else PRICE["zz_line"]


def money(d):
    amt, cur, _ = price(d)
    return "From %s%.2f" % ("A$" if cur == "AUD" else "US$", amt)


# ------------------------------------------------------------------ pictures

def _flat(im, size, pad):
    """A transparent drawing centred on the page's paper, as a square."""
    im = im.convert("RGBA")
    bb = im.getbbox()
    if bb:
        im = im.crop(bb)
    inner = int(size * (1 - 2 * pad))
    im.thumbnail((inner, inner), Image.LANCZOS)
    c = Image.new("RGB", (size, size), PAPER)
    c.paste(im, ((size - im.width) // 2, (size - im.height) // 2), im)
    return c


def pictures(d):
    """The design's pictures in images/, made once from the artwork; their
    names, the first being the main one. [] when none can be made yet."""
    out, idir = [], os.path.join(SITE, "images", "d")
    os.makedirs(idir, exist_ok=True)

    def make(name, fn):
        path = os.path.join(idir, name)
        if not os.path.isfile(path):
            try:
                fn().save(path, quality=86, optimize=True, progressive=True)
            except (OSError, ValueError):
                return
        out.append("images/d/" + name)

    if d["kind"] == "wall":
        def wall():
            im = Image.open(d["path"]).convert("RGB")
            im.thumbnail((1800, 1800), Image.LANCZOS)
            return im
        make(d["id"] + ".jpg", wall)
        return out
    f = d["folder"]
    base = os.path.basename(f)
    art = os.path.join(f, "art.png")
    if not os.path.isfile(art):
        art = os.path.join(f, "Files", base + "_art.png")
    d["art"] = art
    make(d["id"] + ".jpg", lambda: _flat(Image.open(art), 1400, .1))
    make(d["id"] + "-sticker.jpg", lambda: Image.open(os.path.join(f, "_preview_sticker.png")).convert("RGB"))
    tees = sorted(x for x in os.listdir(f) if x.startswith("_preview_tee")) if os.path.isdir(f) else []
    if tees:
        make(d["id"] + "-tee.jpg", lambda: Image.open(os.path.join(f, tees[-1])).convert("RGB"))
    return out


def banner(ds):
    """The home page's banner: a row of the drawings, one from each range in
    turn, each on its own colour shape. Delete images/banner.jpg to remake it."""
    path = os.path.join(SITE, "images", "banner.jpg")
    picks, seen = [], set()
    for k in ("flowers", "celestial", "coastal", "animals", "fruit", "coastal", "flowers"):
        # one of each subject: the gecko comes in four colours
        d = next((x for x in ds if x["range"] == k and x["kind"] == "line" and name_of(x)[0].split()[-1] not in seen
                  and x.get("pics") and os.path.isfile(x.get("art") or "")), None)
        if d:
            seen.add(name_of(d)[0].split()[-1])
            picks.append(d)
    if os.path.isfile(path) or not picks:
        return
    S = 2
    W, H = 3000 * S, 600 * S
    c = Image.new("RGB", (W, H), PAPER)
    n = len(picks)
    cell = W / n
    for i, d in enumerate(picks):
        rgba = Image.open(d["art"]).convert("RGBA")
        bb = rgba.getbbox()
        if bb:
            rgba = rgba.crop(bb)
        s = int(min(cell * .86, H * .86))
        rgba.thumbnail((s, s), Image.LANCZOS)
        cx = int(cell * (i + .5))
        cy = int(H * (.47 if i % 2 == 0 else .53))
        c.paste(rgba, (cx - rgba.width // 2, cy - rgba.height // 2), rgba)
    c = c.resize((W // S, H // S), Image.LANCZOS)
    c.save(path, quality=86, optimize=True, progressive=True)


# ------------------------------------------------------------------ pages

def head(title, desc, root, extra=""):
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
%s
<title>%s</title>
<meta name="description" content="%s">
%s
<link rel="stylesheet" href="%sstyle.css?v=%s">
%s
</head>
<body>
<header class="site-head">
  <div class="bar">
    <a class="mark" href="%sindex.html">Mirrors Studio</a>
    <nav>
      <a href="%sindex.html#shop">Shop</a>
      <a href="%sindex.html#about">About</a>
      <a class="out" href="%s">Redbubble</a>
      <a class="out" href="%s">Zazzle</a>
    </nav>
  </div>
</header>
""" % (VERIFY, html.escape(title), html.escape(desc), FONTS, root, CSS_V, extra, root, root, root, RB_SHOP, ZZ_SHOP)


def foot(root):
    return """<footer class="site-foot">
  <div class="cols">
    <div>
      <p class="mark">Mirrors Studio</p>
      <p>One-line drawings and wall art by Carolina &amp; Alan, Sydney, made into stickers, tees, mugs and prints. Orders are made, paid for and shipped by Redbubble and Zazzle.</p>
    </div>
    <div>
      <p class="label">Shop</p>
      <a href="%sindex.html#shop">All designs</a><a href="%s">Redbubble shop</a><a href="%s">Zazzle shop</a>
    </div>
    <div>
      <p class="label">Also by us</p>
      <a href="%s">Mirrors Fine Art photography</a><a href="%sprivacy.html">Privacy</a>
    </div>
  </div>
  <p class="fine">© 2026 Carolina &amp; Alan. Every design is our own drawing.</p>
</footer>
</body>
</html>
""" % (root, RB_SHOP, ZZ_SHOP, MAIN, root)


def tile(d, root=""):
    name, rest = name_of(d)
    return ('<a class="tile" data-range="%s" href="%sd/%s.html"><span class="ph%s"><img src="%s%s" alt="%s" loading="lazy"></span>'
            '<span class="tn">%s</span><span class="tm">%s</span></a>'
            % (d["range"], root, d["id"], " wide" if d["kind"] == "wall" else "", root, d["pics"][0],
               html.escape(name), html.escape(name), html.escape(money(d))))


def design_page(d, related):
    name, rest = name_of(d)
    rname, colour = RANGE[d["range"]]
    photos = [BASE + "/" + p for p in d["pics"]]
    thumbs = "".join('<button type="button" data-i="%d"%s aria-label="Picture %d"><img src="../%s" alt="" loading="lazy"></button>'
                     % (i, ' class="on"' if i == 0 else "", i + 1, p) for i, p in enumerate(d["pics"]))
    amt, cur, cheapest = price(d)
    buys = []
    if d["rb"]:
        what = "Prints, canvas and posters" if d["kind"] == "wall" else "Stickers, tees, mugs and more"
        buys.append('<a class="btn wide" href="%s">Shop on Redbubble<span>%s</span></a>' % (html.escape(d["rb"]), what))
    if d["zz"]:
        cls = "btn wide" if not d["rb"] else "btn wide alt"
        buys.append('<a class="%s" href="%s">Shop on Zazzle<span>%d products</span></a>'
                    % (cls, html.escape(d["zz_page"]), len(d["zz"])))
    zz = ""
    if len(d["zz"]) > 1:
        zz = ('<details class="prods"><summary>On Zazzle</summary><ul>%s</ul></details>'
              % "".join('<li><a href="%s">%s</a></li>' % (html.escape(p["url"]), html.escape(p["name"])) for p in d["zz"]))
    rel = "".join(tile(x, "../") for x in related)
    ld = {"@context": "https://schema.org", "@type": "Product", "name": d["title"], "image": photos,
          "description": d["description"][:500], "brand": {"@type": "Brand", "name": "Mirrors Studio"},
          "offers": {"@type": "Offer", "price": "%.2f" % amt, "priceCurrency": cur,
                     "availability": "https://schema.org/InStock", "url": "%s/d/%s.html" % (BASE, d["id"])}}
    extra = ('<meta property="og:type" content="product"><meta property="og:title" content="%s">'
             '<meta property="og:image" content="%s"><meta property="og:url" content="%s/d/%s.html">'
             '<meta property="product:price:amount" content="%.2f"><meta property="product:price:currency" content="%s">'
             '<meta property="og:availability" content="instock"><script type="application/ld+json">%s</script>'
             % (html.escape(d["title"]), html.escape(photos[0]), BASE, d["id"], amt, cur,
                json.dumps(ld).replace("</", "<\\/")))
    return head("%s · Mirrors Studio" % name, d["description"][:155], "../", extra) + """
<main class="design" style="--blob:%(colour)s">
  <nav class="crumbs" aria-label="Breadcrumb"><a href="../index.html#shop">Shop</a><span>/</span><a href="../index.html#%(r)s">%(rname)s</a><span>/</span>%(name)s</nav>
  <div class="pgrid">
    <div class="viewer">
      <div class="stage%(wide)s"><img id="main" src="../%(main)s" alt="%(name)s"></div>
      <div class="strip">%(thumbs)s</div>
    </div>
    <div class="buy">
      <p class="range-tag">%(rname)s</p>
      <h1>%(name)s</h1>
      %(rest)s
      <p class="price">%(money)s <span>(%(cheapest)s)</span></p>
      %(buys)s
      %(zz)s
      <p class="story">%(desc)s</p>
      <p class="fine-print">You'll finish your order on Redbubble or Zazzle. They print it, ship it and look after returns.</p>
    </div>
  </div>
  <section class="more">
    <div class="sec-head"><h2>More %(rname_l)s</h2><a href="../index.html#%(r)s">See them all</a></div>
    <div class="tiles">%(rel)s</div>
  </section>
</main>
<script>
(function () {
  var main = document.getElementById('main'), thumbs = document.querySelectorAll('.strip button');
  thumbs.forEach(function (t) {
    t.addEventListener('click', function () {
      main.src = t.querySelector('img').src;
      thumbs.forEach(function (x) { x.classList.toggle('on', x === t); });
    });
  });
  if (thumbs.length < 2) document.querySelector('.strip').hidden = true;
})();
</script>
""" % {"colour": colour, "r": d["range"], "rname": html.escape(rname), "rname_l": html.escape(rname.lower()),
       "name": html.escape(name), "rest": ('<p class="set">%s</p>' % html.escape(rest)) if rest else "",
       "wide": " wide" if d["kind"] == "wall" else "", "main": d["pics"][0], "thumbs": thumbs,
       "money": html.escape(money(d)), "cheapest": html.escape(cheapest.split(" ", 1)[1] + "s" if cheapest else ""),
       "buys": "".join(buys), "zz": zz, "desc": html.escape(d["description"]), "rel": rel} + foot("../")


def home_page(ds):
    present = [k for k in ORDER if any(d["range"] == k for d in ds)]
    chips = '<button type="button" data-r="all" class="on">All <span>%d</span></button>' % len(ds) + "".join(
        '<button type="button" data-r="%s" style="--blob:%s"><i></i>%s <span>%d</span></button>'
        % (k, RANGE[k][1], html.escape(RANGE[k][0]), sum(1 for d in ds if d["range"] == k)) for k in present)
    return head("Mirrors Studio · one-line art stickers, tees and wall art",
                "One-line drawings and forest wall art by Mirrors Studio, on stickers, tees, mugs and prints from Redbubble and Zazzle.",
                "") + """
<main>
  <section class="hero">
    <img src="images/banner.jpg" alt="A row of one-line drawings, a flower, a moon, a shell, a cat and fruit, joined by one long line">
    <div class="hero-text">
      <h1>Drawn in one line.</h1>
      <p>Flowers, moons, shells and small animals, each drawn without lifting the pen, over a soft shape of colour. On stickers, tees, mugs and prints.</p>
    </div>
  </section>

  <section class="shop" id="shop">
    <div class="chips" role="tablist" aria-label="Ranges">%s</div>
    <div class="tiles" id="tiles">%s</div>
  </section>

  <section class="intro" id="about">
    <h2>About Mirrors Studio</h2>
    <div>
      <p>We are Carolina &amp; Alan, in Sydney. Mirrors Studio is where our drawings live: one-line flowers, celestial and coastal sets, little animals, and misty forest wall art.</p>
      <p>We don't print or ship anything ourselves. Every design is sold through Redbubble and Zazzle, who print each order on demand and send it to you. Each design page links straight to it there.</p>
    </div>
  </section>
</main>
<script>
(function () {
  var chips = document.querySelectorAll('.chips button'), tiles = document.querySelectorAll('#tiles .tile'), keys = %s;
  function show(r) {
    chips.forEach(function (c) { c.classList.toggle('on', c.dataset.r === r); });
    tiles.forEach(function (t) { t.hidden = !(r === 'all' || t.dataset.range === r); });
  }
  chips.forEach(function (c) { c.addEventListener('click', function () { history.replaceState(null, '', c.dataset.r === 'all' ? '#shop' : '#' + c.dataset.r); show(c.dataset.r); }); });
  function fromHash() { var h = location.hash.replace('#', ''); if (keys.indexOf(h) > -1) { show(h); document.getElementById('shop').scrollIntoView(); } else show('all'); }
  fromHash(); window.addEventListener('hashchange', fromHash);
})();
</script>
""" % (chips, "".join(tile(d) for d in ds), json.dumps(present)) + foot("")


def privacy_page():
    return head("Privacy · Mirrors Studio", "Privacy at Mirrors Studio.", "") + """
<main class="prose">
  <h1>Privacy</h1>
  <p class="muted">Last updated 3 November 2026.</p>
  <h2>This website</h2>
  <p>This site shows our designs and links to them on Redbubble and Zazzle. It has no forms, no accounts, no cookies and no analytics, and it collects no personal information.</p>
  <h2>Buying</h2>
  <p>Orders are placed on Redbubble or Zazzle, under <a href="https://www.redbubble.com/privacy">Redbubble's privacy policy</a> or <a href="https://www.zazzle.com/mk/policy/privacy_policy">Zazzle's privacy policy</a>. We see only what they share with the designer.</p>
</main>
""" + foot("")


def feed(ds, path):
    """Pinterest's catalogue columns: each design always in stock, new."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "title", "description", "link", "image_link", "additional_image_link",
                    "price", "availability", "condition", "brand", "product_type"])
        for d in ds:
            amt, cur, _ = price(d)
            w.writerow(["ms-" + d["id"], d["title"][:500], re.sub(r"\s+", " ", d["description"])[:9900],
                        "%s/d/%s.html" % (BASE, d["id"]), "%s/%s" % (BASE, d["pics"][0]),
                        ",".join("%s/%s" % (BASE, p) for p in d["pics"][1:]),
                        "%.2f %s" % (amt, cur), "in stock", "new", "Mirrors Studio", RANGE[d["range"]][0]])


def write(path, text):
    with open(os.path.join(SITE, path), "w", encoding="utf-8") as fh:
        fh.write(text)


def main():
    ds = designs()
    for d in ds:
        d["pics"] = pictures(d)
    waiting = [d for d in ds if not d["pics"]]
    ds = [d for d in ds if d["pics"]]
    banner(ds)
    ddir = os.path.join(SITE, "d")
    shutil.rmtree(ddir, ignore_errors=True)
    os.makedirs(ddir)
    for d in ds:
        same = [x for x in ds if x["range"] == d["range"] and x is not d][:4]
        write(os.path.join("d", "%s.html" % d["id"]), design_page(d, same))
    write("index.html", home_page(ds))
    write("privacy.html", privacy_page())
    feed(ds, os.path.join(SITE, "catalog.csv"))
    print("%d designs: %d pages, index, privacy, catalog.csv%s" % (
        len(ds), len(ds), "; %d waiting for their artwork (drive?)" % len(waiting) if waiting else ""))


if __name__ == "__main__":
    main()
