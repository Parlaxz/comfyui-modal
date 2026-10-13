"""Studio SAM3 masks for inpaint (local ComfyUI path).

Native ComfyUI backend: the INT8 SAM 3.1 Multiplex checkpoint
(models/unet/sam3.1_multiplex_*convrot*.safetensors) loads through the
stock UNetLoader machinery, and segmentation runs through upstream
comfy_extras.nodes_sam3.SAM3_Detect — no sam3.pt pickle, no vendored
sam3 package, no TorchScript workarounds. Memory is ComfyUI-managed,
so there is no manual model parking or device relocation here.

Provides:
- StudioSAM3TextMask node: IMAGE + CLIP + text -> MASK (combined)
- StudioSAM3PointMask node: IMAGE + MODEL + clicks -> MASK
- HTTP routes for the Studio paint editor preview path:
    POST /comfymodal/studio/sam3/text
    POST /comfymodal/studio/sam3/points
  Both accept {image_b64} (exact canvas pixels) with an optional
  legacy {filename, subfolder, type} fallback.
"""

import base64
import io
import json
import os
import threading

import numpy as np
import torch

_LOCK = threading.Lock()
_INFER_LOCK = threading.Lock()
_STATE = {
    "model": None,  # native ModelPatcher (SAM31, INT8, mm-managed)
    "clip": None,   # native CLIP (sam3 text encoder, fp16)
    "import_error": None,
    "yolo": None,   # Ultralytics YOLO proposer (resident, ~22MB)
}

_YOLO_NAME = "yolov8s.pt"


def _ensure_yolo():
    if _STATE["yolo"] is not None:
        return _STATE["yolo"]
    with _LOCK:
        if _STATE["yolo"] is not None:
            return _STATE["yolo"]
        import folder_paths
        target = os.path.join(folder_paths.models_dir, "ultralytics", "bbox", _YOLO_NAME)
        if not os.path.exists(target):
            # Standard Ultralytics auto-fetch, then move into place.
            from ultralytics import YOLO
            os.makedirs(os.path.dirname(target), exist_ok=True)
            print(f"[Studio/SAM3] Downloading {_YOLO_NAME} (one-time, ~22MB) ...")
            fetched = YOLO(_YOLO_NAME)
            src = getattr(fetched, "ckpt_path", "") or _YOLO_NAME
            if os.path.abspath(src) != os.path.abspath(target):
                import shutil
                shutil.move(src, target)
        from ultralytics import YOLO
        _STATE["yolo"] = YOLO(target)
        print("[Studio/SAM3] YOLO proposer ready.")
        return _STATE["yolo"]


def yolo_propose(pil_image, conf=0.25, max_det=20):
    """Fast boxes + COCO labels. Returns [{label, confidence, x, y, width, height}]."""
    import torch
    yolo = _ensure_yolo()
    img = np.array(pil_image.convert("RGB"))
    device = 0 if torch.cuda.is_available() else "cpu"
    with _INFER_LOCK:
        res = _timed(
            "yolo",
            lambda: yolo.predict(img, conf=float(conf), verbose=False, device=device)[0],
        )
    out = []
    boxes = getattr(res, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return out
    names = getattr(res, "names", {})
    for xyxy, cls, cf in zip(
        boxes.xyxy.cpu().tolist(), boxes.cls.cpu().tolist(), boxes.conf.cpu().tolist()
    ):
        x1, y1, x2, y2 = (float(v) for v in xyxy)
        out.append({
            "label": str(names.get(int(cls), int(cls))),
            "confidence": round(float(cf), 3),
            "x": round(x1, 1), "y": round(y1, 1),
            "width": round(max(1.0, x2 - x1), 1),
            "height": round(max(1.0, y2 - y1), 1),
        })
    out.sort(key=lambda d: d["confidence"], reverse=True)
    return out[: int(max_det)]


def boxes_mask(pil_image, boxes):
    """Refine proposer boxes with the SAM decoder. Returns the union mask."""
    model, _clip = _ensure_native()
    w, h = pil_image.size
    image = _pil_to_image_tensor(pil_image)
    clip_boxes = []
    for b in boxes or []:
        try:
            clip_boxes.append({
                "x": float(b["x"]), "y": float(b["y"]),
                "width": float(b["width"]), "height": float(b["height"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    if not clip_boxes:
        return torch.zeros((h, w), dtype=torch.float32)
    try:
        with _INFER_LOCK:
            masks, _boxes = _timed(
                "native-boxes",
                lambda: _detect(model, image, None, ([], []), 0.3, bboxes=clip_boxes),
            )
    finally:
        _release()
    if masks.shape[0] == 0:
        return torch.zeros((h, w), dtype=torch.float32)
    return torch.clamp(masks.amax(dim=0), 0, 1)

_CKPT_NAME = "sam3.1_multiplex_int8_convrot_selective_fp16clip_fp32source.safetensors"


def _timed(label, fn):
    import time
    t0 = time.perf_counter()
    out = fn()
    dt = (time.perf_counter() - t0) * 1000.0
    vram = ""
    try:
        if torch.cuda.is_available():
            vram = f" vram={torch.cuda.memory_allocated() / 1048576:.0f}MB"
    except Exception:
        pass
    print(f"[Studio/SAM3] {label}: {dt:.0f}ms{vram}")
    return out


def _ckpt_path():
    import folder_paths
    p = os.path.join(folder_paths.models_dir, "unet", _CKPT_NAME)
    if not os.path.exists(p):
        raise RuntimeError(
            f"SAM3 INT8 weights missing: place {_CKPT_NAME} in "
            f"{os.path.join(folder_paths.models_dir, 'unet')} "
            "(Sparknight/sam3.1-int8-int4-convrot on Hugging Face)."
        )
    return p


def _ensure_native():
    if _STATE["import_error"]:
        raise RuntimeError(_STATE["import_error"])
    if _STATE["model"] is not None:
        return _STATE["model"], _STATE["clip"]
    with _LOCK:
        if _STATE["model"] is not None:
            return _STATE["model"], _STATE["clip"]
        try:
            import comfy.sd as _sd
            out = _sd.load_checkpoint_guess_config(
                _ckpt_path(),
                output_vae=False,
                output_clip=True,
                output_clipvision=False,
                output_model=True,
            )
        except Exception as e:
            _STATE["import_error"] = f"SAM3 native load failed: {e}"
            raise RuntimeError(_STATE["import_error"])
        model, clip = out[0], out[1]
        if model is None:
            raise RuntimeError("SAM3 native load returned no model.")
        _STATE["model"] = model
        _STATE["clip"] = clip
        print("[Studio/SAM3] Native INT8 model + text encoder ready.")
        return model, clip


def _release():
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _pil_to_image_tensor(pil_image):
    arr = np.array(pil_image.convert("RGB")).astype(np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0).contiguous()


def _detect(model, image, conditioning, points, threshold, refine=2, bboxes=None):
    from comfy_extras.nodes_sam3 import SAM3_Detect
    pos = [{"x": int(x), "y": int(y)} for x, y in points[0]]
    neg = [{"x": int(x), "y": int(y)} for x, y in points[1]]
    # Headless call: no executing prompt, so the progress hook's
    # server_instance.last_prompt_id/last_node_id lookup fails. Lend it
    # ours, then restore (a real run may be concurrent).
    try:
        from server import PromptServer
        _srv = PromptServer.instance
    except Exception:
        _srv = None
    _saved = None
    if _srv is not None:
        _saved = (getattr(_srv, "last_prompt_id", None),
                  getattr(_srv, "last_node_id", None),
                  hasattr(_srv, "last_prompt_id"),
                  hasattr(_srv, "last_node_id"))
        _srv.last_prompt_id = "studio-sam"
        _srv.last_node_id = "studio-sam-detect"
    try:
        out = SAM3_Detect.execute(
            model,
            image,
            conditioning=conditioning,
            bboxes=bboxes,
            positive_coords=json.dumps(pos) if pos else None,
            negative_coords=json.dumps(neg) if neg else None,
            threshold=float(threshold),
            refine_iterations=int(refine),
            individual_masks=True,
        )
    finally:
        if _srv is not None and _saved is not None:
            _pid, _nid, _had_pid, _had_nid = _saved
            if _had_pid:
                _srv.last_prompt_id = _pid
            else:
                try:
                    delattr(_srv, "last_prompt_id")
                except AttributeError:
                    pass
            if _had_nid:
                _srv.last_node_id = _nid
            else:
                try:
                    delattr(_srv, "last_node_id")
                except AttributeError:
                    pass
    masks = out[0].detach().to("cpu").float()
    if masks.ndim == 2:
        masks = masks.unsqueeze(0)
    try:
        boxes = out[1][0] if isinstance(out[1], list) else []
    except Exception:
        boxes = []
    return masks, list(boxes or [])


def text_masks(pil_image, text, threshold=0.3, max_det=20):
    """Combined + per-instance masks for a text prompt. Returns (combined, list)."""
    from nodes import CLIPTextEncode
    model, clip = _ensure_native()
    if clip is None:
        raise RuntimeError("SAM3 checkpoint has no text encoder; text select needs it.")
    w, h = pil_image.size
    image = _pil_to_image_tensor(pil_image)
    query = (text or "").strip()
    try:
        # "person:20" = up to 20 matches (native sam3 max_detections syntax).
        conditioning = CLIPTextEncode().encode(clip, f"{query}:{int(max_det)}")[0]
    except Exception:
        conditioning = CLIPTextEncode().encode(clip, query)[0]
    try:
        with _INFER_LOCK:
            masks, _boxes = _timed(
                "native-text",
                lambda: _detect(model, image, conditioning, ([], []), threshold),
            )
    finally:
        _release()
    if masks.shape[0] == 0:
        return torch.zeros((h, w), dtype=torch.float32), []
    inst = [m for m in masks]
    combined = torch.clamp(torch.stack(inst).amax(dim=0), 0, 1)
    return combined, inst


def _thumb_b64(pil_image, box, size=96):
    from PIL import Image
    import io as _io
    import base64 as _b64
    w, h = pil_image.size
    x1 = max(0, int(box.get("x", 0)))
    y1 = max(0, int(box.get("y", 0)))
    x2 = min(w, x1 + max(1, int(box.get("width", w))))
    y2 = min(h, y1 + max(1, int(box.get("height", h))))
    crop = pil_image.crop((x1, y1, max(x1 + 1, x2), max(y1 + 1, y2)))
    crop.thumbnail((size, size))
    buf = _io.BytesIO()
    crop.save(buf, format="PNG")
    return _b64.b64encode(buf.getvalue()).decode("ascii")


def points_mask(pil_image, points, labels):
    """Single mask from click points. points=[[x,y]...] image pixels, labels 1/0."""
    model, _clip = _ensure_native()
    w, h = pil_image.size
    image = _pil_to_image_tensor(pil_image)
    pos = [p for p, lab in zip(points, labels or []) if int(lab) == 1]
    neg = [p for p, lab in zip(points, labels or []) if int(lab) != 1]
    if not pos and not neg:
        return torch.zeros((h, w), dtype=torch.float32)
    try:
        with _INFER_LOCK:
            masks, _boxes = _timed(
                "native-points",
                lambda: _detect(model, image, None, (pos, neg), 0.3),
            )
    finally:
        _release()
    if masks.shape[0] == 0:
        return torch.zeros((h, w), dtype=torch.float32)
    return torch.clamp(masks.amax(dim=0), 0, 1)


def _mask_to_png_base64(mask_tensor):
    from PIL import Image
    arr = (torch.clamp(mask_tensor, 0, 1).cpu().numpy() * 255).astype(np.uint8)
    img = Image.fromarray(arr, mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _load_image_ref(filename, subfolder, type_):
    import folder_paths
    from PIL import Image
    type_ = type_ or "temp"
    base = {
        "output": folder_paths.get_output_directory(),
        "input": folder_paths.get_input_directory(),
    }.get(type_, folder_paths.get_temp_directory())
    path = os.path.normpath(os.path.join(base, subfolder or "", filename or ""))
    if not path.startswith(os.path.normpath(base)):
        raise ValueError("invalid image path")
    return Image.open(path).convert("RGB")


def _pil_from_payload(data):
    b64 = (data or {}).get("image_b64", "")
    if b64:
        from PIL import Image
        if "," in b64:
            b64 = b64.split(",", 1)[1]
        return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    return _load_image_ref(
        (data or {}).get("filename", ""),
        (data or {}).get("subfolder", ""),
        (data or {}).get("type", "temp"),
    )


class StudioSAM3TextMask:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "clip": ("CLIP", {}),
            "text": ("STRING", {"default": "person", "multiline": False}),
            "threshold": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.05}),
        }}
    RETURN_TYPES = ("MASK",)
    FUNCTION = "run"
    CATEGORY = "Studio/Mask"

    def run(self, image, clip, text, threshold):
        from nodes import CLIPTextEncode
        from PIL import Image
        arr = (image[0].cpu().numpy() * 255).astype(np.uint8)
        pil = Image.fromarray(arr)
        model, _ = _ensure_native()
        conditioning = CLIPTextEncode().encode(clip, f"{text}:20")[0]
        masks, _boxes = _detect(model, _pil_to_image_tensor(pil), conditioning, ([], []), threshold)
        if masks.shape[0] == 0:
            h, w = pil.size[1], pil.size[0]
            return (torch.zeros((1, h, w), dtype=torch.float32),)
        combined = torch.clamp(masks.amax(dim=0), 0, 1)
        return (combined.unsqueeze(0).contiguous(),)


class StudioSAM3PointMask:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "model": ("MODEL", {}),
            "points": ("STRING", {"default": "[]", "multiline": False}),
            "labels": ("STRING", {"default": "[]", "multiline": False}),
        }}
    RETURN_TYPES = ("MASK",)
    FUNCTION = "run"
    CATEGORY = "Studio/Mask"

    def run(self, image, model, points, labels):
        from PIL import Image
        arr = (image[0].cpu().numpy() * 255).astype(np.uint8)
        pil = Image.fromarray(arr)
        pts = json.loads(points or "[]")
        labs = json.loads(labels or "[]")
        pos = [p for p, lab in zip(pts, labs or []) if int(lab) == 1]
        neg = [p for p, lab in zip(pts, labs or []) if int(lab) != 1]
        if not pos and not neg:
            h, w = pil.size[1], pil.size[0]
            return (torch.zeros((1, h, w), dtype=torch.float32),)
        masks, _boxes = _detect(model, _pil_to_image_tensor(pil), None, (pos, neg), 0.3)
        if masks.shape[0] == 0:
            h, w = pil.size[1], pil.size[0]
            return (torch.zeros((1, h, w), dtype=torch.float32),)
        combined = torch.clamp(masks.amax(dim=0), 0, 1)
        return (combined.unsqueeze(0).contiguous(),)


NODE_CLASS_MAPPINGS = {
    "StudioSAM3TextMask": StudioSAM3TextMask,
    "StudioSAM3PointMask": StudioSAM3PointMask,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "StudioSAM3TextMask": "Studio SAM3 Text Mask",
    "StudioSAM3PointMask": "Studio SAM3 Point Mask",
}


def register_sam_routes(server):
    @server.routes.post("/comfymodal/studio/sam3/text")
    async def sam3_text(request):
        try:
            data = await request.json()
        except Exception:
            from aiohttp import web
            return web.json_response({"error": "invalid JSON"}, status=400)
        from aiohttp import web
        import asyncio
        if not (data or {}).get("image_b64") and not (data or {}).get("filename"):
            return web.json_response({"error": "no source image (upload one first)"}, status=400)
        try:
            pil = _pil_from_payload(data)
        except Exception as e:
            return web.json_response({"error": f"could not load source: {e}"}, status=400)
        text = (data or {}).get("text", "")
        threshold = float((data or {}).get("threshold", 0.3))
        loop = asyncio.get_event_loop()
        try:
            combined, inst = await loop.run_in_executor(
                None, text_masks, pil, text, threshold, 20
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return web.json_response({"error": str(e)}, status=500)
        return web.json_response({
            "ok": True, "width": pil.size[0], "height": pil.size[1],
            "count": len(inst), "mask_png": _mask_to_png_base64(combined),
        })

    @server.routes.post("/comfymodal/studio/sam3/points")
    async def sam3_points(request):
        try:
            data = await request.json()
        except Exception:
            from aiohttp import web
            return web.json_response({"error": "invalid JSON"}, status=400)
        from aiohttp import web
        import asyncio
        if not (data or {}).get("image_b64") and not (data or {}).get("filename"):
            return web.json_response({"error": "no source image (upload one first)"}, status=400)
        try:
            pil = _pil_from_payload(data)
        except Exception as e:
            return web.json_response({"error": f"could not load source: {e}"}, status=400)
        points = (data or {}).get("points", [])
        labels = (data or {}).get("labels", [])
        if not points:
            return web.json_response({"error": "no points"}, status=400)
        loop = asyncio.get_event_loop()
        try:
            m = await loop.run_in_executor(None, points_mask, pil, points, labels)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return web.json_response({"error": str(e)}, status=500)
        return web.json_response({
            "ok": True, "width": pil.size[0], "height": pil.size[1],
            "mask_png": _mask_to_png_base64(m),
        })

    @server.routes.post("/comfymodal/studio/sam3/scan-yolo")
    async def sam3_scan_yolo(request):
        try:
            data = await request.json()
        except Exception:
            from aiohttp import web
            return web.json_response({"error": "invalid JSON"}, status=400)
        from aiohttp import web
        import asyncio
        if not (data or {}).get("image_b64") and not (data or {}).get("filename"):
            return web.json_response({"error": "no source image (upload one first)"}, status=400)
        try:
            pil = _pil_from_payload(data)
        except Exception as e:
            return web.json_response({"error": f"could not load source: {e}"}, status=400)
        conf = float((data or {}).get("conf", 0.25))
        loop = asyncio.get_event_loop()
        try:
            dets = await loop.run_in_executor(None, yolo_propose, pil, conf, 20)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return web.json_response({"error": str(e)}, status=500)
        items = []
        for d in dets:
            items.append({
                "label": d["label"],
                "confidence": d["confidence"],
                "box": {k: d[k] for k in ("x", "y", "width", "height")},
                "thumb_png": _thumb_b64(pil, d),
            })
        return web.json_response({
            "ok": True, "width": pil.size[0], "height": pil.size[1],
            "items": items,
        })

    @server.routes.post("/comfymodal/studio/sam3/boxes")
    async def sam3_boxes(request):
        try:
            data = await request.json()
        except Exception:
            from aiohttp import web
            return web.json_response({"error": "invalid JSON"}, status=400)
        from aiohttp import web
        import asyncio
        if not (data or {}).get("image_b64") and not (data or {}).get("filename"):
            return web.json_response({"error": "no source image (upload one first)"}, status=400)
        try:
            pil = _pil_from_payload(data)
        except Exception as e:
            return web.json_response({"error": f"could not load source: {e}"}, status=400)
        boxes = (data or {}).get("boxes", [])
        if not boxes:
            return web.json_response({"error": "no boxes"}, status=400)
        loop = asyncio.get_event_loop()
        try:
            m = await loop.run_in_executor(None, boxes_mask, pil, boxes)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return web.json_response({"error": str(e)}, status=500)
        return web.json_response({
            "ok": True, "width": pil.size[0], "height": pil.size[1],
            "mask_png": _mask_to_png_base64(m),
        })
