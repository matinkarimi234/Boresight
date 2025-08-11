# render_from_sidecar.py
import os, sys, json, argparse
import cv2
import numpy as np
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont


FONT_SIZE = 36
FONT_PATH = "digital-7.ttf"
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    ZoneInfo = None

def _stem_paths(stem_or_path):
    p = os.path.expanduser(stem_or_path)
    base, ext = os.path.splitext(p)
    if ext.lower() == ".mp4":
        mp4 = p; jsonl = base + ".jsonl"
    elif ext.lower() == ".jsonl":
        jsonl = p; mp4 = base + ".mp4"
    else:
        mp4 = base + ".mp4"; jsonl = base + ".jsonl"
    if not os.path.isfile(mp4):   raise FileNotFoundError(f"Video not found: {mp4}")
    if not os.path.isfile(jsonl): raise FileNotFoundError(f"Metadata not found: {jsonl}")
    out = base + "_overlay.mp4"
    return mp4, jsonl, out

def _load_header_and_ticks(jsonl_path):
    header, ticks = {}, []
    with open(jsonl_path, "r") as f:
        for line in f:
            if not line.strip(): continue
            obj = json.loads(line)
            if obj.get("type") == "header": header = obj
            elif obj.get("type") == "tick": ticks.append(obj)
    ticks.sort(key=lambda x: x.get("t_rel", 0.0))
    return header, ticks

def _style_from_header(header):
    s = header.get("overlay_style", {}) if header else {}
    radius   = int(s.get("radius", 10))
    ring     = int(s.get("ring_thickness", 1))
    tick_len = int(s.get("tick_length", 300))
    tick_w   = int(s.get("tick_thickness", 1))
    gap      = int(s.get("gap", 2))
    color_rgba = s.get("color", [130, 0, 0, 255])
    if isinstance(color_rgba, (list, tuple)) and len(color_rgba) >= 3:
        r, g, b = color_rgba[:3]
    else:
        r, g, b = (130, 0, 0)
    color_bgr = (int(b), int(g), int(r))
    return dict(radius=radius, ring=ring, tick_len=tick_len, tick_w=tick_w, gap=gap, color=color_bgr)

def _transforms_from_header(header):
    vt = (header.get("video_transform") or {}) if header else {}
    mx = bool(vt.get("mirror_x", False))
    my = bool(vt.get("mirror_y", False))
    rot = int(vt.get("rotate", 0))  # 0|90|180|270 (clockwise)
    return mx, my, rot

def _apply_transform(cx, cy, w, h, mirror_x=False, mirror_y=False, rotate=0):
    if cx is None or cy is None:
        return cx, cy
    if mirror_x: cx = (w - 1) - cx
    if mirror_y: cy = (h - 1) - cy
    if rotate % 360 == 0:
        return cx, cy
    elif rotate % 360 == 90:
        return (w - 1) - cy, cx
    elif rotate % 360 == 180:
        return (w - 1) - cx, (h - 1) - cy
    elif rotate % 360 == 270:
        return cy, (h - 1) - cx
    else:
        return cx, cy
    
def _resolve_tz(tz_name: str):
    """
    Returns a tzinfo:
      - "local" or "" -> None (use system local)
      - valid IANA string -> ZoneInfo instance
    """
    if not tz_name or tz_name.lower() == "local":
        return None
    if ZoneInfo is None:
        raise RuntimeError(
            "zoneinfo not available. Install tzdata or use --tz local.\n"
            "On Raspberry Pi / Debian: sudo apt install -y tzdata"
        )
    try:
        return ZoneInfo(tz_name)
    except Exception as e:
        raise RuntimeError(
            f"Unknown timezone '{tz_name}'. "
            "Make sure tzdata is installed, e.g.: sudo apt install -y tzdata"
        ) from e
    
def _draw_reticle(img, cx, cy, *, radius, ring, tick_len, tick_w, gap, color):
    h, w = img.shape[:2]
    if cx is None or cy is None:
        return
    cx = int(np.clip(cx, 0, w - 1))
    cy = int(np.clip(cy, 0, h - 1))

    cv2.circle(img, (cx, cy), int(radius), color, int(ring), lineType=cv2.LINE_AA)

    x1 = max(0, cx - radius - gap - tick_len)
    x2 = cx - radius - gap
    if x2 > x1:
        cv2.line(img, (x1, cy), (x2, cy), color, int(tick_w), cv2.LINE_AA)

    x3 = cx + radius + gap
    x4 = min(w - 1, cx + radius + gap + tick_len)
    if x4 > x3:
        cv2.line(img, (x3, cy), (x4, cy), color, int(tick_w), cv2.LINE_AA)

    y1 = max(0, cy - radius - gap - tick_len)
    y2 = cy - radius - gap
    if y2 > y1:
        cv2.line(img, (cx, y1), (cx, y2), color, int(tick_w), cv2.LINE_AA)

    y3 = cy + radius + gap
    y4 = min(h - 1, cy + radius + gap + tick_len)
    if y4 > y3:
        cv2.line(img, (cx, y3), (cx, y4), color, int(tick_w), cv2.LINE_AA)

def _put_text(
    img,                     # np.ndarray (BGR)
    font_path,               # str or None
    font_size,               # px
    text,                    # str
    color_bgr,               # (B,G,R)
    margin=20,
    scale=0.8,               # used only for cv2 fallback
    thickness=2,             # used only for cv2 fallback
    at="top-right",
    stroke=0,
    stroke_color_bgr=(0, 0, 0),
):
    if not text:
        return

    h, w = img.shape[:2]

    if font_path:  # ---- draw with Pillow (TTF/OTF) ----
        # Resolve relative font path near this script, if needed
        if not os.path.isabs(font_path):
            candidate = os.path.join(os.path.dirname(__file__), font_path)
            if os.path.exists(candidate):
                font_path = candidate

        try:
            font = ImageFont.truetype(font_path, int(font_size))
        except Exception as e:
            # Fallback to cv2 if font can't be loaded
            font_path = None
        else:
            # Convert to RGB for PIL
            rgb = (int(color_bgr[2]), int(color_bgr[1]), int(color_bgr[0]))
            stroke_rgb = (int(stroke_color_bgr[2]), int(stroke_color_bgr[1]), int(stroke_color_bgr[0]))

            pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img)

            # Measure
            if hasattr(draw, "textbbox"):
                l, t, r, b = draw.textbbox((0, 0), text, font=font, stroke_width=int(stroke))
                tw, th = r - l, b - t
            else:
                tw, th = draw.textsize(text, font=font)

            # Position (top-left anchored box)
            if at == "top-right":
                x, y = w - margin - tw, margin
            elif at == "top-left":
                x, y = margin, margin
            elif at == "bottom-left":
                x, y = margin, h - margin - th
            else:  # bottom-right
                x, y = w - margin - tw, h - margin - th

            draw.text((x, y), text, font=font, fill=rgb,
                      stroke_width=int(stroke), stroke_fill=stroke_rgb)

            # Back to BGR
            img[:] = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            return

    # ---- Fallback: OpenCV Hershey font (no TTF support) ----
    font_cv = cv2.FONT_HERSHEY_SIMPLEX
    scale_cv = max(0.1, float(scale))
    (tw, th), baseline = cv2.getTextSize(text, font_cv, scale_cv, int(thickness))
    if at == "top-right":
        org = (w - margin - tw, margin + th)
    elif at == "top-left":
        org = (margin, margin + th)
    elif at == "bottom-left":
        org = (margin, h - margin)
    else:
        org = (w - margin - tw, h - margin)

    # crude outline in cv2 if you want stroke>0
    if stroke > 0:
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,1),(-1,1),(1,-1)]:
            cv2.putText(img, text, (org[0]+dx, org[1]+dy),
                        font_cv, scale_cv, stroke_color_bgr, int(thickness)+1, cv2.LINE_AA)
    cv2.putText(img, text, org, font_cv, scale_cv, color_bgr, int(thickness), cv2.LINE_AA)

# ... keep your existing helpers (_stem_paths, _load_header_and_ticks, etc.) ...

def _parse_created_utc(header):
    s = (header or {}).get("created_utc")
    if not s:
        return None
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except Exception:
        try:
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
        except Exception:
            return None

# In render(), add tz_name param and use it for the clock:
def render(stem_or_path, output=None, show_state_text=True, text_pos="top-right",
           mirror_x=None, mirror_y=None, rotate=None,
           show_clock=True, clock_pos="bottom-left", clock_scale=0.8,
           tz_name="Asia/Tehran"):
    video_path, jsonl_path, default_out = _stem_paths(stem_or_path)
    if output is None:
        output = default_out

    header, ticks = _load_header_and_ticks(jsonl_path)
    if not ticks:
        raise RuntimeError("No tick rows found in metadata.")

    style = _style_from_header(header)
    color_bgr = style["color"]

    # transforms
    hdr_mx, hdr_my, hdr_rot = _transforms_from_header(header)
    mx = hdr_mx if mirror_x is None else bool(mirror_x)
    my = hdr_my if mirror_y is None else bool(mirror_y)
    rot = hdr_rot if rotate is None else int(rotate)

    # clock base (UTC) and target tz
    start_utc = _parse_created_utc(header)
    if start_utc is None and ticks and ticks[0].get("utc"):
        s0 = ticks[0]["utc"].strip()
        if s0.endswith("Z"): s0 = s0[:-1] + "+00:00"
        try:
            start_utc = datetime.fromisoformat(s0)
        except Exception:
            start_utc = None
    target_tz = _resolve_tz(tz_name)  # None => system local

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

    i = 0
    current = ticks[0]
    next_tick = ticks[1] if len(ticks) > 1 else None

    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok: break
        t_rel = frame_idx / fps

        while next_tick and t_rel >= next_tick.get("t_rel", 0.0):
            i += 1
            current = next_tick
            next_tick = ticks[i+1] if (i + 1) < len(ticks) else None

        ov = current.get("overlay", {})
        cx = ov.get("cx"); cy = ov.get("cy")
        cx, cy = _apply_transform(cx, cy, w, h, mirror_x=mx, mirror_y=my, rotate=rot)

        _draw_reticle(frame, cx, cy,
                      radius=style["radius"], ring=style["ring"],
                      tick_len=style["tick_len"], tick_w=style["tick_w"],
                      gap=style["gap"], color=color_bgr)

        if show_state_text:
            _put_text(frame, FONT_PATH, FONT_SIZE, current.get("state_text", ""), color_bgr, at=text_pos)

        if show_clock and start_utc is not None:
            wall = (start_utc + timedelta(seconds=t_rel))
            wall = wall.astimezone(target_tz) if target_tz else wall.astimezone()  # Tehran or local
            _put_text(frame, FONT_PATH, FONT_SIZE, wall.strftime("%H:%M:%S"), color_bgr, at=clock_pos, scale=clock_scale)

        out.write(frame)
        frame_idx += 1

    cap.release(); out.release()
    print("Wrote:", output)

def main():
    ap = argparse.ArgumentParser(description="Burn-in reticle, state text, and clock from same-name JSONL sidecar.")
    ap.add_argument("input", help="Path to MP4, JSONL, or stem without extension (must share same name).")
    ap.add_argument("-o", "--output", help="Output MP4 path (default: <stem>_overlay.mp4)")
    ap.add_argument("--no-text", action="store_true", help="Don’t draw state_text from metadata.")
    ap.add_argument("--text-pos", default="top-right",
                    choices=["top-left","top-right","bottom-left","bottom-right"],
                    help="Where to draw the state text.")
    ap.add_argument("--mirror-x", action="store_true", help="Mirror overlay horizontally.")
    ap.add_argument("--mirror-y", action="store_true", help="Mirror overlay vertically.")
    ap.add_argument("--rotate", type=int, choices=[0,90,180,270],
                    help="Rotate coordinates clockwise by 0/90/180/270 (after mirroring).")
    ap.add_argument("--no-clock", action="store_true", help="Disable clock burn-in.")
    ap.add_argument("--clock-pos", default="bottom-left",
                    choices=["top-left","top-right","bottom-left","bottom-right"],
                    help="Where to draw the clock (default bottom-left).")
    ap.add_argument("--clock-scale", type=float, default=0.8, help="Clock font scale (default 0.8).")
    ap.add_argument("--tz", default="Asia/Tehran",
                    help="IANA timezone for the clock (default Asia/Tehran; use 'local' for system local).")
    args = ap.parse_args()
    render(
        args.input,
        output=args.output,
        show_state_text=not args.no_text,
        text_pos=args.text_pos,
        mirror_x=args.mirror_x if args.mirror_x else None,
        mirror_y=args.mirror_y if args.mirror_y else None,
        rotate=args.rotate,
        show_clock=not args.no_clock,
        clock_pos=args.clock_pos,
        clock_scale=args.clock_scale,
        tz_name=args.tz,
    )

if __name__ == "__main__":
    main()
