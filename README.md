# PDF Translate

**PDF Translate** é uma aplicação voltada para a tradução automática de documentos em PDF e imagens que contenham texto. A ferramenta foi projetada para facilitar a leitura e compreensão de materiais em idiomas estrangeiros, utilizando recursos de inteligência artificial aplicada, como OCR com redes neurais e modelos de tradução automática baseados em IA. Com funcionalidades simples e intuitivas, permite extrair, traduzir e reconstruir textos de forma eficiente, mantendo o layout original sempre que possível.

---

## Funcionalidades

### Tradução de PDFs
- Utilizando técnicas de **Inteligência Artificial**, como extração baseada em redes neurais (OCR) e tradução automática por modelos de linguagem.
- Upload de arquivos PDF.
- Seleção do idioma de destino.
- Extração automática de texto do PDF.
- Tradução do conteúdo com **inteligência artificial**.
- Duas opções de saída:
  - **Texto traduzido** (em formato simples).
  - **PDF traduzido** (geração de novo arquivo PDF com o texto traduzido).

### Tradução de Imagens (OCR com IA)
- Baseado em OCR inteligente com Tesseract (redes neurais LSTM) e modelos de tradução automática.
- Upload de imagens (formatos como `.jpg`, `.jpeg`, `.png`, etc.).
- Utilização de OCR (Reconhecimento Óptico de Caracteres) para extrair o texto.
- Tradução automática para o idioma selecionado.
- Exibição do texto traduzido.

---

## Como executar

### 1. Pré-requisitos

- Python 3 instalado na máquina.
- Instalar as dependências do projeto com o comando:
  ```bash
  pip install -r requirements.txt
  ```

### 2. Instalação do Tesseract (para OCR)

Para utilizar a funcionalidade de tradução de imagens:

1. Baixe e instale o Tesseract OCR: [https://github.com/tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract)

2. Após instalar, verifique o caminho do caminho executável do Tesseract no arquivo `utils.py`:

  ```bash
  import pytesseract
  
  pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
  
  ```

---

### 3. Executando o projeto

Você pode iniciar a aplicação de duas formas:

- **Modo debug (atualiza automaticamente ao salvar):**
  ```bash
  python run.py
  ```


- **Modo padrão**
  ```bash
  flask run
  ```

A aplicação estará disponível em:  
`http://localhost:5000`

---
