from flask import render_template, request, flash, Blueprint, send_file, session
import os
import tempfile
import io
from langdetect import detect
from deep_translator import GoogleTranslator

from app.utils import extract_text_from_pdf, translate_text_list, extract_and_translate_pdf, generate_pdf_from_text
from app.utils import translate_image_text, extract_text_from_image, translate_pdf_preserving_layout

main = Blueprint('main', __name__)

TEMP_DIR = tempfile.mkdtemp(prefix='pdftranslate_')

def clear_flashes():
    session.pop('_flashes', None)

@main.route('/')
@main.route('/index')
def index():
    clear_flashes()
    return render_template('index.html')

@main.route('/translate', methods=['POST'])
def translate():
    clear_flashes()
    file = request.files['file']
    filepath = os.path.join(TEMP_DIR, file.filename)
    file.save(filepath)
    try:
        pages = extract_text_from_pdf(filepath)
        if not pages or not any(p.strip() for p in pages):
            flash('Nenhum texto encontrado no PDF.', 'error')
            return render_template('index.html')

        target_lang = request.form['language']
        detected_lang = detect(pages[0]) if pages[0].strip() else 'auto'

        translated_pages = [
            GoogleTranslator(source=detected_lang, target=target_lang).translate(p)
            for p in pages
        ]

        html_content = "<br><hr>".join(
            f"<h3>Página {i+1}</h3><pre>{p}</pre>" for i, p in enumerate(translated_pages)
        )

        return render_template('result.html', title='Resultado', translated_text=html_content, description='Texto extraído e traduzido do PDF.')
    except Exception as e:
        flash(f'Erro ao processar PDF: {str(e)}', 'error')
        return render_template('index.html')
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

@main.route('/translate_to_pdf', methods=['POST'])
def translate_to_pdf():
    clear_flashes()
    file = request.files['file']
    filepath = os.path.join(TEMP_DIR, file.filename)
    file.save(filepath)
    output_path = None
    try:
        target_lang = request.form['language']
        translated_doc = translate_pdf_preserving_layout(filepath, target_lang)

        filename = os.path.splitext(file.filename)[0]
        output_filename = f"{filename}_translated_{target_lang}.pdf"
        output_path = os.path.join(TEMP_DIR, output_filename)
        translated_doc.save(output_path, garbage=4, deflate=True)
        translated_doc.close()

        with open(output_path, 'rb') as f:
            data = io.BytesIO(f.read())

        flash('PDF traduzido com sucesso!', 'success')
        return send_file(data, as_attachment=True, download_name=output_filename, mimetype='application/pdf')
    except Exception as e:
        flash(f'Erro ao processar PDF: {str(e)}', 'error')
        return render_template('index.html')
    finally:
        for p in [filepath, output_path]:
            if p and os.path.exists(p):
                os.remove(p)

@main.route('/translate_image', methods=['POST'])
def translate_image():
    clear_flashes()
    file = request.files['file']
    filepath = os.path.join(TEMP_DIR, file.filename)
    file.save(filepath)
    try:
        target_lang = request.form['language']
        translated_text = translate_image_text(filepath, target_lang)
        return render_template('result.html', title='Resultado',
                               translated_text=translated_text,
                               description='Texto extraído da imagem e traduzido.')
    except RuntimeError as e:
        flash(str(e), 'error')
        return render_template('index.html')
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)
