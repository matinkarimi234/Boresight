import os, json, time, threading, shutil, subprocess
from datetime import datetime

def _ts_now_utc():
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

def _ensure_dir(p):
    if p:
        os.makedirs(p, exist_ok=True)

def now_stamp_local(ms=True):
    dt = datetime.now()
    return dt.strftime("%Y%m%d_%H%M%S_%f")[:-3] if ms else dt.strftime("%Y%m%d_%H%M%S")

def unique_stem(base_dir, prefix="VID"):
    base_dir = os.path.expanduser(base_dir)
    _ensure_dir(base_dir)
    stem = f"{prefix}_{now_stamp_local(ms=True)}"
    n = 1
    def clashes(s):
        return any(os.path.exists(os.path.join(base_dir, s + ext))
                   for ext in (".mp4", ".jsonl", ".h264"))
    candidate = stem
    while clashes(candidate):
        candidate = f"{stem}-{n}"
        n += 1
    return candidate  # return stem only

class MetadataRecorder:
    def __init__(self, jsonl_path, video_path, overlay_display, state_text_fn, extra_header=None, hz=1):
        self.jsonl_path = jsonl_path
        self.video_path = video_path
        self.overlay_display = overlay_display
        self.state_text_fn = state_text_fn or (lambda: "")
        self.extra_header = extra_header or {}
        self.hz = max(1, int(hz))
        self._stop = threading.Event()
        self._th = None
        self._t0 = None
        self._file = None

    def start(self):
        _ensure_dir(os.path.dirname(self.jsonl_path))
        self._file = open(self.jsonl_path, "w", buffering=1)
        self._t0 = time.monotonic()

        header = {
            "type": "header",
            "schema": "Boresight_Camera_V1",
            "created_local": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "created_utc": _ts_now_utc(),
            "video_file": os.path.basename(self.video_path),
            "base_stem": os.path.splitext(os.path.basename(self.video_path))[0],
            "overlay_style": {
                "radius": getattr(self.overlay_display, "radius", None),
                "ring_thickness": getattr(self.overlay_display, "ring_thickness", None),
                "tick_length": getattr(self.overlay_display, "tick_length", None),
                "tick_thickness": getattr(self.overlay_display, "tick_thickness", None),
                "gap": getattr(self.overlay_display, "gap", None),
                "color": getattr(self.overlay_display, "color", None),
            },
            **self.extra_header
        }
        self._file.write(json.dumps(header) + "\n")

        self._th = threading.Thread(target=self._run, daemon=True)
        self._th.start()

    def _run(self):
        period = 1.0 / self.hz
        next_t = time.monotonic()
        while not self._stop.is_set():
            now_mono = time.monotonic()
            if now_mono >= next_t:
                try:
                    cx = int(getattr(self.overlay_display, "vertical_x"))
                    cy = int(getattr(self.overlay_display, "horizontal_y"))
                except Exception:
                    cx = cy = None

                row = {
                    "type": "tick",
                    "utc": _ts_now_utc(),
                    "t_rel": round(now_mono - self._t0, 3),
                    "overlay": {"cx": cx, "cy": cy},
                    "state_text": (self.state_text_fn() or ""),
                }
                self._file.write(json.dumps(row) + "\n")
                next_t += period
            else:
                time.sleep(min(0.01, max(0.0, next_t - now_mono)))

    def stop(self):
        self._stop.set()
        if self._th:
            self._th.join(timeout=2.0)
        if self._file:
            self._file.flush()
            self._file.close()
            self._file = None

# --- helpers for remux ---
def _guess_fps(camera_obj, default=30.0):
    # Try common spots: your CameraSetup may have .camera (PiCamera) or direct .framerate
    for attr in ("framerate",):
        v = getattr(camera_obj, attr, None)
        if v:
            try:
                return float(v)
            except Exception:
                pass
    cam = getattr(camera_obj, "camera", None)
    if cam is not None:
        v = getattr(cam, "framerate", None)
        if v:
            try:
                return float(v)
            except Exception:
                pass
    return float(default)

def _remux_h264_to_mp4(h264_path, mp4_path, fps):
    _ensure_dir(os.path.dirname(mp4_path))
    if shutil.which("MP4Box"):
        subprocess.run(["MP4Box", "-add", h264_path, "-new", mp4_path], check=True)
        return True
    if shutil.which("ffmpeg"):
        subprocess.run([
            "ffmpeg", "-y",
            "-r", str(fps), "-i", h264_path,
            "-c", "copy",
            mp4_path
        ], check=True)
        return True
    return False

class RecordingManager:
    def __init__(self, base_dir="~/Saved_Videos", remove_h264_after_remux=True):
        self.base_dir = os.path.expanduser(base_dir)
        _ensure_dir(self.base_dir)
        self.video_path = None        # intended final (mp4)
        self.meta_path = None
        self.meta = None
        self.active = False

        # fallback vars when PiCamera can't write MP4 directly
        self.stem = None
        self.raw_h264_path = None
        self.needs_remux = False
        self.remove_h264_after_remux = remove_h264_after_remux

    def start(self, camera, overlay_display, state_text_fn):
        if self.active:
            return self.video_path

        self.stem = unique_stem(self.base_dir, prefix="VID")  # same stem
        intended_mp4 = os.path.join(self.base_dir, f"{self.stem}.mp4")
        self.meta_path = os.path.join(self.base_dir, f"{self.stem}.jsonl")

        # Try to start recording to MP4; if camera rejects (e.g., PiCamera), fall back to .h264
        self.needs_remux = False
        self.raw_h264_path = None
        try:
            if hasattr(camera, "start_recording"):
                camera.start_recording(intended_mp4)
                self.video_path = intended_mp4
            else:
                raise RuntimeError("Camera_Setup has no start_recording(path)")
        except Exception as e:
            # Fallback: PiCamera only supports H.264 elementary stream
            self.raw_h264_path = os.path.join(self.base_dir, f"{self.stem}.h264")
            if hasattr(camera, "start_recording"):
                camera.start_recording(self.raw_h264_path)
                self.video_path = intended_mp4  # final goal after remux
                self.needs_remux = True
            else:
                raise

        # Start metadata (always references the intended final video name)
        self.meta = MetadataRecorder(
            jsonl_path=self.meta_path,
            video_path=self.video_path,
            overlay_display=overlay_display,
            state_text_fn=state_text_fn,
            extra_header={},
            hz=1
        )
        self.meta.start()
        self.active = True
        return self.video_path

    def stop(self, camera):
        if not self.active:
            return

        # stop metadata capture
        if self.meta:
            self.meta.stop()

        # stop camera recording
        if hasattr(camera, "stop_recording"):
            try:
                camera.stop_recording()
            except Exception:
                pass

        final_video = self.video_path
        remux_ok = False

        # If we recorded raw .h264, try to remux it now
        if self.needs_remux and self.raw_h264_path and os.path.exists(self.raw_h264_path):
            fps = _guess_fps(camera)
            try:
                remux_ok = _remux_h264_to_mp4(self.raw_h264_path, self.video_path, fps)
                if remux_ok and self.remove_h264_after_remux:
                    try:
                        os.remove(self.raw_h264_path)
                    except OSError:
                        pass
            except Exception:
                remux_ok = False

            if not remux_ok:
                # fall back to returning the .h264 if remux failed
                final_video = self.raw_h264_path

        # Append a footer row with the actual outcome
        try:
            with open(self.meta_path, "a") as f:
                f.write(json.dumps({
                    "type": "footer",
                    "stopped_utc": _ts_now_utc(),
                    "final_video_file": os.path.basename(final_video),
                    "intended_video_file": os.path.basename(self.video_path),
                    "remux_ok": remux_ok,
                }) + "\n")
        except Exception:
            pass

        self.active = False
        return final_video, self.meta_path
