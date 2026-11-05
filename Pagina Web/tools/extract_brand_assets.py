"""Extract only original logo artwork from the supplied Tickia identity PDF."""
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
SOURCE = next(ROOT.glob('Tickia*visual.pdf'))
OUTPUT = ROOT / 'Pagina Web/frontend/public/brand'


def extract(page, name, rectangle):
    # The supplied PDF is raster artwork with an OCR text layer, not vector logos.
    # Render the original artwork inside its crop at twice the CSS resolution.
    page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=pymupdf.Rect(rectangle)).save(OUTPUT / f'{name}.png')


if __name__ == '__main__':
    OUTPUT.mkdir(exist_ok=True)
    doc = pymupdf.open(SOURCE)
    for name, rect in {
        'tickia-dark': (702, 565, 1055, 644),
        'tickia-light': (145, 565, 500, 644),
        'tickia-symbol': (818, 112, 1011, 305),
        'tickia-symbol-lime': (680, 916, 796, 1032),
    }.items():
        extract(doc[1], name, rect)
        print(name, (OUTPUT / f'{name}.png').stat().st_size, 'bytes')
