# Bildstöd 26 – public generation engine

This repository contains only the generation engine, generic preschool scene briefs and a generated style reference. The application repository remains private. Source files here are exported explicitly from that project; no private app files or credentials are included.

Only standard Linux runners in this public repository can generate images. No paid inference API is used. Eight fixed workers have independent `generated-flux-worker-0` … `generated-flux-worker-7` branches. Each completed image is committed immediately to its worker branch. These generated candidates, prompts and metadata are PUBLIC. No automatic publication into the private application's approved library occurs.

Start with Actions → Generate pilot candidates → mode `generate`. Only the configured small calibration set is generated while `calibration_approved` is false. Compare the result with the included reference before unlocking the rest of the queue. Set repository variable `BILDSTOD_NIGHTLY_ENABLED=true` to run every three hours; remove it to stop. Workflows skip private repositories. A run can take up to two hours per worker plus setup time. No fixed images/day is promised until measured.

The model loads once per worker batch. Prompts are encoded upfront; text encoders are then released before image synthesis to reduce RAM usage. The current throughput trial uses native 512 px with a white background and no background removal or upscaling. CPU quality and runtime require verification. FLUX.2 klein uses the included reference as style conditioning. Text weights are removed from disk and memory before loading the image model.

Manual benchmarking workflows compare standard x64, standard ARM64, and a compact CPU implementation. Failed 1024 CPU trials do not establish a daily throughput promise.

Model license: https://huggingface.co/black-forest-labs/FLUX.2-klein-4B . The current profile removes only near-white background connected to image borders, using Pillow; light foreground details remain. No project distribution license is implied. Outputs are review candidates with no assigned distribution license.
