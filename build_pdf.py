import argparse
import ctypes
import ctypes.util
import html
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_library(name):
    path = ctypes.util.find_library(name)
    if path is None:
        raise RuntimeError(f'Required system library not found: {name}')
    return ctypes.CDLL(path)


CAIRO = load_library('cairo')
PANGO = load_library('pango-1.0')
PANGO_CAIRO = load_library('pangocairo-1.0')
GOBJECT = load_library('gobject-2.0')
PANGO_SCALE = 1024
HEADING_SIZES = {1: 21, 2: 14, 3: 11.5}
HEADING_SPACING = {1: 0, 2: 15, 3: 10}
HEADING_PATTERN = re.compile(r'^(#{1,3})\s+(.+)$')
TABLE_SEPARATOR = re.compile(r':?-+:?')


def bind(lib, name, restype, *args):
    function = getattr(lib, name)
    function.restype = restype
    function.argtypes = args
    return function


Pointer, Double, Integer, String = ctypes.c_void_p, ctypes.c_double, ctypes.c_int, ctypes.c_char_p
cairo_pdf_surface_create = bind(CAIRO, 'cairo_pdf_surface_create', Pointer, String, Double, Double)
cairo_surface_finish = bind(CAIRO, 'cairo_surface_finish', None, Pointer)
cairo_surface_destroy = bind(CAIRO, 'cairo_surface_destroy', None, Pointer)
cairo_surface_status = bind(CAIRO, 'cairo_surface_status', Integer, Pointer)
cairo_create = bind(CAIRO, 'cairo_create', Pointer, Pointer)
cairo_destroy = bind(CAIRO, 'cairo_destroy', None, Pointer)
cairo_status = bind(CAIRO, 'cairo_status', Integer, Pointer)
cairo_move_to = bind(CAIRO, 'cairo_move_to', None, Pointer, Double, Double)
cairo_set_source_rgb = bind(CAIRO, 'cairo_set_source_rgb', None, Pointer, Double, Double, Double)
cairo_rectangle = bind(CAIRO, 'cairo_rectangle', None, Pointer, Double, Double, Double, Double)
cairo_fill = bind(CAIRO, 'cairo_fill', None, Pointer)
cairo_stroke = bind(CAIRO, 'cairo_stroke', None, Pointer)
cairo_set_line_width = bind(CAIRO, 'cairo_set_line_width', None, Pointer, Double)
cairo_line_to = bind(CAIRO, 'cairo_line_to', None, Pointer, Double, Double)
cairo_show_page = bind(CAIRO, 'cairo_show_page', None, Pointer)
cairo_tag_begin = bind(CAIRO, 'cairo_tag_begin', None, Pointer, String, String)
cairo_tag_end = bind(CAIRO, 'cairo_tag_end', None, Pointer, String)
cairo_pdf_surface_set_metadata = bind(CAIRO, 'cairo_pdf_surface_set_metadata', None, Pointer, Integer, String)
pango_cairo_create_layout = bind(PANGO_CAIRO, 'pango_cairo_create_layout', Pointer, Pointer)
pango_cairo_show_layout = bind(PANGO_CAIRO, 'pango_cairo_show_layout', None, Pointer, Pointer)
pango_font_description_new = bind(PANGO, 'pango_font_description_new', Pointer)
pango_font_description_set_family = bind(PANGO, 'pango_font_description_set_family', None, Pointer, String)
pango_font_description_set_absolute_size = bind(PANGO, 'pango_font_description_set_absolute_size', None, Pointer, Double)
pango_font_description_set_weight = bind(PANGO, 'pango_font_description_set_weight', None, Pointer, Integer)
pango_font_description_free = bind(PANGO, 'pango_font_description_free', None, Pointer)
pango_layout_set_font_description = bind(PANGO, 'pango_layout_set_font_description', None, Pointer, Pointer)
pango_layout_set_markup = bind(PANGO, 'pango_layout_set_markup', None, Pointer, String, Integer)
pango_layout_set_width = bind(PANGO, 'pango_layout_set_width', None, Pointer, Integer)
pango_layout_set_spacing = bind(PANGO, 'pango_layout_set_spacing', None, Pointer, Integer)
pango_layout_set_wrap = bind(PANGO, 'pango_layout_set_wrap', None, Pointer, Integer)
g_object_unref = bind(GOBJECT, 'g_object_unref', None, Pointer)


class PangoRectangle(ctypes.Structure):
    _fields_ = [(name, Integer) for name in ('x', 'y', 'width', 'height')]


pango_layout_get_extents = bind(PANGO, 'pango_layout_get_extents', None, Pointer, ctypes.POINTER(PangoRectangle), ctypes.POINTER(PangoRectangle))
pango_layout_index_to_pos = bind(PANGO, 'pango_layout_index_to_pos', None, Pointer, Integer, ctypes.POINTER(PangoRectangle))
INLINE_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*|`([^`]+)`')


def parse_inline(text):
    markup = []
    links = []
    byte_offset = 0
    end = 0
    for match in INLINE_PATTERN.finditer(text):
        prefix = text[end:match.start()]
        markup.append(html.escape(prefix))
        byte_offset += len(prefix.encode('utf-8'))
        if match.group(1) is not None:
            label, url = match.group(1, 2)
            start = byte_offset
            markup.append('<span foreground="#215c8b">' + html.escape(label) + '</span>')
            links.append((start, label, url))
        elif match.group(3) is not None:
            label = match.group(3)
            markup.append('<b>' + html.escape(label) + '</b>')
        else:
            label = match.group(4)
            markup.append('<tt>' + html.escape(label) + '</tt>')
        byte_offset += len(label.encode('utf-8'))
        end = match.end()
    markup.append(html.escape(text[end:]))
    return ''.join(markup), links


class PdfDocument:
    width, height, margin = 595.276, 841.89, 49
    bottom = 789

    def __init__(self, path, title="Наблюдаемость микросервисов: план обзора и источники", footer="План обзора литературы • 14.10.2026"):
        self.footer_text = footer
        self.surface = cairo_pdf_surface_create(os.fsencode(path), self.width, self.height)
        cairo_pdf_surface_set_metadata(self.surface, 0, title.encode())
        cairo_pdf_surface_set_metadata(self.surface, 1, 'Соколов Артем Николаевич'.encode())
        cairo_pdf_surface_set_metadata(self.surface, 2, 'OpenTelemetry, диагностика, трассировки, отбор данных'.encode())
        self.context = cairo_create(self.surface)
        self.check_status()
        self.page = 1
        self.y = self.margin
        self.blocks = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.finish()
        else:
            self.close()

    def check_status(self):
        context_code = cairo_status(self.context)
        surface_code = cairo_surface_status(self.surface)
        if context_code or surface_code:
            self.close()
            raise RuntimeError(f'Cairo status: {context_code}, surface: {surface_code}')

    def close(self):
        if self.context is not None:
            cairo_destroy(self.context)
            self.context = None
        if self.surface is not None:
            cairo_surface_destroy(self.surface)
            self.surface = None

    @property
    def content_width(self):
        return self.width - 2 * self.margin

    def measure(self, text, width, size: float = 11, bold=False, sans=False):
        layout, height, _ = self.layout(text, width, size, bold, sans)
        g_object_unref(layout)
        return height

    def layout(self, text, width, size: float = 11, bold=False, sans=False):
        layout = pango_cairo_create_layout(self.context)
        font = pango_font_description_new()
        pango_font_description_set_family(font, b'Liberation Sans' if sans else b'Liberation Serif')
        pango_font_description_set_absolute_size(font, size * PANGO_SCALE)
        pango_font_description_set_weight(font, 700 if bold else 400)
        pango_layout_set_font_description(layout, font)
        pango_font_description_free(font)
        pango_layout_set_width(layout, int(width * PANGO_SCALE))
        pango_layout_set_wrap(layout, 2)
        pango_layout_set_spacing(layout, int(size * .29 * PANGO_SCALE))
        markup, links = parse_inline(text)
        pango_layout_set_markup(layout, markup.encode(), -1)
        logical, ink = PangoRectangle(), PangoRectangle()
        pango_layout_get_extents(layout, ctypes.byref(ink), ctypes.byref(logical))
        return layout, logical.height / PANGO_SCALE, links

    def draw(self, text, x, y, width, size: float = 11, bold=False, sans=False, tint=None):
        layout, height, links = self.layout(text, width, size, bold, sans)
        try:
            cairo_set_source_rgb(self.context, *(tint or (.12, .14, .17)))
            cairo_move_to(self.context, x, y)
            pango_cairo_show_layout(self.context, layout)
            self.draw_links(layout, links, x, y)
        finally:
            g_object_unref(layout)
        self.blocks.append((self.page, x, y, width, height))
        return height

    def draw_links(self, layout, links, x, y):
        for start, label, url in links:
            rows = {}
            offset = start
            for character in label:
                rect = PangoRectangle()
                pango_layout_index_to_pos(layout, offset, ctypes.byref(rect))
                offset += len(character.encode('utf-8'))
                left, right = sorted((rect.x / PANGO_SCALE, (rect.x + rect.width) / PANGO_SCALE))
                top = round(rect.y / PANGO_SCALE, 3)
                height = rect.height / PANGO_SCALE
                if top in rows:
                    row_left, row_right, row_height = rows[top]
                    rows[top] = min(row_left, left), max(row_right, right), max(row_height, height)
                else:
                    rows[top] = left, right, height
            safe_url = url.replace('\\', '\\\\').replace("'", "\\'")
            for top, (left, right, height) in rows.items():
                if right <= left:
                    continue
                attributes = (
                    f'rect=[{x + left:.3f} {y + top:.3f} {right - left:.3f} {height:.3f}] '
                    f"uri='{safe_url}'"
                )
                cairo_tag_begin(self.context, b'Link', attributes.encode())
                cairo_tag_end(self.context, b'Link')

    def footer(self):
        cairo_set_source_rgb(self.context, .78, .80, .82)
        cairo_set_line_width(self.context, .4)
        cairo_move_to(self.context, self.margin, 804)
        cairo_line_to(self.context, self.width - self.margin, 804)
        cairo_stroke(self.context)
        self.draw(self.footer_text, self.margin, 812, 425, 8, sans=True, tint=(.4, .43, .46))
        self.draw(str(self.page), self.width - self.margin - 20, 812, 20, 8, sans=True)

    def new_page(self):
        self.footer()
        cairo_show_page(self.context)
        self.page += 1
        self.y = self.margin

    def ensure(self, height):
        if height > self.bottom - self.margin:
            raise ValueError(f'Block is too tall for a page: {height:.1f} pt')
        if self.y + height > self.bottom:
            self.new_page()

    def paragraph(self, text, heading=0, bullet=False):
        size = HEADING_SIZES.get(heading, 11)
        indent = 11 if bullet else 0
        text = ('• ' if bullet else '') + text
        width = self.content_width - indent
        height = self.measure(text, width, size, bool(heading), bool(heading))
        before = HEADING_SPACING.get(heading, 0)
        after = 8 if heading else (5 if bullet else 8)
        self.ensure(before + height + (48 if heading else 0))
        self.y += before
        self.draw(text, self.margin + indent, self.y, width, size, bool(heading), bool(heading))
        self.y += height + after

    def table_widths(self, rows):
        if not rows or not rows[0]:
            raise ValueError('Table must have a header')
        columns = len(rows[0])
        if any(len(row) != columns for row in rows):
            raise ValueError('Table rows must have the same number of columns')
        fractions = [.18, .35, .47] if columns == 3 else [1 / columns] * columns
        return [self.content_width * fraction for fraction in fractions]

    def row_height(self, row, widths, header=False):
        return max(
            self.measure(cell, width - 14, 9.3, header, True)
            for cell, width in zip(row, widths)
        ) + 14

    def draw_row(self, row, widths, height, header=False, shade=False):
        x = self.margin
        if header or shade:
            background = (.89, .92, .95) if header else (.966, .971, .976)
            cairo_set_source_rgb(self.context, *background)
            cairo_rectangle(self.context, x, self.y, self.content_width, height)
            cairo_fill(self.context)
        for cell, width in zip(row, widths):
            self.draw(cell, x + 7, self.y + 7, width - 14, 9.3, header, True)
            x += width
        cairo_set_source_rgb(self.context, .76, .79, .82)
        cairo_set_line_width(self.context, .35)
        cairo_move_to(self.context, self.margin, self.y + height)
        cairo_line_to(self.context, self.width - self.margin, self.y + height)
        cairo_stroke(self.context)
        self.y += height

    def table(self, rows):
        widths = self.table_widths(rows)
        heights = [self.row_height(row, widths, index == 0) for index, row in enumerate(rows)]
        header_height = heights[0]
        first_row_height = heights[1] if len(heights) > 1 else 0
        page_height = self.bottom - self.margin
        if header_height > page_height or any(
            header_height + height > page_height for height in heights[1:]
        ):
            raise ValueError('Table row is too tall to fit on a page with its header')
        self.ensure(header_height + first_row_height)
        self.draw_row(rows[0], widths, header_height, header=True)
        for index, (row, height) in enumerate(zip(rows[1:], heights[1:])):
            if self.y + height > self.bottom:
                self.new_page()
                self.draw_row(rows[0], widths, header_height, header=True)
            self.draw_row(row, widths, height, shade=index % 2 == 0)
        self.y += 12

    def table_height(self, rows):
        widths = self.table_widths(rows)
        return sum(self.row_height(row, widths, index == 0) for index, row in enumerate(rows))

    def finish(self):
        try:
            self.footer()
            cairo_surface_finish(self.surface)
            self.check_status()
            for page, x, y, width, height in self.blocks:
                if x < 0 or y < 0 or x + width > self.width + .1 or y + height > self.height:
                    raise RuntimeError(f'Block outside page {page}: {(x, y, width, height)}')
        finally:
            self.close()


def read_table(lines, index):
    rows = []
    while index < len(lines) and lines[index].strip().startswith('|'):
        cells = [cell.strip() for cell in lines[index].strip().strip('|').split('|')]
        if not all(TABLE_SEPARATOR.fullmatch(cell) for cell in cells):
            rows.append(cells)
        index += 1
    if not rows:
        raise ValueError('Table contains no header or data rows')
    return rows, index


def reserve_heading_space(pdf, lines, index):
    next_index = index + 1
    while next_index < len(lines) and not lines[next_index].strip():
        next_index += 1
    if next_index == len(lines):
        return
    next_line = lines[next_index].strip()
    if next_line.startswith('|'):
        rows, _ = read_table(lines, next_index)
        height = pdf.table_height(rows) + 55
        if height < pdf.bottom - pdf.margin:
            pdf.ensure(height)
    elif HEADING_PATTERN.match(next_line):
        reserve = 40
        while index < len(lines):
            line = lines[index].strip()
            index += 1
            if not line:
                continue
            heading = HEADING_PATTERN.match(line)
            if heading is None:
                break
            level = len(heading.group(1))
            height = pdf.measure(heading.group(2), pdf.content_width, HEADING_SIZES[level], True, True)
            reserve += height + HEADING_SPACING[level] + 8
        if reserve <= pdf.bottom - pdf.margin:
            pdf.ensure(reserve)


def render_markdown(pdf, lines):
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if line.startswith('|'):
            rows, index = read_table(lines, index)
            pdf.table(rows)
            continue
        heading = HEADING_PATTERN.match(line)
        if heading:
            reserve_heading_space(pdf, lines, index)
            pdf.paragraph(heading.group(2), heading=len(heading.group(1)))
        elif line.startswith('- '):
            pdf.paragraph(line[2:], bullet=True)
        elif line:
            pdf.paragraph(line)
        index += 1


def main():
    parser = argparse.ArgumentParser(description='Сборка PDF из Markdown')
    parser.add_argument('source', nargs='?', default='plan_obzora.md')
    args = parser.parse_args()
    source = ROOT / args.source
    destination = ROOT / 'artefacts' / source.with_suffix('.pdf').name
    lines = source.read_text(encoding='utf-8').splitlines()
    destination.parent.mkdir(parents=True, exist_ok=True)
    options = {}
    if source.stem == 'predvaritelny_spisok_literatury':
        options = {'title': 'Наблюдаемость микросервисов: предварительный список литературы',
                   'footer': 'Предварительный список литературы • 29.10.2026'}
    with PdfDocument(destination, **options) as pdf:
        render_markdown(pdf, lines)
    print(f'{destination}: {pdf.page} pages, {destination.stat().st_size} bytes')


if __name__ == '__main__':
    main()
