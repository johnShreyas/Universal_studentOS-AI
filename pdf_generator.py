# ══════════════════════════════════════════════════════════
#  pdf_generator.py — Student OS PDF Builder
# ══════════════════════════════════════════════════════════
import io
import textwrap
import unicodedata
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

SYMBOL_MAP = {
    "\u2080": "0", "\u2081": "1", "\u2082": "2", "\u2083": "3", "\u2084": "4",
    "\u2085": "5", "\u2086": "6", "\u2087": "7", "\u2088": "8", "\u2089": "9",
    "\u2070": "^0", "\u00b9": "^1", "\u00b2": "^2", "\u00b3": "^3", "\u2074": "^4",
    "\u2075": "^5", "\u2076": "^6", "\u2077": "^7", "\u2078": "^8", "\u2079": "^9",
    "\u03b1": "alpha", "\u03b2": "beta",  "\u03b3": "gamma", "\u03b4": "delta",
    "\u03b5": "epsilon","\u03b8": "theta","\u03bb": "lambda","\u03bc": "mu",
    "\u03c0": "pi",    "\u03c3": "sigma", "\u03c9": "omega", "\u0394": "Delta",
    "\u03a9": "Omega", "\u03a6": "Phi",   "\u03c6": "phi",
    "\u221e": "inf",  "\u221a": "sqrt", "\u2248": "~",  "\u2260": "!=",
    "\u2264": "<=",   "\u2265": ">=",   "\u00b0": " deg", "\u00b1": "+/-",
    "\u2212": "-",    "\u00d7": "x",    "\u00f7": "/",  "\u2022": "-",
    "\u2192": "->", "\u2190": "<-", "\u2194": "<->", "\u21d2": "=>",
    "\u00bd": "1/2", "\u00bc": "1/4", "\u00be": "3/4",
    "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u2026": "...",
}


def sanitise(text: str) -> str:
    result = []
    for ch in text:
        if ch in SYMBOL_MAP:
            result.append(SYMBOL_MAP[ch])
        elif ord(ch) > 127:
            decomposed = unicodedata.normalize("NFKD", ch)
            ascii_ch   = decomposed.encode("ascii", "ignore").decode("ascii")
            result.append(ascii_ch if ascii_ch else "?")
        else:
            result.append(ch)
    return "".join(result)


def create_pro_pdf(content: str, title: str = "Student OS — Practice Sheet") -> io.BytesIO:
    buffer = io.BytesIO()
    c      = canvas.Canvas(buffer, pagesize=letter)
    pw, ph = letter
    margin = 50
    wrap_w = int((pw - 2 * margin) / 6.5)

    def draw_header(page_num: int):
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(pw / 2, ph - margin, sanitise(title))
        c.setFont("Helvetica", 9)
        c.drawString(margin, ph - margin - 14,
                     f"Generated: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        c.drawRightString(pw - margin, ph - margin - 14,
                          f"Student OS  |  Page {page_num}")
        c.setLineWidth(0.5)
        c.line(margin, ph - margin - 20, pw - margin, ph - margin - 20)

    def draw_footer():
        c.setFont("Helvetica-Oblique", 8)
        c.drawCentredString(pw / 2, margin - 20,
                            "Study smart · Cite sources · Verify facts · Student OS")
        c.setLineWidth(0.3)
        c.line(margin, margin - 10, pw - margin, margin - 10)

    page_num = 1
    draw_header(page_num)
    draw_footer()
    y      = ph - margin - 38
    line_h = 16

    for raw_line in content.split("\n"):
        if "would you like me to save" in raw_line.lower():
            continue

        clean = sanitise(
            raw_line
            .replace("**", "").replace("*", "")
            .replace("##", "").replace("`", "")
            .replace("$$", "").replace("$", "")
            .strip()
        )
        sub_lines = textwrap.wrap(clean, width=wrap_w) if clean else [""]

        for sub in sub_lines:
            if y < margin + 20:
                c.showPage()
                page_num += 1
                draw_header(page_num)
                draw_footer()
                y = ph - margin - 38

            is_q = len(sub) > 1 and sub[0].isdigit() and sub[1] in ".): "
            c.setFont("Helvetica-Bold" if is_q else "Helvetica", 12 if is_q else 11)
            c.drawString(margin, y, sub)
            y -= line_h

        if clean and clean[0].isdigit() and len(clean) > 1 and clean[1] in ".): ":
            y -= 4

    c.save()
    buffer.seek(0)
    return buffer
