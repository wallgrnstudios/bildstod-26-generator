"""One public-runner benchmark of the same model with compact CPU weights."""
import hashlib
import time
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from bildstod.generation import (ROOT, load_config, load_briefs, plan, run_batch,
    review_sheet, checkpoint_git, check_compute_permission)

FILES = {
    'engine.zip': ('https://github.com/leejet/stable-diffusion.cpp/releases/download/master-975-95b3090/sd-master-95b3090-bin-Linux-Ubuntu-24.04-x86_64.zip', '23757b2d46edd68ec59ad252e6e3d6c1854ab01d6be5d47a06e0bc751c2eee2a'),
    'diffusion.gguf': ('https://huggingface.co/leejet/FLUX.2-klein-4B-GGUF/resolve/3b1f5a9dc3abb32238b053aeb3d823c30afdacbd/flux-2-klein-4b-Q4_0.gguf', 'd1023499ef3f2f82ff7c50e6778495195c1b6cc34835741778868428111f9ff4'),
    'text.gguf': ('https://huggingface.co/unsloth/Qwen3-4B-GGUF/resolve/22c9fc8a8c7700b76a1789366280a6a5a1ad1120/Qwen3-4B-Q4_K_M.gguf', 'f6f851777709861056efcdad3af01da38b31223a3ba26e61a4f8bf3a2195813a'),
    'vae.safetensors': ('https://huggingface.co/Comfy-Org/flux2-klein-4B/resolve/5f526678002e43af5551dadb73ce2e8c91b43afe/split_files/vae/flux2-vae.safetensors', '868fe7b343cc8f3a19dbcfcafbc3d5f888802be3f89bd81b65b3621a066ce8f3'),
}


def download(target, url, expected):
    print('Downloading ' + target.name, flush=True)
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={'User-Agent':'Bildstod26-benchmark'})
    with urllib.request.urlopen(request, timeout=90) as source, target.open('wb') as destination:
        while chunk := source.read(1024*1024):
            digest.update(chunk)
            destination.write(chunk)
    if digest.hexdigest() != expected:
        raise ValueError('Download checksum mismatch: ' + target.name)


def main():
    check_compute_permission(False)
    config = load_config(ROOT/'config/generation.json')
    config.update(style_version='storybook-transparent-0.9-gguf', calibration_ids=['FSK_03_04'],
        worker_overrides={}, cpu_dtype='q4_0', implementation='stable-diffusion.cpp-95b3090',
        quantized_files={key: value[1] for key,value in FILES.items()})
    output = ROOT/'.state/data'/config['style_version']
    entries = load_briefs(ROOT/'catalog/pilot/concepts.json')
    batch = plan(entries, config, output, 1)
    output.mkdir(parents=True,exist_ok=True)
    benchmark_started=time.monotonic()
    with tempfile.TemporaryDirectory(dir=os.environ.get('RUNNER_TEMP')) as temporary:
        cache = Path(temporary)
        for name,(url,checksum) in FILES.items():
            download(cache/name,url,checksum)
        download_seconds=time.monotonic()-benchmark_started
        with zipfile.ZipFile(cache/'engine.zip') as archive:
            for name in archive.namelist():
                if not (cache/name).resolve().is_relative_to(cache):
                    raise ValueError('Unsafe release archive')
            archive.extractall(cache)
        binary = next(cache.rglob('sd-cli'))
        binary.chmod(0o755)
        env = dict(os.environ)
        env['LD_LIBRARY_PATH'] = ':'.join(sorted({str(x.parent) for x in cache.rglob('*.so*')}))
        with Image.open(ROOT/config['reference_asset']) as source:
            rgba=source.convert('RGBA'); canvas=Image.new('RGBA',rgba.size,'white');canvas.alpha_composite(rgba)
            canvas.convert('RGB').resize((512,512),Image.Resampling.LANCZOS).save(cache/'reference.png')
        def render(entry, cfg, seed):
            from bildstod.generation import prompt_for
            command=[str(binary),'--diffusion-model',str(cache/'diffusion.gguf'),
                '--llm',str(cache/'text.gguf'),'--vae',str(cache/'vae.safetensors'),
                '-r',str(cache/'reference.png'),'-p',prompt_for(entry,cfg),
                '-o',str(cache/'candidate.png'),'-W','1024','-H','1024','--steps','4',
                '--cfg-scale','1','--sampling-method','euler','--rng','cpu','--seed',str(seed),
                '--threads','4','--flash-attn','off,diffusion=on','--offload-to-cpu']
            with (output/'engine.log').open('w') as log:
                subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=3600)
            with Image.open(cache/'candidate.png') as image:
                return image.convert('RGB')
        try:
            run_batch(entries,config,output,batch,render=render,
                checkpoint=lambda directory:checkpoint_git(directory,'generated-flux-worker-7'))
        finally:
            (output/'benchmark.json').write_text(json.dumps({'download_seconds':round(download_seconds,2),'total_seconds':round(time.monotonic()-benchmark_started,2),'implementation':config['implementation']},indent=2))
            review_sheet(output)
            checkpoint_git(output,'generated-flux-worker-7')


if __name__ == '__main__':
    main()
