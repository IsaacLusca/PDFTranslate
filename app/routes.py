from flask import render_template, request, flash, Blueprint, send_file
import os
from langdetect import detect
from deep_translator import GoogleTranslator

from app.utils import extract_text_from_pdf, translate_text_list, extract_and_translate_pdf, generate_pdf_from_text
from app.utils import translate_image_text, extract_text_from_image, translate_pdf_preserving_layout

main = Blueprint('main', __name__)

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'temp')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@main.route('/')
@main.route('/index')
def index():
    return render_template('index.html')

@main.route('/translate', methods=['POST'])
def translate():
    file = request.files['file']
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    pages = extract_text_from_pdf(filepath)
    target_lang = request.form['language']
    detected_lang = detect(pages[0]) if pages else 'auto'

    translated_pages = [
        GoogleTranslator(source=detected_lang, target=target_lang).translate(p)
        for p in pages
    ]

    html_content = "<br><hr>".join(
        f"<h3>Página {i+1}</h3><pre>{p}</pre>" for i, p in enumerate(translated_pages)
    )

    return render_template('result.html', title='Resultado', translated_text=html_content, description='Texto extraído e traduzido do PDF.')

@main.route('/translate_to_pdf', methods=['POST'])
def translate_to_pdf():
    file = request.files['file']
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    target_lang = request.form['language']
    translated_doc = translate_pdf_preserving_layout(filepath, target_lang)

    filename = os.path.splitext(file.filename)[0]
    output_filename = f"{filename}_translated_{target_lang}.pdf"
    output_path = os.path.join(UPLOAD_FOLDER, output_filename)

    translated_doc.save(output_path)
    translated_doc.close()

    flash('PDF traduzido com sucesso!', 'success')
    return send_file(output_path, as_attachment=True)

@main.route('/translate_image', methods=['POST'])
def translate_image():
    file = request.files['file']
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    target_lang = request.form['language']
    translated_text = translate_image_text(filepath, target_lang)

    return render_template('result.html', title='Resultado', translated_text=translated_text, description='Texto extraído da imagem e traduzido.')
