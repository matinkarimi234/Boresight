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
