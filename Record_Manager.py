import os, json, time, threading
from datetime import datetime

def _ts_now_utc():
    # ISO-8601 with milliseconds and Z
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

def _ensure_dir(p):
    os.makedirs(p, exist_ok=True)


def now_stamp_local(ms=True):
    dt = datetime.now()  # system local time
    return dt.strftime("%Y%m%d_%H%M%S_%f")[:-3] if ms else dt.strftime("%Y%m%d_%H%M%S")

def _timestamped_basename(prefix="rec", ext="mp4"):
    return f"{prefix}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.{ext}"

def unique_stem(base_dir, prefix="VID"):
    stem = f"{prefix}_{now_stamp_local(ms=True)}"  # e.g., VID_20250811_143012_123
    # ensure uniqueness if called twice in same ms
    candidate = os.path.join(base_dir, stem)
    n = 1
    while os.path.exists(candidate + ".mp4") or os.path.exists(candidate + ".jsonl"):
        candidate = os.path.join(base_dir, f"{stem}-{n}")
        n += 1
    return os.path.basename(candidate)  # return stem only

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
                # snapshot overlay + state text
                try:
                    cx = int(getattr(self.overlay_display, "vertical_x"))
                    cy = int(getattr(self.overlay_display, "horizontal_y"))
                except Exception:
                    cx = cy = None

                row = {
                    "type": "tick",
                    "utc": _ts_now_utc(),
                    "t_rel": round(now_mono - self._t0, 3),  # seconds from start
                    "overlay": {"cx": cx, "cy": cy},
                    "state_text": (self.state_text_fn() or ""),
                }
                self._file.write(json.dumps(row) + "\n")
                next_t += period
            else:
                time.sleep(min(0.01, max(0.0, next_t - now_mono)))
        # flush/close on stop in stop()

    def stop(self):
        self._stop.set()
        if self._th:
            self._th.join(timeout=2.0)
        if self._file:
            self._file.flush()
            self._file.close()
            self._file = None

class RecordingManager:
    def __init__(self, base_dir="~/Saved_Videos"):
        self.base_dir = os.path.expanduser(base_dir)
        _ensure_dir(self.base_dir)
        self.video_path = None
        self.meta_path = None
        self.meta = None
        self.active = False

    def start(self, camera, overlay_display, state_text_fn):
        if self.active:
            return self.video_path

        stem = unique_stem(self.base_dir, prefix="VID")   # <- same stem for both
        self.video_path = os.path.join(self.base_dir, f"{stem}.mp4")
        self.meta_path  = os.path.join(self.base_dir, f"{stem}.jsonl")

        if hasattr(camera, "start_recording"):
            camera.start_recording(self.video_path)
        else:
            raise RuntimeError("Camera_Setup has no start_recording(path)")

        self.meta = MetadataRecorder(
            jsonl_path=self.meta_path,
            video_path=self.video_path,           # <- pass video here
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
        # Stop metadata first so last tick is captured
        if self.meta:
            self.meta.stop()
        # Stop camera
        if hasattr(camera, "stop_recording"):
            camera.stop_recording()
        self.active = False
        return self.video_path, self.meta_path
