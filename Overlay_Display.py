import numpy as np
import json, os
from dispmanx import DispmanX
from PIL import Image, ImageDraw, ImageFont

class OverlayDisplay:
    OFFSET_FILE = "~/Saved_Videos/overlay_offset.json"

    def __init__(self, desired_res=(1280, 720),
                 radius=120,                # circle radius (px)
                 ring_thickness=3,          # circle outline thickness (px)
                 tick_length=80,            # length of outside ticks (px)
                 tick_thickness=3,          # tick line thickness (px)
                 gap=6,                     # gap between circle and tick start (px)
                 color=(130, 0, 0, 255)):   # RGBA
        self.desired_res = desired_res  # (W, H)
        self.disp = DispmanX(pixel_format="RGBA", buffer_type="numpy", layer=2000)
        self.disp_width, self.disp_height = self.disp.size

        # draw params
        self.radius = radius
        self.ring_thickness = ring_thickness
        self.tick_length = tick_length
        self.tick_thickness = tick_thickness
        self.gap = gap
        self.color = color

        # Our overlay bitmap is ALWAYS desired_res (no scaling here)
        self.overlay_image = np.zeros((self.desired_res[1], self.desired_res[0], 4), dtype=np.uint8)

        # Center this bitmap once on the display
        self.offset_x = (self.disp_width  - self.desired_res[0]) // 2
        self.offset_y = (self.disp_height - self.desired_res[1]) // 2

        self.horizontal_y, self.vertical_x = self.load_offset()
        # make sure center keeps circle on-screen
        self._clamp_center_to_keep_circle_visible()

    def _clamp_center_to_keep_circle_visible(self):
        W, H = self.desired_res
        r = self.radius
        self.vertical_x   = int(np.clip(self.vertical_x,   r, W - 1 - r))
        self.horizontal_y = int(np.clip(self.horizontal_y, r, H - 1 - r))

    def _draw_reticle(self, img_array, cx, cy):
        """
        Draws:
          - a ring (circle outline) centered at (cx, cy)
          - four ticks outside the circle (up/down/left/right)
        """
        H, W, _ = img_array.shape
        pil_img = Image.fromarray(img_array, mode='RGBA')
        d = ImageDraw.Draw(pil_img)

        r = int(self.radius)
        # Circle (ring)
        bbox = [cx - r, cy - r, cx + r, cy + r]
        try:
            # Pillow >= 8 supports width=
            d.ellipse(bbox, outline=self.color, width=int(self.ring_thickness))
        except TypeError:
            # Fallback: draw multiple concentric ellipses
            for t in range(self.ring_thickness):
                bb = [bbox[0]-t//2, bbox[1]-t//2, bbox[2]+t//2, bbox[3]+t//2]
                d.ellipse(bb, outline=self.color)

        # Ticks (outside only)
        g = int(self.gap)
        L = int(self.tick_length)
        w = int(self.tick_thickness)

        # Right tick: from circle edge outward
        d.line([(cx + r + g, cy), (cx + r + g + L, cy)], fill=self.color, width=w)
        # Left tick
        d.line([(cx - r - g, cy), (cx - r - g - L, cy)], fill=self.color, width=w)
        # Top tick
        d.line([(cx, cy - r - g), (cx, cy - r - g - L)], fill=self.color, width=w)
        # Bottom tick
        d.line([(cx, cy + r + g), (cx, cy + r + g + L)], fill=self.color, width=w)

        return np.array(pil_img, dtype=np.uint8)

    def update_overlay_image(self, horizontal_y=None, vertical_x=None):
        if horizontal_y is not None:
            self.horizontal_y = int(horizontal_y)
        if vertical_x is not None:
            self.vertical_x = int(vertical_x)
        self._clamp_center_to_keep_circle_visible()

        # clear & draw
        self.overlay_image[:] = 0
        self.overlay_image[:] = self._draw_reticle(
            self.overlay_image, cx=self.vertical_x, cy=self.horizontal_y
        )

    def refresh(self):
        """Redraw reticle and push the centered bitmap to the display."""
        self.update_overlay_image(self.horizontal_y, self.vertical_x)
        y0, y1 = self.offset_y, self.offset_y + self.desired_res[1]
        x0, x1 = self.offset_x, self.offset_x + self.desired_res[0]
        self.disp.buffer[y0:y1, x0:x1, :] = self.overlay_image
        self.disp.update()

    # helpers to move the reticle center
    def nudge_vertical(self, dx):   # move center left/right
        W = self.desired_res[0]
        self.vertical_x = int(np.clip(self.vertical_x + dx, self.radius, W - 1 - self.radius))
        self.refresh()

    def nudge_horizontal(self, dy): # move center up/down
        H = self.desired_res[1]
        self.horizontal_y = int(np.clip(self.horizontal_y + dy, self.radius, H - 1 - self.radius))
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

    # optional: quick setters for live tuning
    def set_style(self, *, radius=None, ring_thickness=None,
                  tick_length=None, tick_thickness=None, gap=None, color=None):
        if radius is not None: self.radius = int(radius)
        if ring_thickness is not None: self.ring_thickness = int(ring_thickness)
        if tick_length is not None: self.tick_length = int(tick_length)
        if tick_thickness is not None: self.tick_thickness = int(tick_thickness)
        if gap is not None: self.gap = int(gap)
        if color is not None: self.color = tuple(color)
        self._clamp_center_to_keep_circle_visible()
        self.refresh()


class StaticPNGOverlay:
    def __init__(self, png_path, layer=1999, pos=('left', 'top'), scale=None, offset=20):
        self.disp = DispmanX(pixel_format="RGBA", buffer_type="numpy", layer=layer)
        self.disp_w, self.disp_h = self.disp.size
        self.offset = offset
        self.pos = pos

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
        # Apply offset to each position mode
        x_positions = {
            'left': self.offset,
            'center': (self.disp_w - W) // 2,
            'right': self.disp_w - W - self.offset
        }
        y_positions = {
            'top': self.offset,
            'center': (self.disp_h - H) // 2,
            'bottom': self.disp_h - H - self.offset
        }

        # Compute position
        x = x_positions.get(self.pos[0], self.pos[0] + self.offset if isinstance(self.pos[0], int) else self.offset)
        y = y_positions.get(self.pos[1], self.pos[1] + self.offset if isinstance(self.pos[1], int) else self.offset)
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
    def __init__(self, layer, font_path, font_size, pos=('left', 'top'), color=(255,255,255,255), offset=20):
        self.disp = DispmanX(pixel_format="RGBA", buffer_type="numpy", layer=layer)
        self.disp_w, self.disp_h = self.disp.size
        self.font = ImageFont.truetype(font_path, font_size)
        self.color = color
        self.pos = pos
        self.offset = offset
        self.last_text = None

    def set_text(self, text):
        if text == self.last_text:
            return
        self.last_text = text

        # Clear buffer
        self.disp.buffer[:] = 0
        img = Image.new('RGBA', (self.disp_w, self.disp_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Measure text (Pillow 10+: textbbox; fallback for older versions)
        def measure(draw, txt, font):
            if hasattr(draw, "textbbox"):
                l, t, r, b = draw.textbbox((0, 0), txt, font=font)
                return (r - l), (b - t)
            # very old fallback
            if hasattr(font, "getbbox"):
                l, t, r, b = font.getbbox(txt)
                return (r - l), (b - t)
            return font.getsize(txt)  # last resort

        w, h = measure(draw, text, self.font)

        # Apply offset to each position mode
        x_positions = {
            'left': self.offset,
            'center': (self.disp_w - w) // 2,
            'right': self.disp_w - w - self.offset
        }
        y_positions = {
            'top': self.offset,
            'center': (self.disp_h - h) // 2,
            'bottom': self.disp_h - h - self.offset
        }

        # Compute position
        x = x_positions.get(self.pos[0], self.pos[0] + self.offset if isinstance(self.pos[0], int) else self.offset)
        y = y_positions.get(self.pos[1], self.pos[1] + self.offset if isinstance(self.pos[1], int) else self.offset)

        draw.text((x, y), text, font=self.font, fill=self.color)
        self.disp.buffer[:] = np.array(img, dtype=np.uint8)
        self.disp.update()

