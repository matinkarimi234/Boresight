# render_from_sidecar.py
# Burn-in reticle using *.jsonl sidecar that shares the same stem as the video.
# Requires: python3, opencv-python, numpy

import os, sys, json, argparse
import cv2
import numpy as np

def _stem_paths(stem_or_path):
    p = os.path.expanduser(stem_or_path)
    base, ext = os.path.splitext(p)
    if ext.lower() == ".mp4":
        mp4 = p
        jsonl = base + ".jsonl"
    elif ext.lower() == ".jsonl":
        jsonl = p
        mp4 = base + ".mp4"
    else:
        mp4 = base + ".mp4"
        jsonl = base + ".jsonl"

    if not os.path.isfile(mp4):
        raise FileNotFoundError(f"Video not found: {mp4}")
    if not os.path.isfile(jsonl):
        raise FileNotFoundError(f"Metadata not found: {jsonl}")

    out = base + "_overlay.mp4"
    return mp4, jsonl, out

def _load_header_and_ticks(jsonl_path):
    header = {}
    ticks = []
    with open(jsonl_path, "r") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get("type") == "header":
                header = obj
            elif obj.get("type") == "tick":
                ticks.append(obj)
    ticks.sort(key=lambda x: x.get("t_rel", 0.0))
    return header, ticks

def _style_from_header(header):
    s = header.get("overlay_style", {}) if header else {}
    radius        = int(s.get("radius", 10))
    ring          = int(s.get("ring_thickness", 1))
    tick_len      = int(s.get("tick_length", 300))
    tick_w        = int(s.get("tick_thickness", 1))
    gap           = int(s.get("gap", 2))
    color_rgba    = s.get("color", [130, 0, 0, 255])

    # convert RGBA(list) -> BGR(tuple) for OpenCV
    if isinstance(color_rgba, (list, tuple)) and len(color_rgba) >= 3:
        r, g, b = color_rgba[:3]
    else:
        r, g, b = (130, 0, 0)
    color_bgr = (int(b), int(g), int(r))
    return dict(radius=radius, ring=ring, tick_len=tick_len, tick_w=tick_w, gap=gap, color=color_bgr)

def _draw_reticle(img, cx, cy, *, radius, ring, tick_len, tick_w, gap, color):
    h, w = img.shape[:2]
    if cx is None or cy is None:
        return
    cx = int(np.clip(cx, 0, w - 1))
    cy = int(np.clip(cy, 0, h - 1))

    # circle
    cv2.circle(img, (cx, cy), int(radius), color, int(ring), lineType=cv2.LINE_AA)

    # horizontal ticks (left/right)
    x1 = max(0, cx - radius - gap - tick_len)
    x2 = cx - radius - gap
    if x2 > x1:
        cv2.line(img, (x1, cy), (x2, cy), color, int(tick_w), cv2.LINE_AA)

    x3 = cx + radius + gap
    x4 = min(w - 1, cx + radius + gap + tick_len)
    if x4 > x3:
        cv2.line(img, (x3, cy), (x4, cy), color, int(tick_w), cv2.LINE_AA)

    # vertical ticks (top/bottom)
    y1 = max(0, cy - radius - gap - tick_len)
    y2 = cy - radius - gap
    if y2 > y1:
        cv2.line(img, (cx, y1), (cx, y2), color, int(tick_w), cv2.LINE_AA)

    y3 = cy + radius + gap
    y4 = min(h - 1, cy + radius + gap + tick_len)
    if y4 > y3:
        cv2.line(img, (cx, y3), (cx, y4), color, int(tick_w), cv2.LINE_AA)

def _put_state_text(img, text, color, margin=20, scale=0.8, thickness=2, at="top-right"):
    if not text:
        return
    h, w = img.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    if at == "top-right":
        org = (w - margin - tw, margin + th)
    elif at == "top-left":
        org = (margin, margin + th)
    elif at == "bottom-left":
        org = (margin, h - margin)
    else:  # bottom-right
        org = (w - margin - tw, h - margin)
    cv2.putText(img, text, org, font, scale, color, thickness, cv2.LINE_AA)

def render(stem_or_path, output=None, show_state_text=True, text_pos="top-right"):
    video_path, jsonl_path, default_out = _stem_paths(stem_or_path)
    if output is None:
        output = default_out

    header, ticks = _load_header_and_ticks(jsonl_path)
    if not ticks:
        raise RuntimeError("No tick rows found in metadata.")

    style = _style_from_header(header)
    color_bgr = style["color"]

    # Open input video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output, fourcc, fps, (w, h))
    if not out.isOpened():
        raise RuntimeError(f"Failed to open writer: {output}")

    # Iterate frames and advance current tick when the frame time passes the next tick's t_rel
    i = 0
    current = ticks[0]
    next_tick = ticks[1] if len(ticks) > 1 else None

    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t_rel = frame_idx / fps

        while next_tick and t_rel >= next_tick.get("t_rel", 0.0):
            i += 1
            current = next_tick
            next_tick = ticks[i+1] if (i + 1) < len(ticks) else None

        ov = current.get("overlay", {})
        cx = ov.get("cx")
        cy = ov.get("cy")

        _draw_reticle(
            frame, cx, cy,
            radius=style["radius"],
            ring=style["ring"],
            tick_len=style["tick_len"],
            tick_w=style["tick_w"],
            gap=style["gap"],
            color=color_bgr
        )

        if show_state_text:
            _put_state_text(frame, current.get("state_text", ""), color_bgr, at=text_pos)

        out.write(frame)
        frame_idx += 1

    cap.release()
    out.release()
    print("Wrote:", output)

def main():
    ap = argparse.ArgumentParser(description="Burn-in reticle overlay from same-name JSONL sidecar.")
    ap.add_argument("input", help="Path to MP4, JSONL, or stem without extension (must share same name).")
    ap.add_argument("-o", "--output", help="Output MP4 path (default: <stem>_overlay.mp4)")
    ap.add_argument("--no-text", action="store_true", help="Don’t draw state_text from metadata.")
    ap.add_argument("--text-pos", default="top-right",
                    choices=["top-left","top-right","bottom-left","bottom-right"],
                    help="Where to draw state text.")
    args = ap.parse_args()
    render(args.input, output=args.output, show_state_text=not args.no_text, text_pos=args.text_pos)

if __name__ == "__main__":
    main()
