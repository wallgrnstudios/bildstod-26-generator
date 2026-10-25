"""Consume only explicitly published render briefs; private reviews are never read."""
import argparse
import copy
import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from .metadata import read_url
from .generation import load_briefs, load_config, ROOT

PUBLIC_QUEUE='https://firestore.googleapis.com/v1/projects/wallgrnstudios-e8cb1/databases/(default)/documents/bildstod26RenderQueue'
FIELDS={'concept_id','source_sha256','prompt_en','createdAt','public_approved','schema_version','revision'}


def _fetch_queue():
    rows=[]
    token=None
    while True:
        page=json.loads(read_url(PUBLIC_QUEUE+'?'+urlencode({'pageSize':300,**({'pageToken':token} if token else {})})))
        for doc in page.get('documents',[]):
            f=doc['fields']
            # Cancelled requests are audit history, never executable work. They may
            # contain a server-side update timestamp added by the archival action.
            # Skip them before enforcing the strict active-queue schema.
            if f.get('cancelled',{}).get('booleanValue') is True:
                continue
            if not FIELDS.issubset(f) or set(f)-FIELDS-{'cancelled'} or f['public_approved'].get('booleanValue') is not True or f['schema_version'].get('integerValue')!='1':
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


def fetch_queue(warnings=None):
    """Read public rework briefs without allowing a rate limit to stop normal generation.

    A missed read only defers explicit reworks. It must never prevent unrelated
    pending concepts from reaching the worker batch.
    """
    for attempt in range(2):
        try:
            return _fetch_queue()
        except HTTPError as error:
            if error.code != 429:
                raise
            if attempt == 0:
                time.sleep(2)
                continue
            if warnings is not None:
                warnings.append('Omgenereringskön kunde inte läsas på grund av tillfällig kvotgräns; vanliga bildkandidater fortsätter utan köändringar.')
            return []


def _has_verified_source(output, concept_id, source_sha256):
    """Find the reviewed source across renderer-profile directories.

    A rework request names the image hash it was made from.  Worker state is
    deliberately retained by profile, so a renderer upgrade must not silently
    strand a valid request just because its original receipt lives under the
    preceding profile directory.
    """
    for sidecar in output.glob(f'*/{concept_id}.json'):
        try:
            receipt = json.loads(sidecar.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if receipt.get('sha256') == source_sha256 or receipt.get('regeneration_source_sha256') == source_sha256:
            return True
    return False


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
        source_matches = (old.get('sha256') == r['source_sha256']
                          or old.get('regeneration_source_sha256') == r['source_sha256']
                          or _has_verified_source(output, e['id'], r['source_sha256']))
        if old.get('regeneration_request_id')!=r['request_id'] and not source_matches:
            continue
        e['visual_prompt_en']=r['prompt_en']
        e['regeneration_request_id']=r['request_id']
        e['regeneration_source_sha256']=r['source_sha256']
        # Reworks are deliberately text-led: the style reference has repeatedly
        # leaked pose and composition into otherwise simple symbols.
        e['reference_conditioning']=False
        e['style_prompt_override']='Modern gentle children’s-book illustration, fine brown pencil line and light watercolor colour. Isolated on pure white, no text or scenery.'
        e['generation_priority']=0
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['fetch','apply']);p.add_argument('--queue',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--catalog',type=Path)
    a=p.parse_args()
    if a.command=='fetch':
        warnings=[];requests=fetch_queue(warnings)
        a.queue.parent.mkdir(parents=True,exist_ok=True);a.queue.write_text(json.dumps(requests,ensure_ascii=False))
        for warning in warnings: print('WARNING: '+warning)
        return
    config=load_config(ROOT/'config/generation.json')
    entries=apply_requests(load_briefs(ROOT/config['catalog_path']),json.loads(a.queue.read_text()),a.output/config['style_version'])
    a.catalog.write_text(json.dumps(entries,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
