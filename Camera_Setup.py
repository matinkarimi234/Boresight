# Camera_Setup.py
import time
import math

class CameraSetup:
    def __init__(self, resolution=(1640, 922), sensor_mode=5, iso=800, framerate=30,
                 exposure_mode='auto', awb_mode='auto'):
        from picamera import PiCamera
        self.camera = PiCamera()
        self.camera.resolution = resolution
        self.camera.sensor_mode = sensor_mode
        self.camera.iso = iso
        self.camera.framerate = framerate
        self.camera.exposure_mode = exposure_mode
        self.camera.awb_mode = awb_mode

        # Your app sets this; rotation/hflip/vflip are handled in mapping
        self.camera.rotation = 180
        self.camera.hflip = False
        self.camera.vflip = False

        # We need the real display size (from DispmanX)
        self.display_size = None  # set via set_display_size(w, h)

    # ---------- Public API ----------
    def set_display_size(self, w, h):
        """Tell the camera helper the real screen size (from DispmanX)."""
        self.display_size = (int(w), int(h))

    def start_preview(self):
        # Fullscreen is fine; we compute letterbox analytically, no preview.window reads.
        self.camera.start_preview(fullscreen=True)
        time.sleep(0.2)

    def stop_preview(self):
        self.camera.stop_preview()
        self.camera.close()

    def center_zoom_step(self, step: float, max_step: float = 8.0, reticle_norm_display=None):
        """
        Zoom centered on the reticle (provided in DISPLAY-normalized coords (nx,ny)).
        If reticle_norm_display is None, zoom around center of frame.
        No use of preview.window.
        """
        # ----- sanitize zoom -----
        try:
            z = float(step)
        except Exception:
            z = 1.0
        z = max(1.0, min(float(max_step), z))

        # Reset to full frame
        if z <= 1.0001:
            self.camera.zoom = (0.0, 0.0, 1.0, 1.0)
            return

        # ----- choose center (in SENSOR-normalized coords) -----
        if reticle_norm_display is None:
            cx, cy = 0.5, 0.5
        else:
            if self.display_size is None:
                # If not told the display size, assume the reticle coords are already sensor-normalized
                cx, cy = float(reticle_norm_display[0]), float(reticle_norm_display[1])
            else:
                nx_disp = float(reticle_norm_display[0])
                ny_disp = float(reticle_norm_display[1])
                disp_w, disp_h = self.display_size
                mode_w, mode_h = self.camera.resolution
                cx, cy = self._display_norm_to_sensor_norm(
                    nx_disp, ny_disp,
                    display_w=disp_w, display_h=disp_h,
                    mode_w=mode_w, mode_h=mode_h,
                    rotation=self.camera.rotation,
                    hflip=self.camera.hflip,
                    vflip=self.camera.vflip
                )

        # ----- compute ROI with correct aspect (no clamping drift) -----
        roi = self._compute_roi(center_x=cx, center_y=cy, zoom=z,
                                mode_w=self.camera.resolution[0],
                                mode_h=self.camera.resolution[1])
        self.camera.zoom = roi

    # ---------- Helpers (no preview.window used) ----------
    @staticmethod
    def _apply_rotation_flips(nx, ny, rotation=0, hflip=False, vflip=False):
        # Flips first, then 90°-step rotation.
        if hflip:
            nx = 1.0 - nx
        if vflip:
            ny = 1.0 - ny
        r = ((int(rotation) // 90) % 4)
        if r == 1:       # 90°
            nx, ny = ny, 1.0 - nx
        elif r == 2:     # 180°
            nx, ny = 1.0 - nx, 1.0 - ny
        elif r == 3:     # 270°
            nx, ny = 1.0 - ny, nx
        return nx, ny

    @staticmethod
    def _letterbox_rect(display_w, display_h, mode_w, mode_h):
        """Fullscreen letterbox rectangle of the camera image within the display."""
        disp_ar = display_w / float(display_h)
        mode_ar = mode_w / float(mode_h)
        if disp_ar > mode_ar:
            # pillarbox (left/right bars)
            h = display_h
            w = int(round(h * mode_ar))
            x = (display_w - w) // 2
            y = 0
        else:
            # letterbox (top/bottom bars)
            w = display_w
            h = int(round(w / mode_ar))
            x = 0
            y = (display_h - h) // 2
        return x, y, w, h

    def _display_norm_to_sensor_norm(self, nx_disp, ny_disp,
                                     display_w, display_h, mode_w, mode_h,
                                     rotation=0, hflip=False, vflip=False):
        """
        Map DISPLAY-normalized (nx,ny) to SENSOR-normalized (cx,cy),
        accounting for fullscreen letterbox and rotation/flips.
        """
        # 1) display pixels
        x_disp = nx_disp * display_w
        y_disp = ny_disp * display_h

        # 2) preview rect inside display (fullscreen letterbox)
        px, py, pw, ph = self._letterbox_rect(display_w, display_h, mode_w, mode_h)

        # 3) normalize within the preview rect
        if pw <= 0 or ph <= 0:
            return 0.5, 0.5
        nx_prev = (x_disp - px) / float(pw)
        ny_prev = (y_disp - py) / float(ph)
        nx_prev = max(0.0, min(1.0, nx_prev))
        ny_prev = max(0.0, min(1.0, ny_prev))

        # 4) apply orientation to match sensor ROI space
        cx, cy = self._apply_rotation_flips(nx_prev, ny_prev, rotation=rotation,
                                            hflip=hflip, vflip=vflip)
        return cx, cy

    @staticmethod
    def _compute_roi(center_x, center_y, zoom, mode_w, mode_h):
        """
        Return (x,y,w,h) in [0..1] with aspect = mode_w:mode_h.
        Keeps the exact center by shrinking ROI when close to edges
        (instead of sliding/clamping).
        """
        Z = max(1.0, float(zoom))
        ar = mode_w / float(mode_h)  # e.g., ~1.777 for 16:9

        # Start from height; width follows aspect
        h = 1.0 / Z
        w = h * ar

        # If width > 1, scale to fit
        if w > 1.0:
            s = 1.0 / w
            w *= s
            h *= s

        # Keep center exact: compute max box (same aspect) around center that fits
        # Max half sizes by distance to borders:
        max_w = min(2.0 * min(center_x, 1.0 - center_x), 1.0)
        max_h = min(2.0 * min(center_y, 1.0 - center_y), 1.0)
        # Respect aspect by limiting the larger one
        max_w_from_h = max_h * ar
        if max_w > max_w_from_h:
            max_w = max_w_from_h
        else:
            max_h = max_w / ar

        if w > max_w or h > max_h:
            s = min(max_w / w, max_h / h)
            w *= s
            h *= s

        x = center_x - w / 2.0
        y = center_y - h / 2.0

        # numeric guard
        x = max(0.0, min(1.0 - w, x))
        y = max(0.0, min(1.0 - h, y))
        return (x, y, w, h)
