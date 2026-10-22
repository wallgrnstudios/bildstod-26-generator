"""Reviewed registry of recurring illustrated figures and the capped variant briefs that may use them."""
import json
import re
from pathlib import Path

from .generation import ROOT

STATUSES = {'proposed', 'approved', 'retired'}


def validate_registry(registry, variants=(), active_ids=()):
    """Raise ValueError unless every figure and variant brief is explicit, reviewed and bounded."""
    if registry.get('schema_version') != 1 or not isinstance(registry.get('characters'), list):
        raise ValueError('Invalid character registry')
    seen = {}
    for c in registry['characters']:
        if not re.fullmatch(r'FIG_\d{3}', c.get('character_id', '')) or c['character_id'] in seen:
            raise ValueError('Character IDs must be unique FIG_000 identifiers')
        if c.get('status') not in STATUSES or not 10 <= len(c.get('description_en', '')) <= 300 or not c.get('name_sv'):
            raise ValueError('Character needs a name, a bounded illustration description and a status: ' + c['character_id'])
        ref = c.get('reference')
        if c['status'] == 'approved':
            # The reference is a specific reviewed image version, never "the latest image".
            if not ref or not re.fullmatch(r'FSK_\d{2}_\d{2}', ref.get('concept_id', '')) or not re.fullmatch('[a-f0-9]{64}', ref.get('sha256', '')) \
                    or not re.fullmatch('[a-f0-9]{40}', ref.get('source_commit', '')) or not c.get('approved_at'):
                raise ValueError('Approved characters need a pinned, human-approved reference image: ' + c['character_id'])
        seen[c['character_id']] = c
    if len(variants) > registry.get('max_active_variant_briefs', 0):
        raise ValueError('Too many active variant briefs; only requested variants may be queued')
    ids = set()
    for v in variants:
        figure = seen.get(v.get('character_id'))
        if not figure or figure['status'] != 'approved':
            raise ValueError('Variant briefs may only use approved characters: ' + str(v.get('variant_id')))
        if v.get('concept_id') not in active_ids or not re.fullmatch(re.escape(v['concept_id']) + r'-V\d{2}', v.get('variant_id', '')) or v['variant_id'] in ids:
            raise ValueError('Variant IDs must be <concept_id>-V00 for an active concept: ' + str(v.get('variant_id')))
        if v.get('requested') is not True or not 10 <= len(v.get('visual_prompt_en', '')) <= 500:
            raise ValueError('Only explicitly requested variants with a bounded brief are allowed: ' + v['variant_id'])
        ids.add(v['variant_id'])
    return seen


def load(path=ROOT / 'config/characters.json', variants_path=ROOT / 'catalog/pilot/variants.json'):
    registry = json.loads(Path(path).read_text())
    variants = json.loads(Path(variants_path).read_text()) if Path(variants_path).exists() else []
    active = {e['id'] for e in json.loads((ROOT / 'catalog/pilot/symbols.json').read_text()) if e.get('generation_enabled', True)}
    validate_registry(registry, variants, active)
    return registry, variants
