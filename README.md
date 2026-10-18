# Bildstöd 26 – public generation engine

This repository contains only the generation engine, generic preschool scene briefs and a generated style reference. The application repository remains private. Source files here are exported explicitly from that project; no private app files or credentials are included.

Only standard Linux runners in this public repository can generate images. No paid inference API is used. Four fixed workers have independent `generated-worker-0` … `generated-worker-3` branches. Each completed image is committed immediately to its worker branch. These generated candidates, prompts and metadata are PUBLIC. No automatic publication into the private application's approved library occurs.

Start with Actions → Generate pilot candidates → mode `generate`. Only a single calibration image is generated while `calibration_approved` is false. Compare the result with the included reference before unlocking the rest of the queue. Set repository variable `BILDSTOD_NIGHTLY_ENABLED=true` to run every six hours; remove it to stop. Workflows skip private repositories. A run can take up to two hours per worker plus setup time. No fixed images/day is promised until measured.

The model loads once per worker batch. Prompts are encoded upfront; text encoders are then released before image synthesis to reduce RAM usage. The output is native 1024 px with subsequent transparent-background removal, not upscaled. CPU quality and runtime require verification. The style reference is not model conditioning.

Model license: https://huggingface.co/stabilityai/sdxl-turbo/blob/main/LICENSE.TXT . Background removal: https://github.com/danielgatis/rembg . No project distribution license is implied. Outputs are review candidates with no assigned distribution license.
