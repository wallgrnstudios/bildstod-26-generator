"""Activate individually written atomic briefs, preserving every existing image contract."""
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STYLE=('Contemporary hand-drawn children book illustration, fine neutral charcoal lines, natural proportions, gentle precise shading. '
       'Fresh clean modern materials and clear true-to-life colors. White textiles and hygiene products stay bright white with very light cool-gray shadows. '
       'Smooth even color on fabric and plastic; no sepia, ochre wash, grunge, stains, yellowing, distressed paper or aged patina. '
       'Borrow drawing technique only from reference, never its brown palette. Isolated on pure white without text, scenery or cast shadows.')

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
               'meaning_sv':f'{label.capitalize()}: {criterion}. Avser föremålet, inte en hel situation.',
               'visual_prompt_en':prompt+' Isolated on pure white. No people, decorative scenery, brand names or lettering.',
               'must_show_sv':[criterion],'must_not_show_sv':['Personer eller en hel berättelse i samma bild'],
               'contrast_terms_sv':[contrast],'generation_enabled':True,'generation_priority':1,
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
    assert len(vocabulary)==2000 and len({e['id'] for e in symbols})==len(symbols)
    if not added:
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
    (base/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'new_briefs':len(added),'enabled':sum(e.get('generation_enabled',True) for e in symbols),'backlog':summary['brief_status']},ensure_ascii=False))

if __name__=='__main__':main()
