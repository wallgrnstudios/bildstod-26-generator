"""Activate individually written atomic briefs, preserving every existing image contract."""
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STYLE=('Contemporary hand-drawn children book illustration, fine neutral charcoal lines, natural proportions, gentle precise shading. '
       'Fresh clean modern materials and clear true-to-life colors. White textiles and hygiene products stay bright white with very light cool-gray shadows. '
       'Smooth even color on fabric and plastic; no sepia, ochre wash, grunge, stains, yellowing, distressed paper or aged patina. '
       'Borrow drawing technique only from reference, never its brown palette. Isolated on pure white without text, scenery or cast shadows.')

# Typed templates for individually resolved catalog entries. Legacy list briefs stay objects.
TEMPLATES={
    'object':' Isolated on pure white. No people, decorative scenery, brand names or lettering.',
    'action':(' Show the action itself at its most recognizable moment, with the body movement and any object it acts on clearly visible.'
              ' Include only the people needed to perform the action. No destination, audience, decorative scenery, brand names or lettering.'),
    'person':(' One person alone, full body, friendly neutral expression. Any role is shown only through the named concrete attributes;'
              ' no badges, logos, lettering or decorative scenery.'),
    'body_part':(' The body part is large and centered in a clear, friendly, non-medical view of a child, cropped only as described,'
                 ' natural skin tone, fully appropriate for preschool use, no injury or nudity. No lettering or scenery.'),
    'situation':' Only the people and objects described; no decorative scenery, brand names or lettering.',
}
RESOLUTIONS={'standalone':'generation_ready','reuse':'reuses_symbol','composition':'composition_defined',
             'convention_proposal':'convention_proposed','open_question':'decision_required'}
UNRESOLVED={'brief_required','convention_required','composition_required'}
REQUIRED={'standalone':('symbol_type','visual_prompt_en','must_show_sv','must_not_show_sv','contrast_terms_sv'),
          'reuse':('reuse_symbol_id',),'composition':('parts',),
          'convention_proposal':('proposal_sv','proposal_visual_en','review_question_sv','contrast_terms_sv'),
          'open_question':('question_sv','options_sv')}


def validate_resolutions(resolutions,vocabulary,symbols):
    by_id={e['id']:e for e in vocabulary};symbol_ids={e['id'] for e in symbols}
    pending={e['id'] for e in symbols if e.get('convention_status')=='pending'};active=symbol_ids-pending
    seen=set();kinds={r['id']:r.get('resolution') for r in resolutions}
    for r in resolutions:
        row=by_id.get(r.get('id'))
        if not row or r['id'] in seen or r.get('text_sv')!=row['text_sv']:
            raise ValueError('Unknown, duplicate or relabelled entry: '+str(r.get('id')))
        seen.add(r['id']);kind=r.get('resolution')
        if kind not in RESOLUTIONS or not str(r.get('meaning_sv','')).strip():
            raise ValueError('Resolution and bounded meaning required: '+r['id'])
        if row.get('resolution')!=kind and (row['brief_status'] not in UNRESOLVED or r['id'] in active and kind!='standalone'):
            raise ValueError('Entry is already resolved or active: '+r['id'])
        if kind=='standalone' and r['id'] in pending:
            raise ValueError('Pending conventions are never activated as standalone images: '+r['id'])
        missing=[k for k in REQUIRED[kind] if not r.get(k)]
        if missing:raise ValueError(f'{r["id"]} lacks {missing}')
        if kind=='standalone':
            words=r['text_sv'].split()
            if row['entry_type']!='concept' or len(words)>3 or words[0].casefold() in ('jag','vi'):
                raise ValueError('Phrases are compositions, never standalone images: '+r['id'])
            if r['symbol_type'] not in TEMPLATES:raise ValueError('Unknown symbol type: '+r['id'])
            if r['symbol_type'] in ('action','person','situation') and 'no people' in r['visual_prompt_en'].casefold():
                raise ValueError('People are needed for this symbol type: '+r['id'])
        if kind=='reuse' and r['reuse_symbol_id'] not in symbol_ids|{k for k,v in kinds.items() if v=='standalone'}:
            raise ValueError('Reused symbol does not exist: '+r['id'])
        if kind=='composition':
            if ''.join(p['text'] for p in r['parts'])!=r['text_sv']:
                raise ValueError('Composition must preserve the exact text: '+r['id'])
            for part in r['parts']:
                ref=part.get('symbol_id')
                if ref and ref not in symbol_ids and kinds.get(ref) not in ('standalone','convention_proposal'):
                    raise ValueError(f'{r["id"]} references unresolved symbol {ref}')


def prepare_resolutions(symbols,vocabulary,resolutions):
    validate_resolutions(resolutions,vocabulary,symbols)
    by_id={e['id']:e for e in vocabulary};existing={e['id'] for e in symbols};added=[]
    for r in resolutions:
        row=by_id[r['id']];kind=r['resolution']
        row.update(meaning_sv=r['meaning_sv'],brief_status=RESOLUTIONS[kind],resolution=kind)
        if kind!='standalone':
            # Disabled convention symbols keep their reference; nothing is activated.
            row.update(generation_enabled=False,symbol_id=row['id'] if row['id'] in existing else None)
            continue
        row.update(generation_enabled=True,symbol_id=row['id'])
        if r['id'] in existing:
            # Activated symbols may carry reviewer corrections; never regenerate them from the source brief.
            continue
        entry={'id':row['id'],'text_sv':row['text_sv'],'symbol_type':r['symbol_type'],'meaning_sv':r['meaning_sv'],
               'visual_prompt_en':r['visual_prompt_en'].strip()+TEMPLATES[r['symbol_type']],
               'must_show_sv':r['must_show_sv'],'must_not_show_sv':r['must_not_show_sv'],'contrast_terms_sv':r['contrast_terms_sv'],
               'review_status':'draft','generation_enabled':True,'generation_priority':row.get('priority_tier',1),
               'category':row['category'],'style_prompt_override':STYLE}
        symbols.append(entry);existing.add(r['id']);added.append(r['id'])
    return added


def prepare(symbols,vocabulary,briefs):
    by_label={e['text_sv'].casefold():e for e in vocabulary}
    existing={e['id']:e for e in symbols}
    added=[]
    for label,prompt,criterion,contrast in briefs:
        row=by_label[label.casefold()]
        if row['id'] in existing:
            # Already activated entries may have subsequent reviewer corrections.
            continue
        if row['brief_status']!='brief_required' or row['entry_type']!='concept':
            raise ValueError('Only concrete concept briefs may be promoted: '+label)
        if not all(isinstance(x,str) and x.strip() for x in (label,prompt,criterion,contrast)):
            raise ValueError('Incomplete brief: '+label)
        entry={'id':row['id'],'text_sv':label,'symbol_type':'object',
               'meaning_sv':f'{label.capitalize()}: {criterion}. Avser det avgränsade motivet, inte en hel situation.',
               'visual_prompt_en':prompt+' Isolated on pure white. No people, decorative scenery, brand names or lettering.',
               'must_show_sv':[criterion],'must_not_show_sv':['Personer eller en hel berättelse i samma bild'],
               'contrast_terms_sv':[contrast],'generation_enabled':True,'generation_priority':row.get('priority_tier',1),
               'review_status':'draft','style_prompt_override':STYLE}
        symbols.append(entry);existing[row['id']]=entry;added.append(row['id'])
        row.update(meaning_sv=entry['meaning_sv'],brief_status='generation_ready',generation_enabled=True,symbol_id=row['id'])
    return added


def main():
    base=ROOT/'catalog/school'
    symbols=json.loads((ROOT/'catalog/pilot/symbols.json').read_text())
    vocabulary=json.loads((base/'vocabulary-2000.json').read_text())
    briefs=json.loads((base/'production-briefs.json').read_text())
    before=json.dumps(symbols,ensure_ascii=False)
    added=prepare(symbols,vocabulary,briefs)
    resolutions_path=base/'concept-resolutions.json'
    resolutions=json.loads(resolutions_path.read_text()) if resolutions_path.exists() else []
    vocabulary_before=json.dumps(vocabulary,ensure_ascii=False)
    added+=prepare_resolutions(symbols,vocabulary,resolutions)
    assert len(vocabulary)==2000 and len({e['id'] for e in symbols})==len(symbols)
    if not added and json.dumps(vocabulary,ensure_ascii=False)==vocabulary_before:
        print('No new briefs; existing queue left unchanged.')
        return
    # Existing entries must be byte-for-byte equivalent as JSON values.
    assert symbols[:len(json.loads(before))]==json.loads(before)
    for path,data in [(ROOT/'catalog/pilot/symbols.json',symbols),(base/'vocabulary-2000.json',vocabulary)]:
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    ready=json.loads((base/'ready-briefs.json').read_text());labels={x[0].casefold() for x in ready}
    ready.extend(row for row in briefs if row[0].casefold() not in labels)
    (base/'ready-briefs.json').write_text('[\n'+',\n'.join(json.dumps(r,ensure_ascii=False,separators=(',',':')) for r in ready)+'\n]\n')
    summary=json.loads((base/'summary.json').read_text());summary['brief_status']=dict(Counter(e['brief_status'] for e in vocabulary))
    summary['resolutions']=dict(Counter(r['resolution'] for r in resolutions))
    summary['standalone_symbol_types']=dict(Counter(r['symbol_type'] for r in resolutions if r['resolution']=='standalone'))
    (base/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'new_briefs':len(added),'enabled':sum(e.get('generation_enabled',True) for e in symbols),'backlog':summary['brief_status']},ensure_ascii=False))

if __name__=='__main__':main()
