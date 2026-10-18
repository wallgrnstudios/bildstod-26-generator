import json
import re
import unicodedata
from pathlib import Path


def normalize(value):
    return unicodedata.normalize('NFKC', value).casefold().strip()


def keywords(entry):
    return list(dict.fromkeys([entry['word_sv'], entry['word_en'],
        *entry['synonyms_sv'], *entry['inflections_sv'],
        *(term for terms in entry['translations'].values() for term in terms)]))


def load(path):
    entries = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(entries, list):
        raise ValueError('Ordlistan måste vara en lista')
    seen = set()
    for entry in entries:
        identifier = entry.get('id', '')
        if not re.fullmatch(r'ORD_[0-9]{4,}', identifier) or identifier in seen:
            raise ValueError(f'Ogiltigt eller dubblerat id: {identifier}')
        seen.add(identifier)
        for field in ('word_sv', 'word_en', 'category', 'visual_prompt_specific'):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f'{identifier}: {field} saknas')
        for field in ('synonyms_sv', 'inflections_sv'):
            if not isinstance(entry.get(field), list) or any(not isinstance(x, str) for x in entry[field]):
                raise ValueError(f'{identifier}: ogiltigt {field}')
        translations = entry.get('translations')
        if not isinstance(translations, dict) or any(not isinstance(v, list) or any(not isinstance(x, str) for x in v) for v in translations.values()):
            raise ValueError(f'{identifier}: ogiltiga översättningar')
    return entries


def search(entries, query, category='', limit=60):
    query = normalize(query)
    matches = []
    for entry in entries:
        if category and entry['category'] != category:
            continue
        terms = [normalize(x) for x in keywords(entry)]
        rank = 0 if query in terms else 1 if any(x.startswith(query) for x in terms) else 2
        if not query or any(query in x for x in terms):
            matches.append((rank, entry['word_sv'], entry))
    return [x[2] for x in sorted(matches, key=lambda x: x[:2])[:limit]]
