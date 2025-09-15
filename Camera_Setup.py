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

    def start_preview(self):
        self.camera.start_preview(fullscreen=True)
        time.sleep(2)  # Allow the preview to initialize.

    def stop_preview(self):
        self.camera.stop_preview()
        self.camera.close()

    
    def center_zoom_step(self, step: float, max_step: float = 10.0):
        """
        Center zoom with a simple step scale:
        step = 1.0 -> full frame (no zoom)
        step = 10.0 -> 10x zoom (crop to 1/10 x 1/10 of frame), centered
        Keeps aspect ratio. Safe to call while previewing/recording.
        """
        # clamp (allow fractional steps like 1.5 too)
        try:
            z = float(step)
        except Exception:
            z = 1.0
        z = max(1.0, min(float(max_step), z))

        if z <= 1.0001:
            # full frame
            self.camera.zoom = (0.0, 0.0, 1.0, 1.0)
            return

        # normalized crop width/height; keep aspect ratio by using same factor
        w = 1.0 / z
        h = 1.0 / z
        x = 0.5 - (w / 2.0)
        y = 0.5 - (h / 2.0)

        # safety clamp
        x = max(0.0, min(1.0 - w, x))
        y = max(0.0, min(1.0 - h, y))

        self.camera.zoom = (x, y, w, h)
