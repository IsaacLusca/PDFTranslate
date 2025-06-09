# from app import app
from flask import redirect, render_template, request, url_for, session, flash, Blueprint, send_file
import os
from googletrans import Translator
from langdetect import detect
from deep_translator import GoogleTranslator

# função para extrair texto do PDF 
from app.utils import extract_text_from_pdf, translate_text_list, extract_and_translate_pdf, generate_pdf_from_text
from app.utils import translate_image_text, extract_text_from_image

# criação do blueprint
# O blueprint é uma forma de organizar o código em Flask, permitindo dividir a aplicação em partes menores e mais gerenciáveis.
main = Blueprint('main', __name__)

# definindo o diretório de upload
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'temp')  # agora vira absoluto

# Verifica se o diretório de upload existe, caso contrário, cria o diretório.
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@main.route('/')	
@main.route('/index')
def index():
    return render_template('index.html')

@main.route('/translate', methods=['POST'])
def translate():
    # Verifica se o arquivo foi enviado na requisição
    file = request.files['file']
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    # salva o arquivo no diretório de upload
    file.save(filepath)

    # pages recebe o texto extraído do PDF
    pages = extract_text_from_pdf(filepath)

    target_lang = request.form['language']

    # detecta pela primeira página:
    detected_lang = detect(pages[0]) if pages else 'auto'

    translated_pages = [
        GoogleTranslator(source=detected_lang, target=target_lang).translate(p)
        for p in pages
    ]
    html = "<br><hr>".join(f"<h3>Página {i+1}</h3><pre>{p}</pre>" for i, p in enumerate(translated_pages))
    return html

@main.route('/translate_to_pdf', methods=['POST'])
# Função para traduzir o PDF e gerar um novo PDF com o texto traduzido
def translate_to_pdf():
    file = request.files['file']
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    target_lang = request.form['language']
    translated_pages = extract_and_translate_pdf(filepath, target_lang)

    filename = os.path.splitext(file.filename)[0]  
    output_filename = f"{filename}_translated_{target_lang}.pdf"
    output_path = os.path.join(UPLOAD_FOLDER, output_filename)    

    generate_pdf_from_text(translated_pages, output_path)

    return send_file(output_path, as_attachment=True)


@main.route('/translate_image', methods=['POST'])
def translate_image():
    file = request.files['file']
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    target_lang = request.form['language']
    translated_text = translate_image_text(filepath, target_lang)

    return f"<h3>Texto traduzido da imagem:</h3><pre>{translated_text}</pre>"