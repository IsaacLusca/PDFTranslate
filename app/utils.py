import fitz
from deep_translator import GoogleTranslator
from langdetect import detect
from PIL import Image
import os
from concurrent.futures import ThreadPoolExecutor, as_completed


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


def _span_color(span):
    c = span.get("color", 0)
    if c is None:
        return (0, 0, 0)
    return ((c >> 16) & 0xFF) / 255.0, ((c >> 8) & 0xFF) / 255.0, (c & 0xFF) / 255.0

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
    src = fitz.open(path)
    dst = fitz.open()
    dst.insert_pdf(src)
    src.close()

    for pno in range(len(dst)):
        page = dst[pno]
        text_dict = page.get_text("dict")

        blocks = [b for b in text_dict["blocks"] if "lines" in b]

        spans = [
            span
            for block in blocks
            for line in block["lines"]
            for span in line["spans"]
            if span["text"].strip()
        ]

        if not spans:
            continue

        originals = [span["text"] for span in spans]
        translated = translate_text_list(originals, target_lang, max_workers=10)

        for span in spans:
            r = fitz.Rect(span["bbox"])
            page.add_redact_annot(r, text="")

        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)

        for span, tr in zip(spans, translated):
            r = fitz.Rect(span["bbox"])
            r.x0 = max(r.x0, page.rect.x0 + 2)
            r.x1 = min(r.x1, page.rect.x1 - 2)
            if r.x0 >= r.x1:
                r.x1 = r.x0 + 10
            r.y0 = max(r.y0, page.rect.y0 + 2)
            r.y1 = min(r.y1, page.rect.y1 - 2)

            ret = page.insert_textbox(
                r, tr,
                fontsize=span["size"],
                fontname=_span_fontname(span),
                fill=_span_color(span),
                align=fitz.TEXT_ALIGN_LEFT,
            )

            if ret < 0:
                r.y1 = page.rect.y1 - 2
                fs = span["size"]
                while fs > 4:
                    ret = page.insert_textbox(
                        r, tr,
                        fontsize=fs,
                        fontname=_span_fontname(span),
                        fill=_span_color(span),
                        align=fitz.TEXT_ALIGN_LEFT,
                    )
                    if ret >= 0:
                        break
                    fs -= 1
    return dst

def generate_translated_pdf(translated_doc, output_path):
    """salvar documento traduzido"""
    translated_doc.save(output_path)
    translated_doc.close()