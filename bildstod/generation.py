"""Free-compute pilot generation: no inference API, no automatic publication."""
import argparse
import gc
import hashlib
import html
import json
import os
import platform
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw, PngImagePlugin
from .pipeline import atomic_json

ROOT = Path(__file__).resolve().parents[1]


def load_config(path):
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    if config['model'] not in ('stabilityai/sdxl-turbo', 'Lykon/dreamshaper-xl-lightning', 'black-forest-labs/FLUX.2-klein-4B') or not re.fullmatch(r'[0-9a-f]{40}', config['revision']):
        raise ValueError('Only the pinned pilot model is supported')
    if not re.fullmatch(r'[a-z0-9.-]+', config['style_version']):
        raise ValueError('Invalid style version')
    is_flux = config.get('backend') == 'flux2-klein'
    if not is_flux and (config['weight_variant'] != 'fp16' or config['cpu_dtype'] != 'float32'):
        raise ValueError('Only compact safetensor weights and CPU float32 are configured')
    if config['background_model'] not in ('u2netp', 'isnet-general-use', 'white-connected') or config['width'] != 1024 or config['height'] != 1024:
        raise ValueError('Pilot requires 1024 px and a configured foreground model')
    if not 1 <= config['steps'] <= 4 or not 1 <= config['batch_limit'] <= config['max_batch_limit'] <= 100:
        raise ValueError('Invalid batch or step limit')
    reference = ROOT / config['reference_asset']
    if hashlib.sha256(reference.read_bytes()).hexdigest() != config['reference_sha256']:
        raise ValueError('Style reference has changed. Review and version the generation profile first.')
    return config


def load_briefs(path):
    entries = json.loads(Path(path).read_text(encoding='utf-8'))
    seen = set()
    for entry in entries:
        if not re.fullmatch(r'FSK_[0-9]{2}_[0-9]{2}', entry['id']) or entry['id'] in seen:
            raise ValueError('Invalid or duplicate concept ID')
        if not isinstance(entry.get('visual_prompt_en'), str) or not entry['visual_prompt_en'].strip():
            raise ValueError(f"Missing scene brief: {entry['id']}")
        seen.add(entry['id'])
    return entries


def prompt_for(entry, config):
    # Short prompts, action first: long style preambles can truncate the actual action.
    if config.get('backend') == 'flux2-klein':
        return ('Use the reference image only as an illustration style guide. Create a completely new preschool action scene: '
                + entry['visual_prompt_en'] + ' ' + config['style_prompt']
                + ' Replace the reference scene entirely; do not include its coat, hook or pose unless this new action requires them.')
    return 'Isolated watercolor illustration on pure white. ' + entry['visual_prompt_en'] + ' ' + config['style_prompt']


def identity(entry, config):
    parameters = {key: config[key] for key in ('model', 'revision', 'style_version', 'style_prompt', 'width', 'height', 'steps', 'guidance_scale', 'background_model', 'seed_base', 'weight_variant', 'cpu_dtype', 'reference_sha256', 'negative_prompt', 'reference_conditioning')}
    payload = {'entry': entry['visual_prompt_en'], 'entry_negative': entry.get('negative_prompt_en', ''), 'label': entry['text_sv'], 'config': parameters}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def seed_for(entry, config):
    return (config['seed_base'] + int(hashlib.sha256(entry['id'].encode()).hexdigest()[:8], 16)) % (2**31)


def plan(entries, config, output, limit, retry_failed=False, shard_index=0, shard_count=1):
    if not 1 <= limit <= config['max_batch_limit']:
        raise ValueError('Batch size exceeds the configured maximum')
    if not 0 <= shard_index < shard_count <= 8:
        raise ValueError('Invalid worker shard')
    candidates = []
    ordered = sorted(entries, key=lambda x: (x.get('generation_priority', 2), x['id']))
    for entry in ordered:
        worker = 0 if entry['id'] == 'FSK_01_04' else int(hashlib.sha256(entry['id'].encode()).hexdigest()[:8], 16) % shard_count
        worker = config.get('worker_overrides', {}).get(entry['id'], worker)
        if worker != shard_index:
            continue
        if not config.get('calibration_approved', False) and entry['id'] not in config.get('calibration_ids', ['FSK_01_04']):
            continue
        target = output / (entry['id'] + '.png')
        sidecar = target.with_suffix('.json')
        if sidecar.exists():
            metadata = json.loads(sidecar.read_text(encoding='utf-8'))
            if metadata.get('fingerprint') == identity(entry, config):
                if metadata.get('status') == 'failed' and not retry_failed:
                    continue
                if metadata.get('status') == 'pending_review':
                    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != metadata['sha256']:
                        raise ValueError(f"Damaged output, restore backup first: {entry['id']}")
                    continue
        candidates.append({'id': entry['id'], 'label': entry['text_sv'], 'prompt': prompt_for(entry, config), 'seed': seed_for(entry, config)})
    return candidates[:limit]


def verify_transparency(image):
    if image.mode != 'RGBA':
        raise ValueError('Background removal did not produce RGBA')
    alpha = image.getchannel('A')
    histogram = alpha.histogram()
    pixels = image.width * image.height
    transparent = sum(histogram[:8]) / pixels
    opaque = sum(histogram[248:]) / pixels
    if transparent < 0.05 or opaque < 0.05:
        raise ValueError('Empty or opaque background-removal result')
    # This verifies technical transparency, not semantic segmentation or hair quality.
    return {'transparent_fraction': round(transparent, 4), 'opaque_fraction': round(opaque, 4)}


class CpuRenderer:
    """Load weights once, encode the batch, then free text encoders before diffusion."""
    def __init__(self, config, entries):
        import torch
        from diffusers import AutoPipelineForText2Image, DPMSolverMultistepScheduler
        self.torch = torch
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        self.pipeline = AutoPipelineForText2Image.from_pretrained(
            config['model'], revision=config['revision'], torch_dtype=torch.float32,
            variant=config['weight_variant'], use_safetensors=True, low_cpu_mem_usage=True,
        ).to('cpu')
        if config['model'] == 'Lykon/dreamshaper-xl-lightning':
            self.pipeline.scheduler = DPMSolverMultistepScheduler.from_config(self.pipeline.scheduler.config)
        self.pipeline.enable_vae_slicing()
        self.pipeline.enable_vae_tiling()
        self.embeddings = {}
        for entry in entries:
            prompt = prompt_for(entry, config)
            for tokenizer in (self.pipeline.tokenizer, self.pipeline.tokenizer_2):
                if tokenizer is not None and len(tokenizer.encode(prompt)) > tokenizer.model_max_length:
                    raise ValueError(f"Prompt is too long: {entry['id']}")
            with torch.inference_mode():
                encoded = self.pipeline.encode_prompt(prompt=prompt, negative_prompt=', '.join(filter(None, [config.get('negative_prompt'), entry.get('negative_prompt_en')])), device='cpu', do_classifier_free_guidance=config['guidance_scale'] > 1)
                self.embeddings[entry['id']] = encoded
        self.pipeline.text_encoder = None
        self.pipeline.text_encoder_2 = None
        gc.collect()
        # Return freed encoder memory to Linux, if libc supports it.
        try:
            import ctypes
            ctypes.CDLL(None).malloc_trim(0)
        except (AttributeError, OSError):
            pass

    def __call__(self, entry, config, seed):
        prompt_embeds, negative, pooled, negative_pooled = self.embeddings[entry['id']]
        with self.torch.inference_mode():
            result = self.pipeline(prompt_embeds=prompt_embeds, pooled_prompt_embeds=pooled,
                negative_prompt_embeds=negative, negative_pooled_prompt_embeds=negative_pooled,
                width=config['width'], height=config['height'], num_inference_steps=config['steps'],
                guidance_scale=config['guidance_scale'],
                generator=self.torch.Generator(device='cpu').manual_seed(seed))
        if any(getattr(result, 'nsfw_content_detected', None) or []):
            raise ValueError('Generation rejected by model safety checker')
        return result.images[0]

    def close(self):
        self.embeddings.clear()
        self.pipeline = None
        gc.collect()


class BackgroundRemover:
    def __init__(self, config):
        self.config = config
        self.session = None

    def __call__(self, image, config):
        if config['background_model'] == 'white-connected':
            # Only near-white pixels connected to the image border are background.
            # Keep pale skin, white clothing and highlights enclosed by drawn outlines.
            rgb = image.convert('RGB')
            mask = Image.new('L', rgb.size)
            mask.putdata([255 if min(pixel) >= 245 and max(pixel)-min(pixel) <= 8 else 0 for pixel in rgb.getdata()])
            width, height = rgb.size
            boundary = [(x,y) for x in range(width) for y in (0,height-1)]
            boundary += [(x,y) for y in range(height) for x in (0,width-1)]
            for point in boundary:
                if mask.getpixel(point) == 255:
                    ImageDraw.floodfill(mask, point, 128)
            result = rgb.convert('RGBA')
            result.putalpha(mask.point([0 if value == 128 else 255 for value in range(256)]))
            return result
        from rembg import new_session, remove
        if self.session is None:
            self.session = new_session(config['background_model'], providers=['CPUExecutionProvider'])
        return remove(image, session=self.session).convert('RGBA')

    def close(self):
        self.session = None
        gc.collect()


def checkpoint_git(output, branch):
    """Push image receipts to an isolated worker branch using the runner's own token."""
    root = output.parent.parent
    if not re.fullmatch(r'generated(?:-flux)?-worker-[0-7]', branch) or not (root / '.git').exists():
        raise ValueError('Checkpoint requires the isolated worker state repository')
    subprocess.run(['git', '-C', str(root), 'add', 'data'], check=True)
    changed = subprocess.run(['git', '-C', str(root), 'diff', '--cached', '--quiet'])
    if changed.returncode == 1:
        subprocess.run(['git', '-C', str(root), 'commit', '-m', 'Save generated candidate and queue receipt'], check=True)
        subprocess.run(['git', '-C', str(root), 'push', 'origin', f'HEAD:{branch}'], check=True)
    elif changed.returncode != 0:
        raise RuntimeError('Unable to inspect checkpoint changes')


def run_batch(entries, config, output, batch, render=None, remove=None, checkpoint=None, max_seconds=None):
    by_id = {x['id']: x for x in entries}
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / config['reference_asset'], output / 'reference.png')
    if not batch:
        return
    started = time.monotonic()
    owned_render = render is None
    owned_remove = remove is None
    if render is None:
        if config.get('backend') == 'flux2-klein':
            from .flux_renderer import FluxRenderer
            render = FluxRenderer(config, [by_id[x['id']] for x in batch])
        else:
            render = CpuRenderer(config, [by_id[x['id']] for x in batch])
    remove = remove or BackgroundRemover(config)
    initialization_seconds = time.monotonic() - started
    durations = []
    for item in batch:
        if max_seconds and time.monotonic() - started + (max(durations) if durations else 0) + 120 >= max_seconds:
            break
        item_started = time.monotonic()
        entry = by_id[item['id']]
        target = output / (entry['id'] + '.png')
        metadata = {'concept_id': entry['id'], 'label_sv': entry['text_sv'],
                    'fingerprint': identity(entry, config), 'prompt': item['prompt'], 'seed': item['seed'],
                    'negative_prompt': '' if config.get('backend') == 'flux2-klein' else ', '.join(filter(None, [config.get('negative_prompt'), entry.get('negative_prompt_en')])),
                    'model': config['model'], 'revision': config['revision'],
                    'style_version': config['style_version'], 'background_model': config['background_model'],
                    'created_at': datetime.now(timezone.utc).isoformat(), 'license': None,
                    'model_license_url': config['model_license_url'], 'style_approved': False,
                    'reference_asset': config['reference_asset'], 'reference_sha256': config['reference_sha256'],
                    'reference_conditioning': config.get('reference_conditioning', False),
                    'implementation': config.get('implementation', 'diffusers'),
                    'quantized_files': config.get('quantized_files'),
                    'width': config['width'], 'height': config['height'], 'steps': config['steps'],
                    'guidance_scale': config['guidance_scale'], 'cpu_dtype': config['cpu_dtype']}
        try:
            image = render(entry, config, item['seed'])
            render_seconds = time.monotonic() - item_started
            if image.size != (config['width'], config['height']):
                raise ValueError('Wrong native output resolution')
            raw = output / 'raw'; raw.mkdir(exist_ok=True)
            image.save(raw / target.name, format='PNG')
            removal_started = time.monotonic()
            cutout = remove(image, config)
            removal_seconds = time.monotonic() - removal_started
            metrics = verify_transparency(cutout)
            if cutout.size != image.size:
                raise ValueError('Background removal changed image size')
            metadata.update(status='pending_review', transparency=metrics, render_seconds=round(render_seconds, 3), background_seconds=round(removal_seconds, 3), elapsed_seconds=round(time.monotonic() - item_started, 3))
            info = PngImagePlugin.PngInfo()
            info.add_itxt('bildstod', json.dumps(metadata, ensure_ascii=False))
            temporary = target.with_suffix('.tmp')
            cutout.save(temporary, format='PNG', pnginfo=info)
            temporary.replace(target)
            metadata['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
            atomic_json(target.with_suffix('.json'), metadata)
            durations.append(metadata['elapsed_seconds'])
        except Exception as error:
            # A failed model/download/mask stops the run. No hidden retry or paid fallback.
            metadata.update(status='failed', error_type=type(error).__name__)
            atomic_json(target.with_suffix('.json'), metadata)
            if checkpoint:
                checkpoint(output)
            if owned_render:
                render.close()
            if owned_remove:
                remove.close()
            raise
        if checkpoint:
            review_sheet(output)
            checkpoint(output)
    if owned_render:
        render.close()
    if owned_remove:
        remove.close()
    atomic_json(output / 'metrics.json', {'completed_this_run': len(durations), 'initialization_seconds': round(initialization_seconds, 2), 'elapsed_seconds': round(time.monotonic() - started, 2), 'seconds_per_candidate': round(sum(durations)/len(durations), 2) if durations else None})


def review_sheet(output):
    cards = []
    candidates = []
    for sidecar in sorted(output.glob('FSK_*.json')):
        metadata = json.loads(sidecar.read_text(encoding='utf-8'))
        if metadata.get('status') == 'pending_review':
            candidates.append(metadata)
            identifier = metadata['concept_id']
            label = html.escape(metadata['label_sv'])
            cards.append(f'<figure><img src="{identifier}.png" alt="{label}"><figcaption>{label}</figcaption><small>Utkast · granskning krävs</small><details><summary>Före friläggning</summary><img src="raw/{identifier}.png" alt="Motivet före bakgrundsborttagning"></details></figure>')
    atomic_json(output / 'candidates.json', {'style_version': output.name, 'candidates': candidates})
    # Generated report is local and contains only pipeline-owned IDs and escaped labels.
    (output / 'review.html').write_text('<!doctype html><html lang="sv"><meta charset="utf-8"><title>Bildkandidater</title><style>body{font:16px system-ui;margin:32px;color:#344453;background:white}.cards{display:flex;flex-wrap:wrap;gap:24px}figure{margin:0;width:240px;border:1px solid #ddd;padding:12px}img{width:100%;height:auto}small{color:#666}</style><h1>Bildkandidater</h1><figure><img src="reference.png" alt="Godkänd stilreferens"><figcaption>Stilreferens · se kandidatens metadata för om modellen använder referensbilden som indata.</figcaption></figure><p>Kontrollera handling, händer, borttagning av bakgrund och stil mot referensbilden. Ingen kandidat är publicerad.</p><div class="cards">' + ''.join(cards) + '</div></html>', encoding='utf-8')


def check_compute_permission(allow_local):
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        if os.environ.get('BILDSTOD_PUBLIC_STANDARD_RUNNER') != 'true':
            raise ValueError('Generation requires the guarded public-repository workflow')
    elif not allow_local:
        raise ValueError('Local model execution is off. Use GitHub workflow or explicitly pass --allow-local-compute on a chosen machine.')
    if platform.system() != 'Linux':
        raise ValueError('This CPU configuration is intended for a separate Linux runner, not this Mac')
    memory_kib = int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemTotal:')))
    if memory_kib < 14 * 1024 * 1024:
        raise ValueError('At least 14 GiB RAM required; do not run on the 8 GB Mac')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['plan', 'run'])
    parser.add_argument('--config', default='config/generation.json')
    parser.add_argument('--catalog', default='catalog/pilot/concepts.json')
    parser.add_argument('--output', default='output/generation')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--retry-failed', action='store_true')
    parser.add_argument('--shard-index', type=int, default=0)
    parser.add_argument('--shard-count', type=int, default=1)
    parser.add_argument('--max-seconds', type=int, default=7200)
    parser.add_argument('--checkpoint-branch')
    parser.add_argument('--allow-local-compute', action='store_true')
    args = parser.parse_args()
    config = load_config(args.config)
    entries = load_briefs(args.catalog)
    output = Path(args.output) / config['style_version']
    if args.command == 'run' and output.exists() and sum(p.stat().st_size for p in output.rglob('*') if p.is_file()) > 96 * 1024 * 1024:
        raise ValueError('Candidate archive exceeds 96 MiB. Download and archive it before continuing.')
    batch = plan(entries, config, output, args.limit if args.limit is not None else config['batch_limit'], args.retry_failed, args.shard_index, args.shard_count)
    output.mkdir(parents=True, exist_ok=True)
    atomic_json(output / 'plan.json', {'model': config['model'], 'revision': config['revision'], 'style_calibration_required': not config.get('calibration_approved', False), 'batch': batch})
    print(json.dumps({'pending_this_run': len(batch), 'ids': [x['id'] for x in batch], 'mode': args.command}, ensure_ascii=False))
    if args.command == 'run' and batch:
        try:
            check_compute_permission(args.allow_local_compute)
        except ValueError as error:
            parser.error(str(error))
        try:
            run_batch(entries, config, output, batch, max_seconds=args.max_seconds, checkpoint=(lambda directory: checkpoint_git(directory, args.checkpoint_branch)) if args.checkpoint_branch else None)
        finally:
            review_sheet(output)
            if args.checkpoint_branch:
                checkpoint_git(output, args.checkpoint_branch)


if __name__ == '__main__':
    main()
