"""Consume only explicitly published render briefs; private reviews are never read."""
import argparse
import copy
import json
import re
from pathlib import Path
from urllib.parse import urlencode
from .metadata import read_url
from .generation import load_briefs, load_config, ROOT

PUBLIC_QUEUE='https://firestore.googleapis.com/v1/projects/wallgrnstudios-e8cb1/databases/(default)/documents/bildstod26RenderQueue'
FIELDS={'concept_id','source_sha256','prompt_en','createdAt','public_approved','schema_version','revision'}


def fetch_queue():
    rows=[]
    token=None
    while True:
        page=json.loads(read_url(PUBLIC_QUEUE+'?'+urlencode({'pageSize':300,**({'pageToken':token} if token else {})})))
        for doc in page.get('documents',[]):
            f=doc['fields']
            if set(f)!=FIELDS or f['public_approved'].get('booleanValue') is not True or f['schema_version'].get('integerValue')!='1':
                raise ValueError('Invalid public render queue schema')
            row={k:f[k]['stringValue'] for k in ('concept_id','source_sha256','prompt_en')}
            row['created_at']=f['createdAt']['timestampValue']
            row['revision']=int(f['revision']['integerValue'])
            row['request_id']=doc['name'].rsplit('/',1)[-1]+'_r'+str(row['revision'])
            if not re.fullmatch(r'FSK_\d{2}_\d{2}',row['concept_id']) or not re.fullmatch('[a-f0-9]{64}',row['source_sha256']) or not 1<=row['revision']<=1000 or row['request_id']!=row['concept_id']+'_'+row['source_sha256']+'_r'+str(row['revision']) or not 10<=len(row['prompt_en'])<=700:
                raise ValueError('Invalid public render request')
            rows.append(row)
        token=page.get('nextPageToken')
        if not token: return rows
        if len(rows)>5000: raise ValueError('Render request safety limit exceeded')


def apply_requests(entries, requests, output):
    result=copy.deepcopy(entries)
    latest={}
    for r in sorted(requests,key=lambda r:(r['created_at'],r['request_id'])):
        latest[r['concept_id']]=r
    for e in result:
        r=latest.get(e['id'])
        if not r or not e.get('generation_enabled',True): continue
        sidecar=output/(e['id']+'.json')
        old=json.loads(sidecar.read_text()) if sidecar.exists() else {}
        # Re-apply completed overrides every run so the base catalog cannot revert them.
        if old.get('regeneration_request_id')!=r['request_id'] and old.get('sha256',old.get('regeneration_source_sha256'))!=r['source_sha256']:
            continue
        e['visual_prompt_en']=r['prompt_en']
        e['regeneration_request_id']=r['request_id']
        e['regeneration_source_sha256']=r['source_sha256']
        e['generation_priority']=0
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['fetch','apply']);p.add_argument('--queue',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--catalog',type=Path)
    a=p.parse_args()
    if a.command=='fetch':
        a.queue.parent.mkdir(parents=True,exist_ok=True);a.queue.write_text(json.dumps(fetch_queue(),ensure_ascii=False));return
    config=load_config(ROOT/'config/generation.json')
    entries=apply_requests(load_briefs(ROOT/config['catalog_path']),json.loads(a.queue.read_text()),a.output/config['style_version'])
    a.catalog.write_text(json.dumps(entries,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
