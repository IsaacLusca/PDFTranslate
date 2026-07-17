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
TABLE_LINE_TOLERANCE = 2.5
TABLE_CELL_PADDING = 2

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


def _cluster_positions(values, tolerance=TABLE_LINE_TOLERANCE):
    clusters = []
    for value in sorted(values):
        for cluster in clusters:
            if abs(value - cluster[-1]) <= tolerance:
                cluster.append(value)
                break
        else:
            clusters.append([value])
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _line_covers_interval(lines, coord, start, end, orientation):
    segments = [
        (line_start, line_end)
        for line_coord, line_start, line_end in lines
        if abs(line_coord - coord) <= TABLE_LINE_TOLERANCE
    ]
    if not segments:
        return False

    cursor = start
    for seg_start, seg_end in sorted(segments):
        if seg_end < cursor - TABLE_LINE_TOLERANCE:
            continue
        if seg_start > cursor + TABLE_LINE_TOLERANCE:
            return False
        cursor = max(cursor, seg_end)
        if cursor >= end - TABLE_LINE_TOLERANCE:
            return True
    return False


def _detect_table_cells(page):
    horizontal = []
    vertical = []

    for drawing in page.get_drawings():
        for item in drawing.get("items", []):
            if item[0] != "re":
                continue
            rect = fitz.Rect(item[1])
            if rect.width > 20 and rect.height <= 3:
                horizontal.append(((rect.y0 + rect.y1) / 2, rect.x0, rect.x1))
            elif rect.height > 10 and rect.width <= 3:
                vertical.append(((rect.x0 + rect.x1) / 2, rect.y0, rect.y1))

    if not horizontal or not vertical:
        return []

    xs = _cluster_positions([line[0] for line in vertical])
    candidate_intervals = set()
    for x0, x1 in zip(xs, xs[1:]):
        if x1 - x0 >= 8:
            candidate_intervals.add((round(x0, 1), round(x1, 1)))

    for _, start, end in horizontal:
        if end - start < 8:
            continue
        left = min(xs, key=lambda x: abs(x - start))
        right = min(xs, key=lambda x: abs(x - end))
        if abs(left - start) <= TABLE_LINE_TOLERANCE and abs(right - end) <= TABLE_LINE_TOLERANCE and right - left >= 8:
            candidate_intervals.add((round(left, 1), round(right, 1)))

    cells = []
    seen = set()

    for x0, x1 in sorted(candidate_intervals):
        ys = [
            y
            for y, start, end in horizontal
            if start <= x0 + TABLE_LINE_TOLERANCE and end >= x1 - TABLE_LINE_TOLERANCE
        ]
        ys = _cluster_positions(ys)
        if len(ys) < 2:
            continue

        for y0, y1 in zip(ys, ys[1:]):
            if y1 - y0 < 6:
                continue
            if not _line_covers_interval(vertical, x0, y0, y1, "v"):
                continue
            if not _line_covers_interval(vertical, x1, y0, y1, "v"):
                continue
            has_internal_vertical = any(
                x0 + TABLE_LINE_TOLERANCE < x < x1 - TABLE_LINE_TOLERANCE
                and _line_covers_interval(vertical, x, y0, y1, "v")
                for x in xs
            )
            if has_internal_vertical:
                continue
            key = tuple(round(v, 1) for v in (x0, y0, x1, y1))
            if key in seen:
                continue
            seen.add(key)
            cells.append(fitz.Rect(x0, y0, x1, y1))

    return cells


def _span_center(span):
    rect = fitz.Rect(span["bbox"])
    return ((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)


def _spans_in_rect(spans, rect):
    found = []
    for span in spans:
        x, y = _span_center(span)
        if rect.x0 - 0.5 <= x <= rect.x1 + 0.5 and rect.y0 - 0.5 <= y <= rect.y1 + 0.5:
            found.append(span)
    return found


def _padded_rect(rect, padding=TABLE_CELL_PADDING):
    padded = fitz.Rect(rect)
    x_padding = min(padding, max(0, rect.width * 0.1))
    y_padding = min(padding, max(0, (rect.height - 10) / 2))
    padded.x0 += x_padding
    padded.x1 -= x_padding
    padded.y0 += y_padding
    padded.y1 -= y_padding
    if padded.x0 >= padded.x1:
        padded = fitz.Rect(rect)
    if padded.y0 >= padded.y1:
        padded = fitz.Rect(rect)
    return padded


def _add_table_cell_text_item(items, text, rect, span, kind="table_cell", translate=None):
    if not text.strip():
        return
    item_rect = fitz.Rect(rect) if "marker" in kind else _padded_rect(rect)
    min_height = (span.get("size", 10) or 10) * 1.25
    if item_rect.height < min_height:
        item_rect.y1 = item_rect.y0 + min_height
    items.append(_make_layout_item(
        text.strip(),
        item_rect,
        span,
        kind=kind,
        translate=translate,
        fixed_rect=True,
    ))


def _flush_table_list_item(items, current):
    if not current:
        return
    text = "\n".join(current["lines"]).strip()
    if not text:
        return
    _add_table_cell_text_item(
        items,
        text,
        current["rect"],
        current["span"],
        kind="table_list_item",
        translate=True,
    )


def _add_items_from_table_cell(items, cell_rect, spans):
    rows = _group_spans_by_visual_row(spans)
    if not rows:
        return []

    used_spans = []
    normal_lines = []
    normal_rect = None
    normal_span = None
    current_list = None

    for row in rows:
        row_spans = row["spans"]
        used_spans.extend(row_spans)
        first = row_spans[0]
        first_text = _normalized_marker(first.get("text", ""))
        row_rect = _row_rect(row)

        if len(row_spans) >= 2 and _is_list_marker(first_text):
            _flush_table_list_item(items, current_list)
            current_list = None
            marker_rect = fitz.Rect(first["bbox"])
            _add_table_cell_text_item(items, first_text, marker_rect, first, kind="table_list_marker", translate=False)
            content_spans = row_spans[1:]
            content_text = _row_text_with_gaps({"spans": content_spans})
            content_rect = _row_rect({"spans": content_spans})
            content_rect.x1 = cell_rect.x1
            current_list = {
                "lines": [content_text] if content_text else [],
                "rect": content_rect,
                "span": content_spans[0],
            }
            continue

        split = _split_inline_list_text(first.get("text", ""))
        if split and len(row_spans) == 1:
            _flush_table_list_item(items, current_list)
            current_list = None
            marker, content = split
            first_rect = fitz.Rect(first["bbox"])
            marker_width = max(first.get("size", 10) or 10, first_rect.width * len(marker) / max(1, len(first.get("text", ""))))
            marker_rect = fitz.Rect(first_rect.x0, first_rect.y0, min(first_rect.x1, first_rect.x0 + marker_width), first_rect.y1)
            content_rect = fitz.Rect(marker_rect.x1 + 2, first_rect.y0, cell_rect.x1, first_rect.y1)
            _add_table_cell_text_item(items, marker, marker_rect, first, kind="table_list_marker", translate=False)
            current_list = {"lines": [content], "rect": content_rect, "span": first}
            continue

        line_text = _row_text_with_gaps(row)
        if current_list and row_rect.x0 >= current_list["rect"].x0 - max(4, first.get("size", 10) or 10):
            current_list["lines"].append(line_text)
            current_list["rect"] = current_list["rect"] | row_rect
            current_list["rect"].x1 = cell_rect.x1
            continue

        _flush_table_list_item(items, current_list)
        current_list = None
        if line_text:
            normal_lines.append(line_text)
            normal_rect = row_rect if normal_rect is None else normal_rect | row_rect
            if normal_span is None:
                normal_span = first

    _flush_table_list_item(items, current_list)

    if normal_lines and normal_rect is not None:
        _add_table_cell_text_item(
            items,
            "\n".join(normal_lines),
            cell_rect,
            normal_span,
            kind="table_cell",
        )

    return used_spans


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


def _make_layout_item(text, rect, span, kind="block", translate=None, fixed_rect=False):
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
        "fixed_rect": fixed_rect,
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


def _extract_layout_items(text_blocks, table_cells=None):
    items = []
    all_spans = []
    table_span_ids = set()

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

    if table_cells:
        for cell in table_cells:
            cell_spans = _spans_in_rect(all_spans, cell)
            if not cell_spans:
                continue
            used_spans = _add_items_from_table_cell(items, cell, cell_spans)
            table_span_ids.update(id(span) for span in used_spans)

    for block in text_blocks:
        spans = [
            span
            for line in block["lines"]
            for span in line["spans"]
            if (
                span.get("text", "").strip()
                and (span.get("size", 0) or 0) > 0
                and id(span) not in table_span_ids
            )
        ]
        if not spans:
            continue

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

    if item.get("fixed_rect"):
        if rect.width < 4:
            rect.x1 = min(page_rect.x1 - PAGE_MARGIN, rect.x0 + 4)
        if rect.height < 4:
            rect.y1 = min(page_rect.y1 - PAGE_MARGIN, rect.y0 + 4)
        return rect

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

        table_cells = _detect_table_cells(page)
        layout_items, all_spans = _extract_layout_items(text_blocks, table_cells=table_cells)
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
