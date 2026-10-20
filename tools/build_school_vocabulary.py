"""Build an editorial school shortlist, NOT a measured top-2000 AAC frequency list.
Optional build dependency: wordfreq==3.1.1. No model, image or remote API calls.
"""
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from wordfreq import zipf_frequency

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'catalog/school'
# Priority is editorial relevance to communication and the school day, not prevalence.
CORE=set('kommunikation|behov|känslor|kroppsliga behov|familj|skolpersonal|skolmiljö|utemiljö|skoldag|kläder|klädtillbehör|påklädning|måltidsföremål|mat|frukt och grönt|bröd och dryck|matvanor|hygien|hygienhandlingar|kroppen|trygghet och gränser|socialt samspel|rörelse|lek|skapande|bildmaterial|läsa och skriva|skolmaterial|position|beskrivningar|tid|lärstrategier|självreglering|vardagshandlingar|skolfraser'.split('|'))
# Exact, short labels requiring context or an agreed symbol convention.
CONVENTION_CATEGORIES=set('kommunikation|behov|känslor|kroppsliga behov|skolorganisation|trygghet och gränser|position|beskrivningar|färger och sinnen|tid|mätning|matematik|geometri|språk|mediekunskap|historia och religion|lärstrategier|självreglering'.split('|'))

def build():
    current=json.loads((ROOT/'catalog/pilot/symbols.json').read_text())
    # Previous school additions must not change the fixed initial cohort or ID allocation.
    initial=[x for x in current if int(x['id'].split('_')[1])>=90]
    existing={x['text_sv'].casefold():x for x in initial}
    ready=json.loads((PATH/'ready-briefs.json').read_text())
    ready_labels={x[0].casefold() for x in ready}
    ready_by_label={x[0].casefold():x for x in ready}
    prior_path=PATH/'vocabulary-2000.json'
    prior={x['text_sv'].casefold():x['id'] for x in json.loads(prior_path.read_text())} if prior_path.exists() else {}
    candidates={}
    for line in (PATH/'editorial-vocabulary.txt').read_text().splitlines():
        category,words=line.split('|',1);category=category.strip()
        for text in words.split(';'):
            text=unicodedata.normalize('NFC',text.strip())
            if text.casefold() in candidates:continue
            candidates[text.casefold()]={'text_sv':text,'category':category,'source_order':len(candidates)}
    for label,*_ in ready:
        if label.casefold() not in candidates:candidates[label.casefold()]={'text_sv':label,'category':'vardagsföremål','source_order':len(candidates)}
    for key,entry in existing.items():
        if key not in candidates:candidates[key]={'text_sv':entry['text_sv'],'category':'befintlig pilot','source_order':len(candidates)}
    for key,row in candidates.items():
        row['frequency_hint']=zipf_frequency(row['text_sv'],'sv')
        row['priority']=0 if key in existing else 1 if row['category'] in CORE else 2
    def order(row):return(row['priority'],-row['frequency_hint'],row['source_order'])
    # Minimum coverage prevents general-language frequency from excluding specialist needs.
    selected=dict((key,row) for key,row in candidates.items() if key in existing or key in ready_labels)
    categories=list(dict.fromkeys(x['category'] for x in candidates.values()))
    for category in categories:
        cohort=sorted([x for x in candidates.values() if x['category']==category],key=order)
        for row in cohort[:(22 if category in CORE else 22)]:selected[row['text_sv'].casefold()]=row
    for row in sorted(candidates.values(),key=order):
        if len(selected)==2000:break
        selected[row['text_sv'].casefold()]=row
    rows=[];new_index=0
    reserved=set(prior.values())|{x['id'] for x in initial}
    for rank,row in enumerate(sorted(selected.values(),key=order),1):
        text=row['text_sv'];old=existing.get(text.casefold())
        if old:identifier=old['id']
        elif text.casefold() in prior:identifier=prior[text.casefold()]
        else:
            # 99 slots per namespace; disjoint from existing FSK_90…92 IDs.
            while True:
                identifier=f'FSK_{10+new_index//99:02}_{1+new_index%99:02}';new_index+=1
                if identifier not in reserved:break
            reserved.add(identifier)
        phrase=len(text.split())>1
        kind='phrase' if phrase else 'concept'
        status='composition_required' if phrase else 'convention_required' if row['category'] in CONVENTION_CATEGORIES else 'brief_required'
        if old:status='generation_ready' if old.get('generation_enabled') else 'convention_required'
        if text.casefold() in ready_labels:status='generation_ready'
        rows.append({'id':identifier,'text_sv':text,'category':row['category'],'entry_type':kind,
            'priority_tier':row['priority'],'editorial_order':rank,
            'meaning_sv':old['meaning_sv'] if old else f'{text.capitalize()} som föremål. Inte en hel handling eller instruktion.' if text.casefold() in ready_labels else f'{text} – betydelsen ska avgränsas inom {row["category"]} före bildgenerering.',
            'age_scope':['förskola','grundskola'] if row['priority']<2 else ['grundskola'],
            'brief_status':status,'generation_enabled':bool((old and old.get('generation_enabled')) or text.casefold() in ready_labels),
            'symbol_id':identifier if status=='generation_ready' or old else None,
            'composition_policy':'Bevara texten; koppla endast granskade delbetydelser.' if phrase else None,
            'review_status':'editorial_draft','frequency_claim':'editorial_selection_not_school_frequency_rank'})
    assert len(rows)==2000 and len({x['id'] for x in rows})==2000 and len({x['text_sv'].casefold() for x in rows})==2000
    (PATH/'vocabulary-2000.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    (PATH/'vocabulary-2000.txt').write_text('\n'.join(f'{x["editorial_order"]:04}  {x["text_sv"]}  [{x["category"]}]' for x in rows)+'\n')
    summary={'total':len(rows),'selection':'editorial school relevance with general Swedish frequency as a tie-breaker; not measured school/AAC frequency','input_count':len(candidates),'categories':dict(sorted(Counter(x['category'] for x in rows).items())),'brief_status':dict(Counter(x['brief_status'] for x in rows)),'wordfreq_version':'3.1.1','sources':['https://www.spsm.se/stod-och-rad/sprak-och-kommunikation/alternativ-och-kompletterande-kommunikation/','https://github.com/rspeer/wordfreq'],'images_or_arasaac_metadata_imported':False}
    (PATH/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ('total','input_count','brief_status')},ensure_ascii=False))
if __name__=='__main__':build()
