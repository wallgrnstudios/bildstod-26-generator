"""Contact sheets for spotting motifs that only work large or in colour. Does not replace user testing."""
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .generation import ROOT

# (name, cell px, labels, grayscale): small and grey variants expose details that disappear.
VARIANTS = [('etiketter-96-farg', 96, True, False), ('etiketter-96-gra', 96, True, True), ('utan-etikett-48-farg', 48, False, False),
            ('utan-etikett-48-gra', 48, False, True), ('utan-etikett-24-farg', 24, False, False)]
PER_SHEET = 60


def font(size):
    for path in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf'):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def slug(text):
    text = text.casefold().translate(str.maketrans('åäö', 'aao'))
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')


def render(items, cell, labels, gray, columns=10):
    """items: [(label, PIL image)]. Labels are drawn below each cell, never on the motif."""
    label_h = 18 if labels else 0
    pad = 6
    rows = (len(items) + columns - 1) // columns
    sheet = Image.new('RGB', (columns * (cell + pad) + pad, rows * (cell + label_h + pad) + pad), 'white')
    draw = ImageDraw.Draw(sheet)
    face = font(11)
    for n, (label, image) in enumerate(items):
        x = pad + (n % columns) * (cell + pad)
        y = pad + (n // columns) * (cell + label_h + pad)
        thumb = image.convert('RGB').resize((cell, cell), Image.Resampling.LANCZOS)
        sheet.paste(ImageOps.grayscale(thumb).convert('RGB') if gray else thumb, (x, y))
        draw.rectangle((x - 1, y - 1, x + cell, y + cell), outline=(225, 225, 225))
        if labels:
            text = label if draw.textlength(label, font=face) <= cell + pad else label[:max(3, cell // 7)] + '…'
            draw.text((x + cell / 2, y + cell + 3), text, fill=(30, 30, 30), font=face, anchor='ma')
    return sheet


def print_pdf(items, path, gray):
    """A4 at 150 dpi, 4 x 5 motifs of about 3.6 cm with labels below."""
    pages = []
    face = font(22)
    for start in range(0, len(items), 20):
        page = Image.new('RGB', (1240, 1754), 'white')
        draw = ImageDraw.Draw(page)
        for n, (label, image) in enumerate(items[start:start + 20]):
            x = 70 + (n % 4) * 280
            y = 80 + (n // 4) * 330
            thumb = image.convert('RGB').resize((215, 215), Image.Resampling.LANCZOS)
            page.paste(ImageOps.grayscale(thumb).convert('RGB') if gray else thumb, (x, y))
            draw.text((x + 107, y + 228), label, fill='black', font=face, anchor='ma')
        pages.append(page)
    pages[0].save(path, save_all=True, append_images=pages[1:], resolution=150)


def build(paths, labels, categories, output):
    output.mkdir(parents=True, exist_ok=True)
    groups = {}
    for concept in sorted(paths, key=lambda c: labels[c]):
        groups.setdefault(categories.get(concept, 'övrigt'), []).append(concept)
    index = []
    for category, concepts in sorted(groups.items()):
        for page, start in enumerate(range(0, len(concepts), PER_SHEET), 1):
            chunk = concepts[start:start + PER_SHEET]
            images = [(labels[c], Image.open(paths[c])) for c in chunk]
            name = slug(category) + (f'-{page}' if len(concepts) > PER_SHEET else '')
            files = {}
            for variant, cell, with_labels, gray in VARIANTS:
                file = f'{name}--{variant}.png'
                render(images, cell, with_labels, gray).save(output / file, optimize=True)
                files[variant] = file
            for gray in (False, True):
                file = f'{name}--utskrift-a4-{"gra" if gray else "farg"}.pdf'
                print_pdf(images, output / file, gray)
                files['utskrift-a4-' + ('gra' if gray else 'farg')] = file
            for _, image in images:
                image.close()
            index.append({'category': category, 'page': page, 'concepts': chunk, 'files': files})
    return index


def main():
    triage = json.loads(Path('.triage/triage.json').read_text())
    paths = json.loads(Path('.triage/paths.json').read_text())
    vocabulary = json.loads((ROOT / 'catalog/school/vocabulary-2000.json').read_text())
    categories = {e['id']: e['category'] for e in vocabulary}
    labels = {r['concept_id']: r['label_sv'] for r in triage['records']}
    index = build({k: v for k, v in paths.items() if k in labels}, labels, categories, Path('.triage/sheets'))
    Path('.triage/sheets/index.json').write_text(json.dumps({'schema_version': 1, 'checked_at': triage['checked_at'], 'variants': [v[0] for v in VARIANTS],
        'notice_sv': 'Kontaktkartor hjälper att hitta motiv som bara fungerar stora eller i färg. Begripligheten måste fortfarande provas med användare.',
        'sheets': index}, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'sheets': len(index)}))


if __name__ == '__main__':
    main()
