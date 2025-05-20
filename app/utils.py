# importação do PyMuPDF
import fitz 
from deep_translator import GoogleTranslator

# Extraindo o texto do pdf.
def extract_text_from_pdf(path):
    text_pages = []
    with fitz.open(path) as doc:
        for page in doc:
            text_pages.append(page.get_text())

    return text_pages

def translate_text_list(pages, dest):
    return [GoogleTranslator(source='auto', target=dest).translate(p) for p in pages]
