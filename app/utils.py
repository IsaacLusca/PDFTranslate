import math
import fitz
from deep_translator import GoogleTranslator
from langdetect import detect
from PIL import Image
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed


PAGE_MARGIN = 2
MIN_FONT_SIZE = 4
FONT_DIR = os.path.join(os.path.dirname(__file__), "static", "fonts")
LIST_MARKER_RE = re.compile(r"^(\(?[A-Za-z0-9]{1,3}(?:[.)])|[-*])$")
INLINE_LIST_RE = re.compile(r"^(\(?[A-Za-z0-9]{1,3}(?:[.)])|[-*])\s+(.+)$")

FONT_CANDIDATES = {
    "regular": [
        os.path.join(FONT_DIR, "NotoSans-Regular.ttf"),
        os.path.join(FONT_DIR, "DejaVuSans.ttf"),
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ],
    "bold": [
        os.path.join(FONT_DIR, "NotoSans-Bold.ttf"),
        os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"),
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ],
    "italic": [
        os.path.join(FONT_DIR, "NotoSans-Italic.ttf"),
        os.path.join(FONT_DIR, "DejaVuSans-Oblique.ttf"),
        r"C:\Windows\Fonts\ariali.ttf",
        r"C:\Windows\Fonts\segoeuii.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Italic.ttf",
    ],
    "bold_italic": [
        os.path.join(FONT_DIR, "NotoSans-BoldItalic.ttf"),
        os.path.join(FONT_DIR, "DejaVuSans-BoldOblique.ttf"),
        r"C:\Windows\Fonts\arialbi.ttf",
        r"C:\Windows\Fonts\segoeuiz.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-BoldItalic.ttf",
    ],
}


def _span_fontname(span):
    flags = span.get("flags", 0)
    font = span.get("font", "").lower()
    bold = bool(flags & 16) or any(x in font for x in ("bold", "heavy", "black", "demi"))
    italic = bool(flags & 2) or any(x in font for x in ("italic", "oblique"))
    mono = bool(flags & 8) or any(x in font for x in ("courier", "mono", "typewriter"))

    if mono:
        if bold and italic: return "Courier-BoldOblique"
        if bold: return "Courier-Bold"
        if italic: return "Courier-Oblique"
        return "Courier"
    if bold and italic: return "Helvetica-BoldOblique"
    if bold: return "Helvetica-Bold"
    if italic: return "Helvetica-Oblique"
    return "Helvetica"


def _font_style(span):
    flags = span.get("flags", 0)
    font = span.get("font", "").lower()
    bold = bool(flags & 16) or any(x in font for x in ("bold", "heavy", "black", "demi"))
    italic = bool(flags & 2) or any(x in font for x in ("italic", "oblique"))
    if bold and italic:
        return "bold_italic"
    if bold:
        return "bold"
    if italic:
        return "italic"
    return "regular"


def _span_fontfile(span):
    style = _font_style(span)
    candidates = FONT_CANDIDATES.get(style, []) + FONT_CANDIDATES["regular"]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _insert_font_args(item):
    return {"fontname": item["fontname"]}


def _needs_external_font(text):
    try:
        text.encode("latin-1")
        return False
    except UnicodeEncodeError:
        return True


def _base_font_text(text):
    replacements = {
        "\u00a0": " ",
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2022": "-",
        "\u2026": "...",
        "\u00ad": "-",
    }
    chars = []
    for ch in text:
        if ch in replacements:
            chars.append(replacements[ch])
            continue
        try:
            ch.encode("latin-1")
            chars.append(ch)
            continue
        except UnicodeEncodeError:
            pass

        category = unicodedata.category(ch)
        if category.startswith("P"):
            chars.append("-")
        elif category.startswith("S"):
            chars.append("*")
        elif category.startswith("Z"):
            chars.append(" ")
        elif category.startswith("C"):
            chars.append("*")
        else:
            chars.append(ch)
    return "".join(chars)


def _text_font_args(item, text):
    text = _base_font_text(text)
    fontfile = item.get("fontfile") if _needs_external_font(text) else None
    if fontfile:
        return {
            "fontname": item.get("font_alias", "pdftranslate"),
            "fontfile": fontfile,
        }, text
    return _insert_font_args(item), text


def _span_color(span):
    c = span.get("color", 0)
    if c is None:
        return (0, 0, 0)
    return ((c >> 16) & 0xFF) / 255.0, ((c >> 8) & 0xFF) / 255.0, (c & 0xFF) / 255.0


def _rect_overlap(a, b, axis):
    if axis == "x":
        return min(a.x1, b.x1) - max(a.x0, b.x0)
    return min(a.y1, b.y1) - max(a.y0, b.y0)


def _clean_text(text):
    return " ".join(text.split())


def _has_letters(text):
    return any(ch.isalpha() for ch in text)


def _row_rect(row):
    rect = None
    for span in row["spans"]:
        span_rect = fitz.Rect(span["bbox"])
        rect = span_rect if rect is None else rect | span_rect
    return rect


def _average_char_width(span):
    text = span.get("text", "")
    rect = fitz.Rect(span["bbox"])
    visible_chars = max(1, len(text.strip()))
    return max(1.0, rect.width / visible_chars)


def _space_for_gap(gap, span):
    if gap <= 0:
        return ""
    char_width = _average_char_width(span)
    if gap < char_width * 0.25:
        return ""
    spaces = int(round(gap / char_width))
    return " " * max(1, min(spaces, 8))


def _separator_between_spans(previous_text, current_text, gap, previous_span):
    previous_text = previous_text.rstrip()
    current_text = current_text.lstrip()
    if not previous_text or not current_text:
        return ""

    if current_text[0] in ".,:;!?%)]}":
        return ""
    if current_text[0] in "'\"" and previous_text[-1].isalnum():
        return " "
    if previous_text[-1] in "([{":
        return ""
    if previous_text[-1] in ".,:;!?":
        return " "
    if previous_text[-1].isalnum() and current_text[0].isalnum():
        gap_space = _space_for_gap(gap, previous_span)
        return gap_space or " "
    return _space_for_gap(gap, previous_span)


def _row_text_with_gaps(row):
    parts = []
    previous = None
    previous_text = ""
    for span in row["spans"]:
        text = span.get("text", "")
        if not text.strip():
            continue
        rect = fitz.Rect(span["bbox"])
        if previous is not None:
            gap = rect.x0 - fitz.Rect(previous["bbox"]).x1
            parts.append(_separator_between_spans(previous_text, text, gap, previous))
        cleaned = text.strip()
        parts.append(cleaned)
        previous = span
        previous_text = cleaned
    return "".join(parts).strip()


def _normalized_marker(text):
    return _base_font_text(text).strip()


def _is_list_marker(text):
    marker = _normalized_marker(text)
    return marker in {"-", "*"} or bool(LIST_MARKER_RE.match(marker))


def _split_inline_list_text(text):
    match = INLINE_LIST_RE.match(_base_font_text(text).strip())
    if not match:
        return None
    return match.group(1), match.group(2)


def _group_spans_by_visual_row(spans):
    rows = []
    for span in sorted(spans, key=lambda s: (fitz.Rect(s["bbox"]).y0, fitz.Rect(s["bbox"]).x0)):
        rect = fitz.Rect(span["bbox"])
        size = span.get("size", 10) or 10
        center_y = (rect.y0 + rect.y1) / 2

        for row in rows:
            if abs(center_y - row["center_y"]) <= max(2, size * 0.45):
                row["spans"].append(span)
                row["center_y"] = (row["center_y"] + center_y) / 2
                break
        else:
            rows.append({"center_y": center_y, "spans": [span]})

    for row in rows:
        row["spans"].sort(key=lambda s: fitz.Rect(s["bbox"]).x0)
    return rows


def _row_has_column_gaps(row):
    spans = row["spans"]
    if len(spans) < 2:
        return False

    sizes = [s.get("size", 10) or 10 for s in spans]
    avg_size = sum(sizes) / len(sizes)
    for left, right in zip(spans, spans[1:]):
        gap = fitz.Rect(right["bbox"]).x0 - fitz.Rect(left["bbox"]).x1
        if gap > avg_size * 2.4:
            return True
    return False


def _make_layout_item(text, rect, span, kind="block", translate=None):
    return {
        "text": text,
        "rect": fitz.Rect(rect),
        "fontname": _span_fontname(span),
        "fontfile": _span_fontfile(span),
        "font_alias": "pdftranslate_" + _font_style(span),
        "color": _span_color(span),
        "size": span.get("size", 10) or 10,
        "kind": kind,
        "translate": _has_letters(text) if translate is None else translate,
    }


def _add_list_items_from_row(items, row):
    spans = row["spans"]
    if not spans:
        return False

    first = spans[0]
    first_text = _normalized_marker(first.get("text", ""))
    first_rect = fitz.Rect(first["bbox"])

    if len(spans) >= 2 and _is_list_marker(first_text):
        content_spans = spans[1:]
        content_rect = None
        for span in content_spans:
            span_rect = fitz.Rect(span["bbox"])
            content_rect = span_rect if content_rect is None else content_rect | span_rect
        content_text = _row_text_with_gaps({"spans": content_spans})
        if content_text:
            items.append(_make_layout_item(first_text, first_rect, first, kind="list_marker", translate=False))
            items.append(_make_layout_item(content_text, content_rect, content_spans[0], kind="list_item", translate=True))
            return True

    split = _split_inline_list_text(first.get("text", ""))
    if split and len(spans) == 1:
        marker, content = split
        marker_width = max(first.get("size", 10) or 10, first_rect.width * len(marker) / max(1, len(first.get("text", ""))))
        marker_rect = fitz.Rect(first_rect.x0, first_rect.y0, min(first_rect.x1, first_rect.x0 + marker_width), first_rect.y1)
        content_rect = fitz.Rect(marker_rect.x1 + 2, first_rect.y0, first_rect.x1, first_rect.y1)
        items.append(_make_layout_item(marker, marker_rect, first, kind="list_marker", translate=False))
        items.append(_make_layout_item(content, content_rect, first, kind="list_item", translate=True))
        return True

    return False


def _extract_layout_items(text_blocks):
    items = []
    all_spans = []

    for block in text_blocks:
        spans = [
            span
            for line in block["lines"]
            for span in line["spans"]
            if span.get("text", "").strip() and (span.get("size", 0) or 0) > 0
        ]
        if not spans:
            continue

        all_spans.extend(spans)
        rows = _group_spans_by_visual_row(spans)

        list_rows = []
        normal_rows = []
        for row in rows:
            if _add_list_items_from_row(items, row):
                list_rows.append(row)
            else:
                normal_rows.append(row)

        if list_rows and not normal_rows:
            continue

        if any(_row_has_column_gaps(row) for row in normal_rows):
            for row in rows:
                if row in list_rows:
                    continue
                for span in row["spans"]:
                    text = _clean_text(span["text"])
                    if text:
                        items.append(_make_layout_item(text, span["bbox"], span, kind="cell"))
            continue

        lines_text = []
        block_rect = None
        first_span = None
        for row in normal_rows:
            line_text = _row_text_with_gaps(row)
            if line_text:
                lines_text.append(line_text)
                row_rect = _row_rect(row)
                block_rect = row_rect if block_rect is None else block_rect | row_rect
                if first_span is None:
                    first_span = row["spans"][0]

        full_text = "\n".join(lines_text).strip()
        if full_text and block_rect is not None:
            items.append(_make_layout_item(full_text, block_rect, first_span, kind="block"))

    return items, all_spans


def _expanded_rect(item, page_rect, obstacles):
    original = fitz.Rect(item["rect"])
    rect = fitz.Rect(original)
    rect.x0 = max(rect.x0, page_rect.x0 + PAGE_MARGIN)
    rect.x1 = min(rect.x1, page_rect.x1 - PAGE_MARGIN)
    rect.y0 = max(rect.y0, page_rect.y0 + PAGE_MARGIN)
    rect.y1 = min(rect.y1, page_rect.y1 - PAGE_MARGIN)

    max_x1 = page_rect.x1 - PAGE_MARGIN
    max_y1 = page_rect.y1 - PAGE_MARGIN

    for other in obstacles:
        if other is original:
            continue
        if abs(other.x0 - original.x0) < 0.01 and abs(other.y0 - original.y0) < 0.01 and abs(other.x1 - original.x1) < 0.01 and abs(other.y1 - original.y1) < 0.01:
            continue

        if other.x0 >= original.x1 and _rect_overlap(original, other, "y") > 0:
            max_x1 = min(max_x1, other.x0 - 1)
        if other.y0 >= original.y1 and _rect_overlap(fitz.Rect(rect.x0, rect.y0, max_x1, rect.y1), other, "x") > 0:
            max_y1 = min(max_y1, other.y0 - 1)

    if item["kind"] == "list_marker":
        rect.x1 = max(rect.x1, original.x1 + 2)
        rect.y1 = max(rect.y1, original.y1 + 2)
    elif item["kind"] == "cell":
        rect.x1 = max(rect.x1, max_x1)
        rect.y1 = max(rect.y1, min(max_y1, original.y1 + max(item["size"] * 1.8, original.height)))
    else:
        column_x1 = original.x1
        for other in obstacles:
            if abs(other.x0 - original.x0) <= max(20, item["size"] * 2):
                vertical_gap = min(abs(other.y0 - original.y1), abs(original.y0 - other.y1))
                if vertical_gap <= max(140, item["size"] * 8):
                    column_x1 = max(column_x1, other.x1)
        extra_height = max(item["size"] * 3.2, original.height * 1.25)
        rect.x1 = max(rect.x1, min(max_x1, column_x1))
        rect.y1 = max(rect.y1, min(max_y1, original.y1 + extra_height))

    if rect.width < 10:
        rect.x1 = min(page_rect.x1 - PAGE_MARGIN, rect.x0 + 10)
    if rect.height < item["size"] * 1.15:
        rect.y1 = min(page_rect.y1 - PAGE_MARGIN, rect.y0 + item["size"] * 1.35)

    return rect


def _insert_fitted_text(page, rect, text, item):
    if not text:
        return True

    lineheight = 1.0 if item["kind"] == "block" else 0.95

    def _fits(candidate, size):
        font_args, candidate = _text_font_args(item, candidate)
        scratch = fitz.open()
        scratch_page = scratch.new_page(width=page.rect.width, height=page.rect.height)
        ret = scratch_page.insert_textbox(
            rect,
            candidate,
            fontsize=size,
            lineheight=lineheight,
            fill=item["color"],
            align=fitz.TEXT_ALIGN_LEFT,
            **font_args,
        )
        scratch.close()
        return ret >= 0

    font_args, text = _text_font_args(item, text)
    font_size = max(MIN_FONT_SIZE, int(round(item["size"])))
    preferred_min_size = MIN_FONT_SIZE if item["kind"] == "cell" else max(MIN_FONT_SIZE, int(font_size * 0.72))

    for size in range(font_size, preferred_min_size - 1, -1):
        ret = page.insert_textbox(
            rect,
            text,
            fontsize=size,
            lineheight=lineheight,
            fill=item["color"],
            align=fitz.TEXT_ALIGN_LEFT,
            **font_args,
        )
        if ret >= 0:
            return True

    for size in range(preferred_min_size - 1, MIN_FONT_SIZE - 1, -1):
        ret = page.insert_textbox(
            rect,
            text,
            fontsize=size,
            lineheight=lineheight,
            fill=item["color"],
            align=fitz.TEXT_ALIGN_LEFT,
            **font_args,
        )
        if ret >= 0:
            return True

    suffix = "..."
    low, high = 0, len(text)
    best = ""
    while low <= high:
        mid = (low + high) // 2
        candidate = text[:mid].rstrip() + suffix
        if _fits(candidate, MIN_FONT_SIZE):
            best = candidate
            low = mid + 1
        else:
            high = mid - 1

    if best:
        page.insert_textbox(
            rect,
            best,
            fontsize=MIN_FONT_SIZE,
            lineheight=lineheight,
            fill=item["color"],
            align=fitz.TEXT_ALIGN_LEFT,
            **font_args,
        )
    return False

TESSERACT_CMD = os.environ.get('TESSERACT_CMD', 'tesseract')
pytesseract = None
HAS_TESSERACT = False
try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    pytesseract.get_tesseract_version()
    HAS_TESSERACT = True
except Exception:
    pass


# Extraindo o texto do pdf.
def extract_text_from_pdf(path):
    text_pages = []
    with fitz.open(path) as doc:
        for page in doc:
            text_pages.append(page.get_text())

    return text_pages

# Função para traduzir uma lista de textos
def translate_text_list(texts, dest, max_workers=10):
    # traduções de textos paralelos
    def _translate(t):
        try:
            return GoogleTranslator(source='auto', target=dest).translate(t)
        except Exception:
            return t

    results = [None] * len(texts)
    with ThreadPoolExecutor(max_workers=max_workers) as exe:
        futures = {exe.submit(_translate, texts[i]): i for i in range(len(texts))}
        for fut in as_completed(futures):
            idx = futures[fut]
            results[idx] = fut.result()
    return results

# Função para extrair e traduzir o texto do PDF
def extract_and_translate_pdf(path, target_lang):
    pages = extract_text_from_pdf(path)
    translated_pages = [
        GoogleTranslator(source='auto', target=target_lang).translate(p)
        for p in pages
    ]
    return translated_pages

# Função para gerar um PDF a partir de uma lista de textos
def generate_pdf_from_text(pages, output_path):
    doc = fitz.open()  
    for text in pages:
        page = doc.new_page()  
        page.insert_text((50, 50), text, fontsize=12)
    doc.save(output_path)
    doc.close()

def extract_text_from_image(image_path):
    if not HAS_TESSERACT:
        raise RuntimeError("Tesseract OCR não está disponível no servidor.")
    image = Image.open(image_path)
    return pytesseract.image_to_string(image)

def translate_image_text(image_path, target_lang):
    text = extract_text_from_image(image_path)
    translated_text = GoogleTranslator(source='auto', target=target_lang).translate(text)
    return translated_text
    

# def extract_text_blocks_from_pdf(path):
#     """extrai blocos com coordenadas"""
#     blocks_pages = []
#     with fitz.open(path) as doc:
#         for page in doc:
#             blocks = page.get_text("blocks")
#             blocks_pages.append(blocks)
#     return blocks_pages

def translate_pdf_preserving_layout(path, target_lang):
    doc = fitz.open(path)

    for pno in range(len(doc)):
        page = doc[pno]
        text_dict = page.get_text("dict")

        text_blocks = [b for b in text_dict["blocks"] if "lines" in b]
        if not text_blocks:
            continue

        layout_items, all_spans = _extract_layout_items(text_blocks)
        if not layout_items:
            continue

        translatable_items = [item for item in layout_items if item.get("translate", _has_letters(item["text"]))]
        originals = [item["text"] for item in translatable_items]
        translated = translate_text_list(originals, target_lang, max_workers=6)
        translated_by_id = {
            id(item): translated_text
            for item, translated_text in zip(translatable_items, translated)
        }

        image_rects = [
            fitz.Rect(block["bbox"])
            for block in text_dict["blocks"]
            if "lines" not in block and "bbox" in block
        ]
        obstacles = [fitz.Rect(item["rect"]) for item in layout_items] + image_rects

        for span in all_spans:
            page.add_redact_annot(fitz.Rect(span["bbox"]), text="")
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)

        for item in layout_items:
            text = translated_by_id.get(id(item), item["text"])
            rect = _expanded_rect(item, page.rect, obstacles)
            _insert_fitted_text(page, rect, text, item)
    return doc

def generate_translated_pdf(translated_doc, output_path):
    """salvar documento traduzido"""
    translated_doc.save(output_path)
    translated_doc.close()
