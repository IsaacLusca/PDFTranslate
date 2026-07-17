import sys
sys.path.insert(0, r'C:\Users\lucas\OneDrive\Documentos\AutoMinuta_V1.0\lista-projetos\PDFTranslate')
from app.utils import translate_pdf_preserving_layout

input_pdf = r'C:\Users\lucas\OneDrive\Documentos\AutoMinuta_V1.0\lista-projetos\PDFTranslate\teste\Get_Started_With_Smallpdf.pdf'
output_pdf = r'C:\Users\lucas\OneDrive\Documentos\AutoMinuta_V1.0\lista-projetos\PDFTranslate\teste\output.pdf'

doc = translate_pdf_preserving_layout(input_pdf, 'pt')
doc.save(output_pdf)
doc.close()
print('PDF traduzido salvo em:', output_pdf)
