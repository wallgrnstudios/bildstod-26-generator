"""Apply individually scoped 2026-10-26 briefs; preserve earlier images and reviews."""
import json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def apply(root=ROOT):
    def read(name):return json.loads((root/name).read_text())
    symbols=read('catalog/pilot/symbols.json'); vocabulary=read('catalog/school/vocabulary-2000.json')
    resolutions=read('catalog/school/concept-resolutions.json')
    completions=read('catalog/school/brief-completions-2026-10-26.json')
    by_symbol={e['id']:e for e in symbols};by_vocab={e['id']:e for e in vocabulary};by_resolution={e['id']:e for e in resolutions}
    activated=[]
    for brief in completions:
        cid=brief['id'];row=by_vocab[cid];previous=by_resolution[cid]
        if previous.get('brief_source')=='brief-completions-2026-10-26':continue
        if previous['resolution']!='open_question':raise ValueError('Completion must not replace an existing resolved brief: '+cid)
        if cid in by_symbol and by_symbol[cid].get('generation_enabled'):raise ValueError('Existing active contract must remain unchanged: '+cid)
        kind=brief['resolution']
        revised={'id':cid,'text_sv':row['text_sv'],'resolution':kind,'meaning_sv':brief['meaning_sv'],
                 'brief_source':'brief-completions-2026-10-26','previous_question_sv':previous['question_sv']}
        row.update(meaning_sv=brief['meaning_sv'],resolution=kind)
        if kind=='standalone':
            entry={**brief,'text_sv':row['text_sv'],'review_status':'draft','generation_enabled':True,'generation_priority':1,
                   'category':row['category'],'reference_conditioning':False,'style_family':'clean_white'}
            entry.pop('resolution');entry.pop('previous_question_sv',None)
            if cid in by_symbol:
                symbols[symbols.index(by_symbol[cid])]=entry
            else:symbols.append(entry)
            by_symbol[cid]=entry
            row.update(entry_type='concept',brief_status='generation_ready',generation_enabled=True,symbol_id=cid)
            revised.update({key:brief[key] for key in ['symbol_type','visual_prompt_en','must_show_sv','must_not_show_sv','contrast_terms_sv']})
            activated.append(cid)
        elif kind=='reuse':
            target=brief['reuse_symbol_id']
            if target not in by_symbol:raise ValueError('Unknown reused symbol: '+target)
            row.update(brief_status='reuses_symbol',generation_enabled=False,symbol_id=None,reuse_symbol_id=target)
            revised['reuse_symbol_id']=target
        elif kind=='convention_proposal':
            row.update(brief_status='convention_proposed',generation_enabled=False,symbol_id=cid if cid in by_symbol else None)
            revised.update(proposal_sv=brief['meaning_sv'],proposal_visual_en=brief['visual_prompt_en'],
                           review_question_sv=brief['review_question_sv'],contrast_terms_sv=brief['contrast_terms_sv'])
        else:raise ValueError('Unknown completion kind: '+kind)
        resolutions[resolutions.index(previous)]=revised;by_resolution[cid]=revised
    for name,data in [('catalog/pilot/symbols.json',symbols),('catalog/school/vocabulary-2000.json',vocabulary),('catalog/school/concept-resolutions.json',resolutions)]:
        (root/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    summary=read('catalog/school/summary.json')
    summary.update(total=len(vocabulary),production_target=3000,brief_status=dict(Counter(e['brief_status'] for e in vocabulary)),
                   resolutions=dict(Counter(e['resolution'] for e in resolutions)))
    (root/'catalog/school/summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return activated

if __name__=='__main__':print(json.dumps({'activated':len(apply())}))
