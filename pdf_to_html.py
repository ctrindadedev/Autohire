#!/usr/bin/env python3
"""
pdf_to_html.py — Converte um currículo em PDF para cv-base.html

Uso:
    python scripts/pdf_to_html.py meu-curriculo.pdf
    python scripts/pdf_to_html.py meu-curriculo.pdf --out cv-base.html

O arquivo gerado é um rascunho estruturado. O Claude Code vai refiná-lo
na sequência — você não precisa editar manualmente.
"""

import sys
import re
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Dependências — instaladas automaticamente pelo setup.sh
# ---------------------------------------------------------------------------
try:
    import pdfplumber
except ImportError:
    sys.exit("Erro: pdfplumber não instalado. Rode: pip install pdfplumber")


# ---------------------------------------------------------------------------
# Extração de texto
# ---------------------------------------------------------------------------

def extract_text(pdf_path: Path) -> list[str]:
    """Retorna lista de linhas não-vazias extraídas do PDF."""
    lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=2)
            if text:
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped:
                        lines.append(stripped)
    return lines


# ---------------------------------------------------------------------------
# Heurísticas de classificação de seções
# ---------------------------------------------------------------------------

SECTION_KEYWORDS = {
    "experience":   ["experience", "work experience", "professional experience",
                     "experiência", "histórico profissional"],
    "education":    ["education", "academic background", "educação", "formação"],
    "skills":       ["skills", "technical skills", "technologies", "stack",
                     "habilidades", "competências"],
    "summary":      ["summary", "profile", "about", "objective", "resumo",
                     "perfil profissional"],
    "projects":     ["projects", "side projects", "projetos", "open source"],
    "certifications": ["certifications", "certificates", "cursos", "certificações"],
    "languages":    ["languages", "idiomas"],
}

def classify_line(line: str) -> str | None:
    """Retorna a chave da seção se a linha for um cabeçalho de seção, senão None."""
    lower = line.lower().strip(".:_-– ")
    for section, keywords in SECTION_KEYWORDS.items():
        if lower in keywords:
            return section
        # Linha curta (≤ 4 palavras) que começa com keyword
        if len(line.split()) <= 4:
            for kw in keywords:
                if lower.startswith(kw):
                    return section
    return None

def looks_like_bullet(line: str) -> bool:
    bullet_prefixes = ("•", "-", "–", "▪", "*", "◦", "→")
    return any(line.startswith(p) for p in bullet_prefixes)

def clean_bullet(line: str) -> str:
    return re.sub(r"^[•\-–▪\*◦→]\s*", "", line).strip()


# ---------------------------------------------------------------------------
# Parser principal
# ---------------------------------------------------------------------------

def parse_cv(lines: list[str]) -> dict:
    """Agrupa as linhas em seções estruturadas."""
    cv = {
        "header": [],
        "summary": [],
        "skills": [],
        "experience": [],
        "education": [],
        "projects": [],
        "certifications": [],
        "languages": [],
        "other": [],
    }

    current_section = "header"

    for line in lines:
        section = classify_line(line)
        if section:
            current_section = section
            continue
        cv[current_section].append(line)

    return cv


# ---------------------------------------------------------------------------
# Geração de HTML
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>CV — {name}</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: 'Arial', sans-serif;
      font-size: 11px;
      line-height: 1.45;
      color: #1a1a1a;
      max-width: 210mm;
      margin: 0 auto;
      padding: 12mm 14mm;
    }}
    .header {{ border-bottom: 2px solid #1a1a1a; padding-bottom: 8px; margin-bottom: 10px; }}
    .name {{ font-size: 22px; font-weight: 700; letter-spacing: -0.5px; }}
    .contact {{ font-size: 10px; color: #555; margin-top: 4px; }}
    .contact a {{ color: #555; text-decoration: none; }}
    .section {{ margin-bottom: 10px; }}
    .section-title {{
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 1px;
      border-bottom: 1px solid #ccc;
      padding-bottom: 2px;
      margin-bottom: 6px;
    }}
    .job {{ margin-bottom: 8px; }}
    .job-header {{ display: flex; justify-content: space-between; align-items: baseline; }}
    .job-company {{ font-weight: 700; font-size: 11.5px; }}
    .job-period {{ font-size: 10px; color: #666; }}
    .job-role {{ color: #333; font-size: 10.5px; margin-bottom: 3px; }}
    ul {{ padding-left: 14px; }}
    li {{ margin-bottom: 2px; }}
    .skills-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 4px 20px; }}
    .skill-category {{ font-weight: 700; }}
    @media print {{
      body {{ padding: 10mm 12mm; }}
      @page {{ size: A4; margin: 0; }}
    }}
  </style>
</head>
<body>

{body}

</body>
</html>
"""

def render_lines_as_p(lines: list[str]) -> str:
    out = []
    for line in lines:
        if looks_like_bullet(line):
            out.append(f"  <li>{clean_bullet(line)}</li>")
        else:
            out.append(f"  <p>{line}</p>")
    return "\n".join(out)

def render_lines_as_ul(lines: list[str]) -> str:
    items = []
    for line in lines:
        text = clean_bullet(line) if looks_like_bullet(line) else line
        items.append(f"    <li>{text}</li>")
    return "<ul>\n" + "\n".join(items) + "\n  </ul>"

def build_html(cv: dict) -> str:
    sections = []

    # --- HEADER ---
    header_lines = cv["header"]
    name = header_lines[0] if header_lines else "Your Name"
    contact_lines = header_lines[1:] if len(header_lines) > 1 else []
    contact_html = " &nbsp;|&nbsp; ".join(contact_lines)
    sections.append(f"""\
  <div class="header">
    <div class="name">{name}</div>
    <div class="contact">{contact_html}</div>
  </div>""")

    # --- SUMMARY ---
    if cv["summary"]:
        body = "\n".join(f"  <p>{l}</p>" for l in cv["summary"])
        sections.append(f"""\
  <div class="section">
    <div class="section-title">Professional Summary</div>
{body}
  </div>""")

    # --- SKILLS ---
    if cv["skills"]:
        raw = " | ".join(cv["skills"])
        sections.append(f"""\
  <div class="section">
    <div class="section-title">Technical Skills</div>
    <!-- TODO: organizar por categorias (Languages, Backend, Cloud, AI & Data, etc.) -->
    <div class="skills-grid">
      <div>{raw}</div>
    </div>
  </div>""")

    # --- EXPERIENCE ---
    if cv["experience"]:
        items_html = render_lines_as_p(cv["experience"])
        sections.append(f"""\
  <div class="section">
    <div class="section-title">Experience</div>
    <!-- TODO: Claude Code vai estruturar em blocos .job com company, period, role e bullets -->
{items_html}
  </div>""")

    # --- PROJECTS ---
    if cv["projects"]:
        items_html = render_lines_as_p(cv["projects"])
        sections.append(f"""\
  <div class="section">
    <div class="section-title">Projects</div>
{items_html}
  </div>""")

    # --- EDUCATION ---
    if cv["education"]:
        items_html = render_lines_as_p(cv["education"])
        sections.append(f"""\
  <div class="section">
    <div class="section-title">Education</div>
{items_html}
  </div>""")

    # --- CERTIFICATIONS ---
    if cv["certifications"]:
        items_html = render_lines_as_p(cv["certifications"])
        sections.append(f"""\
  <div class="section">
    <div class="section-title">Certifications</div>
{items_html}
  </div>""")

    # --- LANGUAGES ---
    if cv["languages"]:
        items_html = render_lines_as_p(cv["languages"])
        sections.append(f"""\
  <div class="section">
    <div class="section-title">Languages</div>
{items_html}
  </div>""")

    # --- OTHER (fallback) ---
    if cv["other"]:
        items_html = render_lines_as_p(cv["other"])
        sections.append(f"""\
  <!-- Conteúdo não classificado — revisar -->
  <div class="section">
{items_html}
  </div>""")

    body = "\n\n".join(sections)
    name = cv["header"][0] if cv["header"] else "CV"
    return HTML_TEMPLATE.format(name=name, body=body)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Converte currículo PDF → cv-base.html")
    parser.add_argument("pdf", help="Caminho para o arquivo PDF do currículo")
    parser.add_argument("--out", default="cv-base.html",
                        help="Arquivo de saída (padrão: cv-base.html)")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        sys.exit(f"Erro: arquivo não encontrado: {pdf_path}")

    print(f"📄 Extraindo texto de {pdf_path.name}...")
    lines = extract_text(pdf_path)

    if not lines:
        sys.exit("Erro: nenhum texto extraído. O PDF pode ser uma imagem escaneada — use um PDF com texto selecionável.")

    print(f"   {len(lines)} linhas extraídas.")

    print("🔍 Classificando seções...")
    cv = parse_cv(lines)

    print("🏗️  Gerando HTML...")
    html = build_html(cv)

    out_path = Path(args.out)
    out_path.write_text(html, encoding="utf-8")
    print(f"✅ Salvo em: {out_path}")
    print()
    print("Próximo passo: abra o Claude Code e diga:")
    print('  "Acabei de gerar o cv-base.html a partir do meu PDF.')
    print('   Revise a estrutura, organize as seções de Experience em blocos')
    print('   .job corretos e deixe o arquivo pronto como fonte da verdade."')


if __name__ == "__main__":
    main()
