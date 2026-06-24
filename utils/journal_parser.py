# -*- coding: utf-8 -*-
"""
kutubxona.uz jurnal soni PDF'idan ALGORITMIK (LLM'siz) maqola ajratuvchi.

Bu modul Desktop'dagi `pdf_parser.py` mantig'ining backend (in-process) varianti.
Diskka yozish o'rniga har bir maqolani xotirada (bytes) qaytaradi.

Asosiy kirish nuqtasi:
    parse_journal(pdf_source) -> list[dict]

`pdf_source` — bytes, fayl yo'li (str) yoki Django FileField/File.
Har bir element (candidate):
    {
      "order": int, "section": str, "title": str, "title_body": str,
      "author_name": str, "extra_info": str,
      "start_page": int|None, "end_page": int|None,
      "article_pdf_bytes": bytes, "photo_png_bytes": bytes|None,
    }

Hech qanday LLM yoki tashqi servis ishlatilmaydi — faqat PyMuPDF (fitz).
"""

import re

import fitz  # PyMuPDF


# --------------------------------------------------------------------------
# SOZLAMALAR (layout konstantalari)
# --------------------------------------------------------------------------
TITLE_FONT_HINT = "BoldMT"          # sarlavha fonti (TimesNewRomanPS-BoldMT)
TITLE_MIN_SIZE = 13.0               # sarlavha minimal o'lcham (~14)
POS_MIN_SIZE = 11.5
FOLIO_FONT_HINT = "ArialMT"         # bet raqami fonti
FOLIO_MIN_SIZE = 13.0

TITLE_PAD = 8.0     # sarlavha ustidan qoldiriladigan kichik joy (pt)
MIN_BAND = 24.0     # bundan kichik "tasma" e'tiborga olinmaydi (pt)
PHOTO_DPI = 200     # rasmni eksport qilish sifati

# True -> har sahifa kontentga teng balandlikda (pastda bo'sh joy QOLMAYDI).
FIT_PAGE_TO_CONTENT = True


# --------------------------------------------------------------------------
# Yordamchi funksiyalar (dedup uchun ham eksport qilinadi)
# --------------------------------------------------------------------------
def normalize(s: str) -> str:
    """Solishtirish uchun: bosh harf, faqat harf/raqam, apostroflarsiz."""
    s = s.replace("ʻ", "").replace("‘", "").replace("’", "")
    s = s.replace("'", "").replace("`", "")
    out = []
    for ch in s.upper():
        if ch.isalnum():
            out.append(ch)
    return "".join(out)


def surname_token(full_name: str) -> str:
    """Ism-familiyadan BOSH HARFLI (familiya) bo'lakni ajratadi.
    'Umida TESHABAYEVA' -> 'TESHABAYEVA'
    'XUSHVAQTOV Husan Ochilboyevich' -> 'XUSHVAQTOV'
    """
    best = ""
    for tok in re.split(r"[\s,]+", full_name.strip()):
        letters = [c for c in tok if c.isalpha()]
        if len(letters) >= 3 and all(c.upper() == c for c in letters):
            if len(tok) > len(best):
                best = tok
    if not best:  # familiya topilmasa -> eng uzun so'z
        toks = [t for t in re.split(r"[\s,]+", full_name.strip()) if t]
        best = max(toks, key=len) if toks else full_name
    return best.strip(",")


def page_spans(page):
    """Sahifadagi barcha matn span'larini qaytaradi (rotatsiyalanmagan)."""
    res = []
    d = page.get_text("dict")
    for b in d["blocks"]:
        if b.get("type", 0) != 0:
            continue
        for line in b["lines"]:
            horizontal = line.get("dir", (1, 0)) == (1.0, 0.0)
            for sp in line["spans"]:
                if not sp["text"].strip():
                    continue
                res.append({
                    "text": sp["text"],
                    "font": sp["font"],
                    "size": sp["size"],
                    "bbox": fitz.Rect(sp["bbox"]),
                    "horizontal": horizontal,
                })
    return res


def page_images(page):
    """Sahifadagi rasm bloklarini (bbox) qaytaradi."""
    res = []
    d = page.get_text("dict")
    for b in d["blocks"]:
        if b.get("type", 0) == 1:
            res.append(fitz.Rect(b["bbox"]))
    return res


# --------------------------------------------------------------------------
# 1) MUNDARIJA (TOC) ni o'qish
# --------------------------------------------------------------------------
def find_toc_page(doc):
    for i in range(min(8, doc.page_count)):
        up = doc[i].get_text("text").upper()
        if "MUNDARIJA" in up or "МУНДАРИЖА" in up or "СОДЕРЖАНИЕ" in up:
            return i
    return 1


def parse_toc(doc, toc_idx):
    """MUNDARIJA dan tartiblangan ro'yxat: {section, author, title, folio}."""
    spans = [s for s in page_spans(doc[toc_idx])
             if s["bbox"].x0 >= 195 and 9.0 <= s["size"] <= 13.5
             and s["horizontal"]]
    spans.sort(key=lambda s: (round(s["bbox"].y0, 1), s["bbox"].x0))
    if not spans:
        return []
    left_margin = min(s["bbox"].x0 for s in spans)

    entries = []
    section = ""
    cur = None

    for s in spans:
        f, x0, t = s["font"], s["bbox"].x0, s["text"].strip()
        if not t:
            continue
        nt = normalize(t)
        if nt in ("MUNDARIJA", "МУНДАРИЖА", "СОДЕРЖАНИЕ"):
            continue
        bold = "Bold" in f
        if bold and x0 <= left_margin + 12:
            if cur:
                entries.append(cur)
            cur = {"section": section, "author": t.rstrip(","),
                   "title": "", "folio": None}
        elif bold:
            section = t
        else:
            if cur is None or cur["folio"] is not None:
                continue
            m = re.search(r"\.{2,}\s*(\d+)\s*$", t)
            if m:
                cur["folio"] = int(m.group(1))
                clean = re.sub(r"\.{2,}\s*\d+\s*$", "", t).strip()
            else:
                clean = re.sub(r"\.{2,}.*$", "", t).strip()
            cur["title"] = (cur["title"] + " " + clean).strip()
    if cur:
        entries.append(cur)
    return [e for e in entries if e["folio"] is not None]


# --------------------------------------------------------------------------
# 2) Bet raqamlari (folio) va sarlavhalarni topish
# --------------------------------------------------------------------------
def build_folio_map(doc):
    """folio(bet raqami) -> pdf sahifa indeksi."""
    folio_to_idx = {}
    for i in range(doc.page_count):
        for s in page_spans(doc[i]):
            if FOLIO_FONT_HINT in s["font"] and s["size"] >= FOLIO_MIN_SIZE:
                txt = s["text"].strip()
                if txt.isdigit():
                    folio_to_idx.setdefault(int(txt), i)
    return folio_to_idx


def detect_titles(doc, content_indices):
    """Har bir kontent sahifasida sarlavha guruhlarini topadi."""
    titles = []
    for i in content_indices:
        lines = []
        for s in page_spans(doc[i]):
            if (TITLE_FONT_HINT in s["font"] and s["size"] >= TITLE_MIN_SIZE
                    and s["horizontal"]):
                lines.append(s)
        if not lines:
            continue
        lines.sort(key=lambda s: s["bbox"].y0)
        groups = []
        cur = [lines[0]]
        for s in lines[1:]:
            if s["bbox"].y0 - cur[-1]["bbox"].y1 <= 8:
                cur.append(s)
            else:
                groups.append(cur)
                cur = [s]
        groups.append(cur)
        for g in groups:
            top = min(s["bbox"].y0 for s in g)
            bottom = max(s["bbox"].y1 for s in g)
            text = " ".join(s["text"].strip() for s in g)
            titles.append({"idx": i, "top": top, "bottom": bottom, "text": text})
    titles.sort(key=lambda t: (t["idx"], t["top"]))
    return titles


# --------------------------------------------------------------------------
# 3) TOC <-> sarlavhalarni moslashtirish -> maqolalar ro'yxati
# --------------------------------------------------------------------------
def build_articles(toc_entries, titles, folio_to_idx):
    used = set()
    articles = []
    for e in toc_entries:
        target_idx = folio_to_idx.get(e["folio"])
        chosen = None
        if target_idx is not None:
            cands = [j for j, t in enumerate(titles)
                     if t["idx"] == target_idx and j not in used]
            if cands:
                chosen = min(cands, key=lambda j: titles[j]["top"])
        if chosen is None:
            cands = [j for j in range(len(titles)) if j not in used]
            if not cands:
                continue
            chosen = min(cands)
        used.add(chosen)
        t = titles[chosen]
        articles.append({
            "section": e["section"],
            "author": e["author"],
            "title_toc": e["title"],
            "title_body": t["text"],
            "folio": e["folio"],
            "idx": t["idx"],
            "top": t["top"],
            "bottom": t["bottom"],
        })
    articles.sort(key=lambda a: (a["idx"], a["top"]))
    return articles


# --------------------------------------------------------------------------
# 4) Har bir maqola uchun "tasma"lar (kesiladigan to'rtburchaklar)
# --------------------------------------------------------------------------
def compute_bands(articles, page_w, page_h, last_content_idx):
    for k, a in enumerate(articles):
        sidx, stop = a["idx"], a["top"]
        bands = []
        if k + 1 < len(articles):
            nidx = articles[k + 1]["idx"]
            ntop = articles[k + 1]["top"]
            split = ntop - TITLE_PAD
            if nidx == sidx:
                bands.append((sidx, max(0.0, stop - TITLE_PAD), split))
            else:
                bands.append((sidx, max(0.0, stop - TITLE_PAD), page_h))
                for p in range(sidx + 1, nidx):
                    bands.append((p, 0.0, page_h))
                if split >= MIN_BAND:
                    bands.append((nidx, 0.0, split))
        else:
            bands.append((sidx, max(0.0, stop - TITLE_PAD), page_h))
            for p in range(sidx + 1, last_content_idx + 1):
                bands.append((p, 0.0, page_h))
        bands = [b for b in bands if (b[2] - b[1]) >= 1.0]
        a["bands"] = bands


# --------------------------------------------------------------------------
# 5) Kesilgan + surilgan PDF yasash -> bytes
# --------------------------------------------------------------------------
def render_article_pdf_bytes(src_doc, bands, page_w, page_h) -> bytes:
    out = fitz.open()
    if FIT_PAGE_TO_CONTENT:
        for (idx, y0, y1) in bands:
            h = y1 - y0
            if h <= 1:
                continue
            page = out.new_page(width=page_w, height=h)
            page.show_pdf_page(fitz.Rect(0, 0, page_w, h), src_doc, idx,
                               clip=fitz.Rect(0, y0, page_w, y1))
    if out.page_count == 0:
        out.new_page(width=page_w, height=page_h)
    data = out.tobytes(garbage=4, deflate=True)
    out.close()
    return data


# --------------------------------------------------------------------------
# 6) Meta ma'lumot + rasm ajratish
# --------------------------------------------------------------------------
def extract_meta(src_doc, article, page_w, page_h):
    """Maqola ichidan: ism (byline), lavozim qatorlari, rasm bbox."""
    sname = normalize(surname_token(article["author"]))
    name_span = None
    search_idx = [article["idx"]] + [b[0] for b in article["bands"]
                                     if b[0] != article["idx"]]
    seen = []
    for i in search_idx:
        if i in seen:
            continue
        seen.append(i)
        for s in page_spans(src_doc[i]):
            if ("Bold" in s["font"] and s["size"] <= TITLE_MIN_SIZE
                    and normalize(s["text"]).find(sname) >= 0):
                name_span = {"idx": i, "rect": s["bbox"], "text": s["text"].strip()}
                break
        if name_span:
            break

    info_lines = []
    photo_rect = None

    if name_span:
        pidx = name_span["idx"]
        nrect = name_span["rect"]
        name_cy = (nrect.y0 + nrect.y1) / 2
        name_cx = (nrect.x0 + nrect.x1) / 2
        spans = page_spans(src_doc[pidx])
        cand = [s for s in spans
                if s["bbox"].y0 > name_cy
                and abs((s["bbox"].x0 + s["bbox"].x1) / 2 - name_cx) < 170
                and s["size"] >= 9.0]
        lines = {}
        for s in cand:
            key = round(s["bbox"].y0 / 3)
            lines.setdefault(key, []).append(s)
        line_items = []
        for key in sorted(lines):
            grp = sorted(lines[key], key=lambda s: s["bbox"].x0)
            text = ""
            prev_x1 = None
            for g in grp:
                if prev_x1 is not None and g["bbox"].x0 - prev_x1 > 1.5:
                    text += " "
                text += g["text"]
                prev_x1 = g["bbox"].x1
            text = text.strip()
            y0 = min(g["bbox"].y0 for g in grp)
            y1 = max(g["bbox"].y1 for g in grp)
            line_items.append({"text": text, "y0": y0, "y1": y1})
        prev_y = nrect.y1
        for li in line_items:
            if li["y0"] - prev_y > 16:  # paragraf bo'shlig'i -> body boshlandi
                break
            info_lines.append(li["text"])
            prev_y = li["y1"]

        best = None
        for r in page_images(src_doc[pidx]):
            rcy = (r.y0 + r.y1) / 2
            overlaps_name = not (r.x1 < nrect.x0 or r.x0 > nrect.x1)
            if (abs(rcy - name_cy) <= 120 and not overlaps_name
                    and r.width < page_w * 0.6):
                d = abs(rcy - name_cy)
                if best is None or d < best[0]:
                    best = (d, r)
        if best:
            photo_rect = (pidx, best[1])

    return {
        "name_text": name_span["text"] if name_span else article["author"],
        "info": " ".join(info_lines).strip(),
        "photo_rect": photo_rect,   # (idx, Rect) | None
    }


def export_clip_png_bytes(src_doc, idx, rect, dpi=PHOTO_DPI) -> bytes:
    pix = src_doc[idx].get_pixmap(clip=rect, dpi=dpi)
    return pix.tobytes("png")


# --------------------------------------------------------------------------
# Asosiy kirish nuqtasi
# --------------------------------------------------------------------------
def _read_source(pdf_source) -> bytes:
    """bytes | path(str) | Django File -> raw bytes."""
    if isinstance(pdf_source, (bytes, bytearray)):
        return bytes(pdf_source)
    if isinstance(pdf_source, str):
        with open(pdf_source, "rb") as fh:
            return fh.read()
    # Django FileField / File
    try:
        pdf_source.open("rb")
    except Exception:
        pass
    raw = pdf_source.read()
    try:
        pdf_source.close()
    except Exception:
        pass
    return raw


def parse_journal(pdf_source) -> list[dict]:
    """Jurnal soni PDF'idan maqola candidatelari ro'yxatini qaytaradi.

    Xatoga chidamli: TOC/maqola topilmasa bo'sh ro'yxat qaytaradi.
    """
    raw = _read_source(pdf_source)
    doc = fitz.open(stream=raw, filetype="pdf")
    try:
        if doc.page_count == 0:
            return []
        page_w = doc[0].rect.width
        page_h = doc[0].rect.height

        toc_idx = find_toc_page(doc)
        toc_entries = parse_toc(doc, toc_idx)
        folio_to_idx = build_folio_map(doc)
        content_indices = sorted(folio_to_idx.values())
        last_content_idx = (max(content_indices) if content_indices
                            else doc.page_count - 1)

        titles = detect_titles(doc, content_indices)
        articles = build_articles(toc_entries, titles, folio_to_idx)
        if not articles:
            return []

        compute_bands(articles, page_w, page_h, last_content_idx)

        results = []
        for k, a in enumerate(articles, 1):
            meta = extract_meta(doc, a, page_w, page_h)

            article_pdf = render_article_pdf_bytes(doc, a["bands"], page_w, page_h)

            photo_bytes = None
            if meta["photo_rect"] is not None:
                pidx, prect = meta["photo_rect"]
                try:
                    photo_bytes = export_clip_png_bytes(doc, pidx, prect)
                except Exception:
                    photo_bytes = None

            start_folio = a["folio"]
            end_folio = None
            if a["bands"]:
                end_idx = a["bands"][-1][0]
                for fol, ix in folio_to_idx.items():
                    if ix == end_idx:
                        end_folio = fol
                        break

            results.append({
                "order": k,
                "section": a["section"],
                "title": a["title_toc"] or a["title_body"],
                "title_body": a["title_body"],
                "author_name": a["author"],
                "extra_info": meta["info"],
                "start_page": start_folio,
                "end_page": end_folio,
                "article_pdf_bytes": article_pdf,
                "photo_png_bytes": photo_bytes,
            })
        return results
    finally:
        doc.close()
