#!/bin/bash

set -e

echo "Instalando dependências Python..."
pip install pdfplumber --quiet

echo ""
echo "✅ Pronto! Para converter seu CV:"
echo "   python pdf_to_html.py seu-curriculo.pdf"
