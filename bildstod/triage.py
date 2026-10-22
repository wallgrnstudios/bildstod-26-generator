"""Order public candidates for human review. Flags are hints; nothing is approved or rejected here."""
import concurrent.futures
import hashlib
import io
import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from .generation import ROOT, load_briefs, load_config
from .metadata import load_candidates, read_url

# Weights only order the review list; they are not calibrated probabilities.
WEIGHTS = {'reference_echo': 4, 'prompt_mismatch': 3, 'contrast_match': 4, 'near_duplicate': 2, 'possible_text': 2, 'cropped': 2,
           'tiny_subject': 2, 'filled_frame': 2, 'warm_cast': 1}
REASONS_SV = {
    'reference_echo': 'Bilden liknar stilreferensen (jacka på krok) i stället för sitt eget motiv',
    'prompt_mismatch': 'Bilden liknar andra begrepps instruktioner mer än sin egen',
    'contrast_match': 'Bilden liknar ett förväxlingsord mer än sitt eget begrepp',
    'near_duplicate': 'Nästan identisk med en annan bild',
    'possible_text': 'Möjlig text eller bokstäver i bilden',
    'cropped': 'Motivet kan vara avklippt vid bildkanten',
    'tiny_subject': 'Motivet är mycket litet',
    'filled_frame': 'Lite vit bakgrund – möjlig miljö eller bakgrund',
    'warm_cast': 'Brun eller gulnad färgton',
}


def dhash(gray):
    small = list(gray.resize((9, 8), Image.Resampling.LANCZOS).getdata())
    bits = ''.join('1' if small[y * 9 + x + 1] > small[y * 9 + x] else '0' for y in range(8) for x in range(8))
    return int(bits, 2)


def image_stats(image, size=256):
    """Pillow-only statistics at 256 px; enough for edge, size and colour-cast checks."""
    rgb = image.convert('RGB').resize((size, size), Image.Resampling.BILINEAR)
    pixels = list(rgb.getdata())
    foreground = [min(p) < 232 for p in pixels]
    band = 2
    def share(indexes):
        indexes = list(indexes)
        return round(sum(foreground[i] for i in indexes) / len(indexes), 4)
    edges = {'top': share(range(band * size)), 'bottom': share(range((size - band) * size, size * size)),
             'left': share(y * size + x for y in range(size) for x in range(band)),
             'right': share(y * size + x for y in range(size) for x in range(size - band, size))}
    fg = [p for p, f in zip(pixels, foreground) if f]
    # Brown/ochre: red > green > blue, clearly warm, moderately saturated and not bright.
    brown = sum(1 for r, g, b in fg if r > g > b and r - b > 45 and r - b < 150 and r < 225)
    xs = [i % size for i, f in enumerate(foreground) if f]
    ys = [i // size for i, f in enumerate(foreground) if f]
    scale = image.width / size
    bbox = [int(min(xs) * scale), int(min(ys) * scale), int((max(xs) + 1) * scale) - 1, int((max(ys) + 1) * scale) - 1] if xs else [0, 0, 0, 0]
    return {'foreground_share': round(len(fg) / len(pixels), 4), 'edge_share': edges,
            'brown_share': round(brown / len(fg), 4) if fg else 0.0, 'bbox': bbox, 'dhash': f'{dhash(image.convert("L")):016x}'}


def thumbnail(image):
    return list(image.convert('L').resize((32, 32), Image.Resampling.BILINEAR).getdata())


def difference(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


# White textiles/hygiene items must not turn brown; wood, brick or leather may legitimately be brown.
WHITE_MATERIAL = re.compile(r'\bwhite\b(?! background)', re.I)


def rule_flags(stats, entry=None):
    entry = entry or {}
    flags = []
    # Body parts are deliberately cropped close-ups.
    if max(stats['edge_share'].values()) > 0.12 and entry.get('symbol_type') != 'body_part':
        flags.append('cropped')
    if stats['foreground_share'] < 0.03:
        flags.append('tiny_subject')
    if stats['foreground_share'] > 0.72:
        flags.append('filled_frame')
    prompt = entry.get('visual_prompt_en', '').replace('pure white', '')
    if stats['brown_share'] > 0.3 and WHITE_MATERIAL.search(prompt):
        flags.append('warm_cast')
    return flags


def duplicates(hashes, thumbs, max_distance=6, max_difference=14):
    """Different concepts that agree both in gradient hash and in grey-level thumbnail."""
    items = sorted(hashes.items())
    pairs = []
    for i, (a, ha) in enumerate(items):
        for b, hb in items[i + 1:]:
            distance = bin(int(ha, 16) ^ int(hb, 16)).count('1')
            if distance <= max_distance and difference(thumbs[a], thumbs[b]) <= max_difference:
                pairs.append((a, b, distance))
    return pairs


def ocr_words(path):
    """Sparse-text OCR; illustrations give false positives, so only confident alphabetic words count."""
    try:
        out = subprocess.run(['tesseract', str(path), 'stdout', '--psm', '11', 'tsv'], capture_output=True, text=True, timeout=60, check=True).stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    words = []
    for line in out.splitlines()[1:]:
        cols = line.split('\t')
        if len(cols) == 12 and cols[11].strip() and float(cols[10]) >= 80 and re.fullmatch(r'[A-Za-zÅÄÖåäö]{3,}', cols[11].strip()):
            words.append(cols[11].strip())
    return words


def clip_ranks(paths, entries, contrasts, model_id, revision):
    """Rank each image's own brief among all active briefs with a pinned CLIP model on the runner CPU."""
    import torch
    from transformers import CLIPModel, CLIPProcessor
    # Newer transformers may wrap projected features in an output object.
    features = lambda out: out if isinstance(out, torch.Tensor) else out.pooler_output
    model = CLIPModel.from_pretrained(model_id, revision=revision).eval()
    processor = CLIPProcessor.from_pretrained(model_id, revision=revision)
    ids = [e['id'] for e in entries]
    texts = [e['visual_prompt_en'].split('. ')[0] for e in entries]
    with torch.no_grad():
        text = []
        for i in range(0, len(texts), 64):
            batch = processor(text=texts[i:i + 64], return_tensors='pt', padding=True, truncation=True, max_length=77)
            text.append(torch.nn.functional.normalize(features(model.get_text_features(**batch)), dim=-1))
        text = torch.cat(text)
        results = {}
        concept_ids = sorted(paths)
        for i in range(0, len(concept_ids), 32):
            chunk = concept_ids[i:i + 32]
            images = [Image.open(paths[c]).convert('RGB') for c in chunk]
            embedding = torch.nn.functional.normalize(features(model.get_image_features(**processor(images=images, return_tensors='pt'))), dim=-1)
            for concept, scores in zip(chunk, (embedding @ text.T).tolist()):
                if concept not in ids:
                    continue
                order = sorted(range(len(ids)), key=lambda j: -scores[j])
                rank = order.index(ids.index(concept)) + 1
                own = scores[ids.index(concept)]
                contrast = [ids[j] for j in order[:rank - 1] if ids[j] in contrasts.get(concept, set())]
                results[concept] = {'rank': rank, 'own_score': round(own, 4), 'top': [ids[j] for j in order[:3]], 'contrast_above': contrast}
    return results


def prioritize(records):
    for r in records.values():
        r['score'] = sum(WEIGHTS[f] for f in r['flags'])
        r['reasons_sv'] = [REASONS_SV[f] for f in r['flags']]
    return sorted(records.values(), key=lambda r: (-r['score'], r['concept_id']))


PUBLISHED = 'https://raw.githubusercontent.com/wallgrnstudios/bildstod-26-generator/quality-triage/triage.json'


def main(force=False):
    config = load_config(ROOT / 'config/generation.json')
    triage = json.loads((ROOT / 'config/triage.json').read_text())
    entries = [e for e in load_briefs(ROOT / config['catalog_path']) if e.get('generation_enabled', True)]
    by_id = {e['id']: e for e in entries}
    labels = {e['text_sv'].casefold(): e['id'] for e in entries}
    candidates = [c for c in load_candidates() if c['concept_id'] in by_id]
    # Skip model loading entirely when images, briefs and thresholds are unchanged.
    fingerprint = hashlib.sha256(json.dumps([sorted((c['concept_id'], c['sha256']) for c in candidates), triage,
                                             sorted((e['id'], e['visual_prompt_en']) for e in entries)]).encode()).hexdigest()
    Path('.triage').mkdir(exist_ok=True)
    if not force:
        try:
            if json.loads(read_url(PUBLISHED)).get('input_fingerprint') == fingerprint:
                print('Unchanged images and briefs; triage skipped.')
                return
        except Exception as error:
            if getattr(error, 'code', None) != 404:
                raise
    work = Path(tempfile.mkdtemp(prefix='bildstod-triage-'))

    def fetch(c):
        data = read_url(c['source_url'])
        if hashlib.sha256(data).hexdigest() != c['sha256']:
            raise ValueError('Image checksum mismatch: ' + c['concept_id'])
        path = work / (c['concept_id'] + '.png')
        path.write_bytes(data)
        return c['concept_id'], path

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        paths = dict(pool.map(fetch, candidates))
    records = {};thumbs = {}
    with Image.open(ROOT / config['reference_asset']) as source:
        canvas = Image.new('RGBA', source.size, 'white');canvas.alpha_composite(source.convert('RGBA'))
        reference = canvas.convert('RGB');reference_hash = dhash(reference.convert('L'));reference_thumb = thumbnail(reference)
    for c in candidates:
        with Image.open(paths[c['concept_id']]) as image:
            stats = image_stats(image);thumbs[c['concept_id']] = thumbnail(image)
        record = {'concept_id': c['concept_id'], 'label_sv': by_id[c['concept_id']]['text_sv'], 'sha256': c['sha256'],
                  'source_url': c['source_url'], 'stats': stats, 'flags': rule_flags(stats, by_id[c['concept_id']]), 'details': {}}
        echo = bin(int(stats['dhash'], 16) ^ reference_hash).count('1')
        if c['concept_id'] not in triage['reference_concepts'] and echo <= triage['reference_max_bits'] and difference(thumbs[c['concept_id']], reference_thumb) <= triage['reference_max_difference']:
            record['flags'].append('reference_echo');record['details']['reference_echo'] = {'bits': echo}
        records[c['concept_id']] = record
    for a, b, distance in duplicates({k: r['stats']['dhash'] for k, r in records.items()}, thumbs, triage['duplicate_max_bits'], triage['duplicate_max_difference']):
        for x, y in ((a, b), (b, a)):
            if 'near_duplicate' not in records[x]['flags']:
                records[x]['flags'].append('near_duplicate')
            records[x]['details'].setdefault('near_duplicate', []).append({'concept_id': y, 'label_sv': records[y]['label_sv'], 'bits': distance})
    ocr_available = True
    for concept, path in paths.items():
        words = ocr_words(path)
        if words is None:
            ocr_available = False
            break
        if words:
            records[concept]['flags'].append('possible_text')
            records[concept]['details']['possible_text'] = words[:8]
    contrasts = {e['id']: {labels[t.casefold()] for t in e.get('contrast_terms_sv', []) if t.casefold() in labels} for e in entries}
    names = {e['id']: e['text_sv'] for e in entries}
    clip = clip_ranks(paths, entries, contrasts, triage['clip_model'], triage['clip_revision'])
    for concept, result in clip.items():
        records[concept]['details']['clip'] = {**result, 'top_labels_sv': [names[i] for i in result['top']],
                                               'contrast_labels_sv': [names[i] for i in result['contrast_above']]}
        if result['contrast_above']:
            records[concept]['flags'].append('contrast_match')
        elif result['rank'] > triage['clip_rank_threshold']:
            records[concept]['flags'].append('prompt_mismatch')
    ordered = prioritize(records)
    report = {'schema_version': 1, 'input_fingerprint': fingerprint, 'checked_at': datetime.now(timezone.utc).isoformat(), 'style_version': config['style_version'],
              'clip_model': triage['clip_model'], 'clip_revision': triage['clip_revision'], 'ocr_available': ocr_available,
              'notice_sv': 'Automatisk prioritering av granskningsordning. Flaggor är ledtrådar, inte beslut; pedagogiskt godkännande är alltid mänskligt.',
              'counts': {f: sum(f in r['flags'] for r in ordered) for f in WEIGHTS}, 'flagged': sum(bool(r['flags']) for r in ordered),
              'total': len(ordered), 'records': ordered}
    Path('.triage/triage.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    Path('.triage/paths.json').write_text(json.dumps({k: str(v) for k, v in paths.items()}))
    print(json.dumps({k: report[k] for k in ('total', 'flagged', 'counts', 'ocr_available')}, ensure_ascii=False))


if __name__ == '__main__':
    import sys
    main(force='--force' in sys.argv)
