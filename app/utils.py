# importação do PyMuPDF
import fitz 
from deep_translator import GoogleTranslator
from langdetect import detect
from PIL import Image
import pytesseract
from concurrent.futures import ThreadPoolExecutor, as_completed
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


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

# func para extrair texto da imagem
def extract_text_from_image(image_path):
    image = Image.open(image_path)
    return pytesseract.image_to_string(image)

# func para traduzir o texto extraído da imagem
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
    translated_doc = fitz.open()
    
    for p in src:
        new = translated_doc.new_page(width=p.rect.width, height=p.rect.height)
        new.show_pdf_page(p.rect, src, p.number)
        text_dict = p.get_text("dict")
        spans = [
            span
            for block in text_dict["blocks"] if "lines" in block
            for line in block["lines"]
            for span in line["spans"]
            if span["text"].strip()
        ]

        originals = [span["text"] for span in spans]
        translated = translate_text_list(originals, target_lang, max_workers=10)

        for span, tr in zip(spans, translated):
            r = fitz.Rect(span["bbox"])
            new.draw_rect(r, fill=(1,1,1), color=None)
            new.insert_text(
                span["origin"],
                tr,
                fontsize=span["size"],
                fontname="helv",
                fill=(0,0,0),
            )
    return translated_doc

def generate_translated_pdf(translated_doc, output_path):
    """salvar documento traduzido"""
    translated_doc.save(output_path)
    translated_doc.close()