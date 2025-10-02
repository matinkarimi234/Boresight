# Camera_Setup.py
import time

class CameraSetup:
    """
    Camera helper that centers PiCamera.zoom on a given reticle position
    (provided in DISPLAY-normalized coords), with exact centering and correct
    aspect ratio (no drift). Assumes fullscreen preview matches the display
    aspect (e.g., 1280x720 monitor with a 16:9 camera mode).
    """

    def __init__(self, resolution=(1280, 720), sensor_mode=5, iso=800, framerate=30,
                 exposure_mode='auto', awb_mode='auto', rotation=180, hflip=False, vflip=False):
        from picamera import PiCamera
        self.camera = PiCamera()
        self.camera.resolution   = resolution        # e.g., (1640, 922) ~16:9
        # self.camera.sensor_mode  = sensor_mode
        self.camera.iso          = iso
        self.camera.framerate    = framerate
        self.camera.exposure_mode= exposure_mode
        self.camera.awb_mode     = awb_mode

        # Orientation (affects mapping from display -> sensor)
        self.camera.rotation = int(rotation)  # 0, 90, 180, 270
        self.camera.hflip    = bool(hflip)
        self.camera.vflip    = bool(vflip)
        self._display_aspect = None  # width / height (e.g., 16/9)

    # ---------- Public API ----------
    def start_preview(self, fullscreen=True):
        """
        Start the GPU preview. fullscreen=True is fine; this class assumes the
        preview fills the screen (no letterbox) and only applies orientation mapping.
        """
        self.camera.start_preview(fullscreen=fullscreen)
        time.sleep(0.2)  # let it settle

    def stop_preview(self):
        self.camera.stop_preview()
        self.camera.close()

    def set_display_aspect(self, w, h):
        """Tell CameraSetup what aspect the preview fills (e.g., 1280x720)."""
        w = float(w); h = float(h)
        self._display_aspect = (w / h) if (w > 0 and h > 0) else None

    def set_orientation(self, *, rotation=None, hflip=None, vflip=None):
        """Optional: change orientation at runtime."""
        if rotation is not None:
            self.camera.rotation = int(rotation)
        if hflip is not None:
            self.camera.hflip = bool(hflip)
        if vflip is not None:
            self.camera.vflip = bool(vflip)

    def center_zoom_step(self, step: float, max_step: float = 8.0, reticle_norm_display=None):
        try:
            z = float(step)
        except Exception:
            z = 1.0
        if z < 1.0: z = 1.0
        if z > float(max_step): z = float(max_step)

        if z <= 1.0001:
            self.camera.zoom = (0.0, 0.0, 1.0, 1.0)
            return

        # Map display-normalized reticle to sensor-normalized (keep whichever mapping worked for you)
        if reticle_norm_display is None:
            cx, cy = 0.5, 0.5
        else:
            nx, ny = float(reticle_norm_display[0]), float(reticle_norm_display[1])
            # If you used the 'forward' mapping and it landed on the reticle, keep it:
            cx, cy = self._display_to_sensor_forward(nx, ny)
            # If that missed on your rig, switch to the inverse version:
            # cx, cy = self._display_to_sensor_inverse(nx, ny)

        roi = self._roi_exact_center_display_aspect(cx, cy, z)
        self.camera.zoom = roi

    # ---------- Internal helpers ----------
    def _display_to_sensor_no_letterbox(self, nx_disp, ny_disp):
        """
        Convert DISPLAY-normalized (0..1) to SENSOR-normalized (0..1),
        assuming preview fills the screen (no letterbox). We only need to
        undo the camera's orientation (inverse of forward).
        """
        x, y = float(nx_disp), float(ny_disp)
        r = (int(self.camera.rotation) // 90) % 4
        hflip = bool(self.camera.hflip)
        vflip = bool(self.camera.vflip)

        # Inverse of forward pipeline:
        # Forward often behaves like: ROTATE -> H/V FLIP
        # So inverse is: UNDO H/V FLIP -> UNDO ROTATE
        if hflip:
            x = 1.0 - x
        if vflip:
            y = 1.0 - y

        if r == 1:       # undo +90 -> -90
            x, y = 1.0 - y, x
        elif r == 2:     # undo 180
            x, y = 1.0 - x, 1.0 - y
        elif r == 3:     # undo +270 -> -270 (+90)
            x, y = y, 1.0 - x

        # clamp
        if x < 0.0: x = 0.0
        if y < 0.0: y = 0.0
        if x > 1.0: x = 1.0
        if y > 1.0: y = 1.0
        return x, y
    
    def _display_to_sensor_forward(self, nx, ny):
        """
        DISPLAY-normalized -> SENSOR-normalized using the SAME transform order
        the preview applies (often: FLIP then ROTATE).
        """
        x, y = float(nx), float(ny)
        r = (int(self.camera.rotation) // 90) % 4
        hf = bool(self.camera.hflip)
        vf = bool(self.camera.vflip)

        # Forward order: apply flips, then rotation
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


    @staticmethod
    def _clamp01(v):
        return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)

    def _roi_exact_center_display_aspect(self, center_x, center_y, zoom):
        """
        Build (x,y,w,h) with aspect = display aspect (e.g., 16:9).
        Keeps the center EXACT. If near edges, SHRINK (no sliding).
        """
        cx = self._clamp01(float(center_x))
        cy = self._clamp01(float(center_y))

        # Choose aspect: prefer display (prevents any stretch on your 1280x720 monitor)
        if self._display_aspect is not None:
            ar = float(self._display_aspect)               # width / height (e.g., 1.777...)
        else:
            mw, mh = self.camera.resolution
            ar = mw / float(mh) if mh else 16.0/9.0

        Z = 1.0 if zoom < 1.0 else float(zoom)

        # Make a box with w/h = ar and linear shrink 1/Z
        # Use height as the primary dimension (stable), width follows aspect
        h = 1.0 / Z
        w = h * ar

        # If too wide to fit, scale both down (rare unless ar is very wide)
        if w > 1.0:
            s = 1.0 / w
            w *= s; h *= s

        # Compute the largest box (same aspect) centered at (cx,cy) that fits
        max_w_all = 2.0 * min(cx, 1.0 - cx)
        max_h_all = 2.0 * min(cy, 1.0 - cy)
        # Enforce aspect on the max box
        max_w_from_h = max_h_all * ar
        if max_w_all > max_w_from_h:
            max_w = max_w_from_h
            max_h = max_h_all
        else:
            max_w = max_w_all
            max_h = max_w_all / ar

        # If requested box would spill, shrink uniformly (keeps center exact)
        if w > max_w or h > max_h:
            s = min(max_w / w, max_h / h)
            w *= s; h *= s

        x = cx - w / 2.0
        y = cy - h / 2.0

        # Final tiny guards
        if x < 0.0: x = 0.0
        if y < 0.0: y = 0.0
        if x + w > 1.0: x = 1.0 - w
        if y + h > 1.0: y = 1.0 - h

        return (x, y, w, h)
