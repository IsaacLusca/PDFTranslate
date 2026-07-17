import fitz
from deep_translator import GoogleTranslator
from concurrent.futures import ThreadPoolExecutor, as_completed

input_pdf = r'C:\Users\lucas\OneDrive\Documentos\AutoMinuta_V1.0\lista-projetos\PDFTranslate\teste\Get_Started_With_Smallpdf.pdf'
output_pdf = r'C:\Users\lucas\OneDrive\Documentos\AutoMinuta_V1.0\lista-projetos\PDFTranslate\teste\output_v2.pdf'

def translate_text_list(texts, dest, max_workers=10):
    def _translate(t):
        try:
            return GoogleTranslator(source="auto", target=dest).translate(t)
        except Exception:
            return t
    results = [None] * len(texts)
    with ThreadPoolExecutor(max_workers=max_workers) as exe:
        futures = {exe.submit(_translate, texts[i]): i for i in range(len(texts))}
        for fut in as_completed(futures):
            idx = futures[fut]
            results[idx] = fut.result()
    return results

src = fitz.open(input_pdf)
dst = fitz.open()
dst.insert_pdf(src)
src.close()

for pno in range(len(dst)):
    page = dst[pno]
    text_dict = page.get_text("dict")
    spans = [
        span
        for block in text_dict["blocks"] if "lines" in block
        for line in block["lines"]
        for span in line["spans"]
        if span["text"].strip()
    ]

    originals = [span["text"] for span in spans]
    translated = translate_text_list(originals, "pt", max_workers=10)

    for span in spans:
        page.add_redact_annot(fitz.Rect(span["bbox"]), text="")
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)

    for span, tr in zip(spans, translated):
        r = fitz.Rect(span["bbox"])
        r.x0 = max(r.x0, page.rect.x0 + 2)
        r.x1 = min(r.x1, page.rect.x1 - 2)
        r.y1 = min(r.y1, page.rect.y1 - 2)
        fs = span["size"]
        while fs > 4:
            ret = page.insert_textbox(r, tr, fontsize=fs, fontname="helv",
                                       fill=(0,0,0), align=fitz.TEXT_ALIGN_LEFT)
            if ret >= 0:
                break
            fs -= 1
        if fs <= 4:
            print("  Nao coube mesmo: %r" % tr)

dst.save(output_pdf)
dst.close()
print("Salvo:", output_pdf)

doc2 = fitz.open(output_pdf)
for i, p in enumerate(doc2):
    txt = p.get_text()
    print("\n=== Pagina %d texto: %r" % (i+1, txt[:500]))
doc2.close()
