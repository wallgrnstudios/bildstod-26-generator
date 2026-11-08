"""Isolated, SHA-bound quality experiments. Never publishes library decisions."""
import argparse
import copy
import hashlib
import html
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image
from .generation import ROOT, load_config, load_briefs, run_batch, prompt_for
from .metadata import read_url
from .pipeline import atomic_json

CHECKS = ('meaning', 'detail', 'no_extra_meaning', 'small_size', 'clean_materials', 'consistent_style')
PROFILES = ('text', 'reference')



REVIEW_SCRIPT = r'''<script>
document.getElementById('export').onclick = () => {
  const decisions = [];
  for (const form of document.querySelectorAll('form')) {
    const data = new FormData(form), decision = data.get('decision');
    if (!decision) continue;
    const checks = Object.fromEntries(Array.from(form.querySelectorAll('[type=checkbox]'), c => [c.name, c.checked]));
    const note = data.get('note').trim(), next_prompt_en = data.get('next_prompt_en').trim();
    if (decision === 'keep_for_pilot' && !Object.values(checks).every(Boolean) || decision !== 'keep_for_pilot' && !note || decision === 'revise' && (next_prompt_en.length < 10 || next_prompt_en.length > 700)) {
      document.getElementById('feedback').textContent = 'Kontrollera alla kriterier för behåll, och skriv orsak samt konkret instruktion för nytt försök.';
      form.scrollIntoView({block:'center'}); return;
    }
    decisions.push({...JSON.parse(form.dataset.identity), decision, checks, note, next_prompt_en});
  }
  if (!decisions.length) { document.getElementById('feedback').textContent = 'Välj minst ett beslut först.'; return; }
  const url = URL.createObjectURL(new Blob([JSON.stringify(decisions,null,2)], {type:'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = 'quality-decisions.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  document.getElementById('feedback').textContent = decisions.length+' beslut nedladdade. Importera filen med quality_lab review. Inget är publicerat.';
};
</script>'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(destination, snapshot, private_reviews=None):
    """Freeze current images and editorial briefs; never modify an existing experiment."""
    spec = json.loads((ROOT/'config/quality-experiment.json').read_text())
    config = load_config(ROOT/'config/generation.json')
    entries = {e['id']: e for e in load_briefs(ROOT/config['catalog_path'])}
    images = {c['concept_id']: c for c in snapshot['images']}
    missing = set(spec['concept_ids']) - images.keys()
    if missing:
        raise ValueError(f'Missing baseline images: {sorted(missing)}')
    if destination.exists():
        raise ValueError('Experiment already exists; choose a new directory')
    reviews = {r['concept_id']: r for r in (private_reviews or []) if r.get('decision') in ('revise', 'reject')}
    improvements = {e['id']: e for e in json.loads((ROOT/'catalog/school/quality-lab-briefs.json').read_text())}
    destination.mkdir(parents=True)
    cases = []
    for identifier in spec['concept_ids']:
        current = images[identifier]
        data = read_url(current['source_url'])
        if hashlib.sha256(data).hexdigest() != current['sha256']:
            raise ValueError(f'Baseline SHA mismatch: {identifier}')
        Image.open(io.BytesIO(data)).verify()
        path = destination/'baseline'/f'{identifier}.png'
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
        entry = copy.deepcopy(entries[identifier])
        entry.update(improvements[identifier])
        cases.append({'id': identifier, 'entry': entry, 'baseline': current,
                      'historical_rejection': reviews.get(identifier), 'attempts': {}})
    state = {'schema_version': 1, 'experiment_id': spec['experiment_id'] + ('-' + os.environ['GITHUB_RUN_ID'] if os.environ.get('GITHUB_RUN_ID') else ''),
             'created_at': datetime.now(timezone.utc).isoformat(), 'config': config,
             'checks': list(CHECKS), 'max_attempts': 2, 'cases': cases}
    atomic_json(destination/'experiment.json', state)
    report(destination, state)
    return state


def plan(state, profile):
    if profile not in PROFILES:
        raise ValueError('Unknown profile')
    jobs = []
    for case in state['cases']:
        attempts = case['attempts'].get(profile, [])
        if any(a.get('decision') == 'keep_for_pilot' for a in attempts):
            continue
        # A second attempt needs a human correction, not a blind retry.
        if len(attempts) >= 2 or (attempts and attempts[-1].get('decision') != 'revise'):
            continue
        entry = copy.deepcopy(case['entry'])
        if attempts:
            entry['visual_prompt_en'] = attempts[-1]['next_prompt_en']
        entry['reference_conditioning'] = profile == 'reference'
        seed = int(hashlib.sha256((state['experiment_id']+case['id']+str(len(attempts)+1)).encode()).hexdigest()[:8], 16)
        jobs.append({'id': case['id'], 'attempt': len(attempts)+1, 'entry': entry, 'seed': seed})
    return jobs


def render(destination, profile):
    # Protect the 8 GB Mac: model execution is restricted to standard hosted runners.
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
        raise ValueError('Run image inference only on a standard GitHub-hosted runner')
    state = json.loads((destination/'experiment.json').read_text())
    jobs = plan(state, profile)
    if not jobs:
        return
    config = state['config']
    entries = [j['entry'] for j in jobs]
    cases = {c['id']: c for c in state['cases']}
    # Reserve attempts BEFORE model initialization. Failed/interrupted attempts count.
    for job in jobs:
        cases[job['id']]['attempts'].setdefault(profile, []).append({
            'attempt': job['attempt'], 'status': 'started', 'seed': job['seed'],
            'prompt': prompt_for(job['entry'], config)})
    atomic_json(destination/'experiment.json', state)
    from .flux_renderer import FluxRenderer
    renderer = None
    try:
        renderer = FluxRenderer(config, entries)
        for job in jobs:
            record = cases[job['id']]['attempts'][profile][-1]
            folder = destination/profile/str(job['attempt'])
            try:
                run_batch(entries, config, folder, [{'id': job['id'], 'seed': job['seed'], 'prompt': prompt_for(job['entry'], config)}], render=renderer)
                path = folder/(job['id']+'.png')
                record.update(status='pending_review', sha256=digest(path), image=str(path.relative_to(destination)))
            except Exception as error:
                record.update(status='failed', error_type=type(error).__name__)
                raise
            finally:
                atomic_json(destination/'experiment.json', state)
    finally:
        if renderer:
            renderer.close()
        report(destination, state)


def save_decisions(destination, decisions):
    state = json.loads((destination/'experiment.json').read_text())
    # Validate the whole batch before saving any decisions.
    for decision in decisions:
        case = next(c for c in state['cases'] if c['id'] == decision['id'])
        records = case['attempts'].get(decision['profile'], [])
        record = next(a for a in records if a['attempt'] == decision['attempt'])
        if record.get('status') != 'pending_review' or record.get('sha256') != decision.get('sha256') or digest(destination/record['image']) != decision['sha256']:
            raise ValueError('Image changed or is not reviewable')
        if decision.get('decision') not in ('keep_for_pilot', 'revise', 'reject'):
            raise ValueError('Invalid decision')
        checks = decision.get('checks', {})
        if set(checks) != set(CHECKS) or any(type(v) is not bool for v in checks.values()):
            raise ValueError('Six explicit boolean checks required')
        if decision['decision'] == 'keep_for_pilot' and not all(checks.values()):
            raise ValueError('All checks must pass')
        if decision['decision'] in ('revise', 'reject') and not str(decision.get('note', '')).strip():
            raise ValueError('Rejection reason required')
        if decision['decision'] == 'revise' and not 10 <= len(decision.get('next_prompt_en', '')) <= 700:
            raise ValueError('Concrete corrected English prompt required (10–700 characters)')
        record.update({k: decision[k] for k in ('decision', 'checks', 'note', 'next_prompt_en') if k in decision})
        record['reviewed_at'] = datetime.now(timezone.utc).isoformat()
    atomic_json(destination/'experiment.json', state)
    report(destination, state)


def report(destination, state):
    rows = []
    metrics = {p: {'generated': 0, 'kept': 0, 'reviewed': 0, 'manual': 0, 'failed': 0} for p in PROFILES}
    for case in state['cases']:
        entry = case['entry']
        cells = [f'<h2>{html.escape(entry["text_sv"])}</h2><p>{html.escape(" · ".join(entry["must_show_sv"]))}</p>',
                 f'<img src="baseline/{case["id"]}.png"><p>Fryst aktuell kandidat</p>']
        for profile in PROFILES:
            records = case['attempts'].get(profile, [])
            m = metrics[profile]
            m['generated'] += sum(a.get('status') == 'pending_review' for a in records)
            m['failed'] += sum(a.get('status') in ('failed', 'started') for a in records)
            m['kept'] += any(a.get('decision') == 'keep_for_pilot' for a in records)
            m['reviewed'] += sum('decision' in a for a in records)
            m['manual'] += bool(records and (records[-1].get('decision') == 'reject' or len(records) == 2 and records[-1].get('decision') == 'revise'))
            parts = []
            for record in records:
                if record.get('image'):
                    parts.append(f'<img src="{html.escape(record["image"])}"><img class="small" src="{html.escape(record["image"])}"><img class="small gray" src="{html.escape(record["image"])}">')
                parts.append(f'<p>Försök {record["attempt"]}: {html.escape(record.get("decision", record["status"]))}</p>')
                if record.get('status') == 'pending_review':
                    identity = html.escape(json.dumps({'id': case['id'], 'profile': profile, 'attempt': record['attempt'], 'sha256': record['sha256']}), quote=True)
                    fields = ''.join(f'<label><input type="checkbox" name="{key}">{label}</label>' for key, label in zip(CHECKS, ('Rätt betydelse', 'Tydliga detaljer', 'Ingen extra betydelse', 'Läsbar i 48 px', 'Rena material', 'Konsekvent stil')))
                    parts.append(f'<form data-identity="{identity}"><select name="decision"><option value="">Välj beslut</option><option value="keep_for_pilot">Behåll för pilot</option><option value="revise">Skapa förbättrat förslag</option><option value="reject">Manuell bearbetning</option></select>{fields}<textarea name="note" placeholder="Vad behöver ändras?"></textarea><textarea name="next_prompt_en" placeholder="Förbättrad engelsk bildinstruktion vid nytt försök (10–700 tecken)"></textarea></form>')
            cells.append(''.join(parts) or 'Väntar på generering')
        rows.append('<tr>'+''.join('<td>'+c+'</td>' for c in cells)+'</tr>')
    atomic_json(destination/'metrics.json', metrics)
    page = '<!doctype html><html lang="sv"><meta charset="utf-8"><title>Bildstöd – kvalitetstest</title><style>body{font:16px system-ui;margin:24px;color:#20332b;background:#fafbf8}table{width:100%;border-collapse:collapse}td,th{padding:16px;border:1px solid #ccd5cc;vertical-align:top;width:25%}label{display:block;font-size:14px}textarea,select{display:block;box-sizing:border-box;width:100%;margin:8px 0}textarea{min-height:70px}button{padding:12px 20px}img{width:180px;max-width:100%;background:white}.small{width:48px}.gray{filter:grayscale(1)}h2{font-size:18px}</style><h1>20 motiv – kvalitetstest</h1><p>Ogranskade kandidater. Baslinjen är aktuell bild, inte nödvändigtvis den historiskt avvisade versionen. Små prov visas i 48 px och gråskala. Inget publiceras automatiskt.</p><table><tr><th>Motiv och krav</th><th>Baslinje</th><th>Textstyrning</th><th>Referensstyrning</th></tr>'+''.join(rows)+'</table><button id="export">Spara granskningsbeslut</button><p id="feedback" role="status"></p>'+REVIEW_SCRIPT+'</html>'
    (destination/'review.html').write_text(page)


def live_snapshot():
    from .metadata import load_candidates
    return {'images': load_candidates()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'plan', 'render', 'review', 'report'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--private-reviews', type=Path)
    parser.add_argument('--profile', choices=PROFILES, default='text')
    parser.add_argument('--decisions', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.directory, json.loads(args.snapshot.read_text()) if args.snapshot else live_snapshot(), json.loads(args.private_reviews.read_text()) if args.private_reviews else None)
    elif args.command == 'render':
        render(args.directory, args.profile)
    elif args.command == 'review':
        save_decisions(args.directory, json.loads(args.decisions.read_text()))
    else:
        state = json.loads((args.directory/'experiment.json').read_text())
        if args.command == 'plan':
            print(json.dumps(plan(state, args.profile), ensure_ascii=False, indent=2))
        else:
            report(args.directory, state)


if __name__ == '__main__':
    main()
