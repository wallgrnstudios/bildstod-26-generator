"""Import/generate candidates, then explicitly approve before distribution."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, PngImagePlugin, ImageOps
from .catalog import load, keywords

MASTER_PROMPT = "Children's book illustration. " + json.loads(
    (Path(__file__).resolve().parents[1] / 'config/generation.json').read_text(encoding='utf-8')
)['style_prompt'] + ' '



def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def fingerprint(entry):
    return hashlib.sha256(json.dumps([MASTER_PROMPT, entry], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def save_candidate(image, entry, target, source, model=None):
    image = ImageOps.exif_transpose(image).convert('RGBA')
    if min(image.size) < 128:
        raise ValueError('Bilden måste vara minst 128 × 128 pixlar')
    metadata = {'entry': entry, 'keywords': keywords(entry), 'prompt': MASTER_PROMPT + entry['visual_prompt_specific'],
        'fingerprint': fingerprint(entry), 'source': source, 'model': model,
        'review_status': 'pending', 'license': None}
    info = PngImagePlugin.PngInfo()
    info.add_itxt('bildstod', json.dumps(metadata, ensure_ascii=False))
    temporary = target.with_suffix('.tmp')
    image.save(temporary, format='PNG', pnginfo=info)
    temporary.replace(target)
    atomic_json(target.with_suffix('.json'), metadata)


def build_index(entries, output):
    published = []
    for entry in entries:
        image = output / (entry['id'] + '.png')
        sidecar = image.with_suffix('.json')
        if not image.exists() or not sidecar.exists():
            continue
        metadata = json.loads(sidecar.read_text(encoding='utf-8'))
        if metadata.get('review_status') == 'approved' and metadata.get('license') and metadata.get('fingerprint') == fingerprint(entry):
            published.append({**entry, 'image_path': image.name, 'license': metadata['license']})
    atomic_json(output / 'index.json', published)
    return published


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--catalog', default='data/ordlista.json')
    parser.add_argument('--output', default='output')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('validate')
    importer = sub.add_parser('import')
    importer.add_argument('id'); importer.add_argument('image')
    generate = sub.add_parser('generate')
    generate.add_argument('--allow-remote', action='store_true', required=True)
    generate.add_argument('--model', required=True)
    generate.add_argument('--provider', required=True)
    generate.add_argument('--limit', type=int, default=1, choices=range(1, 21))
    approve = sub.add_parser('approve')
    approve.add_argument('id'); approve.add_argument('--license', required=True)
    sub.add_parser('index')
    args = parser.parse_args()
    entries = load(args.catalog)
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    by_id = {x['id']: x for x in entries}
    if args.command == 'validate':
        print(f'{len(entries)} giltiga begrepp')
    elif args.command == 'import':
        with Image.open(args.image) as image:
            save_candidate(image, by_id[args.id], output / (args.id + '.png'), 'local-import')
    elif args.command == 'generate':
        parser.error('Betald API-generering är avstängd. Använd python -m bildstod.generation plan eller run enligt docs/GENERATION.md.')
    elif args.command == 'approve':
        entry = by_id[args.id]
        path = output / (args.id + '.json')
        metadata = json.loads(path.read_text(encoding='utf-8'))
        if metadata['fingerprint'] != fingerprint(entry):
            raise ValueError('Begreppet har ändrats. Importera/generera och granska på nytt.')
        metadata.update(review_status='approved', license=args.license)
        atomic_json(path, metadata)
    if args.command != 'validate':
        print(f'{len(build_index(entries, output))} godkända bilder i indexet')


if __name__ == '__main__':
    main()
