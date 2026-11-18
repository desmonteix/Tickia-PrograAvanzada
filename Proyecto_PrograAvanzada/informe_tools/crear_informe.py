"""Construye el Word académico a partir del informe editable y evidencia real.

Usa Microsoft Word para actualizar el índice y exportar el PDF. No modifica
documentos abiertos del usuario: crea una instancia independiente de Word.
"""
from collections import Counter
from pathlib import Path
import argparse
import json
import re
import shutil
import sys

from docx import Document
from docx.enum.section import WD_SECTION_START, WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'Proyecto_PrograAvanzada/entregables/informe'
BUILD = ROOT / 'Proyecto_PrograAvanzada/.local/informe-build'


def field(paragraph, instruction):
    run = paragraph.add_run()
    begin = OxmlElement('w:fldChar'); begin.set(qn('w:fldCharType'), 'begin')
    code = OxmlElement('w:instrText'); code.set(qn('xml:space'), 'preserve'); code.text = instruction
    separator = OxmlElement('w:fldChar'); separator.set(qn('w:fldCharType'), 'separate')
    placeholder = OxmlElement('w:t'); placeholder.text = 'Actualizar campo en Microsoft Word'
    end = OxmlElement('w:fldChar'); end.set(qn('w:fldCharType'), 'end')
    for element in (begin, code, separator, placeholder, end): run._r.append(element)


def inline(paragraph, text):
    for fragment in re.split(r'(\*\*.*?\*\*|`[^`]+`)', text):
        if fragment.startswith('**') and fragment.endswith('**'):
            paragraph.add_run(fragment[2:-2]).bold = True
        elif fragment.startswith('`') and fragment.endswith('`'):
            run = paragraph.add_run(fragment[1:-1]); run.font.name = 'Consolas'; run.font.size = Pt(9)
        else: paragraph.add_run(fragment)


def format_section(section, landscape=False):
    section.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
    section.page_width = Cm(29.7 if landscape else 21)
    section.page_height = Cm(21 if landscape else 29.7)
    section.left_margin = section.right_margin = Cm(2 if landscape else 2.5)
    section.top_margin = section.bottom_margin = Cm(1.9 if landscape else 2.3)
    section.header_distance = section.footer_distance = Cm(.9)
    section.different_first_page_header_footer = False


def table(doc, lines):
    values = [[c.strip() for c in line.strip().strip('|').split('|')] for line in lines]
    values = [row for row in values if not all(re.fullmatch(r':?-+:?', c) for c in row)]
    result = doc.add_table(rows=0, cols=len(values[0])); result.style = 'Table Grid'
    for index, values_row in enumerate(values):
        cells = result.add_row().cells
        props = cells[0]._tc.getparent().get_or_add_trPr()
        no_split = OxmlElement('w:cantSplit'); props.append(no_split)
        if index == 0:
            repeat = OxmlElement('w:tblHeader'); props.append(repeat)
        for cell, value in zip(cells, values_row):
            paragraph = cell.paragraphs[0]; paragraph.paragraph_format.line_spacing = 1
            paragraph.paragraph_format.space_after = Pt(4); paragraph.paragraph_format.space_before = Pt(4)
            inline(paragraph, value)
            for run in paragraph.runs:
                if run.font.name != 'Consolas': run.font.size = Pt(9.5)
                if index == 0: run.bold = True; run.font.color.rgb = RGBColor.from_string('FFFFFF')
            if index == 0:
                shade = OxmlElement('w:shd'); shade.set(qn('w:fill'), '183B56'); cell._tc.get_or_add_tcPr().append(shade)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def build():
    doc = Document()
    doc.core_properties.title = 'Tickia: marketplace multivendedor — informe de proyecto'
    doc.core_properties.subject = 'Programación avanzada, MySQL, patrones de diseño y análisis de datos'
    doc.core_properties.author = 'Equipo del proyecto Tickia'
    doc.core_properties.keywords = 'MySQL, Python, Pandas, 3FN, UML, marketplace'
    normal = doc.styles['Normal']; normal.font.name = 'Times New Roman'; normal.font.size = Pt(12)
    normal.paragraph_format.line_spacing = 1.5; normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for name, size in [('Heading 1', 16), ('Heading 2', 13), ('Heading 3', 12)]:
        style = doc.styles[name]; style.font.name = 'Times New Roman'; style.font.size = Pt(size)
        style.font.color.rgb = RGBColor.from_string('183B56')
        style.paragraph_format.space_before = Pt(12); style.paragraph_format.space_after = Pt(8)
        style.paragraph_format.keep_with_next = True
    caption = doc.styles['Caption']; caption.font.name = 'Times New Roman'; caption.font.size = Pt(10)
    caption.font.color.rgb = RGBColor.from_string('304B60'); caption.paragraph_format.line_spacing = 1
    caption.paragraph_format.space_before = Pt(5); caption.paragraph_format.space_after = Pt(0)

    # La primera sección tiene una sola hoja vacía y encabezados/pies propios vacíos.
    cover = doc.sections[0]; format_section(cover)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)
    index = doc.add_section(WD_SECTION_START.NEW_PAGE); format_section(index)
    index.header.is_linked_to_previous = False; index.footer.is_linked_to_previous = False
    header = index.header.paragraphs[0]; header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = header.add_run('TICKIA · PROYECTO DE PROGRAMACIÓN AVANZADA'); run.font.size = Pt(8); run.font.color.rgb = RGBColor.from_string('607385')
    footer = index.footer.paragraphs[0]; footer.alignment = WD_ALIGN_PARAGRAPH.CENTER; field(footer, 'PAGE')
    page_num = OxmlElement('w:pgNumType'); page_num.set(qn('w:fmt'), 'lowerRoman'); page_num.set(qn('w:start'), '1'); index._sectPr.append(page_num)
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(15)
    r = p.add_run('ÍNDICE'); r.bold = True; r.font.size = Pt(16); r.font.color.rgb = RGBColor.from_string('183B56')
    field(doc.add_paragraph(), 'TOC \\o "1-2" \\h \\z \\u')
    body = doc.add_section(WD_SECTION_START.NEW_PAGE); format_section(body)
    numbering = body._sectPr.find(qn('w:pgNumType'))
    if numbering is not None: body._sectPr.remove(numbering)
    numbering = OxmlElement('w:pgNumType'); numbering.set(qn('w:fmt'), 'decimal'); numbering.set(qn('w:start'), '1'); body._sectPr.append(numbering)
    landscape = False; fresh = True; after_figure = False; figure_number = 0

    def orient(wide):
        nonlocal landscape, fresh
        if wide != landscape:
            sec = doc.add_section(WD_SECTION_START.NEW_PAGE); format_section(sec, wide)
            # Word copia el reinicio de numeración: se retira para continuar la secuencia.
            for item in list(sec._sectPr.findall(qn('w:pgNumType'))): sec._sectPr.remove(item)
            landscape = wide; fresh = True

    lines = (OUT / 'Informe_Tickia.md').read_text(encoding='utf-8').splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith('<!--'): i += 1; continue
        picture = re.fullmatch(r'!\[(.*?)\]\((.*?)\)', line)
        if picture:
            path = OUT / picture.group(2)
            with Image.open(path) as im: width, height = im.size
            wide = width / height > 1.22
            orient(wide)
            if not fresh: doc.add_page_break()
            max_width, max_height = ((25.4, 13.9) if wide else (16, 20.4))
            image_width = min(max_width, max_height * width / height)
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.line_spacing = 1; p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.keep_with_next = True
            p.add_run().add_picture(str(path), width=Cm(image_width))
            figure_number += 1
            p = doc.add_paragraph(style='Caption'); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run(f'Figura {figure_number}. {picture.group(1)}')
            fresh = False; after_figure = True; i += 1; continue
        orient(False)
        if after_figure:
            if not fresh: doc.add_page_break()
            fresh = True; after_figure = False
        heading = re.match(r'^(#{1,3}) (.+)$', line)
        if heading:
            level = len(heading.group(1))
            if level == 1 and not fresh: doc.add_page_break()
            doc.add_paragraph(heading.group(2), style=f'Heading {level}')
            fresh = False; i += 1; continue
        if line.startswith('```'):
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                p = doc.add_paragraph(); fmt = p.paragraph_format
                fmt.line_spacing = 1; fmt.space_before = fmt.space_after = Pt(0)
                fmt.alignment = WD_ALIGN_PARAGRAPH.LEFT; fmt.keep_with_next = False
                run = p.add_run(lines[i] or ' '); run.font.name = 'Consolas'; run.font.size = Pt(8)
                shade = OxmlElement('w:shd'); shade.set(qn('w:fill'), 'F3F5F7'); p._p.get_or_add_pPr().append(shade)
                i += 1
            doc.add_paragraph().paragraph_format.space_after = Pt(0)
            i += 1; fresh = False; continue
        if line.startswith('|'):
            block = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                block.append(lines[i]); i += 1
            table(doc, block); fresh = False; continue
        bullet = re.match(r'^[-*] (.+)$', line)
        paragraph = doc.add_paragraph(style='List Bullet' if bullet else 'Normal')
        inline(paragraph, bullet.group(1) if bullet else line)
        fresh = False; i += 1
    settings = doc.settings.element
    update = OxmlElement('w:updateFields'); update.set(qn('w:val'), 'true'); settings.append(update)
    target = OUT / 'Informe_Tickia.docx'; doc.save(target)
    return target, figure_number


def publish(target, figures):
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    word = None; document = None
    try:
        word = win32com.client.DispatchEx('Word.Application'); word.Visible = False; word.DisplayAlerts = 0
        document = word.Documents.Open(str(target.resolve()), ReadOnly=False, AddToRecentFiles=False)
        document.Fields.Update()
        for index in range(1, document.TablesOfContents.Count + 1): document.TablesOfContents(index).Update()
        document.Repaginate()
        for index in range(1, document.TablesOfContents.Count + 1): document.TablesOfContents(index).UpdatePageNumbers()
        document.Save()
        document.ExportAsFixedFormat(str(target.with_suffix('.pdf').resolve()), 17, OpenAfterExport=False)
    finally:
        if document is not None: document.Close(SaveChanges=False)
        if word is not None: word.Quit()
        pythoncom.CoUninitialize()
    import fitz
    pdf = fitz.open(target.with_suffix('.pdf'))
    texts = [page.get_text() for page in pdf]
    assert not texts[0].strip() and not pdf[0].get_images(), 'La carátula debe estar vacía.'
    assert 'ÍNDICE' in texts[1], 'El índice debe comenzar en la segunda hoja.'
    assert 'Enunciado del caso' in texts[1], 'El índice no fue actualizado.'
    assert all('Error! Bookmark' not in value and '¡Error!' not in value for value in texts)
    blanks = [i + 1 for i, page in enumerate(pdf) if not texts[i].strip() and not page.get_images()]
    assert blanks == [1], f'Páginas en blanco inesperadas: {blanks}'
    all_text = '\n'.join(texts)
    for label in ('111.016', '247.482', '278,67', 'RFM', 'tr_pedido_validar_estado', 'Bibliografía', 'Anexos'):
        assert label in all_text, f'Falta contenido: {label}'
    evidence = dict(pages=len(pdf), figures=figures, cover_blank=True, index_starts_page=2,
                    empty_pages=blanks, native_word_toc=True, source_markdown='Informe_Tickia.md')
    (BUILD / 'validacion_informe.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding='utf-8')
    preview = BUILD / 'revision_word'; preview.mkdir(exist_ok=True)
    selected = sorted(set([0, 1, 2, 3, len(pdf)-1] + list(range(6, len(pdf), 7))))
    for index in selected: pdf[index].get_pixmap(matrix=fitz.Matrix(1, 1)).save(preview / f'pagina_{index+1:03}.png')
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--sin-word', action='store_true'); args = parser.parse_args()
    path, figures = build()
    if not args.sin_word: publish(path, figures)
    print('Word creado:', path.name)
