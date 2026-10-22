"""Validate complete FLUX prompts with its pinned tokenizer, without model weights."""
import argparse
import json
from pathlib import Path

MAX_PROMPT_TOKENS=220


def validate_prompt_budget(entries,config,tokenizer):
    from .generation import prompt_for
    violations=[]
    maximum=0
    for entry in entries:
        count=len(tokenizer.encode(prompt_for(entry,config)))
        maximum=max(maximum,count)
        if count>MAX_PROMPT_TOKENS:
            violations.append(f"{entry['id']}: {count}/{MAX_PROMPT_TOKENS} tokens")
    if violations:
        raise ValueError('FLUX prompt budget exceeded: '+ '; '.join(violations))
    return {'checked':len(entries),'max_tokens':maximum,'limit':MAX_PROMPT_TOKENS}


def main():
    from .generation import ROOT,load_config,load_briefs,prompt_for
    parser=argparse.ArgumentParser()
    parser.add_argument('--plan',type=Path)
    parser.add_argument('--catalog',type=Path)
    parser.add_argument('--checkpoint-branch')
    args=parser.parse_args()
    config=load_config(ROOT/'config/generation.json')
    entries=[e for e in load_briefs(args.catalog or ROOT/config['catalog_path']) if e.get('generation_enabled',True)]
    if args.plan:
        ids={r['id'] for r in json.loads(args.plan.read_text())['batch']}
        by_id={e['id']:e for e in entries}
        if ids-set(by_id):
            raise ValueError('Plan contains unknown or disabled concepts')
        entries=[e for e in entries if e['id'] in ids]
    if not entries:
        print(json.dumps({'checked':0,'limit':MAX_PROMPT_TOKENS}))
        return
    from transformers import Qwen2TokenizerFast
    tokenizer=Qwen2TokenizerFast.from_pretrained(config['model'],subfolder='tokenizer',revision=config['revision'],trust_remote_code=False)
    try:
        result=validate_prompt_budget(entries,config,tokenizer)
    except ValueError:
        # Durable per-request failure lets the admin revise an invalid prompt, without a model download.
        if args.plan and args.checkpoint_branch:
            from .generation import identity,review_sheet,checkpoint_git
            from .pipeline import atomic_json
            output=args.plan.parent
            for e in entries:
                if e.get('regeneration_request_id') and len(tokenizer.encode(prompt_for(e,config)))>MAX_PROMPT_TOKENS:
                    target=output/(e['id']+'.json')
                    if target.exists():
                        old=json.loads(target.read_text())
                        if old.get('status')=='pending_review': atomic_json(target.with_suffix('.previous.json'),old)
                    atomic_json(target,{'concept_id':e['id'],'status':'failed','error_type':'PromptBudgetExceeded','fingerprint':identity(e,config),'regeneration_request_id':e['regeneration_request_id'],'regeneration_source_sha256':e['regeneration_source_sha256']})
            review_sheet(output);checkpoint_git(output,args.checkpoint_branch)
        raise
    print(json.dumps(result))

if __name__=='__main__':main()
