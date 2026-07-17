# PDFTranslate

Aplicação web para tradução automática de documentos PDF e imagens, utilizando OCR com redes neurais e modelos de tradução automática.

**🔗 Live:** https://pdftranslate.onrender.com

## Funcionalidades

- **PDF para PDF:** Traduz o documento mantendo o layout original
- **PDF para Texto:** Extrai e traduz o texto para visualização
- **Imagem para Texto:** Reconhece texto em imagens (OCR) e traduz
- Suporte aos idiomas: português, inglês, espanhol e russo
- Tradução paralela para melhor performance

## Tecnologias

- **Backend:** Python, Flask
- **OCR:** Tesseract (redes neurais LSTM)
- **Tradução:** Google Translate API (deep-translator)
- **PDF:** PyMuPDF (fitz)
- **Frontend:** HTML, CSS (tema escuro personalizado)

## Como rodar

```bash
git clone https://github.com/IsaacLusca/PDFTranslate.git
cd PDFTranslate

python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -r requirements.txt

python wsgi.py
```

Acesse em: `http://localhost:5000`

## Deploy

O projeto está hospedado no Render: https://pdftranslate.onrender.com

> ⚠️ A função de OCR de imagem (Tesseract) não funciona no Render por limitações do ambiente gratuito. As funções de PDF para texto e PDF para PDF funcionam normalmente.

## Estrutura do projeto

```
PDFTranslate/
├── app/
│   ├── static/css/style.css   # Estilos da interface
│   ├── templates/
│   │   ├── base.html          # Layout base
│   │   ├── index.html         # Página inicial com formulários
│   │   └── result.html        # Página de resultado
│   ├── __init__.py            # Factory do app Flask
│   ├── routes.py              # Rotas da aplicação
│   └── utils.py               # Funções de OCR, PDF e tradução
├── wsgi.py                    # Ponto de entrada
├── requirements.txt           # Dependências
└── README.md
```
