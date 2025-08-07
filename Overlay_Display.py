import numpy as np
import json
import os
from dispmanx import DispmanX
import time

class OverlayDisplay:
    OFFSET_FILE = "~/Saved_Videos/overlay_offset.json"  # File path for storing offset

    def __init__(self, desired_res=(1280, 720)):
        self.desired_res = desired_res
        self.disp = DispmanX(pixel_format="RGBA", buffer_type="numpy", layer=2000)
        self.disp_width, self.disp_height = self.disp.size
        self.overlay_image = np.zeros((self.desired_res[1], self.desired_res[0], 4), dtype=np.uint8)
        
        # Load initial offset from file
        self.horizontal_y, self.vertical_x = self.load_offset()

    def scale_overlay(self):
        aspect_ratio = self.desired_res[0] / self.desired_res[1]
        if self.disp_width / self.disp_height > aspect_ratio:
            new_width = self.disp_width
            new_height = int(new_width / aspect_ratio)
        else:
            new_height = self.disp_height
            new_width = int(new_height * aspect_ratio)
        return (new_width, new_height)

    def update_overlay(self, offset_x, offset_y, overlay_res):
        """Update the overlay image buffer with the current crosshair positions."""
        self.update_overlay_image(self.horizontal_y, self.vertical_x)
        self.disp.buffer[offset_y:offset_y+overlay_res[1], offset_x:offset_x+overlay_res[0], :] = self.overlay_image
        self.disp.update()

    def update_overlay_image(self, horizontal_y, vertical_x, thickness=2):
        """Draw the crosshair onto the overlay image buffer."""
        self.overlay_image.fill(0)  # Clear the buffer (transparent background)
        height, width, _ = self.overlay_image.shape
        horizontal_y = max(0, min(height - thickness, horizontal_y))
        vertical_x = max(0, min(width - thickness, vertical_x))
        self.overlay_image[horizontal_y:horizontal_y+thickness, :, :] = [255, 0, 0, 255]  # Horizontal red line
        self.overlay_image[:, vertical_x:vertical_x+thickness, :] = [255, 0, 0, 255]  # Vertical red line

    def load_offset(self):
        """Load crosshair offset from file if available; otherwise return center positions."""
        if os.path.exists(self.OFFSET_FILE):
            try:
                with open(self.OFFSET_FILE, "r") as f:
                    offset_data = json.load(f)
                horizontal_y = offset_data.get("horizontal_y", self.desired_res[1] // 2)
                vertical_x = offset_data.get("vertical_x", self.desired_res[0] // 2)
                print("Loaded saved offset:", horizontal_y, vertical_x)
                return horizontal_y, vertical_x
            except Exception as e:
                print("Error reading offset file, using defaults:", e)
        return self.desired_res[1] // 2, self.desired_res[0] // 2  # Default: center of overlay.

    def save_offset(self):
        """Save the current crosshair offset to file."""
        try:
            with open(self.OFFSET_FILE, "w") as f:
                json.dump({"horizontal_y": self.horizontal_y, "vertical_x": self.vertical_x}, f)
            print("Saved offset:", self.horizontal_y, self.vertical_x)
        except Exception as e:
            print("Error saving offset:", e)
