"""Public, measured operational report and fixed visual regression specimens."""
import concurrent.futures
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from .metadata import load_candidates,read_url,REPO,PROFILE
from .generation import ROOT,load_config,load_briefs,identity
from .rework import fetch_queue


def summarize(entries,candidates,receipts,config):
    images={c['concept_id']:c for c in candidates}
    pending=[];failed=[]
    for e in entries:
        if not e.get('generation_enabled',True):continue
        receipt=receipts.get(e['id'],images.get(e['id'],{}))
        if receipt.get('status')=='failed':failed.append({'id':e['id'],'error_type':receipt.get('error_type','Unknown')})
        elif receipt.get('fingerprint')!=identity(e,config):pending.append(e['id'])
    return {'enabled':sum(e.get('generation_enabled',True) for e in entries),'with_image':len(images),'pending':pending,'failed':failed}


def main():
    config=load_config(ROOT/'config/generation.json');entries=load_briefs(ROOT/config['catalog_path'])
    candidates=load_candidates();images={c['concept_id']:c for c in candidates};requests=fetch_queue()
    # Read only missing concepts and approved reworks, rather than every image receipt.
    ids={e['id'] for e in entries if e.get('generation_enabled',True) and e['id'] not in images}|{r['concept_id'] for r in requests}
    if len(ids)>200:raise ValueError('Too many missing receipts; inspect worker branches before reporting health')
    def receipt(identifier):
        import hashlib
        worker=config.get('worker_overrides',{}).get(identifier,0 if identifier=='FSK_01_04' else int(hashlib.sha256(identifier.encode()).hexdigest()[:8],16)%8)
        try:return identifier,json.loads(read_url(f'{REPO}/generated-flux-worker-{worker}/data/{PROFILE}/{identifier}.json'))
        except Exception as error:
            if getattr(error,'code',None)==404:return identifier,{}
            raise
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:receipts=dict(pool.map(receipt,sorted(ids)))
    # Use the same override selection as the worker without writing images.
    import tempfile
    from .rework import apply_requests
    with tempfile.TemporaryDirectory() as d:
        for key,value in {**images,**receipts}.items():Path(d,key+'.json').write_text(json.dumps(value))
        effective=apply_requests(entries,requests,Path(d))
    coverage=summarize(effective,candidates,receipts,config)
    workflows={}
    for filename,name in [('generate-pilot.yml','Generate pilot candidates'),('metadata-pilot.yml','Suggest image metadata')]:
        runs=json.loads(subprocess.check_output(['gh','api',f'repos/wallgrnstudios/bildstod-26-generator/actions/workflows/{filename}/runs?per_page=20'],text=True))['workflow_runs']
        if runs:
            workflows[name]={k:runs[0][k] for k in ('id','status','conclusion','created_at','updated_at','html_url')}
            workflows[name]['last_success_at']=next((r['updated_at'] for r in runs if r['conclusion']=='success'),None)
    reworks=[]
    for r in requests:
        c=images.get(r['concept_id'],{});receipt=receipts.get(r['concept_id'],c)
        status='completed' if c.get('regeneration_request_id')==r['request_id'] else 'failed' if receipt.get('regeneration_request_id')==r['request_id'] and receipt.get('status')=='failed' else 'queued' if c.get('sha256')==r['source_sha256'] else 'superseded'
        reworks.append({'request_id':r['request_id'],'concept_id':r['concept_id'],'status':status,'replacement_sha256':c.get('sha256') if status=='completed' else None})
    metadata=json.loads(read_url(f'{REPO}/metadata-suggestions/suggestions.json'))
    records=list(metadata.get('records',{}).values())
    specs=json.loads((ROOT/'config/quality-specimens.json').read_text())
    baseline=json.loads((ROOT/'config/quality-baseline.json').read_text()) if (ROOT/'config/quality-baseline.json').exists() else {'specimens':[]}
    old={c['concept_id']:c for c in baseline['specimens']}
    quality=[]
    for spec in specs['specimens']:
        c=images.get(spec['id']);b=old.get(spec['id'])
        quality.append({**spec,'current':c,'baseline':b,'changed':bool(c and b and c['sha256']!=b['sha256'])})
    report={'schema_version':1,'checked_at':datetime.now(timezone.utc).isoformat(),'coverage':coverage,'workflows':workflows,'reworks':reworks,'metadata':{'attempted':len(records),'suggested':sum(r.get('status')=='suggested' for r in records),'failed':sum(r.get('status')=='failed' for r in records),'limit':30},'quality':quality}
    Path('.operations').mkdir(exist_ok=True)
    Path('.operations/status.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'coverage':coverage,'reworks':len(reworks),'quality_specimens':len(quality)},ensure_ascii=False))

if __name__=='__main__':main()
