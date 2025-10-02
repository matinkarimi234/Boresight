# Camera_Setup.py
import time

class CameraSetup:
    """
    Zoom helper for PiCamera that:
      - Maps reticle from DISPLAY-normalized -> SENSOR-normalized.
      - Auto-selects mapping order (forward vs inverse) each zoom to avoid mirrored jumps.
      - Builds an exact-centered, quantized ROI with the *camera video* aspect (no stretching).
      - Applies camera.zoom.
      - Projects the SAME sensor point back to DISPLAY after zoom so callers can use it if needed.

    Notes:
      - While zoomed (>1x), snap the overlay reticle to exact screen center (0.5, 0.5).
      - When returning to 1x, restore the saved pre-zoom reticle position.
    """

    def __init__(self, resolution=(1280, 720), sensor_mode=5, iso=800, framerate=30,
                 exposure_mode='auto', awb_mode='auto',
                 rotation=0, hflip=False, vflip=False,
                 mapping_mode='forward'):
        from picamera import PiCamera
        self.camera = PiCamera()
        self.camera.resolution    = resolution
        self.camera.sensor_mode   = sensor_mode
        self.camera.iso           = iso
        self.camera.framerate     = framerate
        self.camera.exposure_mode = exposure_mode
        self.camera.awb_mode      = awb_mode

        # Orientation (affects display<->sensor mapping)
        self.camera.rotation = int(rotation)  # 0, 90, 180, 270
        self.camera.hflip    = bool(hflip)
        self.camera.vflip    = bool(vflip)

        # User preference; we still auto-pick per-zoom for robustness
        self._mapping_mode = mapping_mode if mapping_mode in ('forward', 'inverse') else 'forward'

        # Optional override: display aspect (w/h). If None, derive from resolution.
        self._display_aspect = None

        # 180 deg rotation
        self.camera.set_orientation(rotation=0, hflip=True, vflip=True)

    # ---------- Public API ----------
    def start_preview(self, fullscreen=True, **kw):
        self.camera.start_preview(fullscreen=fullscreen, **kw)
        time.sleep(0.2)

    def stop_preview(self):
        try:
            self.camera.stop_preview()
        finally:
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
        """'forward' or 'inverse' (kept for manual override / debugging)."""
        m = (mode or '').strip().lower()
        if m in ('forward', 'inverse'):
            self._mapping_mode = m

    def center_zoom_step(self, step: float, max_step: float = 8.0, reticle_norm_display=None):
        """
        Center the zoom on the reticle (DISPLAY-normalized), apply it, and return where that
        SAME world point appears on the display AFTER the zoom.
        Return value: (nx_after, ny_after) in [0..1].
        - At 1x, returns the SAME (nx,ny) you passed (so overlay won’t reset).
        - For >1x, you should snap the overlay reticle to (0.5, 0.5) visually.
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

        # ---- Auto-select mapping: try both and choose the one that lands closest to (0.5, 0.5) ----
        candidates = []

        # Candidate A: 'forward'
        sxA, syA = self._display_to_sensor_forward(nx_in, ny_in)
        roiA = self._roi_for_zoom(sxA, syA, z)
        uA = (sxA - roiA[0]) / roiA[2]; vA = (syA - roiA[1]) / roiA[3]
        nxA, nyA = self._sensor_to_display_inverse(uA, vA)  # inverse of forward
        errA = (nxA - 0.5)**2 + (nyA - 0.5)**2
        candidates.append(('forward', roiA, (nxA, nyA), errA))

        # Candidate B: 'inverse'
        sxB, syB = self._display_to_sensor_inverse(nx_in, ny_in)
        roiB = self._roi_for_zoom(sxB, syB, z)
        uB = (sxB - roiB[0]) / roiB[2]; vB = (syB - roiB[1]) / roiB[3]
        nxB, nyB = self._sensor_to_display_forward(uB, vB)  # forward of inverse
        errB = (nxB - 0.5)**2 + (nyB - 0.5)**2
        candidates.append(('inverse', roiB, (nxB, nyB), errB))

        # Pick the mapping whose projected point is closest to screen center
        mode, roi, (nx_after, ny_after), _ = min(candidates, key=lambda t: t[3])
        self._mapping_mode = mode  # remember what worked (nice for consistency)

        # Apply zoom
        self.camera.zoom = roi
        return nx_after, ny_after

    # ---------- Quantized, video-aspect ROI ----------
    def _roi_exact_center_video_aspect_quantized(self, center_x, center_y, zoom):
        """
        Exact-centered (x,y,w,h) in SENSOR-normalized coords with:
          - aspect = camera.resolution (video stream)
          - sizes quantized to even pixels (avoid MMAL rounding/stretch)
          - if near edges, shrink (don't slide) to keep center exact
        """
        # --- inputs clamped ---
        cx = float(center_x); cy = float(center_y)
        cx = 0.0 if cx < 0.0 else (1.0 if cx > 1.0 else cx)
        cy = 0.0 if cy < 0.0 else (1.0 if cy > 1.0 else cy)

        rw, rh = self.camera.resolution  # stream (e.g. 1280x720)
        rw = int(rw); rh = int(rh)
        ar = (rw / float(rh)) if rh else (16.0/9.0)

        Z = max(1.0, float(zoom))

        # --- target size in OUTPUT pixels (quantize to even) ---
        h_pix = rh / Z
        w_pix = h_pix * ar

        def even(i):
            i = int(round(i))
            return i if (i % 2 == 0) else (i-1 if i > 1 else 2)

        h_pix = max(2, even(h_pix))
        w_pix = max(2, even(w_pix))

        # maximum centered box that fits at (cx,cy) in pixel units (keep 16:9)
        max_w_all = 2.0 * min(cx*rw, (1.0-cx)*rw)
        max_h_all = 2.0 * min(cy*rh, (1.0-cy)*rh)
        max_w_from_h = max_h_all * ar

        if max_w_all > max_w_from_h:
            max_w_pix = int(max_w_from_h)
            max_h_pix = int(max_h_all)
        else:
            max_w_pix = int(max_w_all)
            max_h_pix = int(max_w_all / ar)

        # quantize maxima to even too
        max_w_pix = max(2, max_w_pix - (max_w_pix % 2))
        max_h_pix = max(2, max_h_pix - (max_h_pix % 2))

        # shrink uniformly if needed to fit
        if w_pix > max_w_pix or h_pix > max_h_pix:
            s = min(max_w_pix / float(w_pix), max_h_pix / float(h_pix))
            w_pix = max(2, even(w_pix * s))
            h_pix = max(2, even(h_pix * s))

        # convert size back to normalized
        w = w_pix / float(rw)
        h = h_pix / float(rh)

        # keep exact center by recomputing x,y from center (don’t slide)
        x = cx - w/2.0
        y = cy - h/2.0

        # if any tiny spill from rounding, shave size (don’t move center)
        if x < 0.0:
            spill = -x
            w -= 2*spill
            x = 0.0
        if y < 0.0:
            spill = -y
            h -= 2*spill
            y = 0.0
        if x + w > 1.0:
            spill = (x + w) - 1.0
            w -= 2*spill
        if y + h > 1.0:
            spill = (y + h) - 1.0
            h -= 2*spill

        # final clamps
        if w < 0.0: w = 0.0
        if h < 0.0: h = 0.0
        return (x, y, w, h)

    def _roi_for_zoom(self, sx, sy, z):
        """Wrapper to choose the quantized, video-aspect ROI."""
        return self._roi_exact_center_video_aspect_quantized(sx, sy, z)

    # ---------- Mapping helpers ----------
    def _display_to_sensor_forward(self, nx, ny):
        """
        DISPLAY-normalized -> SENSOR-normalized using the SAME order preview often applies:
        flips first, then rotation.
        """
        x, y = float(nx), float(ny)
        r  = (int(self.camera.rotation) // 90) % 4
        hf = bool(self.camera.hflip)
        vf = bool(self.camera.vflip)

        # flips, then rotation
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
        Use this if your stack applies transforms in the opposite order.
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

    def _sensor_to_display_forward(self, u, v):
        """
        Forward of _display_to_sensor_inverse:
          - apply rotation
          - then apply flips
        Input u,v are pre-orientation preview-normalized (0..1).
        """
        x, y = float(u), float(v)
        r  = (int(self.camera.rotation) // 90) % 4
        hf = bool(self.camera.hflip)
        vf = bool(self.camera.vflip)

        # apply rotation
        if r == 1:
            x, y = 1.0 - y, x
        elif r == 2:
            x, y = 1.0 - x, 1.0 - y
        elif r == 3:
            x, y = y, 1.0 - x

        # then flips
        if hf: x = 1.0 - x
        if vf: y = 1.0 - y

        # clamp
        x = 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)
        y = 0.0 if y < 0.0 else (1.0 if y > 1.0 else y)
        return x, y

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
