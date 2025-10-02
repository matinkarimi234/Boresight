# Camera_Setup.py
import time

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

        # Your orientation
        self.camera.rotation = 180
        self.camera.hflip = False
        self.camera.vflip = False

        # Let your app tell us the actual screen size (from DispmanX)
        self.display_size = None  # (W, H)

    # ---------- public ----------
    def set_display_size(self, w, h):
        self.display_size = (int(w), int(h))

    def start_preview(self):
        # Fullscreen is fine; we’ll compute the letterbox analytically
        self.camera.start_preview(fullscreen=True)
        time.sleep(0.2)

    def stop_preview(self):
        self.camera.stop_preview()
        self.camera.close()

    def center_zoom_step(self, step: float, max_step: float = 8.0, reticle_norm_display=None):
        """
        Zoom centered on reticle given in DISPLAY-normalized coords (nx,ny ∈ [0..1]).
        No preview.window is used.
        """
        # sanitize zoom
        try:
            z = float(step)
        except Exception:
            z = 1.0
        z = max(1.0, min(float(max_step), z))

        # no zoom
        if z <= 1.0001:
            self.camera.zoom = (0.0, 0.0, 1.0, 1.0)
            return

        # map display-normalized → sensor-normalized (inverse orientation!)
        if reticle_norm_display is None:
            cx, cy = 0.5, 0.5
        else:
            nx_disp = float(reticle_norm_display[0])
            ny_disp = float(reticle_norm_display[1])

            if self.display_size is None:
                # assume caller is already providing sensor-normalized
                cx, cy = nx_disp, ny_disp
            else:
                disp_w, disp_h = self.display_size
                mode_w, mode_h = self.camera.resolution
                cx, cy = self._display_norm_to_sensor_norm_inverse(
                    nx_disp, ny_disp,
                    display_w=disp_w, display_h=disp_h,
                    mode_w=mode_w, mode_h=mode_h,
                    rotation=self.camera.rotation,
                    hflip=self.camera.hflip, vflip=self.camera.vflip
                )

        # exact-center ROI with correct aspect (no drift)
        roi = self._compute_roi_exact_center(cx, cy, z, self.camera.resolution[0], self.camera.resolution[1])
        self.camera.zoom = roi

    # ---------- helpers ----------
    @staticmethod
    def _letterbox_rect(display_w, display_h, mode_w, mode_h):
        """Preview rect inside display for fullscreen keep-aspect."""
        disp_ar = display_w / float(display_h)
        mode_ar = mode_w / float(mode_h)
        if disp_ar > mode_ar:
            # pillarbox
            h = display_h
            w = int(round(h * mode_ar))
            x = (display_w - w) // 2
            y = 0
        else:
            # letterbox
            w = display_w
            h = int(round(w / mode_ar))
            x = 0
            y = (display_h - h) // 2
        return x, y, w, h

    @staticmethod
    def _apply_inverse_orientation(nx, ny, rotation=0, hflip=False, vflip=False):
        """
        **Inverse** mapping: preview/display → sensor.
        Undo rotation FIRST (inverse of forward), then undo flips.
        """
        # undo rotation
        r = ((int(rotation) // 90) % 4)
        if r == 1:       # forward was +90; inverse is -90
            nx, ny = 1.0 - ny, nx
        elif r == 2:     # 180 inverse is the same
            nx, ny = 1.0 - nx, 1.0 - ny
        elif r == 3:     # forward was +270; inverse is -270 (+90)
            nx, ny = ny, 1.0 - nx

        # undo flips (inverse of forward flips is the same flip)
        if hflip:
            nx = 1.0 - nx
        if vflip:
            ny = 1.0 - ny
        return nx, ny

    def _display_norm_to_sensor_norm_inverse(self, nx_disp, ny_disp,
                                             display_w, display_h, mode_w, mode_h,
                                             rotation=0, hflip=False, vflip=False):
        """
        DISPLAY-normalized → SENSOR-normalized.
        1) locate letterboxed preview rect
        2) normalize within preview rect
        3) apply **inverse** orientation to reach sensor space
        """
        # display pixels
        x_disp = nx_disp * display_w
        y_disp = ny_disp * display_h

        # preview rect
        px, py, pw, ph = self._letterbox_rect(display_w, display_h, mode_w, mode_h)
        if pw <= 0 or ph <= 0:
            return 0.5, 0.5

        # preview-normalized
        nx_prev = (x_disp - px) / float(pw)
        ny_prev = (y_disp - py) / float(ph)
        nx_prev = max(0.0, min(1.0, nx_prev))
        ny_prev = max(0.0, min(1.0, ny_prev))

        # inverse orientation to sensor
        cx, cy = self._apply_inverse_orientation(nx_prev, ny_prev,
                                                 rotation=rotation, hflip=hflip, vflip=vflip)
        # clamp
        cx = max(0.0, min(1.0, cx))
        cy = max(0.0, min(1.0, cy))
        return cx, cy

    @staticmethod
    def _compute_roi_exact_center(center_x, center_y, zoom, mode_w, mode_h):
        """
        Keep exact center by shrinking ROI if near edges.
        Aspect = mode_w:mode_h (matches video mode), so GPU won’t re-clamp/shift.
        """
        Z = max(1.0, float(zoom))
        ar = mode_w / float(mode_h)

        # start with height; width follows aspect
        h = 1.0 / Z
        w = h * ar

        # fit inside [0..1]
        if w > 1.0:
            s = 1.0 / w
            w *= s; h *= s

        # compute maximum box (same aspect) centered at (cx,cy) that fits
        # max half-sizes by distance to borders
        max_w_all = 2.0 * min(center_x, 1.0 - center_x)
        max_h_all = 2.0 * min(center_y, 1.0 - center_y)

        # enforce aspect: cap width/height consistently
        # (choose the limiting dimension and scale the other)
        # limit by height
        w_from_h = max_h_all * ar
        # limit by width
        h_from_w = max_w_all / ar

        max_w = min(max_w_all, w_from_h)
        max_h = min(max_h_all, h_from_w)

        # if requested box is larger than allowed, shrink uniformly
        if w > max_w or h > max_h:
            s = min(max_w / w, max_h / h)
            w *= s; h *= s

        x = center_x - w / 2.0
        y = center_y - h / 2.0

        # final guards
        x = max(0.0, min(1.0 - w, x))
        y = max(0.0, min(1.0 - h, y))
        return (x, y, w, h)
