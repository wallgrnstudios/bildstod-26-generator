"""Public image-only metadata suggestions. No private review data or cloud credentials."""
import argparse
import concurrent.futures
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REPO = 'https://raw.githubusercontent.com/wallgrnstudios/bildstod-26-generator'
REMOTE = 'https://github.com/wallgrnstudios/bildstod-26-generator.git'
PROFILE = 'symbol-white-0.13-arm512'
FIELDS = ('characterId','hairColor','hairStyle','skinTone','genderPresentation','ageGroup','distinguishingFeatures')
COLORS = {'black':'svart','brown':'brunt','blond':'blont','red':'rött','gray':'grått','white':'vitt','bald':'inget synligt hår','unknown':''}
STYLES = {'short':'kort','long':'långt','curly':'lockigt','braids':'flätor','ponytail':'hästsvans','bald':'inget synligt hår','unknown':''}
SKIN = {'light':'ljus','medium':'mellan','dark':'mörk','unknown':''}
AGE = {'child':'barn','adult':'vuxen','unknown':''}
PROMPT = '''Describe only the human characters visibly drawn in this illustration, not dolls, animals or imagined people. Return ONLY JSON. List people from left to right. If no humans, return {"people":[]}. Up to four humans. For each human use exactly these keys and allowed values: hairColor: black/brown/blond/red/gray/white/bald/unknown; hairStyle: short/long/curly/braids/ponytail/bald/unknown; skinTone: light/medium/dark/unknown; ageGroup: child/adult/unknown. If hidden or uncertain use unknown. Do not infer identity, gender or ethnicity. Format: {"people":[{"hairColor":"brown","hairStyle":"short","skinTone":"light","ageGroup":"child"}]}'''


def read_url(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read(5*1024*1024+1)
    if len(data) > 5*1024*1024:
        raise ValueError('Oversized public input')
    return data


def load_candidates():
    def worker(n):
        head = subprocess.check_output(['git','ls-remote',REMOTE,f'refs/heads/generated-flux-worker-{n}'],text=True).split()[0]
        index = json.loads(read_url(f'{REPO}/{head}/data/{PROFILE}/candidates.json'))
        result=[]
        for item in index['candidates']:
            if item.get('status') != 'pending_review':
                continue
            if not re.fullmatch(r'FSK_\d{2}_\d{2}',item['concept_id']) or not re.fullmatch('[a-f0-9]{64}',item['sha256']):
                raise ValueError('Invalid image identity')
            result.append({**item,'source_commit':head,'source_url':f'{REPO}/{head}/data/{PROFILE}/{item["concept_id"]}.png'})
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        return [c for group in pool.map(worker,range(8)) for c in group]


def parse_people(raw):
    # Model output is untrusted and never controls IDs, URLs, commands or instructions.
    text=raw.strip()
    if text.startswith('```'):
        text=re.sub(r'^```(?:json)?\s*|\s*```$','',text)
    payload=json.loads(text)
    people=payload.get('people')
    if not isinstance(people,list) or len(people)>4:
        raise ValueError('Expected up to four illustrated people')
    result=[]
    for p in people:
        if not isinstance(p,dict) or set(p) != {'hairColor','hairStyle','skinTone','ageGroup'}:
            raise ValueError('Unexpected person schema')
        person={k:'' for k in FIELDS}
        for key,mapping in [('hairColor',COLORS),('hairStyle',STYLES),('skinTone',SKIN),('ageGroup',AGE)]:
            if p[key] not in mapping:
                raise ValueError('Unrecognized appearance value')
            person[key]=mapping[p[key]]
        result.append(person)
    return result


def select_batch(candidates,state,config):
    # Fixed lifetime pilot cap, including failures. Schedules cannot silently expand it.
    records=state.get('records',{})
    remaining=max(0,config['pilot_limit']-len(records))
    briefs=json.loads((ROOT/'catalog/pilot/symbols.json').read_text())
    prompts={e['id']:e['visual_prompt_en'].lower() for e in briefs}
    def order(c):
        human=bool(re.search(r'\b(child|children|person|people|hand)\b',prompts.get(c['concept_id'],'')))
        return (not human,c['concept_id'])
    return [c for c in sorted(candidates,key=order) if c['concept_id']+':'+c['sha256'] not in records][:remaining]


def checkpoint(path,state,branch):
    target=path/'suggestions.json'
    temporary=target.with_suffix('.tmp')
    temporary.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(target)
    if branch:
        subprocess.run(['git','-C',str(path),'add','suggestions.json'],check=True)
        if subprocess.run(['git','-C',str(path),'diff','--cached','--quiet']).returncode:
            subprocess.run(['git','-C',str(path),'commit','-m','Checkpoint image-only metadata pilot'],check=True)
            subprocess.run(['git','-C',str(path),'push','origin',f'HEAD:{branch}'],check=True)


def make_analyzer(config):
    # Only called after confirming a nonempty plan on a public Linux runner.
    if os.getenv('BILDSTOD_PUBLIC_STANDARD_RUNNER')!='true' or os.getenv('GITHUB_REPOSITORY')!='wallgrnstudios/bildstod-26-generator':
        raise RuntimeError('Inference is restricted to the public standard runner')
    import torch
    from transformers import AutoProcessor,AutoModelForImageTextToText
    torch.set_num_threads(4)
    processor=AutoProcessor.from_pretrained(config['model'],revision=config['revision'],trust_remote_code=False)
    model=AutoModelForImageTextToText.from_pretrained(config['model'],revision=config['revision'],torch_dtype=torch.float32,attn_implementation='eager',trust_remote_code=False).eval()
    def analyze(image):
        messages=[{'role':'user','content':[{'type':'image'},{'type':'text','text':PROMPT}]}]
        text=processor.apply_chat_template(messages,add_generation_prompt=True,tokenize=False)
        inputs=processor(text=text,images=[image],return_tensors='pt')
        with torch.inference_mode():
            output=model.generate(**inputs,max_new_tokens=256,do_sample=False)
        return processor.batch_decode(output[:,inputs['input_ids'].shape[1]:],skip_special_tokens=True)[0]
    return analyze


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['plan','run'])
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--checkpoint-branch')
    args=parser.parse_args()
    config=json.loads((ROOT/'config/metadata.json').read_text())
    args.state.mkdir(parents=True,exist_ok=True)
    target=args.state/'suggestions.json'
    state=json.loads(target.read_text()) if target.exists() else {'schema_version':1,'records':{}}
    batch=select_batch(load_candidates(),state,config)
    if args.mode=='plan':
        print(json.dumps({'count':len(batch),'pilot_limit':config['pilot_limit']}))
        return
    if not batch:
        print('Pilot cap reached or no new images; no model loaded.')
        return
    analyze=make_analyzer(config)
    started=time.monotonic()
    for c in batch:
        if time.monotonic()-started>config['max_seconds']:
            break
        key=c['concept_id']+':'+c['sha256']
        base={k:c[k] for k in ('concept_id','sha256','source_commit')}
        base.update(model=config['model'],revision=config['revision'],model_version=config['model_version'],status='processing',created_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat())
        # Receipt before inference prevents repeated costly retries after hard termination.
        state['records'][key]=base
        checkpoint(args.state,state,args.checkpoint_branch)
        tick=time.monotonic()
        raw=''
        try:
            data=read_url(c['source_url'])
            if hashlib.sha256(data).hexdigest()!=c['sha256']:
                raise ValueError('Image SHA mismatch')
            image=Image.open(io.BytesIO(data));image.load()
            if image.size!=(512,512):
                raise ValueError('Unexpected image dimensions')
            raw=analyze(image.convert('RGB'))
            people=parse_people(raw)
            state['records'][key]={**base,'status':'suggested','people':people,'duration_seconds':round(time.monotonic()-tick,2)}
        except Exception as error:
            state['records'][key]={**base,'status':'failed','error_type':type(error).__name__,'raw_output':locals().get('raw','')[:2000]}
        checkpoint(args.state,state,args.checkpoint_branch)
        print(c['concept_id'],state['records'][key]['status'],flush=True)
    print(json.dumps({'attempted':len(state['records']),'suggested':sum(r['status']=='suggested' for r in state['records'].values())}))


if __name__=='__main__':
    main()
