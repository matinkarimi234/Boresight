import numpy as np
import json, os
from dispmanx import DispmanX

class OverlayDisplay:
    OFFSET_FILE = "~/Saved_Videos/overlay_offset.json"

    def __init__(self, desired_res=(1280, 720)):
        self.desired_res = desired_res  # (W, H)
        self.disp = DispmanX(pixel_format="RGBA", buffer_type="numpy", layer=2000)
        self.disp_width, self.disp_height = self.disp.size

        # Our overlay bitmap is ALWAYS desired_res (no scaling here)
        self.overlay_image = np.zeros((self.desired_res[1], self.desired_res[0], 4), dtype=np.uint8)

        # Center this bitmap once on the display
        self.offset_x = (self.disp_width  - self.desired_res[0]) // 2
        self.offset_y = (self.disp_height - self.desired_res[1]) // 2

        self.horizontal_y, self.vertical_x = self.load_offset()

    def update_overlay_image(self, horizontal_y, vertical_x, thickness=2):
        self.overlay_image.fill(0)
        H, W, _ = self.overlay_image.shape
        y = max(0, min(H - thickness, horizontal_y))
        x = max(0, min(W - thickness, vertical_x))
        self.overlay_image[y:y+thickness, :, :] = [255, 0, 0, 255]
        self.overlay_image[:, x:x+thickness, :] = [255, 0, 0, 255]

    def refresh(self):
        """Redraw lines and push the centered bitmap to the display."""
        self.update_overlay_image(self.horizontal_y, self.vertical_x)
        y0, y1 = self.offset_y, self.offset_y + self.desired_res[1]
        x0, x1 = self.offset_x, self.offset_x + self.desired_res[0]
        self.disp.buffer[y0:y1, x0:x1, :] = self.overlay_image
        self.disp.update()

    # helpers to move the lines
    def nudge_vertical(self, dx):   # move vertical line left/right
        W = self.desired_res[0]
        self.vertical_x = int(np.clip(self.vertical_x + dx, 0, W - 2))
        self.refresh()

    def nudge_horizontal(self, dy): # move horizontal line up/down
        H = self.desired_res[1]
        self.horizontal_y = int(np.clip(self.horizontal_y + dy, 0, H - 2))
        self.refresh()

    def load_offset(self):
        path = os.path.expanduser(self.OFFSET_FILE)
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    d = json.load(f)
                print("Loaded saved offset:", d.get("horizontal_y"), d.get("vertical_x"))
                return d.get("horizontal_y", self.desired_res[1] // 2), d.get("vertical_x", self.desired_res[0] // 2)
            except Exception as e:
                print("Error reading offset file, using defaults:", e)
        return self.desired_res[1] // 2, self.desired_res[0] // 2

    def save_offset(self):
        try:
            path = os.path.expanduser(self.OFFSET_FILE)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump({"horizontal_y": self.horizontal_y, "vertical_x": self.vertical_x}, f)
            print("Saved offset:", self.horizontal_y, self.vertical_x)
        except Exception as e:
            print("Error saving offset:", e)
