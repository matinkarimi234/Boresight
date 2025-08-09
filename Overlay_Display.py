import numpy as np
import json, os
from dispmanx import DispmanX
from PIL import Image, ImageDraw, ImageFont

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


class StaticPNGOverlay:
    def __init__(self, png_path, layer=1999, pos=('left', 'top'), scale=None):
        self.disp = DispmanX(pixel_format="RGBA", buffer_type="numpy", layer=layer)
        self.disp_w, self.disp_h = self.disp.size

        im = Image.open(png_path).convert('RGBA')
        if scale is not None:
            if isinstance(scale, tuple):  # exact size
                im = im.resize(scale, Image.LANCZOS)
            else:  # uniform scale factor
                im = im.resize((int(im.width*scale), int(im.height*scale)), Image.LANCZOS)

        # If you see halo artifacts, enable premultiplied alpha (commented out by default):
        # arr = np.array(im, dtype=np.uint8)
        # a = arr[...,3:4].astype(np.uint16)
        # arr[...,0:3] = (arr[...,0:3].astype(np.uint16) * a // 255).astype(np.uint8)
        # self.img = arr

        self.img = np.array(im, dtype=np.uint8)
        H, W, _ = self.img.shape

        # position: accepts pixel ints or ('left'|'center'|'right', 'top'|'center'|'bottom')
        x = {'left': 0, 'center': (self.disp_w - W)//2, 'right': self.disp_w - W}.get(pos[0], pos[0])
        y = {'top': 0, 'center': (self.disp_h - H)//2, 'bottom': self.disp_h - H}.get(pos[1], pos[1])
        self.x = int(max(min(x, self.disp_w - W), 0))
        self.y = int(max(min(y, self.disp_h - H), 0))

    def show(self):
        # Start this layer fully transparent, then paste the PNG region only
        self.disp.buffer[:] = 0
        H, W, _ = self.img.shape
        x0, y0 = self.x, self.y
        x1, y1 = min(self.disp_w, x0+W), min(self.disp_h, y0+H)
        sx0, sy0 = 0, 0
        if x0 < 0: sx0 = -x0; x0 = 0
        if y0 < 0: sy0 = -y0; y0 = 0
        if x1 > x0 and y1 > y0:
            self.disp.buffer[y0:y1, x0:x1, :] = self.img[sy0:sy0+(y1-y0), sx0:sx0+(x1-x0), :]
        self.disp.update()  # one-time push

    def hide(self):
        self.disp.buffer[:] = 0
        self.disp.update()

class TextOverlay:
    def __init__(self, layer, font_path, font_size, pos=('left', 'top'), color=(255,255,255,255)):
        self.disp = DispmanX(pixel_format="RGBA", buffer_type="numpy", layer=layer)
        self.disp_w, self.disp_h = self.disp.size
        self.font = ImageFont.truetype(font_path, font_size)
        self.color = color
        self.pos = pos
        self.last_text = None

    def set_text(self, text):
        if text == self.last_text:
            return  # no change → no update
        self.last_text = text

        # Clear buffer
        self.disp.buffer[:] = 0
        img = Image.new('RGBA', (self.disp_w, self.disp_h), (0,0,0,0))
        draw = ImageDraw.Draw(img)

        # Get position
        w, h = draw.textsize(text, font=self.font)
        x = {'left': 0, 'center': (self.disp_w - w)//2, 'right': self.disp_w - w}.get(self.pos[0], self.pos[0])
        y = {'top': 0, 'center': (self.disp_h - h)//2, 'bottom': self.disp_h - h}.get(self.pos[1], self.pos[1])

        draw.text((x, y), text, font=self.font, fill=self.color)
        self.disp.buffer[:] = np.array(img, dtype=np.uint8)
        self.disp.update()

