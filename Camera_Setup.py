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
        if r == 0:   sx, sy = nx, ny
        elif r == 90:  sx, sy = ny, 1.0 - nx
        elif r == 180: sx, sy = 1.0 - nx, 1.0 - ny
        elif r == 270: sx, sy = 1.0 - ny, nx
        else:          sx, sy = nx, ny
        if self.camera.hflip: sx = 1.0 - sx
        if self.camera.vflip: sy = 1.0 - sy
        return max(0.0, min(1.0, sx)), max(0.0, min(1.0, sy))

    def _reticle_to_sensor_norm(self, overlay):
        # reticle pixel on the display
        rx, ry = overlay.reticle_display_px()

        # current preview window (fullscreen returns 0,0,0,0)
        try:
            px, py, pw, ph = self.camera.preview.window
        except Exception:
            px = py = pw = ph = 0

        if pw <= 0 or ph <= 0:
            # treat as fullscreen using display size
            px, py = 0, 0
            pw, ph = overlay.disp_width, overlay.disp_height

        nx = (rx - px + 0.5) / float(pw)
        ny = (ry - py + 0.5) / float(ph)
        nx = 0.0 if nx < 0.0 else (1.0 if nx > 1.0 else nx)
        ny = 0.0 if ny < 0.0 else (1.0 if ny > 1.0 else ny)
        return self._apply_rotation_flips_to_preview_norm(nx, ny)
    

    def _align_window_after_zoom(self, overlay, cx, cy, roi):
        x, y, w, h = roi
        if w <= 0 or h <= 0:
            return
        u = (cx - x) / w   # 0..1 across the displayed image
        v = (cy - y) / h   # 0..1 down the displayed image
        # clamp to be safe
        u = 0.0 if u < 0.0 else (1.0 if u > 1.0 else u)
        v = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)

        # 2) Get display and current window size (we’ll keep window size == display size)
        disp_w, disp_h = overlay.disp_width, overlay.disp_height
        # Use a fixed window size equal to full display (this produces black borders when shifted)
        win_w, win_h = disp_w, disp_h

        # 3) Reticle pixel on display:
        rx, ry = overlay.reticle_display_px()
        # We want: window_x + u*win_w == rx,   window_y + v*win_h == ry
        win_x = int(round(rx - u * win_w))
        win_y = int(round(ry - v * win_h))

        # 4) Apply window (stays in windowed mode; no new allocations)
        try:
            self.camera.preview.fullscreen = False
            self.camera.preview.window = (win_x, win_y, win_w, win_h)
        except Exception as e:
            # If driver rejects something, just ignore and keep old window
            # (zoom still applied)
            pass

    def center_zoom_step_at_reticle(self, step: float, overlay, max_step: float = 8.0):
            # sanitize zoom
        try:
            z = float(step)
        except Exception:
            z = 1.0
        z = max(1.0, min(float(max_step), z))

        # reticle in sensor-normalized coordinates
        cx, cy = self._reticle_to_sensor_norm(overlay)

        if z <= 1.0001:
            # full frame
            self.camera.zoom = (0.0, 0.0, 1.0, 1.0)
            # center the full frame under the reticle position by moving the preview window
            self._align_window_after_zoom(overlay, cx, cy, (0.0, 0.0, 1.0, 1.0))
            return

        # requested ROI
        w = 1.0 / z
        h = 1.0 / z
        x_req = cx - w / 2.0
        y_req = cy - h / 2.0

        # MMAL requires [0,1]; it will clamp, but we’ll keep request and compute the clamped ROI
        x = max(0.0, min(1.0 - w, x_req))
        y = max(0.0, min(1.0 - h, y_req))
        roi = (x, y, w, h)
        self.camera.zoom = roi

        # Move the preview window so that the reticle’s scene point lands exactly under the reticle pixel.
        self._align_window_after_zoom(overlay, cx, cy, roi)