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
    from .generation import ROOT,load_config,load_briefs
    parser=argparse.ArgumentParser()
    parser.add_argument('--plan',type=Path)
    args=parser.parse_args()
    config=load_config(ROOT/'config/generation.json')
    entries=[e for e in load_briefs(ROOT/config['catalog_path']) if e.get('generation_enabled',True)]
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
    print(json.dumps(validate_prompt_budget(entries,config,tokenizer)))

if __name__=='__main__':main()
