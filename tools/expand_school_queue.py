"""Add the curated concrete school supplement with stable, deduplicated IDs."""
import json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def apply(root=ROOT):
    def read(name):return json.loads((root/name).read_text())
    symbols=read('catalog/pilot/symbols.json');vocabulary=read('catalog/school/vocabulary-2000.json')
    source=read('catalog/school/expansion-2026-10-26.json')
    labels={e['text_sv'].casefold() for e in vocabulary};ids={e['id'] for e in symbols}|{e['id'] for e in vocabulary}
    added=[];index=0
    for item in source:
        if item['text_sv'].casefold() in labels:continue
        while True:
            cid=f'FSK_{34+index//99:02}_{index%99+1:02}';index+=1
            if cid not in ids:break
        ids.add(cid);labels.add(item['text_sv'].casefold())
        entry={**item,'id':cid,'meaning_sv':item['must_show_sv'][0],
               'review_status':'draft','generation_enabled':True,'generation_priority':2,
               'reference_conditioning':False,'style_family':'color_focus_v1','composition_family':'close_readable_v1'}
        symbols.append(entry);added.append(cid)
        vocabulary.append(dict(id=cid,text_sv=entry['text_sv'],category=entry['category'],entry_type='concept',
            priority_tier=2,editorial_order=len(vocabulary)+1,meaning_sv=entry['meaning_sv'],age_scope=['förskola','grundskola'],
            brief_status='generation_ready',generation_enabled=True,symbol_id=cid,composition_policy=None,
            review_status='editorial_draft',frequency_claim='editorial_school_supplement_not_frequency_rank'))
    for name,data in [('catalog/pilot/symbols.json',symbols),('catalog/school/vocabulary-2000.json',vocabulary)]:
        (root/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    summary=read('catalog/school/summary.json')
    summary.update(total=len(vocabulary),production_target=3000,
                   brief_status=dict(Counter(e['brief_status'] for e in vocabulary)),
                   categories=dict(sorted(Counter(e['category'] for e in vocabulary).items())))
    (root/'catalog/school/summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return added

if __name__=='__main__':print(json.dumps({'added':len(apply())}))
