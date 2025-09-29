from picamera import PiCamera
import time
class CameraSetup:
    def __init__(self, resolution=(1640, 922), sensor_mode=5, iso=800, framerate=30, exposure_mode='auto', awb_mode='auto'):
        self.camera = PiCamera()
        self.camera.resolution = resolution
        self.camera.sensor_mode = sensor_mode
        self.camera.iso = iso
        self.camera.framerate = framerate
        self.camera.exposure_mode = exposure_mode
        self.camera.awb_mode = awb_mode
        self.camera.rotation = 180

    def start_preview(self):
        self.camera.start_preview(fullscreen=True)
        time.sleep(2)  # Allow the preview to initialize.

    def stop_preview(self):
        self.camera.stop_preview()
        self.camera.close()

    
    def _apply_rotation_flips_to_preview_norm(self, nx, ny):
        r = (self.camera.rotation or 0) % 360
        if r == 0:
            sx, sy = nx, ny
        elif r == 90:
            sx, sy = ny, 1.0 - nx
        elif r == 180:
            sx, sy = 1.0 - nx, 1.0 - ny
        elif r == 270:
            sx, sy = 1.0 - ny, nx
        else:
            sx, sy = nx, ny
        if self.camera.hflip: sx = 1.0 - sx
        if self.camera.vflip: sy = 1.0 - sy
        return max(0.0, min(1.0, sx)), max(0.0, min(1.0, sy))

    def _reticle_to_sensor_norm(self, overlay):
        """
        Map reticle display pixel -> normalized coords inside the *current* preview.
        Works for both fullscreen (window=(0,0,0,0)) and windowed preview.
        """
        rx, ry = overlay.reticle_display_px()

        # Try to read current preview window
        try:
            px, py, pw, ph = self.camera.preview.window
        except Exception:
            px = py = pw = ph = 0

        # If fullscreen, picamera reports (0,0,0,0). Use the *display* size.
        if pw <= 0 or ph <= 0:
            # use DispmanX display size from your overlay
            disp_w, disp_h = overlay.disp_width, overlay.disp_height
            px, py, pw, ph = 0, 0, disp_w, disp_h

        # Normalized coords inside the preview rect
        nx = (rx - px + 0.5) / float(pw)
        ny = (ry - py + 0.5) / float(ph)

        # Clamp to [0,1] just in case
        nx = 0.0 if nx < 0.0 else (1.0 if nx > 1.0 else nx)
        ny = 0.0 if ny < 0.0 else (1.0 if ny > 1.0 else ny)

        # Undo rotation/flips so we end in sensor-normalized coords
        return self._apply_rotation_flips_to_preview_norm(nx, ny)

    def center_zoom_step_at_reticle(self, step: float, overlay, max_step: float = 8.0):
        try: z = float(step)
        except: z = 1.0
        z = max(1.0, min(float(max_step), z))

        cx, cy = self._reticle_to_sensor_norm(overlay)

        # limit zoom so ROI never clamps (prevents drift/jumps near edges)
        eps = 1e-6
        z_max_x = 1.0 / max(eps, 2.0 * min(cx, 1.0 - cx))
        z_max_y = 1.0 / max(eps, 2.0 * min(cy, 1.0 - cy))
        z = min(z, z_max_x, z_max_y)

        if z <= 1.0001:
            self.camera.zoom = (0.0, 0.0, 1.0, 1.0); return

        w = 1.0 / z; h = 1.0 / z
        x = max(0.0, min(1.0 - w, cx - w/2.0))
        y = max(0.0, min(1.0 - h, cy - h/2.0))
        self.camera.zoom = (x, y, w, h)
