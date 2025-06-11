# importação do PyMuPDF
import fitz 
from deep_translator import GoogleTranslator
from langdetect import detect
from PIL import Image
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# Extraindo o texto do pdf.
def extract_text_from_pdf(path):
    text_pages = []
    with fitz.open(path) as doc:
        for page in doc:
            text_pages.append(page.get_text())

    return text_pages

# Função para traduzir uma lista de textos
def translate_text_list(pages, dest):
    return [GoogleTranslator(source='auto', target=dest).translate(p) for p in pages]

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
    translated_doc = fitz.open()
    
    with fitz.open(path) as src_doc:
        for page in src_doc:
            new_page = translated_doc.new_page(
                width=page.rect.width,
                height=page.rect.height
            )

            text_dict = page.get_text("dict")

            for block in text_dict["blocks"]:
                if "lines" not in block:
                    continue

                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        if not text:
                            continue
                        try:
                            translated = GoogleTranslator(source='auto', target=target_lang).translate(text)
                        except Exception as e:
                            print(f"Erro ao traduzir span: {e}")
                            translated = text
                        
                        # coordenadas
                        x, y = span["origin"]
                        font_size = span["size"]
                        font_name = "helv"  

                        new_page.insert_text(
                            (x, y),
                            translated,
                            fontsize=font_size,
                            fontname=font_name,
                            fill=(0, 0, 0)
                        )

    return translated_doc

def generate_translated_pdf(translated_doc, output_path):
    """salvar documento traduzido"""
    translated_doc.save(output_path)
    translated_doc.close()