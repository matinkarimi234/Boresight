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

    
    def center_zoom_step(self, step: float, max_step: float = 8.0, reticle_norm=None):
        """
        Zoom centered on reticle if reticle_norm=(nx,ny) is provided (0..1).
        Otherwise, center of frame.
        """
        try:
            z = float(step)
        except Exception:
            z = 1.0
        z = max(1.0, min(float(max_step), z))

        if z <= 1.0001:
            self.camera.zoom = (0.0, 0.0, 1.0, 1.0)
            return

        w = 1.0 / z
        h = 1.0 / z

        if reticle_norm is None:
            nx, ny = 0.5, 0.5
        else:
            nx = float(reticle_norm[0])
            ny = float(reticle_norm[1])

        x = nx - (w / 2.0)
        y = ny - (h / 2.0)

        # keep ROI inside sensor bounds; if near edges this may shift center slightly
        # x = max(0.0, min(1.0 - w, x))
        # y = max(0.0, min(1.0 - h, y))

        self.camera.zoom = (x, y, w, h)
