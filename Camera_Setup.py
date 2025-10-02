# Camera_Setup.py
import time

class CameraSetup:
    """
    Camera helper that centers PiCamera.zoom on a given reticle position
    (provided in DISPLAY-normalized coords), with exact centering and correct
    aspect ratio (no drift). Assumes fullscreen preview matches the display
    aspect (e.g., 1280x720 monitor with a 16:9 camera mode).
    """

    def __init__(self, resolution=(1640, 922), sensor_mode=5, iso=800, framerate=30,
                 exposure_mode='auto', awb_mode='auto', rotation=180, hflip=False, vflip=False):
        from picamera import PiCamera
        self.camera = PiCamera()
        self.camera.resolution   = resolution        # e.g., (1640, 922) ~16:9
        self.camera.sensor_mode  = sensor_mode
        self.camera.iso          = iso
        self.camera.framerate    = framerate
        self.camera.exposure_mode= exposure_mode
        self.camera.awb_mode     = awb_mode

        # Orientation (affects mapping from display -> sensor)
        self.camera.rotation = int(rotation)  # 0, 90, 180, 270
        self.camera.hflip    = bool(hflip)
        self.camera.vflip    = bool(vflip)

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

    def set_orientation(self, *, rotation=None, hflip=None, vflip=None):
        """Optional: change orientation at runtime."""
        if rotation is not None:
            self.camera.rotation = int(rotation)
        if hflip is not None:
            self.camera.hflip = bool(hflip)
        if vflip is not None:
            self.camera.vflip = bool(vflip)

    def center_zoom_step(self, step: float, max_step: float = 8.0, reticle_norm_display=None):
        """
        Apply zoom such that the ROI is centered on the given reticle position.

        Parameters
        ----------
        step : float
            Zoom level (1..max_step). 1 means full frame.
        max_step : float
            Maximum allowed zoom factor (clamped).
        reticle_norm_display : (nx, ny) or None
            Reticle center in DISPLAY-normalized coords (0..1). If None, uses (0.5, 0.5).
        """
        # sanitize zoom
        try:
            z = float(step)
        except Exception:
            z = 1.0
        if z < 1.0:
            z = 1.0
        if z > float(max_step):
            z = float(max_step)

        # no zoom -> full frame
        if z <= 1.0001:
            self.camera.zoom = (0.0, 0.0, 1.0, 1.0)
            return

        # map reticle from DISPLAY-normalized to SENSOR-normalized (inverse orientation only)
        if reticle_norm_display is None:
            cx, cy = 0.5, 0.5
        else:
            nx, ny = float(reticle_norm_display[0]), float(reticle_norm_display[1])
            cx, cy = self._display_to_sensor_no_letterbox(nx, ny)

        # exact-center ROI with the camera mode's aspect (prevents GPU clamping drift)
        mode_w, mode_h = self.camera.resolution
        roi = self._roi_exact_center(cx, cy, z, mode_w, mode_h)

        # apply
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

    @staticmethod
    def _roi_exact_center(center_x, center_y, zoom, mode_w, mode_h):
        """
        Build (x, y, w, h) in [0..1] keeping the exact center (cx,cy).
        The ROI uses the camera mode aspect (mode_w:mode_h). If the requested
        box would spill outside near edges, it SHRINKS w/h (same aspect) so the
        center remains exact; it never slides.
        """
        Z  = 1.0 if zoom < 1.0 else float(zoom)
        ar = mode_w / float(mode_h)  # e.g., ~1.777... for 16:9

        # Start from height; width follows aspect
        h = 1.0 / Z
        w = h * ar

        # Fit into [0..1] if width spills
        if w > 1.0:
            s = 1.0 / w
            w *= s
            h *= s

        # Maximum centered box (same aspect) around (center_x, center_y) that fits
        max_w_all = 2.0 * min(center_x, 1.0 - center_x)
        max_h_all = 2.0 * min(center_y, 1.0 - center_y)

        # Enforce aspect on the max box
        max_w_from_h = max_h_all * ar
        if max_w_all > max_w_from_h:
            max_w = max_w_from_h
            max_h = max_h_all
        else:
            max_w = max_w_all
            max_h = max_w_all / ar

        # If requested box is too big to keep the center, shrink (don't slide)
        if w > max_w or h > max_h:
            s = min(max_w / w, max_h / h)
            w *= s
            h *= s

        x = center_x - w / 2.0
        y = center_y - h / 2.0

        # numeric guards
        if x < 0.0: x = 0.0
        if y < 0.0: y = 0.0
        if x + w > 1.0: x = 1.0 - w
        if y + h > 1.0: y = 1.0 - h

        return (x, y, w, h)
