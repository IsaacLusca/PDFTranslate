# from app import app
from flask import redirect, render_template, request, url_for, session, flash, Blueprint
import os
from googletrans import Translator

# função para extrair texto do PDF 
from app.utils import extract_text_from_pdf, translate_text_list

# criação do blueprint
# O blueprint é uma forma de organizar o código em Flask, permitindo dividir a aplicação em partes menores e mais gerenciáveis.
main = Blueprint('main', __name__)

# definindo o diretório de upload
UPLOAD_FOLDER = 'temp'

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
    
    translated_pages = translate_text_list(pages, dest='en')

    html = "<br><hr>".join(f"<h3>Página {i+1}</h3><pre>{p}</pre>" for i, p in enumerate(translated_pages))
    return html