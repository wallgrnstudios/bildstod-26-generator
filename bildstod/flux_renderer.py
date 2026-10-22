"""Staged FLUX.2 klein execution: text weights and image weights never coexist."""
import gc
import os
import tempfile
from pathlib import Path
from PIL import Image
from .prompt_budget import validate_prompt_budget

ROOT = Path(__file__).resolve().parents[1]


def release_memory():
    gc.collect()
    try:
        import ctypes
        ctypes.CDLL(None).malloc_trim(0)
    except (AttributeError, OSError):
        pass


class FluxRenderer:
    def __init__(self, config, entries):
        import torch
        from diffusers import Flux2KleinPipeline
        from transformers import Qwen3ForCausalLM, Qwen2TokenizerFast
        from .generation import prompt_for
        self.torch = torch
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        self.embeddings = {}
        # Each component is ~8 GB. Delete encoder cache before fetching image weights,
        # so the public runner does not need 16+ GB of disk or both models in RAM.
        with tempfile.TemporaryDirectory(prefix='bildstod-encoder-', dir=os.environ.get('RUNNER_TEMP')) as cache:
            tokenizer = Qwen2TokenizerFast.from_pretrained(config['model'], subfolder='tokenizer', revision=config['revision'], cache_dir=cache)
            validate_prompt_budget(entries,config,tokenizer)
            encoder = Qwen3ForCausalLM.from_pretrained(config['model'], subfolder='text_encoder', revision=config['revision'], cache_dir=cache, torch_dtype=torch.bfloat16, use_safetensors=True, low_cpu_mem_usage=True)
            encoder.config.use_cache = False
            text_pipeline = Flux2KleinPipeline(scheduler=None, vae=None, text_encoder=encoder, tokenizer=tokenizer, transformer=None, is_distilled=True)
            for entry in entries:
                prompt = prompt_for(entry, config)
                with torch.inference_mode():
                    embeddings, ids = text_pipeline.encode_prompt(prompt=prompt, device='cpu', max_sequence_length=256)
                    self.embeddings[entry['id']] = embeddings.detach().clone()
                    del embeddings, ids
            del text_pipeline, encoder, tokenizer
            release_memory()
        self.cache = tempfile.TemporaryDirectory(prefix='bildstod-image-model-', dir=os.environ.get('RUNNER_TEMP'))
        self.pipeline = Flux2KleinPipeline.from_pretrained(config['model'], revision=config['revision'], cache_dir=self.cache.name, text_encoder=None, tokenizer=None, torch_dtype=torch.bfloat16, use_safetensors=True, low_cpu_mem_usage=True).to('cpu')
        self.pipeline.vae.enable_tiling()
        # A 512px reference is sufficient for style; output itself is native 1024px.
        with Image.open(ROOT / config['reference_asset']) as source:
            rgba = source.convert('RGBA')
            canvas = Image.new('RGBA',rgba.size,'white')
            canvas.alpha_composite(rgba)
            reference_size = config.get('reference_size',512)
            self.reference = canvas.convert('RGB').resize((reference_size,reference_size),Image.Resampling.LANCZOS)

    def __call__(self, entry, config, seed):
        with self.torch.inference_mode():
            reference = None if entry.get('reference_conditioning') is False else self.reference
            result = self.pipeline(image=reference, prompt_embeds=self.embeddings[entry['id']],
                width=config['width'],height=config['height'],num_inference_steps=config['steps'],
                guidance_scale=1.0,max_sequence_length=256,
                generator=self.torch.Generator(device='cpu').manual_seed(seed))
        return result.images[0]

    def close(self):
        self.embeddings.clear()
        self.pipeline = None
        release_memory()
        self.cache.cleanup()
