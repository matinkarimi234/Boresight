from picamera import PiCamera

class CameraSetup:
    def __init__(self, resolution=(1640, 922), sensor_mode=5, iso=800, framerate=30,
                 exposure_mode='auto', awb_mode='auto', rotation=180, hflip=False, vflip=False):
        self.camera = PiCamera()
        self.camera.resolution = resolution
        self.camera.sensor_mode = sensor_mode
        self.camera.iso = iso
        self.camera.framerate = framerate
        self.camera.exposure_mode = exposure_mode
        self.camera.awb_mode = awb_mode
        self.camera.rotation = rotation        # 0, 90, 180, 270
        self.camera.hflip = bool(hflip)
        self.camera.vflip = bool(vflip)

        self._preview_window = None  # (x,y,w,h)

    def start_preview(self, overlay=None):
        """
        Start preview exactly under the overlay to keep coordinate mapping 1:1.
        """
        if overlay is not None:
            x, y, w, h = overlay.overlay_display_rect()
            self.camera.start_preview(fullscreen=False, window=(x, y, w, h))
            self._preview_window = (x, y, w, h)
        else:
            # Fallback: fullscreen (mapping may be off if overlay isn't fullscreen)
            self.camera.start_preview(fullscreen=True)
            # If you *must* run fullscreen, set _preview_window to the display size
            # and ensure overlay also covers the full display.
            self._preview_window = (0, 0, 0, 0)  # unknown; avoid using

    def stop_preview(self):
        self.camera.stop_preview()

    # --- mapping helpers -------------------------------------------------------
    def _apply_rotation_flips_to_preview_norm(self, nx, ny):
        """
        Map normalized coords from *displayed preview* to *sensor/zoom* coords,
        inverting camera.rotation/hflip/vflip effects.
        """
        # invert rotation first
        r = (self.camera.rotation or 0) % 360
        if r == 0:
            sx, sy = nx, ny
        elif r == 90:
            # display = rotate(sensor,+90) -> sensor = rotate(display,-90)
            sx, sy = ny, 1.0 - nx
        elif r == 180:
            sx, sy = 1.0 - nx, 1.0 - ny
        elif r == 270:
            sx, sy = 1.0 - ny, nx
        else:
            # non-orthogonal rotations aren't supported by picamera anyway
            sx, sy = nx, ny

        # invert flips (if the preview shows hflip/vflip)
        if self.camera.hflip:
            sx = 1.0 - sx
        if self.camera.vflip:
            sy = 1.0 - sy

        # clamp
        sx = max(0.0, min(1.0, sx))
        sy = max(0.0, min(1.0, sy))
        return sx, sy

    def _reticle_to_sensor_norm(self, overlay):
        """
        Convert reticle display pixel -> normalized coords inside the preview -> sensor norm.
        """
        if not self._preview_window or self._preview_window[2] == 0:
            # No reliable mapping known
            return 0.5, 0.5

        rx, ry = overlay.reticle_display_px()
        px, py, pw, ph = self._preview_window

        # normalized inside preview window
        nx = (rx - px + 0.5) / float(pw)
        ny = (ry - py + 0.5) / float(ph)

        # map back through rotation/flips to sensor space
        sx, sy = self._apply_rotation_flips_to_preview_norm(nx, ny)
        return sx, sy

    def center_zoom_step_at_reticle(self, step: float, overlay, max_step: float = 8.0):
        """
        Zoom with ROI centered on the reticle's scene point.
        Clamps zoom so ROI remains inside the sensor.
        """
        try:
            z = float(step)
        except Exception:
            z = 1.0
        z = max(1.0, min(float(max_step), z))

        # reticle center in sensor norm
        cx, cy = self._reticle_to_sensor_norm(overlay)

        # compute max allowed zoom so ROI stays inside [0,1]
        # constraint: w = 1/z <= 2*min(cx, 1-cx) and likewise for cy
        eps = 1e-6
        z_max_x = 1.0 / max(eps, 2.0 * min(cx, 1.0 - cx))
        z_max_y = 1.0 / max(eps, 2.0 * min(cy, 1.0 - cy))
        z_allowed = min(z, z_max_x, z_max_y)
        if z_allowed < z:
            z = z_allowed  # avoid ROI clamping drift

        if z <= 1.0001:
            self.camera.zoom = (0.0, 0.0, 1.0, 1.0)
            return

        w = 1.0 / z
        h = 1.0 / z

        x = cx - (w / 2.0)
        y = cy - (h / 2.0)

        # safety clamp (should be no-op thanks to z_allowed)
        x = max(0.0, min(1.0 - w, x))
        y = max(0.0, min(1.0 - h, y))

        self.camera.zoom = (x, y, w, h)