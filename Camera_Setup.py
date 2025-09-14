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

    
    def center_zoom(self, target_w_px=640, target_h_px=480):
        """Center-crop to exact px size and let preview scale it.
        If requested size is larger than sensor frame, reset to full frame.
        """
        frame_w, frame_h = self.camera.resolution

        if target_w_px >= frame_w or target_h_px >= frame_h:
            self.camera.zoom = (0.0, 0.0, 1.0, 1.0)
            return

        w = float(target_w_px) / float(frame_w)
        h = float(target_h_px) / float(frame_h)
        x = 0.5 - (w / 2.0)
        y = 0.5 - (h / 2.0)
        x = max(0.0, min(1.0 - w, x))
        y = max(0.0, min(1.0 - h, y))

        self.camera.zoom = (x, y, w, h)