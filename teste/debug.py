import fitz, os, sys
sys.path.insert(0, r'C:\Users\lucas\OneDrive\Documentos\AutoMinuta_V1.0\lista-projetos\PDFTranslate')

input_pdf = r'C:\Users\lucas\OneDrive\Documentos\AutoMinuta_V1.0\lista-projetos\PDFTranslate\teste\Get_Started_With_Smallpdf.pdf'
output_pdf = r'C:\Users\lucas\OneDrive\Documentos\AutoMinuta_V1.0\lista-projetos\PDFTranslate\teste\output_debug.pdf'

src = fitz.open(input_pdf)
print("Paginas:", len(src))

p = src[0]
text_dict = p.get_text("dict")
spans = [
    span
    for block in text_dict["blocks"] if "lines" in block
    for line in block["lines"]
    for span in line["spans"]
    if span["text"].strip()
]
print("Spans encontrados:", len(spans))
for i, s in enumerate(spans[:5]):
    print("  Span %d: text=%r, bbox=%s, origin=%s, size=%s" % (i, s["text"][:60], s["bbox"], s["origin"], s["size"]))

if spans:
    from deep_translator import GoogleTranslator
    tr = GoogleTranslator(source="auto", target="pt").translate(spans[0]["text"])
    print("Traducao:", tr)

    dst = fitz.open()
    dst.insert_pdf(src)
    src.close()
    page = dst[0]
    page.add_redact_annot(fitz.Rect(spans[0]["bbox"]), text="")
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)

    r = fitz.Rect(spans[0]["bbox"])
    ret = page.insert_textbox(r, tr, fontsize=spans[0]["size"], fontname="helv", fill=(0,0,0), align=fitz.TEXT_ALIGN_LEFT)
    print("Insert_textbox retorno:", ret)

    text2 = page.get_text()
    print("Texto apos insercao:", text2[:300])

    dst.save(output_pdf)
    dst.close()
    print("Debug PDF salvo")
