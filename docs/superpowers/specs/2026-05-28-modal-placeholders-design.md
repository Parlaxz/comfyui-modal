# Modal Local Placeholder Restoration Design

## Goal

Restore the local placeholder flow so models stored only in Modal Volume still appear in local ComfyUI dropdowns without downloading the real model file to the local machine.

## Root cause

- The repo still has the checkpoint-family folder mapping (`checkpoints` + `diffusion_models` + `unet`) and preserves each model's real `file.folder`.
- The placeholder system was previously implemented, then removed in later rewrites:
  - backend inject route removed from `__init__.py`
  - frontend inject controls and auto-inject flow removed from `web/modal-settings.js`
- README text describing placeholder behavior was left behind, so docs now describe behavior the code no longer provides.

## Approved scope

- Keep the existing grouped sidebar model display.
- Reuse the existing real-folder behavior (`file.folder ?? folder`) for checkpoint-family models.
- Restore and harden local placeholder creation.
- Use the exact remote filename locally. No `modal-` prefix.
- Support every folder already exposed in the download dropdown, plus repo-supported `unet`.

## Design

### Backend helper

Add a small pure-Python helper module for local placeholder operations so it can be tested without importing the full ComfyUI extension module.

Responsibilities:

- define the allowed local model folders
- validate `folder`
- validate `filename`
- resolve `<ComfyUI root>/models/<folder>/<filename>` safely
- create a zero-byte file only when missing
- never overwrite an existing non-empty file
- report file metadata

Expected metadata:

- `folder`
- `filename`
- `local_path`
- `created`
- `existed`
- `size`
- `is_placeholder`
- `is_real_file`

### Folder support

Allowed folders will be the union of current repo-supported model folders:

- `checkpoints`
- `diffusion_models`
- `unet`
- `loras`
- `vae`
- `controlnet`
- `upscale_models`
- `embeddings`
- `clip`
- `text_encoders`
- `model_patches`
- `clip_vision`
- `style_models`
- `vae_approx`
- `hypernetworks`
- `gligen`
- `photomaker`
- `latent_upscale_models`
- `audio_encoders`
- `frame_interpolation`

### Route integration

Use the helper in four places:

1. `POST /comfymodal/model/install`
2. `POST /comfymodal/models/batch-install`
3. `POST /comfymodal/models/inject`
4. `POST /comfymodal/models/inject-all`

Behavior details:

- validate folder/filename before download or placeholder creation
- after successful remote download, create the local placeholder with the same folder and filename
- return placeholder metadata in route responses
- if remote download succeeds but placeholder creation fails unexpectedly, return a success payload with placeholder error details so the user understands the remote model exists but local injection needs retry

### Model listing

Keep the current grouped display from the backend and frontend.

For each listed model, enrich the response with local file status derived from the helper using the real folder (`file.folder`) when present. This lets the UI show:

- placeholder already exists
- real local file already exists
- no local file exists yet

### Frontend

Restore clear placeholder actions in the sidebar:

- per-model action to create a local placeholder manually
- visible “create all missing placeholders” action
- clear download success message explaining that the Modal model is stored remotely and a local placeholder was created
- help text warning that placeholders only work when Modal execution is enabled

The frontend will keep using the actual storage folder (`file.folder ?? folder`) so checkpoint-family entries still inject/delete correctly.

### Safety rules

Reject these inputs:

- `../anything.safetensors`
- `..\\anything.safetensors`
- `C:\\Users\\...`
- `/etc/passwd`
- filenames containing `/` or `\\`
- folders not in the allowed folder set

Only create files under `ComfyUI/models/<allowed-folder>/`.

### Testing

Add pure helper tests covering:

1. exact-filename zero-byte creation for:
   - `text_encoders/qwen_3_8b_fp8mixed.safetensors`
   - `diffusion_models/flux-2-klein-9b-fp8.safetensors`
   - `vae/flux2-vae.safetensors`
2. existing zero-byte placeholder stays untouched
3. existing non-empty local file is preserved
4. path traversal / absolute-path rejection
5. batch placeholder creation over multiple models

## Non-goals

- redesigning the full model browser
- workflow filename rewriting
- changing remote Modal storage layout
- changing local-mode behavior beyond warning text
