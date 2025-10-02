# Camera_Setup.py
import time

class CameraSetup:
    """
    Zoom helper for PiCamera that:
      - Maps reticle from DISPLAY-normalized -> SENSOR-normalized with selectable mapping order.
      - Builds an exact-centered ROI with DISPLAY aspect (e.g., 16:9) to prevent stretching.
      - Applies camera.zoom.
      - Projects the SAME sensor point back to DISPLAY after zoom, so the caller can
        move the overlay reticle and keep it on the target.

    Notes:
      - If left/right looks reversed on your hardware, set mapping_mode='inverse'
        (or call set_mapping_mode('inverse')).
      - At 1x, this returns the SAME (nx,ny) you pass in (no reticle reset).
    """

    def __init__(self, resolution=(1280, 720), sensor_mode=5, iso=800, framerate=30,
                 exposure_mode='auto', awb_mode='auto',
                 rotation=180, hflip=False, vflip=False,
                 mapping_mode='forward'):
        from picamera import PiCamera
        self.camera = PiCamera()
        self.camera.resolution    = resolution
        self.camera.sensor_mode = sensor_mode  # uncomment if you rely on a specific mode
        self.camera.iso           = iso
        self.camera.framerate     = framerate
        self.camera.exposure_mode = exposure_mode
        self.camera.awb_mode      = awb_mode

        # Orientation (affects display<->sensor mapping)
        self.camera.rotation = int(rotation)  # 0, 90, 180, 270
        self.camera.hflip    = bool(hflip)
        self.camera.vflip    = bool(vflip)

        # Mapping order selector (fixes "reverse" symptom)
        self._mapping_mode = mapping_mode if mapping_mode in ('forward', 'inverse') else 'forward'

        # Optional override: display aspect (w/h). If None, derive from resolution (or 16:9).
        self._display_aspect = None

    # ---------- Public API ----------
    # def start_preview(self, fullscreen=True):
    #     self.camera.start_preview(fullscreen=fullscreen)
    #     time.sleep(0.2)

    def stop_preview(self):
        self.camera.stop_preview()
        self.camera.close()

    def set_display_aspect(self, w, h):
        """Tell CameraSetup what aspect the preview fills (e.g., 1280x720)."""
        w = float(w); h = float(h)
        self._display_aspect = (w / h) if (w > 0 and h > 0) else None

    def set_orientation(self, *, rotation=None, hflip=None, vflip=None):
        """Optional: change orientation at runtime."""
        if rotation is not None: self.camera.rotation = int(rotation)
        if hflip    is not None: self.camera.hflip    = bool(hflip)
        if vflip    is not None: self.camera.vflip    = bool(vflip)

    def set_mapping_mode(self, mode: str):
        """'forward' or 'inverse'. Use 'inverse' if left/right feels swapped."""
        m = (mode or '').strip().lower()
        if m in ('forward', 'inverse'):
            self._mapping_mode = m

    def center_zoom_step(self, step: float, max_step: float = 8.0, reticle_norm_display=None):
        """
        Center the zoom on the reticle (DISPLAY-normalized), apply it, and return where that
        SAME world point appears on the display AFTER the zoom.
        Return value: (nx_after, ny_after) in [0..1].
        - At 1x, returns the SAME (nx,ny) you passed (so your overlay won't reset).
        """
        # sanitize zoom
        try: z = float(step)
        except: z = 1.0
        if z < 1.0: z = 1.0
        if z > float(max_step): z = float(max_step)

        # default reticle center if none provided
        if reticle_norm_display is None:
            nx_in, ny_in = 0.5, 0.5
        else:
            nx_in, ny_in = float(reticle_norm_display[0]), float(reticle_norm_display[1])

        # 1x -> full frame; do NOT recenter overlay (return same coords)
        if z <= 1.0001:
            self.camera.zoom = (0.0, 0.0, 1.0, 1.0)
            return nx_in, ny_in

        # 1) DISPLAY -> SENSOR (choose mapping mode that matches your rig)
        if self._mapping_mode == 'forward':
            sx, sy = self._display_to_sensor_forward(nx_in, ny_in)
        else:
            sx, sy = self._display_to_sensor_inverse(nx_in, ny_in)

        # 2) Build ROI centered at (sx,sy) with DISPLAY aspect (prevents stretching)
        roi = self._roi_exact_center_display_aspect(sx, sy, z)

        # 3) Apply zoom
        self.camera.zoom = roi

        # 4) Project the SAME sensor point back to DISPLAY after crop/scale/orientation
        nx_after, ny_after = self._project_sensor_point_to_display_after_roi(sx, sy, roi)
        return nx_after, ny_after

    # ---------- Mapping helpers ----------
    def _display_to_sensor_forward(self, nx, ny):
        """
        DISPLAY-normalized -> SENSOR-normalized using the SAME order the preview applies
        (commonly: flips first, then rotation). Often correct for rotation=180 rigs.
        """
        x, y = float(nx), float(ny)
        r  = (int(self.camera.rotation) // 90) % 4
        hf = bool(self.camera.hflip)
        vf = bool(self.camera.vflip)

        # forward: apply flips, then rotation
        if hf: x = 1.0 - x
        if vf: y = 1.0 - y

        if r == 1:       # +90
            x, y = y, 1.0 - x
        elif r == 2:     # 180
            x, y = 1.0 - x, 1.0 - y
        elif r == 3:     # +270
            x, y = 1.0 - y, x

        # clamp
        x = 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)
        y = 0.0 if y < 0.0 else (1.0 if y > 1.0 else y)
        return x, y

    def _display_to_sensor_inverse(self, nx_disp, ny_disp):
        """
        DISPLAY-normalized -> SENSOR-normalized by UNDOing rotation first, then flips.
        Use this if your stack applies transforms in the opposite order and left/right
        look reversed with 'forward'.
        """
        x, y = float(nx_disp), float(ny_disp)
        r  = (int(self.camera.rotation) // 90) % 4
        hf = bool(self.camera.hflip)
        vf = bool(self.camera.vflip)

        # undo rotation
        if r == 1:       # undo +90 -> -90
            x, y = 1.0 - y, x
        elif r == 2:     # undo 180
            x, y = 1.0 - x, 1.0 - y
        elif r == 3:     # undo +270 -> -270 (+90)
            x, y = y, 1.0 - x

        # undo flips
        if hf: x = 1.0 - x
        if vf: y = 1.0 - y

        x = 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)
        y = 0.0 if y < 0.0 else (1.0 if y > 1.0 else y)
        return x, y

    # ---------- ROI builder ----------
    @staticmethod
    def _clamp01(v):
        return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)

    def _roi_exact_center_display_aspect(self, center_x, center_y, zoom):
        """
        Build (x,y,w,h) in SENSOR-normalized coords:
          - exact center at (center_x, center_y)
          - width/height match DISPLAY aspect (no stretch on 1280x720)
          - if near edges, SHRINK box (don't slide) so center remains exact
        """
        cx = self._clamp01(float(center_x))
        cy = self._clamp01(float(center_y))

        # choose aspect: prefer caller-set display aspect, else derive from resolution, else 16:9
        if self._display_aspect is not None:
            ar = float(self._display_aspect)
        else:
            rw, rh = self.camera.resolution
            ar = (rw / float(rh)) if rh else (16.0 / 9.0)

        Z = max(1.0, float(zoom))
        h = 1.0 / Z
        w = h * ar
        if w > 1.0:
            s = 1.0 / w
            w *= s; h *= s

        # largest centered box (same aspect) that fits at (cx,cy)
        max_w_all = 2.0 * min(cx, 1.0 - cx)
        max_h_all = 2.0 * min(cy, 1.0 - cy)
        max_w_from_h = max_h_all * ar
        if max_w_all > max_w_from_h:
            max_w = max_w_from_h; max_h = max_h_all
        else:
            max_w = max_w_all;    max_h = max_w_all / ar

        # shrink uniformly if requested box would spill
        if w > max_w or h > max_h:
            s = min(max_w / w, max_h / h)
            w *= s; h *= s

        x = cx - w / 2.0
        y = cy - h / 2.0
        if x < 0.0: x = 0.0
        if y < 0.0: y = 0.0
        if x + w > 1.0: x = 1.0 - w
        if y + h > 1.0: y = 1.0 - h
        return (x, y, w, h)

    # ---------- Projection back to display ----------
    def _project_sensor_point_to_display_after_roi(self, sx, sy, roi):
        """
        Given sensor point (sx,sy) and applied ROI=(x,y,w,h), return its DISPLAY-normalized
        coordinates after crop+scale+orientation. Assumes fullscreen preview (no letterbox).
        """
        x, y, w, h = roi
        # crop+scale into ROI space
        u = (float(sx) - x) / w
        v = (float(sy) - y) / h

        # inverse of the *forward* mapping to reach display coords
        nx_disp, ny_disp = self._sensor_to_display_inverse(u, v)
        # clamp
        nx_disp = 0.0 if nx_disp < 0.0 else (1.0 if nx_disp > 1.0 else nx_disp)
        ny_disp = 0.0 if ny_disp < 0.0 else (1.0 if ny_disp > 1.0 else ny_disp)
        return nx_disp, ny_disp

    def _sensor_to_display_inverse(self, u, v):
        """
        Inverse of _display_to_sensor_forward:
          - undo rotation
          - then undo flips
        Input u,v are pre-orientation preview-normalized.
        """
        x, y = float(u), float(v)
        r  = (int(self.camera.rotation) // 90) % 4
        hf = bool(self.camera.hflip)
        vf = bool(self.camera.vflip)

        # undo rotation
        if r == 1:
            x, y = 1.0 - y, x
        elif r == 2:
            x, y = 1.0 - x, 1.0 - y
        elif r == 3:
            x, y = y, 1.0 - x

        # undo flips
        if hf: x = 1.0 - x
        if vf: y = 1.0 - y

        # clamp
        x = 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)
        y = 0.0 if y < 0.0 else (1.0 if y > 1.0 else y)
        return x, y
