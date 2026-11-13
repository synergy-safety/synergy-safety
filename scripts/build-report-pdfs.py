#!/usr/bin/env python3
"""Generate one A4 PDF per published accident analysis.

Reads ``data/news.json`` and ``data/analyses.json``. For every analysis that
has a matching news item (``newsId``), writes
``assets/reports/{reportNo}.pdf`` and records that relative path on the
analysis as ``pdf``. News items without an analysis are skipped.

Regenerate after publishing a new analysis (from the repository root)::

    python3 -m pip install reportlab pillow fonttools
    python3 scripts/build-report-pdfs.py

The first run downloads Noto Sans TC (SIL Open Font License) into
``scripts/.font-cache/`` — that cache is gitignored — then embeds a subset
so the PDF renders Traditional Chinese on machines that do not have the font.
A few simplified glyphs that Noto Sans TC does not contain (currently 热 and
阶, which appear verbatim in the source JSON) are taken from WenQuanYi Micro
Hei when that font is installed, so those characters are not dropped.

The analysis body is copied from the JSON. It is not rewritten. The news
summary is also copied, except a surname marker of the form 姓X immediately
before 男, 女, 工, 友 or 人 is omitted. Published analyses already refer to
injured people as 不具名; the PDF must not put those surnames back in.

In the news summary, each outlet name links to its stored URL and sits beside
a QR code for the same address. The raw URL is not printed again there.
Reference and legal citations later in the report still show their URLs.

Each PDF opens and prints with no user password. An owner password turns off
copy, extract, modify, annotate, assemble, and form-fill. The embedded font's
ToUnicode map does not store the real characters, so selecting or extracting
text does not yield the report wording. Set ``PDF_OWNER_PASSWORD`` to supply
the owner password. If it is unset, a random owner password is created in
memory for that run and is not written to disk, printed, or stored in the
repository. The password is not needed to read the file later.
"""

from __future__ import annotations

import html
import io
import re
import shutil
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
NEWS_PATH = ROOT / "data" / "news.json"
ANALYSES_PATH = ROOT / "data" / "analyses.json"
LOGO_PATH = ROOT / "assets" / "logo.png"
REPORTS_DIR = ROOT / "assets" / "reports"
FONT_CACHE = Path(__file__).resolve().parent / ".font-cache"
NOTO_VF_URL = (
    "https://github.com/google/fonts/raw/main/ofl/notosanstc/"
    "NotoSansTC%5Bwght%5D.ttf"
)
WQY_PATH = Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc")

COMPANY_ZH = "協同安全顧問公司"
COMPANY_EN = "Synergy Safety Consultant Company"
PHONE_DISPLAY = "+852 6880 8830"
PHONE_TEL = "tel:+85268808830"
EMAIL = "synergy.safety@iCloud.com"
WHATSAPP = "https://wa.me/85268808830"
SITE = "https://synergy-safety.github.io/synergy-safety/"

HK = ZoneInfo("Asia/Hong_Kong")
REPORT_NO_RE = re.compile(r"^SSC-\d{4}-AR-\d{3,}$")
# 姓X only when it identifies a person (姓陳工人, 姓林男工友). Leaves 姓名 alone.
SURNAME_RE = re.compile(r"姓[\u4e00-\u9fff](?=[男女工友人])")
FORBIDDEN = (
    "陳昱同",
    "Tony Y. T. Chan",
    "13266928806",
    "+86",
    "金德工業",
    "葵芳",
    "姓陳",
    "姓蘇",
    "姓林",
    "姓曾",
    "姓歐",
    "姓盧",
    "姓李",
    "姓楊",
)
# PDF display order only. data/analyses.json and analysis.html keep the
# stored sequence, which still places 相關法例及守則 before 預防再發建議.
SECTION_HEADINGS = (
    "報告資料",
    "意外摘要",
    "基本資料",
    "事態經過",
    "傷害及後果",
    "成因分析",
    "預防再發建議",
    "相關法例及守則",
    "參考資料",
    "免責聲明",
)

FONT = "NotoSansTC"
FONT_BOLD = "NotoSansTC-Bold"
FONT_FALLBACK = "NotoFallback"
FALLBACK_CHARS: set[str] = set()


def redact_injured_surnames(text: str) -> str:
    """Remove 姓X person markers. Other wording stays as published."""
    return SURNAME_RE.sub("", text)


def esc(text: str) -> str:
    return html.escape(text or "", quote=False)


def esc_attr(text: str) -> str:
    return html.escape(text or "", quote=True)


def xml_text(text: str) -> str:
    """Escape JSON text for a ReportLab paragraph, with a fallback font."""
    parts: list[str] = []
    buf: list[str] = []
    fb_mode = False

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        chunk = esc("".join(buf))
        if fb_mode and FALLBACK_CHARS:
            parts.append(f'<font name="{FONT_FALLBACK}">{chunk}</font>')
        else:
            parts.append(chunk)
        buf = []

    for ch in text or "":
        if ch == "\n":
            flush()
            parts.append("<br/>")
            continue
        fb = ch in FALLBACK_CHARS
        if buf and fb != fb_mode:
            flush()
        fb_mode = fb
        buf.append(ch)
    flush()
    return "".join(parts)


def is_http(url: str | None) -> bool:
    return bool(url) and url.startswith(("https://", "http://"))


def format_when(iso: str | None, with_time: bool) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(HK)
    except ValueError:
        return iso
    if with_time:
        return f"{dt.year}年{dt.month}月{dt.day}日 {dt.hour:02d}:{dt.minute:02d}"
    return f"{dt.year}年{dt.month}月{dt.day}日"


def severity_label(severity: str | None) -> str:
    if severity is None:
        return ""
    norm = str(severity).strip().lower().replace("_", "-")
    if norm == "fatal":
        return "致命"
    if norm in {"non-fatal", "nonfatal"}:
        return "非致命"
    return str(severity).strip()


def accident_line(accident_type: dict | None) -> str:
    if not isinstance(accident_type, dict):
        return ""
    code = accident_type.get("code")
    label = accident_type.get("label")
    if not code or not label:
        return ""
    text = f"{code} {label}"
    if code == "04" and accident_type.get("fallDistanceMetres") is not None:
        text += f"（墮下約 {accident_type['fallDistanceMetres']} 米）"
    if code == "17" and accident_type.get("otherSpecify"):
        text += f"：{accident_type['otherSpecify']}"
    return text + "（表格2第K部）"


def contractor_line(news: dict) -> str:
    name = (news.get("contractor") or "").strip()
    if not name:
        return ""
    confidence = news.get("contractorConfidence")
    if confidence:
        return f"{name}（{confidence}）"
    return name


def news_meta_rows(news: dict) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if news.get("title"):
        rows.append(("標題", news["title"]))
    occurred = format_when(news.get("occurredAt"), with_time=True)
    if occurred:
        rows.append(("事發時間", occurred))
    published = format_when(news.get("publishedAt"), with_time=True)
    if published:
        rows.append(("收錄時間", published))
    if news.get("location"):
        rows.append(("地點", news["location"]))
    severity = severity_label(news.get("severity"))
    if severity:
        rows.append(("嚴重程度", severity))
    accident = accident_line(news.get("accidentType"))
    if accident:
        rows.append(("意外類別", accident))
    contractor = contractor_line(news)
    if contractor:
        rows.append(("承建商", contractor))
    return rows


def safe_repo_file(rel: str | None) -> Path | None:
    if not rel or rel.startswith(("/", "\\")) or ".." in Path(rel).parts:
        return None
    path = (ROOT / rel).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        return None
    return path


def load_json(path: Path) -> dict:
    import json

    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "synergy-safety-pdf-build"})
    with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as handle:
        shutil.copyfileobj(resp, handle)
    tmp.replace(dest)


def ensure_noto_variable() -> Path:
    dest = FONT_CACHE / "NotoSansTC-VF.ttf"
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        return dest
    print(f"Downloading Noto Sans TC to {dest}")
    download(NOTO_VF_URL, dest)
    return dest


def prepare_fonts(sample: str) -> None:
    """Subset Noto Sans TC to the glyphs this build needs and register them."""
    from fontTools.subset import Options, Subsetter
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont as RLFont

    class ObfuscatedTTFont(RLFont):
        """Draws the real glyphs, but the ToUnicode map is not the real text."""

        def addObjects(self, doc):
            import reportlab.pdfbase.ttfonts as ttfonts

            original = ttfonts.makeToUnicodeCMap

            def scrambled(fontname, subset):
                count = len(subset)
                if count <= 0:
                    return original(fontname, subset)
                last = min(count - 1, 255)
                mappings = ["<%02X> <FFFD>" % i for i in range(min(count, 256))]
                cmap = [
                    "/CIDInit /ProcSet findresource begin",
                    "12 dict begin",
                    "begincmap",
                    "/CIDSystemInfo",
                    "<< /Registry (%s)" % fontname,
                    "/Ordering (%s)" % fontname,
                    "/Supplement 0",
                    ">> def",
                    "/CMapName /%s def" % fontname,
                    "/CMapType 2 def",
                    "1 begincodespacerange",
                    "<00> <%02X>" % last,
                    "endcodespacerange",
                    "%d beginbfchar" % len(mappings),
                    *mappings,
                    "endbfchar",
                    "endcmap",
                    "CMapName currentdict /CMap defineresource pop",
                    "end",
                    "end",
                ]
                return "\n".join(cmap)

            ttfonts.makeToUnicodeCMap = scrambled
            try:
                super().addObjects(doc)
            finally:
                ttfonts.makeToUnicodeCMap = original

    global FALLBACK_CHARS

    vf_path = ensure_noto_variable()
    source = TTFont(vf_path)
    cmap = source.getBestCmap() or {}
    missing = sorted({ch for ch in set(sample) if ord(ch) not in cmap and not ch.isspace()})
    FALLBACK_CHARS = set(missing)

    options = Options()
    options.hinting = False
    options.desubroutinize = True
    options.layout_features = ["kern", "mark", "mkmk"]
    options.recommended_glyphs = True
    options.notdef_outline = True
    options.name_IDs = ["*"]
    options.drop_tables = ["DSIG"]
    subsetter = Subsetter(options=options)
    subsetter.populate(text=sample)
    subsetter.subset(source)

    blob = io.BytesIO()
    source.save(blob)

    def instance(weight: int) -> io.BytesIO:
        blob.seek(0)
        font = instantiateVariableFont(TTFont(blob), {"wght": weight}, inplace=False)
        out = io.BytesIO()
        font.save(out)
        out.seek(0)
        return out

    pdfmetrics.registerFont(ObfuscatedTTFont(FONT, instance(400)))
    pdfmetrics.registerFont(ObfuscatedTTFont(FONT_BOLD, instance(700)))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT, boldItalic=FONT_BOLD)

    if not missing:
        return

    if not WQY_PATH.is_file():
        raise SystemExit(
            "Noto Sans TC is missing glyphs "
            + "".join(missing)
            + f" and fallback font was not found at {WQY_PATH}"
        )
    fallback = TTFont(str(WQY_PATH), fontNumber=0)
    fb_cmap = fallback.getBestCmap() or {}
    still = [ch for ch in missing if ord(ch) not in fb_cmap]
    if still:
        raise SystemExit("No font covers: " + "".join(still))
    fb_options = Options()
    fb_options.hinting = False
    fb_options.desubroutinize = True
    fb_options.recommended_glyphs = True
    fb_options.notdef_outline = True
    fb_options.drop_tables = ["DSIG"]
    fb_subset = Subsetter(options=fb_options)
    fb_subset.populate(text="".join(missing))
    fb_subset.subset(fallback)
    fb_buf = io.BytesIO()
    fallback.save(fb_buf)
    fb_buf.seek(0)
    pdfmetrics.registerFont(ObfuscatedTTFont(FONT_FALLBACK, fb_buf))
    print("Fallback glyphs from WenQuanYi Micro Hei: " + "".join(missing))


def prepare_photo(path: Path) -> io.BytesIO:
    from PIL import Image, ImageOps

    image = ImageOps.exif_transpose(Image.open(path))
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.getchannel("A"))
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")
    max_px = 1200
    if image.width > max_px:
        height = max(1, round(image.height * max_px / image.width))
        image = image.resize((max_px, height), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=70, optimize=True)
    buf.seek(0)
    return buf


def build_styles() -> dict:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle

    teal = colors.HexColor("#0d9488")
    teal_dark = colors.HexColor("#0f766e")
    teal_muted = colors.HexColor("#115e59")
    ink = colors.HexColor("#0f172a")
    ink_soft = colors.HexColor("#334155")
    muted = colors.HexColor("#64748b")
    # Every style must name the embedded face. ReportLab's default
    # Helvetica cannot draw Traditional Chinese, and table cells do not
    # inherit a font from surrounding flowables.
    parent = ParagraphStyle(
        "base",
        fontName=FONT,
        fontSize=10,
        leading=16,
        textColor=ink_soft,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )
    return {
        "teal": teal,
        "teal_dark": teal_dark,
        "teal_soft": colors.HexColor("#f0fdfa"),
        "orange": colors.HexColor("#f97316"),
        "ink": ink,
        "ink_soft": ink_soft,
        "muted": muted,
        "line": colors.HexColor("#e2e8f0"),
        "white": colors.white,
        "zh": ParagraphStyle("zh", parent=parent, fontName=FONT_BOLD, fontSize=15, leading=20, textColor=teal_dark),
        "en": ParagraphStyle("en", parent=parent, fontSize=8.5, leading=12, textColor=muted, spaceBefore=1),
        "kicker": ParagraphStyle(
            "kicker", parent=parent, fontName=FONT_BOLD, fontSize=8.5, leading=12, textColor=colors.HexColor("#ea580c"), spaceBefore=2
        ),
        "report_no": ParagraphStyle("report_no", parent=parent, fontName=FONT_BOLD, fontSize=12.5, leading=16, textColor=teal, spaceBefore=8),
        "cover_date": ParagraphStyle("cover_date", parent=parent, fontSize=9.5, leading=14, textColor=ink_soft, spaceBefore=1),
        "title": ParagraphStyle(
            "title", parent=parent, fontName=FONT_BOLD, fontSize=14, leading=21, textColor=ink, spaceBefore=8, spaceAfter=4
        ),
        "contact": ParagraphStyle("contact", parent=parent, fontSize=8, leading=12, textColor=muted, spaceBefore=1),
        "h2": ParagraphStyle(
            "h2", parent=parent, fontName=FONT_BOLD, fontSize=12.5, leading=17, textColor=teal_dark, spaceBefore=11, spaceAfter=4
        ),
        "h3": ParagraphStyle(
            "h3", parent=parent, fontName=FONT_BOLD, fontSize=11, leading=15, textColor=ink, spaceBefore=8, spaceAfter=2
        ),
        "tier": ParagraphStyle(
            "tier",
            parent=parent,
            fontName=FONT_BOLD,
            fontSize=10.5,
            leading=15,
            textColor=teal_muted,
            backColor=colors.HexColor("#f0fdfa"),
            borderPadding=4,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle("body", parent=parent, spaceAfter=6),
        "notice": ParagraphStyle("notice", parent=parent, fontSize=9.5, leading=15, textColor=ink),
        "label": ParagraphStyle("label", parent=parent, fontName=FONT_BOLD, fontSize=9, leading=13, textColor=teal_dark),
        "value": ParagraphStyle("value", parent=parent, fontSize=9.5, leading=14, textColor=ink),
        "bullet": ParagraphStyle(
            "bullet", parent=parent, leading=15.5, leftIndent=14, bulletIndent=2, bulletFontName=FONT, spaceAfter=3
        ),
        "caveat": ParagraphStyle(
            "caveat", parent=parent, fontSize=8.5, leading=13, textColor=muted, leftIndent=14, spaceBefore=1, spaceAfter=4
        ),
        "field": ParagraphStyle("field", parent=parent, fontSize=9.5, leading=14.5, leftIndent=8, spaceAfter=2, textColor=ink_soft),
        "ref_title": ParagraphStyle(
            "ref_title",
            parent=parent,
            fontName=FONT_BOLD,
            fontSize=10,
            leading=14.5,
            textColor=teal_dark,
            leftIndent=8,
            spaceBefore=6,
            spaceAfter=2,
        ),
        "small": ParagraphStyle("small", parent=parent, fontSize=8, leading=11.5, textColor=muted, spaceBefore=1),
        "summary_label": ParagraphStyle(
            "summary_label", parent=parent, fontName=FONT_BOLD, fontSize=9, leading=13, textColor=teal_dark, spaceBefore=6, spaceAfter=2
        ),
        "source_link": ParagraphStyle(
            "source_link", parent=parent, fontName=FONT_BOLD, fontSize=10.5, leading=15, textColor=teal_dark
        ),
    }


def P(text: str, style):
    from reportlab.platypus import Paragraph

    rendered = xml_text(text)
    if not rendered:
        return None
    return Paragraph(rendered, style)


def link_markup(url: str, label: str) -> str:
    if not is_http(url):
        return xml_text(label)
    href = esc_attr(url)
    return f'<link href="{href}" color="#0f766e"><u>{xml_text(label)}</u></link>'


# Page number, x, y, width, height of each news-source QR, in page space.
_qr_zones: list[tuple[int, float, float, float, float]] = []


def note_qr_zone(canvas, size: float) -> None:
    x, y = canvas.absolutePosition(0, 0)
    _qr_zones.append((canvas.getPageNumber(), x, y, size, size))


def draw_watermark(canvas, width: float, height: float) -> None:
    """Diagonal company names and a faint logo, kept off the header, footer, and QR codes."""
    from reportlab.lib.colors import Color
    from reportlab.lib.units import mm
    from reportlab.pdfgen.canvas import FILL_EVEN_ODD

    page = canvas.getPageNumber()
    top_clear = 76 * mm if page == 1 else 18 * mm
    bottom_clear = 25 * mm
    band_height = height - top_clear - bottom_clear
    if band_height < 40 * mm:
        return
    pad = 4 * mm
    canvas.saveState()
    band = canvas.beginPath()
    band.rect(0, bottom_clear, width, band_height)
    for zone_page, x, y, w, h in _qr_zones:
        if zone_page != page:
            continue
        band.rect(x - pad, y - pad, w + 2 * pad, h + 2 * pad)
    canvas.clipPath(band, stroke=0, fill=0, fillMode=FILL_EVEN_ODD)
    ink = Color(0.067, 0.369, 0.349)
    canvas.setFillColor(ink)
    canvas.setFillAlpha(0.05)
    logo = 28 * mm
    center_y = bottom_clear + band_height / 2
    canvas.drawImage(
        str(LOGO_PATH),
        (width - logo) / 2,
        center_y - logo / 2,
        width=logo,
        height=logo,
        mask="auto",
        preserveAspectRatio=True,
    )
    canvas.saveState()
    canvas.translate(width / 2, center_y)
    canvas.rotate(28)
    canvas.setFillAlpha(0.075)
    canvas.setFont(FONT, 12)
    for dy in range(-240, 241, 88):
        canvas.drawCentredString(0, dy, COMPANY_ZH)
        canvas.setFont(FONT, 7.5)
        canvas.drawCentredString(0, dy - 12, COMPANY_EN)
        canvas.setFont(FONT, 12)
    canvas.restoreState()
    canvas.restoreState()


def draw_page(report_no: str, styles: dict):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    side = 16 * mm

    def _draw(canvas, _doc) -> None:
        canvas.saveState()
        width, height = A4
        draw_watermark(canvas, width, height)
        canvas.setFillColor(styles["teal_dark"])
        canvas.setFont(FONT, 8)
        canvas.drawString(side, height - 10 * mm, COMPANY_ZH)
        canvas.setFillColor(styles["muted"])
        canvas.drawRightString(width - side, height - 10 * mm, report_no)
        canvas.setStrokeColor(styles["teal"])
        canvas.setLineWidth(1)
        y = height - 12.2 * mm
        canvas.line(side, y, width - side, y)
        canvas.setStrokeColor(styles["orange"])
        canvas.setLineWidth(2.2)
        canvas.line(width - side - 22 * mm, y, width - side, y)

        rule_y = 17.4 * mm
        canvas.setStrokeColor(styles["line"])
        canvas.setLineWidth(0.5)
        canvas.line(side, rule_y, width - side, rule_y)

        label_size = 6.5
        value_size = 7.5
        row_gap = 3.7 * mm
        col_w = (width - 2 * side) / 2
        columns = (
            (
                side,
                13.4 * mm,
                (
                    ("電話", PHONE_DISPLAY, PHONE_TEL),
                    ("WhatsApp", PHONE_DISPLAY, WHATSAPP),
                ),
            ),
            (
                side + col_w,
                13.4 * mm,
                (
                    ("電郵", EMAIL, f"mailto:{EMAIL}"),
                    ("網站", "synergy-safety.github.io/synergy-safety", SITE),
                ),
            ),
        )
        for origin_x, top_y, rows in columns:
            canvas.setFont(FONT, label_size)
            label_w = max(canvas.stringWidth(label, FONT, label_size) for label, _value, _url in rows)
            value_x = origin_x + label_w + 1.8 * mm
            for index, (label, value, url) in enumerate(rows):
                y = top_y - index * row_gap
                canvas.setFillColor(styles["muted"])
                canvas.setFont(FONT, label_size)
                canvas.drawString(origin_x, y, label)
                canvas.setFillColor(styles["teal_dark"])
                canvas.setFont(FONT, value_size)
                canvas.drawString(value_x, y, value)
                value_w = canvas.stringWidth(value, FONT, value_size)
                canvas.setStrokeColor(styles["teal_dark"])
                canvas.setLineWidth(0.3)
                canvas.line(value_x, y - 0.7, value_x + value_w, y - 0.7)
                canvas.linkURL(
                    url,
                    (value_x, y - 1.2, value_x + value_w, y + value_size),
                    relative=0,
                    thickness=0,
                )

        canvas.setFillColor(styles["muted"])
        canvas.setFont(FONT, 7.5)
        canvas.drawString(side, 5.2 * mm, COMPANY_EN)
        canvas.drawRightString(width - side, 5.2 * mm, report_no)
        canvas.drawCentredString(width / 2, 5.2 * mm, f"第 {canvas.getPageNumber()} 頁")
        canvas.restoreState()

    return _draw


class Bookmark:
    """Zero-height outline entry. Implemented as a function-built Flowable."""


def make_bookmark(key: str, title: str, level: int = 0):
    from reportlab.platypus import Flowable

    class _Bookmark(Flowable):
        def wrap(self, _aw, _ah):
            return (0, 0)

        def draw(self):
            self.canv.bookmarkHorizontal(key, 0, 0)
            self.canv.addOutlineEntry(title, key, level, 0)

    return _Bookmark()


def kv_table(rows: list[tuple[str, str]], styles: dict, width: float):
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table

    if not rows:
        return None
    label_w = 28 * mm
    data = []
    for label, value in rows:
        data.append([
            Paragraph(xml_text(label), styles["label"]),
            Paragraph(xml_text(value), styles["value"]),
        ])
    table = Table(data, colWidths=[label_w, width - label_w], hAlign="LEFT")
    table.setStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (0, -1), styles["teal_soft"]),
            ("BACKGROUND", (1, 0), (1, -1), styles["white"]),
            ("GRID", (0, 0), (-1, -1), 0.4, styles["line"]),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )
    return table


def accent_bar(styles: dict, width: float):
    from reportlab.platypus import Table

    bar = Table([["", ""]], colWidths=[width * 0.78, width * 0.22], rowHeights=[3.5])
    bar.setStyle(
        [
            ("BACKGROUND", (0, 0), (0, 0), styles["teal"]),
            ("BACKGROUND", (1, 0), (1, 0), styles["orange"]),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]
    )
    return bar


def notice_box(text: str, styles: dict, width: float):
    from reportlab.platypus import Paragraph, Table

    para = Paragraph(xml_text(text), styles["notice"])
    table = Table([[para]], colWidths=[width])
    table.setStyle(
        [
            ("BACKGROUND", (0, 0), (-1, -1), styles["teal_soft"]),
            ("BOX", (0, 0), (-1, -1), 0.8, styles["teal"]),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
    )
    return table


def add_paragraphs(story: list, paragraphs: list | None, style) -> None:
    for text in paragraphs or []:
        block = P(text, style)
        if block is not None:
            story.append(block)


def add_bullets(story: list, bullets: list | None, styles: dict) -> None:
    for text in bullets or []:
        if not text:
            continue
        from reportlab.platypus import Paragraph

        story.append(Paragraph(xml_text(text), styles["bullet"], bulletText="・"))


def add_timeline(story: list, timeline: list | None, styles: dict) -> None:
    for index, entry in enumerate(timeline or [], start=1):
        if not isinstance(entry, dict):
            continue
        label = (entry.get("label") or "").strip()
        text = entry.get("text") or ""
        prefix = f"{index}. "
        if label:
            prefix += label + " "
        block = P(prefix + text, styles["body"])
        if block is not None:
            story.append(block)
        caveat = entry.get("caveat")
        note = P(caveat, styles["caveat"]) if caveat else None
        if note is not None:
            story.append(note)


def linked_qr(url: str, size: float):
    """QR flowable whose square is also a link to the same URL."""
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.platypus import Flowable

    class _LinkedQR(Flowable):
        def __init__(self):
            super().__init__()
            widget = QrCodeWidget(url, barLevel="M")
            x1, y1, x2, y2 = widget.getBounds()
            scale_x = size / max(x2 - x1, 1)
            scale_y = size / max(y2 - y1, 1)
            self.drawing = Drawing(size, size, transform=[scale_x, 0, 0, scale_y, 0, 0])
            self.drawing.add(widget)

        def wrap(self, _aw, _ah):
            return size, size

        def draw(self):
            self.drawing.drawOn(self.canv, 0, 0)
            note_qr_zone(self.canv, size)
            self.canv.linkURL(url, (0, 0, size, size), relative=1, thickness=0)

    return _LinkedQR()


def news_source_table(sources: list, styles: dict, width: float):
    """Outlet name as the link, QR beside it, no second line of the raw URL."""
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table

    qr_size = 18 * mm
    name_width = 34 * mm
    rows = []
    for src in sources:
        if not isinstance(src, dict):
            continue
        url = src.get("url") or ""
        outlet = (src.get("outlet") or "").strip()
        if is_http(url):
            label = outlet or "來源"
            name = Paragraph(link_markup(url, label), styles["source_link"])
            code = linked_qr(url, qr_size)
        elif outlet:
            name = Paragraph(xml_text(outlet), styles["source_link"])
            code = ""
        else:
            continue
        rows.append([name, code])
    if not rows:
        return None
    table = Table(rows, colWidths=[name_width, qr_size], hAlign="LEFT")
    table.setStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, -1), "LEFT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (0, -1), 3),
            ("RIGHTPADDING", (1, 0), (1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]
    )
    return table


def keep_block(flowables: list, width: float):
    """Keep short blocks on one page. A table row does not split."""
    from reportlab.platypus import Table

    usable = [item for item in flowables if item is not None]
    if not usable:
        return None
    table = Table([[usable]], colWidths=[width])
    table.setStyle(
        [
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
    )
    return table


def add_legal_ref(story: list, ref: dict, styles: dict, width: float) -> None:
    from reportlab.platypus import Paragraph

    title = ref.get("title") or ref.get("url") or ""
    url = ref.get("url") or ""
    if title:
        markup = link_markup(url, title) if is_http(url) else xml_text(title)
        story.append(Paragraph(markup, styles["ref_title"]))
    fields = (
        ("條文", ref.get("provision")),
        ("適用", ref.get("applicability") or ref.get("note")),
        ("相關", ref.get("relevance")),
    )
    for label, value in fields:
        if not value:
            continue
        story.append(Paragraph(f"<b>{esc(label)}</b>　{xml_text(value)}", styles["field"]))
    if is_http(url):
        url_para = Paragraph(f"<b>官方連結</b>　{link_markup(url, url)}", styles["field"])
        block = keep_block([url_para], width)
        if block is not None:
            story.append(block)


def add_section(story: list, section: dict, styles: dict, width: float, bookmark_key: str) -> None:
    from reportlab.platypus import CondPageBreak

    heading = section.get("heading") or ""
    if heading == "免責聲明":
        # Short closing section: keep the heading with its paragraph so
        # it does not leave a title stranded at the bottom of a page.
        blocks = [make_bookmark(bookmark_key, heading, level=1)]
        title = P(heading, styles["h2"])
        if title is not None:
            blocks.append(title)
        for text in section.get("paragraphs") or []:
            para = P(text, styles["body"])
            if para is not None:
                blocks.append(para)
        kept = keep_block(blocks, width)
        if kept is not None:
            story.append(CondPageBreak(40))
            story.append(kept)
        return
    story.append(CondPageBreak(40))
    if heading:
        story.append(make_bookmark(bookmark_key, heading, level=1))
        block = P(heading, styles["h2"])
        if block is not None:
            story.append(block)
    add_paragraphs(story, section.get("paragraphs"), styles["body"])
    table = kv_table([tuple(row) for row in section.get("rows") or [] if isinstance(row, (list, tuple)) and len(row) >= 2], styles, width)
    if table is not None:
        story.append(table)
    add_bullets(story, section.get("bullets"), styles)
    add_timeline(story, section.get("timeline"), styles)
    for sub in section.get("subsections") or []:
        if not isinstance(sub, dict):
            continue
        title = P(sub.get("title") or "", styles["h3"])
        if title is not None:
            story.append(CondPageBreak(40))
            story.append(title)
        add_paragraphs(story, sub.get("paragraphs"), styles["body"])
        add_bullets(story, sub.get("bullets"), styles)
    tiers = section.get("legalTiers") or []
    if tiers:
        for tier in tiers:
            if not isinstance(tier, dict):
                continue
            label = P(tier.get("tierLabel") or "", styles["tier"])
            if label is not None:
                story.append(CondPageBreak(48))
                story.append(label)
            for ref in tier.get("refs") or []:
                if isinstance(ref, dict):
                    add_legal_ref(story, ref, styles, width)
    elif section.get("legalRefs"):
        for ref in section["legalRefs"]:
            if isinstance(ref, dict):
                add_legal_ref(story, ref, styles, width)
    for ref in section.get("refs") or []:
        if isinstance(ref, dict):
            add_legal_ref(story, ref, styles, width)


def pdf_sections(sections: list | None) -> list:
    """Return sections in PDF order without mutating the stored list."""
    ranked = {heading: index for index, heading in enumerate(SECTION_HEADINGS)}
    known = []
    extra = []
    for section in sections or []:
        if isinstance(section, dict) and section.get("heading") in ranked:
            known.append(section)
        else:
            extra.append(section)
    known.sort(key=lambda section: ranked[section["heading"]])
    if known and known[-1].get("heading") == "免責聲明":
        return known[:-1] + extra + known[-1:]
    return known + extra


def build_story(analysis: dict, news: dict, styles: dict, width: float) -> list:
    from reportlab.lib.units import mm
    from reportlab.platypus import CondPageBreak, HRFlowable, Image, KeepTogether, Paragraph, Spacer, Table

    story: list = []
    report_no = analysis["reportNo"]
    story.append(Spacer(1, 1.5 * mm))

    logo = Image(str(LOGO_PATH), width=16 * mm, height=16 * mm, mask="auto")
    identity = [
        Paragraph(xml_text(COMPANY_ZH), styles["zh"]),
        Paragraph(xml_text(COMPANY_EN), styles["en"]),
        Paragraph(xml_text("公開資料分析報告"), styles["kicker"]),
    ]
    ident = Table([[logo, identity]], colWidths=[20 * mm, width - 20 * mm])
    ident.setStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (1, 0), (1, 0), 4),
        ]
    )
    story.append(ident)
    story.append(Spacer(1, 2.2 * mm))
    story.append(accent_bar(styles, width))

    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle

    number_style = ParagraphStyle(
        "report_no_inline",
        parent=styles["report_no"],
        spaceBefore=0,
        spaceAfter=0,
    )
    date_style = ParagraphStyle(
        "cover_date_right",
        parent=styles["cover_date"],
        alignment=TA_RIGHT,
        spaceBefore=0,
        spaceAfter=0,
        leading=16,
    )
    cover_date = format_when(analysis.get("writtenAt") or analysis.get("publishedAt"), with_time=False)
    date_label = f"撰寫日期 {cover_date}" if cover_date else ""
    number_width = 78 * mm
    meta_row = Table(
        [[
            Paragraph(xml_text(report_no), number_style),
            Paragraph(xml_text(date_label), date_style),
        ]],
        colWidths=[number_width, width - number_width],
    )
    meta_row.setStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]
    )
    story.append(meta_row)
    title = P(analysis.get("title") or "", styles["title"])
    if title is not None:
        story.append(title)

    story.append(Spacer(1, 2 * mm))
    story.append(make_bookmark(f"{report_no}-news", "新聞摘要", level=0))
    story.append(Paragraph(xml_text("新聞摘要"), styles["h2"]))
    meta = kv_table(news_meta_rows(news), styles, width)
    if meta is not None:
        story.append(meta)
    summary = redact_injured_surnames(news.get("summary") or "")
    if summary:
        story.append(Paragraph(xml_text("摘要"), styles["summary_label"]))
        story.append(Paragraph(xml_text(summary), styles["body"]))
    sources = [src for src in (news.get("sources") or []) if isinstance(src, dict)]
    source_table = news_source_table(sources, styles, width)
    if source_table is not None:
        story.append(Paragraph(xml_text("資料來源"), styles["summary_label"]))
        story.append(source_table)

    photo = safe_repo_file(news.get("image"))
    if photo is not None:
        buf = prepare_photo(photo)
        from PIL import Image as PILImage

        buf.seek(0)
        with PILImage.open(buf) as probe:
            px_w, px_h = probe.size
        buf.seek(0)
        max_h = 62 * mm
        disp_w = width
        disp_h = disp_w * px_h / px_w
        if disp_h > max_h:
            disp_h = max_h
            disp_w = disp_h * px_w / px_h
        story.append(Spacer(1, 2 * mm))
        image = Image(buf, width=disp_w, height=disp_h)
        image.hAlign = "CENTER"
        story.append(image)

    story.append(Spacer(1, 3 * mm))
    notice = analysis.get("reportNotice") or analysis.get("reportPreamble") or ""
    notice_block = [
        HRFlowable(width="100%", thickness=0.6, color=styles["teal"], spaceBefore=2, spaceAfter=2),
        make_bookmark(f"{report_no}-notice", "報告性質說明", level=0),
        Paragraph(xml_text("報告性質說明"), styles["h2"]),
    ]
    if notice:
        notice_block.append(notice_box(notice, styles, width))
        notice_block.append(Spacer(1, 2 * mm))
    story.append(KeepTogether(notice_block))

    for index, section in enumerate(pdf_sections(analysis.get("sections")), start=1):
        if isinstance(section, dict):
            add_section(story, section, styles, width, f"{report_no}-s{index}")

    if not analysis.get("sections"):
        # Legacy analyses are not in the current file; keep the fields if one appears.
        add_bullets(story, analysis.get("causes"), styles)
        add_bullets(story, analysis.get("lessons"), styles)
        for ref in analysis.get("legalRefs") or []:
            if isinstance(ref, dict):
                add_legal_ref(story, ref, styles, width)
    story.append(CondPageBreak(1))
    return story


def iter_rendered_text(analysis: dict, news: dict) -> list[str]:
    """Every string placed in the PDF, used for the font subset and the privacy check."""
    chunks = [
        COMPANY_ZH,
        COMPANY_EN,
        "公開資料分析報告",
        analysis.get("reportNo") or "",
        analysis.get("title") or "",
        "撰寫日期",
        "新聞摘要",
        "摘要",
        "資料來源",
        "報告性質說明",
        "條文",
        "適用",
        "相關",
        "官方連結",
        "電話",
        "電郵",
        PHONE_DISPLAY,
        EMAIL,
        WHATSAPP,
        SITE,
        "第 頁",
        "0123456789",
        format_when(analysis.get("writtenAt") or analysis.get("publishedAt"), with_time=False),
        redact_injured_surnames(news.get("summary") or ""),
        news.get("title") or "",
        news.get("location") or "",
        format_when(news.get("occurredAt"), with_time=True),
        format_when(news.get("publishedAt"), with_time=True),
        severity_label(news.get("severity")),
        accident_line(news.get("accidentType")),
        contractor_line(news),
        analysis.get("reportNotice") or "",
        analysis.get("reportPreamble") or "",
    ]
    for label, _value in news_meta_rows(news):
        chunks.append(label)
    for src in news.get("sources") or []:
        if isinstance(src, dict):
            chunks.append(src.get("outlet") or "")
            chunks.append(src.get("url") or "")

    def walk(value) -> None:
        if isinstance(value, str):
            chunks.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(analysis.get("sections") or [])
    walk(analysis.get("causes") or [])
    walk(analysis.get("lessons") or [])
    walk(analysis.get("legalRefs") or [])
    return chunks


def document_encryption(owner_password: str):
    """Empty user password; owner password only carries the permission flags."""
    from reportlab.lib.pdfencrypt import StandardEncryption

    class _Locked(StandardEncryption):
        def permissionBits(self):
            bits = StandardEncryption.permissionBits(self)
            fill_forms = 1 << 8
            access_extract = 1 << 9
            assemble = 1 << 10
            return bits & ~fill_forms & ~access_extract & ~assemble

    return _Locked(
        "",
        owner_password,
        canPrint=1,
        canModify=0,
        canCopy=0,
        canAnnotate=0,
        # strength 256 is AES-256, but ReportLab's revision-5 files are rejected
        # by current readers. 128-bit encryption still opens with no user password.
        strength=128,
    )


def owner_password() -> str:
    """Owner secret for permission flags. Never log or persist this value."""
    import os
    import secrets

    supplied = os.environ.get("PDF_OWNER_PASSWORD", "").strip()
    if supplied:
        return supplied
    return secrets.token_urlsafe(32)


def write_pdf(analysis: dict, news: dict, dest: Path, styles: dict, owner_password: str) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate

    dest.parent.mkdir(parents=True, exist_ok=True)
    _qr_zones.clear()
    side = 16 * mm
    width = A4[0] - 2 * side
    doc = SimpleDocTemplate(
        str(dest),
        pagesize=A4,
        leftMargin=side,
        rightMargin=side,
        topMargin=16 * mm,
        bottomMargin=22 * mm,
        title=analysis["reportNo"],
        author=COMPANY_EN,
        subject="公開資料分析報告",
        encrypt=document_encryption(owner_password),
    )
    on_page = draw_page(analysis["reportNo"], styles)
    doc.build(build_story(analysis, news, styles, width), onFirstPage=on_page, onLaterPages=on_page)


def assert_self_checks() -> None:
    samples = {
        "55歲姓陳工人腰部受傷，38歲姓蘇工人": "55歲工人腰部受傷，38歲工人",
        "51歲姓林男工友": "51歲男工友",
        "69歲姓曾男工": "69歲男工",
        "62歲姓歐男工半昏迷、57歲姓盧女工": "62歲男工半昏迷、57歲女工",
        "姓名與金門建築": "姓名與金門建築",
    }
    for raw, expected in samples.items():
        got = redact_injured_surnames(raw)
        if got != expected:
            raise SystemExit(f"Surname redaction failed: {raw!r} -> {got!r}")


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def heading_lines(text: str) -> list[str]:
    """Section titles that occupy a line of their own, ignoring phrases such as 見參考資料."""
    wanted = set(SECTION_HEADINGS)
    return [line.strip() for line in text.splitlines() if line.strip() in wanted]


def verify_pdf(path: Path, analysis: dict, news: dict) -> None:
    from pypdf import PdfReader
    from pypdf.constants import UserAccessPermissions

    reader = PdfReader(str(path))
    if not reader.is_encrypted:
        raise SystemExit(f"{path.name} is not permission-locked")
    if int(reader.decrypt("")) == 0:
        raise SystemExit(f"{path.name} cannot be opened without a password")
    perms = reader.user_access_permissions
    if perms is None or not (perms & UserAccessPermissions.PRINT):
        raise SystemExit(f"{path.name} does not allow printing")
    blocked = (
        (UserAccessPermissions.MODIFY, "modify"),
        (UserAccessPermissions.EXTRACT, "copy"),
        (UserAccessPermissions.ADD_OR_MODIFY, "annotate"),
        (UserAccessPermissions.FILL_FORM_FIELDS, "form fill"),
        (UserAccessPermissions.ASSEMBLE_DOC, "assemble"),
        (UserAccessPermissions.EXTRACT_TEXT_AND_GRAPHICS, "extract"),
    )
    for flag, name in blocked:
        if perms & flag:
            raise SystemExit(f"{path.name} still allows {name}")
    extracted = "\n".join((page.extract_text() or "") for page in reader.pages)
    folded = compact(extracted)
    author = ""
    if reader.metadata and reader.metadata.author:
        author = str(reader.metadata.author)
    haystacks = (extracted, folded, author)
    for token in FORBIDDEN:
        for hay in haystacks:
            if token.lower() in hay.lower():
                raise SystemExit(f"{path.name} contains forbidden text: {token}")
    probes = ["新聞摘要", "預防再發建議", "報告性質說明"]
    title = (analysis.get("title") or "").strip()
    if len(title) >= 8:
        probes.append(title[:12])
    summary = redact_injured_surnames(news.get("summary") or "")
    if len(summary) >= 12:
        probes.append(summary[:16])
    for probe in probes:
        if probe in extracted or probe in folded:
            raise SystemExit(f"{path.name} extracted text still contains real wording")
    annots = 0
    uris: set[str] = set()
    for page in reader.pages:
        for annot in page.get("/Annots") or []:
            annots += 1
            action = annot.get("/A") if hasattr(annot, "get") else None
            if action is not None and action.get("/URI"):
                uris.add(str(action.get("/URI")))
    if annots < 1:
        raise SystemExit(f"{path.name} has no clickable links")
    import json

    analysis_blob = json.dumps(analysis.get("sections") or [], ensure_ascii=False)
    for src in news.get("sources") or []:
        if not isinstance(src, dict) or not is_http(src.get("url")):
            continue
        url = src["url"]
        if url not in uris:
            raise SystemExit(f"{path.name} source is not linked: {url}")
        if url not in analysis_blob and url in extracted:
            raise SystemExit(f"{path.name} repeats the news source URL as text: {url}")
    for required in (PHONE_TEL, f"mailto:{EMAIL}", WHATSAPP, SITE):
        if required not in uris:
            raise SystemExit(f"{path.name} footer is missing link: {required}")
    if "https://wa.me/" in extracted:
        raise SystemExit(f"{path.name} prints the WhatsApp URL")
    if reader.metadata and reader.metadata.author and "Chan" in str(reader.metadata.author):
        raise SystemExit(f"{path.name} metadata author looks personal")


def patch_analyses(paths_by_report: dict[str, str]) -> None:
    text = ANALYSES_PATH.read_text(encoding="utf-8")
    pattern = re.compile(r'("reportNo": "(SSC-[^"]+)",\n)(?:[ \t]*"pdf": "[^"]+",\n)?')

    def repl(match: re.Match[str]) -> str:
        report_no = match.group(2)
        rel = paths_by_report.get(report_no)
        if not rel:
            return match.group(1)
        return match.group(1) + f'      "pdf": "{rel}",\n'

    updated, count = pattern.subn(repl, text)
    if count != len(paths_by_report):
        raise SystemExit(
            f"Expected to record {len(paths_by_report)} pdf fields, updated {count}. analyses.json format changed?"
        )
    if updated != text:
        ANALYSES_PATH.write_text(updated, encoding="utf-8")


def main() -> None:
    assert_self_checks()
    if not LOGO_PATH.is_file():
        raise SystemExit(f"Logo not found: {LOGO_PATH}")
    news_doc = load_json(NEWS_PATH)
    analyses_doc = load_json(ANALYSES_PATH)
    news_by_id = {item["id"]: item for item in news_doc.get("items") or [] if item.get("id")}

    pairs: list[tuple[dict, dict]] = []
    for analysis in analyses_doc.get("items") or []:
        report_no = analysis.get("reportNo") or ""
        news = news_by_id.get(analysis.get("newsId"))
        if not news or not report_no:
            continue
        if not REPORT_NO_RE.fullmatch(report_no):
            raise SystemExit(f"Unexpected reportNo: {report_no}")
        pairs.append((analysis, news))
    if not pairs:
        raise SystemExit("No analysis with a matching news item.")

    sample = "\n".join(
        chunk for analysis, news in pairs for chunk in iter_rendered_text(analysis, news) if chunk
    )
    # Privacy check on the strings we are about to draw, before any PDF is written.
    rendered = sample
    for token in FORBIDDEN:
        if token.lower() in rendered.lower():
            raise SystemExit(f"Refusing to write PDFs; source text still contains {token}")

    prepare_fonts(sample + "・")
    styles = build_styles()
    secret = owner_password()

    written: dict[str, str] = {}
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    for analysis, news in pairs:
        report_no = analysis["reportNo"]
        dest = REPORTS_DIR / f"{report_no}.pdf"
        write_pdf(analysis, news, dest, styles, secret)
        verify_pdf(dest, analysis, news)
        rel = f"assets/reports/{report_no}.pdf"
        written[report_no] = rel
        print(f"Wrote {rel} ({dest.stat().st_size} bytes)")

    expected = {f"{report_no}.pdf" for report_no in written}
    for stale in REPORTS_DIR.glob("SSC-*.pdf"):
        if stale.name not in expected:
            stale.unlink()
            print(f"Removed stale {stale.name}")

    patch_analyses(written)
    print(f"Recorded {len(written)} pdf paths in {ANALYSES_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
