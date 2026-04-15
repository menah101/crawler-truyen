"""
Shared helper: sinh ảnh qua HuggingFace Router — tự chuyển (model, provider)
khi fail. Khi cả provider chain của model chính chết, fallback sang model khác
cùng family (FLUX.1-dev) rồi khác family (SD 3.5) trước khi raise.

Dùng `huggingface_hub.InferenceClient` để nó lo chênh lệch payload giữa các
provider. Caller chỉ cần truyền prompt + params chung và nhận PIL Image.

Cấu hình chain ở `config.HF_IMAGE_CHAIN` — list các tuple
`(model, provider, attempts, delay)`.
"""

from __future__ import annotations

import logging
import time
from typing import Iterable

from PIL import Image

logger = logging.getLogger(__name__)

# Chain mặc định (model, provider, attempts, delay) — override qua
# config.HF_IMAGE_CHAIN. Ưu tiên free → same-model paid → fallback-model paid.
_DEFAULT_CHAIN: tuple[tuple[str, str, int, int], ...] = (
    ("black-forest-labs/FLUX.1-schnell", "hf-inference", 1, 0),
    ("black-forest-labs/FLUX.1-schnell", "fal-ai",       1, 0),
    ("black-forest-labs/FLUX.1-schnell", "replicate",    1, 0),
    ("black-forest-labs/FLUX.1-dev",     "fal-ai",       1, 0),
    ("black-forest-labs/FLUX.1-dev",     "replicate",    1, 0),
    ("stabilityai/stable-diffusion-3.5-large", "fal-ai", 1, 0),
)

# Override params theo model khi fallback. Schnell train với 1–4 steps,
# guidance=0. Dev / SD3.5 cần nhiều steps hơn và guidance > 0 để ra ảnh đẹp.
_MODEL_OVERRIDES: dict[str, dict[str, float]] = {
    "black-forest-labs/FLUX.1-dev": {"num_inference_steps": 28, "guidance_scale": 3.5},
    "stabilityai/stable-diffusion-3.5-large": {"num_inference_steps": 28, "guidance_scale": 4.5},
}


def _ensure_size(img: Image.Image, want_w: int, want_h: int) -> Image.Image:
    """
    Đảm bảo ảnh trả về đúng (want_w × want_h). Một số provider (fal-ai,
    replicate) làm tròn về preset image_size hoặc trả size gần nhất → tỷ lệ
    sai. Nếu lệch: center-crop theo tỷ lệ rồi resize về đúng kích thước.
    """
    cur_w, cur_h = img.size
    if cur_w == want_w and cur_h == want_h:
        return img

    want_ratio = want_w / want_h
    cur_ratio = cur_w / cur_h
    if abs(cur_ratio - want_ratio) > 0.01:
        if cur_ratio > want_ratio:
            new_w = int(cur_h * want_ratio)
            offset = (cur_w - new_w) // 2
            img = img.crop((offset, 0, offset + new_w, cur_h))
        else:
            new_h = int(cur_w / want_ratio)
            offset = (cur_h - new_h) // 2
            img = img.crop((0, offset, cur_w, offset + new_h))

    if img.size != (want_w, want_h):
        img = img.resize((want_w, want_h), Image.LANCZOS)
        logger.info(f"  ↻ Resize {cur_w}x{cur_h} → {want_w}x{want_h}")
    return img


def _chain_from_config() -> Iterable[tuple[str, str, int, int]]:
    try:
        from config import HF_IMAGE_CHAIN  # type: ignore
    except ImportError:
        return _DEFAULT_CHAIN
    if not HF_IMAGE_CHAIN:
        return _DEFAULT_CHAIN
    out: list[tuple[str, str, int, int]] = []
    for entry in HF_IMAGE_CHAIN:
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        model = entry[0]
        provider = entry[1]
        attempts = int(entry[2]) if len(entry) > 2 else 1
        delay = int(entry[3]) if len(entry) > 3 else 0
        out.append((model, provider, attempts, delay))
    return out or _DEFAULT_CHAIN


def generate_flux_image(
    prompt: str,
    *,
    api_token: str,
    width: int,
    height: int,
    num_inference_steps: int = 4,
    guidance_scale: float = 0.0,
    seed: int | None = None,
    negative_prompt: str | None = None,
) -> Image.Image:
    """
    Sinh ảnh qua (model, provider) chain. Raise RuntimeError nếu mọi combo
    đều fail — caller phải bắt và xử lý (log ❌ / dùng placeholder).
    """
    try:
        from huggingface_hub import InferenceClient
        from huggingface_hub.errors import HfHubHTTPError
    except ImportError as e:
        raise RuntimeError(
            "huggingface_hub chưa cài — chạy `pip install huggingface_hub`"
        ) from e

    last_error: str = "unknown"
    for model, provider, attempts, delay in _chain_from_config():
        # Áp override cho model non-schnell (dev / SD cần steps cao + guidance).
        overrides = _MODEL_OVERRIDES.get(model, {})
        steps = int(overrides.get("num_inference_steps", num_inference_steps))
        guidance = float(overrides.get("guidance_scale", guidance_scale))

        client = InferenceClient(provider=provider, api_key=api_token)
        for attempt in range(attempts):
            try:
                img = client.text_to_image(
                    prompt,
                    model=model,
                    width=width,
                    height=height,
                    num_inference_steps=steps,
                    guidance_scale=guidance,
                    seed=seed,
                    negative_prompt=negative_prompt,
                )
                logger.info(f"  ✅ Image via {provider} / {model.split('/')[-1]}")
                return _ensure_size(img, width, height)
            except HfHubHTTPError as e:
                status = getattr(e.response, "status_code", "?") if getattr(e, "response", None) else "?"
                body = str(e)[:200]
                last_error = f"{provider}/{model.split('/')[-1]} HTTP {status}: {body}"
                logger.warning(f"  ⚠️ Image {last_error}")
            except Exception as e:
                last_error = f"{provider}/{model.split('/')[-1]} {type(e).__name__}: {e}"
                logger.warning(f"  ⚠️ Image {last_error}")

            if attempt < attempts - 1 and delay > 0:
                time.sleep(delay)

    raise RuntimeError(f"Image generation failed — cả chain (model, provider) đều fail. Last: {last_error}")
