"""
retrieval/visual.py
-------------------
Visual-modality retrieval for emoji.

The default visual index is built offline:

1. Render each Unicode emoji into a normalized PNG canvas.
2. Encode those images with the CLIP image encoder.
3. Learn a ridge-regression projection from CLIP visual vectors into the
   existing Bi-Encoder text embedding space.
4. Search by comparing the query text vector with aligned visual vectors.

Runtime search only loads local cache artifacts. If the visual index is
missing or stale, build it before starting Flask:

    .venv\\Scripts\\python.exe -m retrieval.visual --build --force
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from retrieval.cache_utils import build_cache_meta, cache_meta_matches, file_sha256, save_cache_meta


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATASET = DATA_DIR / "emoji_dataset.json"
TEXT_EMB_FILE = DATA_DIR / "bi_encoder_embeddings.npy"
IMAGE_DIR = DATA_DIR / "emoji_images"
MANIFEST_FILE = DATA_DIR / "emoji_images_manifest.json"
CLIP_EMB_FILE = DATA_DIR / "clip_visual_embeddings.npy"
VISUAL_FEATURE_FILE = DATA_DIR / "visual_features.npy"  # compatibility alias for CLIP vectors
VISUAL_STATS_FILE = DATA_DIR / "visual_feature_stats.json"
VISUAL_PROJECTION_FILE = DATA_DIR / "visual_projection.npy"
VISUAL_EMB_FILE = DATA_DIR / "aligned_visual_embeddings.npy"

IMAGE_SIZE = 128
CLIP_MODEL_NAME = "openai/clip-vit-base-patch32"
FEATURE_VERSION = "clip_vit_base_patch32_image_v1"
PIXEL_FEATURE_VERSION = "pil_pixel_v1"
ALIGNMENT_VERSION = "clip_ridge_visual_to_biencoder_v1"
VISUAL_METHOD = "clip_image_encoder_ridge_alignment"


def _configure_stdout() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _canonical_char(char: str) -> str:
    return char.replace("\ufe0f", "").replace("\ufe0e", "")


def _l2_normalize(v: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(norms, 1e-10)


def _emoji_filename(index: int, char: str) -> str:
    code = "-".join(f"{ord(ch):x}" for ch in char)
    return f"{index:04d}_{code}.png"


def _font_candidates() -> list[Path]:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    return [
        windir / "Fonts" / "seguiemj.ttf",
        windir / "Fonts" / "seguisym.ttf",
        windir / "Fonts" / "segoeui.ttf",
        Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
        Path("/System/Library/Fonts/Apple Color Emoji.ttc"),
    ]


def _load_emoji_font(size: int) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, str]:
    for path in _font_candidates():
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size), str(path)
            except Exception:
                continue
    return ImageFont.load_default(), "PIL_default"


def render_emoji_image(char: str, path: Path, *, size: int = IMAGE_SIZE) -> str:
    """Render one emoji to a transparent PNG and return the font identifier."""
    font, font_id = _load_emoji_font(int(size * 0.72))
    image = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)

    try:
        bbox = draw.textbbox((0, 0), char, font=font, embedded_color=True)
    except TypeError:
        bbox = draw.textbbox((0, 0), char, font=font)

    tw = max(1, bbox[2] - bbox[0])
    th = max(1, bbox[3] - bbox[1])
    xy = ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1])
    try:
        draw.text(xy, char, font=font, embedded_color=True)
    except TypeError:
        draw.text(xy, char, font=font, fill=(30, 30, 30, 255))

    if not np.asarray(image.getchannel("A")).any():
        fallback = ImageFont.load_default()
        draw = ImageDraw.Draw(image)
        draw.text((size * 0.30, size * 0.42), "?", font=fallback, fill=(30, 30, 30, 255))

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return font_id


def _composite_on_white(image: Image.Image) -> np.ndarray:
    rgba = image.convert("RGBA")
    arr = np.asarray(rgba).astype(np.float32)
    alpha = arr[..., 3:4] / 255.0
    rgb = arr[..., :3] * alpha + 255.0 * (1.0 - alpha)
    return rgb.astype(np.float32)


def _image_for_clip(image_path: Path) -> Image.Image:
    image = Image.open(image_path).convert("RGBA")
    return Image.fromarray(_composite_on_white(image).astype(np.uint8)).convert("RGB")


def extract_pixel_features(image_path: Path) -> np.ndarray:
    """Return a deterministic fallback descriptor from the rendered emoji image."""
    image = Image.open(image_path).convert("RGBA")
    rgb = _composite_on_white(image)
    alpha = np.asarray(image.getchannel("A")).astype(np.float32) / 255.0

    rgb32 = np.asarray(Image.fromarray(rgb.astype(np.uint8)).resize((32, 32), Image.Resampling.LANCZOS)).astype(np.float32)
    alpha16 = np.asarray(Image.fromarray((alpha * 255).astype(np.uint8)).resize((16, 16), Image.Resampling.LANCZOS)).astype(np.float32) / 255.0
    gray16 = np.asarray(
        Image.fromarray(rgb.astype(np.uint8)).convert("L").resize((16, 16), Image.Resampling.LANCZOS)
    ).astype(np.float32) / 255.0

    channels = rgb32.reshape(-1, 3)
    hists = []
    for c in range(3):
        hist, _ = np.histogram(channels[:, c], bins=8, range=(0, 255))
        hists.append(hist.astype(np.float32) / max(float(hist.sum()), 1.0))

    non_bg = alpha > 0.03
    if non_bg.any():
        ys, xs = np.where(non_bg)
        bbox = np.array(
            [
                xs.min() / max(alpha.shape[1] - 1, 1),
                ys.min() / max(alpha.shape[0] - 1, 1),
                xs.max() / max(alpha.shape[1] - 1, 1),
                ys.max() / max(alpha.shape[0] - 1, 1),
            ],
            dtype=np.float32,
        )
    else:
        bbox = np.zeros(4, dtype=np.float32)

    stats = np.concatenate(
        [
            channels.mean(axis=0) / 255.0,
            channels.std(axis=0) / 255.0,
            channels.min(axis=0) / 255.0,
            channels.max(axis=0) / 255.0,
            np.array([float(non_bg.mean())], dtype=np.float32),
            bbox,
        ]
    )

    return np.concatenate(
        [
            *hists,
            stats,
            alpha16.reshape(-1),
            (1.0 - gray16).reshape(-1),
        ]
    ).astype(np.float32)


def _default_renderer_font_id() -> str:
    _, font_id = _load_emoji_font(int(IMAGE_SIZE * 0.72))
    return font_id


def _expected_meta(records: list[dict], *, backend: str = "clip") -> dict:
    text_sha = file_sha256(str(TEXT_EMB_FILE)) if TEXT_EMB_FILE.exists() else ""
    feature_version = FEATURE_VERSION if backend == "clip" else PIXEL_FEATURE_VERSION
    visual_model = CLIP_MODEL_NAME if backend == "clip" else "local_pixel_descriptor"
    extra = {
        "num_records": len(records),
        "text_embedding_file": TEXT_EMB_FILE.name,
        "text_embedding_sha256": text_sha,
        "feature_backend": backend,
        "feature_version": feature_version,
        "alignment_version": ALIGNMENT_VERSION,
        "image_size": IMAGE_SIZE,
        "renderer_font": _default_renderer_font_id(),
        "visual_model": visual_model,
        "visual_method": VISUAL_METHOD if backend == "clip" else "pixel_descriptor_ridge_alignment",
    }
    return build_cache_meta(str(DATASET), kind="visual_alignment", extra=extra)


def _load_records() -> list[dict]:
    with open(DATASET, "r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_text_embeddings() -> None:
    if TEXT_EMB_FILE.exists():
        return
    from retrieval.bi_encoder import BiEncoderRetriever

    BiEncoderRetriever().load()


def _write_manifest(records: list[dict], *, force: bool = False) -> tuple[list[dict], list[Path]]:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    image_paths = []
    renderer_font = None

    for idx, record in enumerate(records):
        char = record["char"]
        image_path = IMAGE_DIR / _emoji_filename(idx, char)
        if force or not image_path.exists():
            renderer_font = render_emoji_image(char, image_path)
        elif renderer_font is None:
            _, renderer_font = _load_emoji_font(int(IMAGE_SIZE * 0.72))

        image_paths.append(image_path)
        manifest.append(
            {
                "index": idx,
                "char": char,
                "canonical_char": _canonical_char(char),
                "codepoint": record.get("codepoint", ""),
                "file": str(image_path.relative_to(ROOT_DIR)).replace("\\", "/"),
                "image_size": IMAGE_SIZE,
                "renderer_font": renderer_font,
                "platform": sys.platform,
            }
        )

    return manifest, image_paths


def _extract_clip_embeddings(
    image_paths: list[Path],
    *,
    batch_size: int = 32,
    local_files_only: bool = False,
) -> np.ndarray:
    import torch
    from transformers import AutoProcessor, CLIPModel

    processor = AutoProcessor.from_pretrained(CLIP_MODEL_NAME, local_files_only=local_files_only)
    model = CLIPModel.from_pretrained(CLIP_MODEL_NAME, local_files_only=local_files_only)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    model.eval()

    features = []
    with torch.no_grad():
        for start in range(0, len(image_paths), batch_size):
            batch_paths = image_paths[start : start + batch_size]
            images = [_image_for_clip(path) for path in batch_paths]
            inputs = processor(images=images, return_tensors="pt")
            inputs = {k: v.to(device) for k, v in inputs.items()}
            output = model.get_image_features(**inputs)
            if isinstance(output, torch.Tensor):
                tensor = output
            elif hasattr(output, "image_embeds") and output.image_embeds is not None:
                tensor = output.image_embeds
            elif hasattr(output, "pooler_output") and output.pooler_output is not None:
                tensor = output.pooler_output
            else:
                raise TypeError(f"Unsupported CLIP output type: {type(output)!r}")
            batch = tensor.detach().cpu().numpy().astype(np.float32)
            features.append(batch)
            print(f"  [Visual] CLIP encoded {min(start + batch_size, len(image_paths))}/{len(image_paths)}")

    return _l2_normalize(np.vstack(features).astype(np.float32))


def _extract_pixel_embeddings(image_paths: list[Path]) -> np.ndarray:
    descriptors = []
    for idx, image_path in enumerate(image_paths):
        descriptors.append(extract_pixel_features(image_path))
        if (idx + 1) % 250 == 0:
            print(f"  [Visual] pixel features {idx + 1}/{len(image_paths)}")
    return np.vstack(descriptors).astype(np.float32)


def _learn_projection(visual_features: np.ndarray, text_embeddings: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    if len(visual_features) != len(text_embeddings):
        raise ValueError(
            f"Visual/text count mismatch: visual={len(visual_features)} text={len(text_embeddings)}"
        )

    text_target = _l2_normalize(text_embeddings.astype(np.float32))
    mean = visual_features.mean(axis=0, keepdims=True)
    std = np.maximum(visual_features.std(axis=0, keepdims=True), 1e-6)
    x_norm = (visual_features - mean) / std
    x_aug = np.concatenate([x_norm, np.ones((x_norm.shape[0], 1), dtype=np.float32)], axis=1)

    alpha = 1e-3
    reg = np.eye(x_aug.shape[1], dtype=np.float32) * alpha
    reg[-1, -1] = 0.0
    try:
        projection = np.linalg.solve(x_aug.T @ x_aug + reg, x_aug.T @ text_target)
    except np.linalg.LinAlgError:
        projection = np.linalg.pinv(x_aug.T @ x_aug + reg) @ x_aug.T @ text_target

    aligned = _l2_normalize(x_aug @ projection).astype(np.float32)
    stats = {
        "mean": mean.reshape(-1).tolist(),
        "std": std.reshape(-1).tolist(),
        "ridge_lambda": alpha,
    }
    return projection.astype(np.float32), aligned, stats


def visual_index_status(records: list[dict] | None = None) -> dict:
    records = records or _load_records()
    expected = _expected_meta(records, backend="clip")
    core_files = [MANIFEST_FILE, CLIP_EMB_FILE, VISUAL_FEATURE_FILE, VISUAL_PROJECTION_FILE, VISUAL_EMB_FILE]
    existing = {path.name: path.exists() for path in core_files}
    meta_ok = all(cache_meta_matches(str(path), expected) for path in core_files if path.exists())
    files_ready = all(existing.values())
    ready = files_ready and meta_ok

    visual_count = 0
    visual_dim = 0
    if VISUAL_EMB_FILE.exists():
        try:
            arr = np.load(VISUAL_EMB_FILE, mmap_mode="r")
            visual_count = int(arr.shape[0])
            visual_dim = int(arr.shape[1]) if len(arr.shape) > 1 else 0
        except Exception:
            visual_count = 0
            visual_dim = 0

    if not files_ready:
        message = "missing visual cache artifacts"
    elif not meta_ok:
        message = "visual cache metadata is stale"
    elif visual_count != len(records):
        ready = False
        message = "visual cache count does not match dataset"
    else:
        message = "ready"

    return {
        "visual_index_ready": ready,
        "visual_manifest_ready": MANIFEST_FILE.exists() and cache_meta_matches(str(MANIFEST_FILE), expected),
        "visual_model": CLIP_MODEL_NAME,
        "visual_method": VISUAL_METHOD,
        "visual_backend": "clip",
        "visual_count": visual_count,
        "visual_dim": visual_dim,
        "visual_expected_count": len(records),
        "visual_feature_file": CLIP_EMB_FILE.name,
        "visual_cache_files": existing,
        "visual_index_message": message,
    }


def build_visual_index(
    *,
    force: bool = False,
    limit: int | None = None,
    backend: str = "clip",
    batch_size: int = 32,
    local_files_only: bool = False,
) -> dict:
    """Build rendered images, CLIP visual embeddings, and aligned vectors."""
    _configure_stdout()
    if backend not in {"clip", "pixel"}:
        raise ValueError("backend must be 'clip' or 'pixel'")

    records = _load_records()
    if limit is not None:
        records = records[:limit]

    _ensure_text_embeddings()
    text_embeddings = np.load(TEXT_EMB_FILE).astype(np.float32)
    if limit is not None:
        text_embeddings = text_embeddings[:limit]

    meta = _expected_meta(records, backend=backend)
    if (
        backend == "clip"
        and not force
        and limit is None
        and visual_index_status(records)["visual_index_ready"]
    ):
        return {"rebuilt": False, "count": len(records), "path": str(VISUAL_EMB_FILE)}

    manifest, image_paths = _write_manifest(records, force=force)

    if backend == "clip":
        visual_features = _extract_clip_embeddings(
            image_paths,
            batch_size=batch_size,
            local_files_only=local_files_only,
        )
    else:
        visual_features = _extract_pixel_embeddings(image_paths)

    projection, aligned, stats = _learn_projection(visual_features, text_embeddings)

    if limit is None:
        np.save(CLIP_EMB_FILE, visual_features)
        np.save(VISUAL_FEATURE_FILE, visual_features)
        np.save(VISUAL_PROJECTION_FILE, projection)
        np.save(VISUAL_EMB_FILE, aligned)
        with open(VISUAL_STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    **stats,
                    "feature_backend": backend,
                    "feature_version": FEATURE_VERSION if backend == "clip" else PIXEL_FEATURE_VERSION,
                    "visual_model": CLIP_MODEL_NAME if backend == "clip" else "local_pixel_descriptor",
                },
                f,
                ensure_ascii=False,
            )
        with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        final_meta = _expected_meta(records, backend=backend)
        for artifact in [MANIFEST_FILE, CLIP_EMB_FILE, VISUAL_FEATURE_FILE, VISUAL_PROJECTION_FILE, VISUAL_EMB_FILE, VISUAL_STATS_FILE]:
            save_cache_meta(str(artifact), final_meta)

    return {
        "rebuilt": True,
        "backend": backend,
        "model": CLIP_MODEL_NAME if backend == "clip" else "local_pixel_descriptor",
        "count": len(records),
        "visual_dim": int(visual_features.shape[1]),
        "aligned_dim": int(aligned.shape[1]),
        "path": str(VISUAL_EMB_FILE),
    }


class VisualRetriever:
    """Search emoji by aligning rendered visual features with query text vectors."""

    def __init__(self):
        self.records: list[dict] | None = None
        self.embeddings: np.ndarray | None = None
        self._encoder = None

    def load(self):
        self.records = _load_records()
        status = visual_index_status(self.records)
        if not status["visual_index_ready"]:
            raise RuntimeError(
                "Visual index is missing or stale. "
                "Run `.venv\\Scripts\\python.exe -m retrieval.visual --build --force` before starting Flask. "
                f"Status: {status['visual_index_message']}"
            )
        self.embeddings = np.load(VISUAL_EMB_FILE).astype(np.float32)
        if self.embeddings.shape[0] != len(self.records):
            raise RuntimeError("Visual index count does not match emoji dataset")
        return self

    def _lazy_encoder(self):
        if self._encoder is None:
            from retrieval.bi_encoder import BiEncoderRetriever

            self._encoder = BiEncoderRetriever().load()
        return self._encoder

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        encoder = self._lazy_encoder()
        q_vec = encoder._encode_batch([query])[0]
        return self.search_with_query_vector(q_vec, top_k=top_k)

    def search_with_query_vector(self, q_vec: np.ndarray, top_k: int = 10) -> list[dict]:
        if self.embeddings is None or self.records is None:
            self.load()

        q = q_vec.astype(np.float32)
        q = q / max(float(np.linalg.norm(q)), 1e-10)
        scores = self.embeddings @ q
        top_idxs = np.argsort(-scores)[:top_k]

        results = []
        for rank, idx in enumerate(top_idxs, 1):
            r = self.records[int(idx)]
            score = float(scores[int(idx)])
            results.append(
                {
                    "rank": rank,
                    "score": score,
                    "visual_score": score,
                    "modality_scores": {
                        "visual": score,
                    },
                    "char": r["char"],
                    "codepoint": r["codepoint"],
                    "en": r["en"],
                    "zh": r["zh"],
                    "ja": r.get("ja", ""),
                    "keywords": r["keywords"],
                    "category": r["category"],
                }
            )
        return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true", help="Build the full visual index")
    parser.add_argument("--force", action="store_true", help="Rebuild even if cache metadata matches")
    parser.add_argument("--limit", type=int, default=None, help="Build only the first N records for smoke testing")
    parser.add_argument("--backend", choices=["clip", "pixel"], default="clip", help="Visual feature backend")
    parser.add_argument("--batch-size", type=int, default=32, help="CLIP image encoding batch size")
    parser.add_argument("--local-files-only", action="store_true", help="Do not download CLIP files")
    parser.add_argument("--status", action="store_true", help="Print visual index status")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(visual_index_status(), ensure_ascii=False, indent=2))
        return

    if args.build or args.limit:
        info = build_visual_index(
            force=args.force,
            limit=args.limit,
            backend=args.backend,
            batch_size=args.batch_size,
            local_files_only=args.local_files_only,
        )
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        ret = VisualRetriever().load()
        for query in ["happy smile", "love heart", "cat", "rain"]:
            hits = ret.search(query, top_k=5)
            print(query, " ".join(h["char"] for h in hits))


if __name__ == "__main__":
    main()
