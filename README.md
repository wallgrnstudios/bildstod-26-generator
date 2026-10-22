# Bildstöd 26 – public generation engine

This repository contains only the generation engine, atomic symbol contracts, preschool comparison sentences and a generated style reference. The application repository remains private. Source files here are exported explicitly from that project; no private app files or credentials are included.

Only standard Linux runners in this public repository can generate images. No paid inference API is used. Eight fixed workers have independent `generated-flux-worker-0` … `generated-flux-worker-7` branches. Each completed image is committed immediately to its worker branch. These generated candidates, prompts and metadata are PUBLIC. No automatic publication into the private application's approved library occurs.

The scheduled candidate queue is enabled for preschool vocabulary. The active catalog is `catalog/pilot/symbols.json`; complete comparison sentences are separate fixtures, not image meanings. The school vocabulary contains 2,000 editorially selected concepts and phrases. Of these, 804 have enabled atomic generation briefs. The other entries are documented in `catalog/school/concept-resolutions.json` as reused symbols, compositions, unreviewed convention proposals or open questions; none of those are generated. All outputs require human review. Abstract concepts stay as text until their visual convention is reviewed.

Start with Actions → Generate pilot candidates → mode `generate`. Only the configured small calibration set is generated while `calibration_approved` is false. Compare the result with the included reference before unlocking the rest of the queue. Set repository variable `BILDSTOD_NIGHTLY_ENABLED=true` to run every three hours; remove it to stop. Workflows skip private repositories. A run can take up to two hours per worker plus setup time. No fixed images/day is promised until measured.

Metadata suggestions run separately in `metadata-pilot.yml` after generation and every three hours when `BILDSTOD_METADATA_ENABLED=true`. The pilot has a durable lifetime cap of 30 image versions, including failed attempts. A pinned SmolVLM2-500M model analyzes native 512 px images on CPU; image SHA and immutable source commit are checked. Only public illustrations are analyzed. Suggestions are stored on `metadata-suggestions`, never in the private review database. They require human confirmation. Character identity and gender presentation are never inferred.

The model loads once per worker batch. Prompts are encoded upfront; text encoders are then released before image synthesis to reduce RAM usage. The current throughput trial uses native 512 px with a white background and no background removal or upscaling. CPU quality and runtime require verification. FLUX.2 klein uses the included reference as style conditioning. Text weights are removed from disk and memory before loading the image model.

Image triage runs in `quality-triage.yml` after generation and daily. Rule checks (cropping, tiny subject, filled frame, brown cast on white materials, near duplicates, similarity to the style reference), Tesseract OCR and a pinned CLIP ViT-B/32 (MIT, CPU) only order the human review list; they never approve or reject. Results and contact sheets (96/48/24 px, colour/grey, with/without labels, A4 print proofs) are replaced on the `quality-triage` branch.

Manual benchmarking workflows compare standard x64, standard ARM64, and a compact CPU implementation. Failed 1024 CPU trials do not establish a daily throughput promise.

Model license: https://huggingface.co/black-forest-labs/FLUX.2-klein-4B . The current profile retains a white background without background removal. No project distribution license is implied. Outputs are review candidates with no assigned distribution license.
