import numpy as np
import json, os
from dispmanx import DispmanX
from PIL import Image, ImageDraw, ImageFont
import threading
import cv2 as cv

import os
import json
import numpy as np
import cv2 as cv

# Replace with your DispmanX wrapper import if different
# from your_dispmanx_module import DispmanX

class OverlayDisplay:
    OFFSET_FILE = "~/Saved_Videos/overlay_offset.json"
    OVERLAY_COLOR = (180, 0, 0, 255)   # BGRA

    def __init__(self, desired_res=(1280, 720),
                 radius=120,                # circle radius (px)
                 ring_thickness=3,          # circle outline thickness (px)
                 tick_length=80,            # length of outside ticks (px)
                 tick_thickness=3,          # tick line thickness (px)
                 gap=6,                     # gap between circle and tick start (px)
                 color=OVERLAY_COLOR):      # RGBA/BGRA
        self.desired_res = desired_res  # (W, H)

        # Create DispmanX display object (your wrapper)
        self.disp = DispmanX(pixel_format="RGBA", buffer_type="numpy", layer=2000)
        self.disp_width, self.disp_height = self.disp.size

        # draw params (visual)
        self.radius = int(radius)
        self.ring_thickness = int(ring_thickness)
        self.tick_length = int(tick_length)
        self.tick_thickness = int(tick_thickness)
        self.gap = int(gap)
        # color is stored as BGRA tuple for direct array writes / cv drawing on BGRA buffer
        self.color = tuple(color)

        # Default scale parameters (can be changed with set_style)
        self.scale_spacing = 20           # pixels between minor ticks
        self.scale_major_every = 5        # every Nth tick is major
        self.scale_minor_length = 8       # minor tick pixel length
        self.scale_major_length = 16      # major tick pixel length
        self.scale_tick_thickness = max(1, self.tick_thickness)  # thickness for scale ticks
        self.scale_label_font = cv.FONT_HERSHEY_SIMPLEX
        self.scale_label_font_scale = 0.45
        self.scale_label_thickness = 1
        self.scale_label_offset = 6       # px offset from tick to label
        self.scale_label_show = True      # whether to draw numeric labels
        self.scale_label_units = "px"     # label units string (displayed after number)

        # overlay backing buffer (RGBA)
        W, H = self.desired_res
        self.overlay_image = np.zeros((H, W, 4), dtype=np.uint8)

        # center offset to place the bitmap on display
        self.offset_x = (self.disp_width  - W) // 2
        self.offset_y = (self.disp_height - H) // 2

        # center coordinates (load saved offsets or default to center)
        self.horizontal_y, self.vertical_x = self.load_offset()
        self._clamp_center_to_keep_circle_visible()

    def _clamp_center_to_keep_circle_visible(self):
        W, H = self.desired_res
        r = self.radius
        # keep center such that entire circle remains on the overlay bitmap
        self.vertical_x   = int(np.clip(self.vertical_x,   r, W - 1 - r))
        self.horizontal_y = int(np.clip(self.horizontal_y, r, H - 1 - r))

    def _draw_reticle(self, img_array, cx, cy):
        """
        Draw circle, outside ticks, graduated scales (outside-only), and numeric labels.
        img_array is BGRA (4-channel) numpy array.
        """
        H, W, C = img_array.shape
        assert C == 4, "overlay buffer must be RGBA/BGRA (4 channels)"

        # ensure ints
        cx = int(cx); cy = int(cy)
        r_pix = int(self.radius)
        g = int(self.gap)
        L = int(self.tick_length)
        w = int(self.tick_thickness)
        wt = int(self.ring_thickness)

        # --- Circle (ring) ---
        if r_pix > 0 and wt > 0:
            cv.circle(img_array, (cx, cy), r_pix, self.color, thickness=wt, lineType=cv.LINE_AA)

        # --- Main outside ticks (existing behavior) ---
        # Right
        cv.line(img_array, (cx + r_pix + g, cy), (cx + r_pix + g + L, cy), self.color, thickness=w, lineType=cv.LINE_AA)
        # Left
        cv.line(img_array, (cx - r_pix - g, cy), (cx - r_pix - g - L, cy), self.color, thickness=w, lineType=cv.LINE_AA)
        # Top
        cv.line(img_array, (cx, cy - r_pix - g), (cx, cy - r_pix - g - L), self.color, thickness=w, lineType=cv.LINE_AA)
        # Bottom
        cv.line(img_array, (cx, cy + r_pix + g), (cx, cy + r_pix + g + L), self.color, thickness=w, lineType=cv.LINE_AA)

        # --- 1 px center dot ---
        if 0 <= cx < W and 0 <= cy < H:
            img_array[cy, cx, :] = self.color

        # --- Graduated scales (start from center and go outward) ---
        spacing = int(max(1, self.scale_spacing))
        major_every = max(1, int(self.scale_major_every))
        minor_len = int(self.scale_minor_length)
        major_len = int(self.scale_major_length)
        tick_w = int(max(1, self.scale_tick_thickness))

        label_font = self.scale_label_font
        label_scale = float(self.scale_label_font_scale)
        label_thickness = int(max(1, self.scale_label_thickness))
        label_offset = int(self.scale_label_offset)
        show_labels = bool(self.scale_label_show)
        units = str(self.scale_label_units)

        def draw_label(text, pos_x, pos_y, align='center'):
            (tw, th), baseline = cv.getTextSize(text, label_font, label_scale, label_thickness)
            x = int(pos_x)
            y = int(pos_y)
            if align == 'center':
                x = int(x - tw // 2)
                y = int(y + th // 2)
            elif align == 'right':
                x = int(x - tw)
                y = int(y + th // 2)
            x = max(0, min(W - tw - 1, x))
            y = max(th, min(H - 1, y))
            cv.putText(img_array, text, (x, y), label_font, label_scale, self.color, label_thickness, lineType=cv.LINE_AA)

        # Horizontal ticks: start at center and go right and left
        # Right (including center as i=0, but skip drawing a tick at center because we already draw the center dot)
        i = 0
        x = cx
        while x < W:
            is_center = (i == 0)
            is_major = (i % major_every) == 0
            length = major_len if is_major else minor_len

            if not is_center:
                y0 = int(np.clip(cy - (length // 2), 0, H - 1))
                y1 = int(np.clip(cy + (length // 2), 0, H - 1))
                cv.line(img_array, (x, y0), (x, y1), self.color, thickness=tick_w, lineType=cv.LINE_AA)

                if is_major and show_labels:
                    dist = x - cx
                    txt = f"+{dist}{units}"
                    label_x = x
                    label_y = cy + (length // 2) + label_offset + int(label_scale * 10)
                    draw_label(txt, label_x, label_y, align='center')
            i += 1
            x += spacing

        # Left
        i = 0
        x = cx
        while x >= 0:
            is_center = (i == 0)
            is_major = (i % major_every) == 0
            length = major_len if is_major else minor_len

            if not is_center:
                y0 = int(np.clip(cy - (length // 2), 0, H - 1))
                y1 = int(np.clip(cy + (length // 2), 0, H - 1))
                cv.line(img_array, (x, y0), (x, y1), self.color, thickness=tick_w, lineType=cv.LINE_AA)

                if is_major and show_labels:
                    dist = cx - x
                    txt = f"-{dist}{units}"
                    label_x = x
                    label_y = cy + (length // 2) + label_offset + int(label_scale * 10)
                    draw_label(txt, label_x, label_y, align='center')
            i += 1
            x -= spacing

        # Vertical ticks: start at center and go down and up
        # Down
        i = 0
        y = cy
        while y < H:
            is_center = (i == 0)
            is_major = (i % major_every) == 0
            length = major_len if is_major else minor_len

            if not is_center:
                x0 = int(np.clip(cx - (length // 2), 0, W - 1))
                x1 = int(np.clip(cx + (length // 2), 0, W - 1))
                cv.line(img_array, (x0, y), (x1, y), self.color, thickness=tick_w, lineType=cv.LINE_AA)

                if is_major and show_labels:
                    dist = y - cy
                    txt = f"+{dist}{units}"
                    label_x = cx + (length // 2) + label_offset + int(label_scale * 6)
                    label_y = y
                    draw_label(txt, label_x, label_y, align='left')
            i += 1
            y += spacing

        # Up
        i = 0
        y = cy
        while y >= 0:
            is_center = (i == 0)
            is_major = (i % major_every) == 0
            length = major_len if is_major else minor_len

            if not is_center:
                x0 = int(np.clip(cx - (length // 2), 0, W - 1))
                x1 = int(np.clip(cx + (length // 2), 0, W - 1))
                cv.line(img_array, (x0, y), (x1, y), self.color, thickness=tick_w, lineType=cv.LINE_AA)

                if is_major and show_labels:
                    dist = cy - y
                    txt = f"-{dist}{units}"
                    label_x = cx + (length // 2) + label_offset + int(label_scale * 6)
                    label_y = y
                    draw_label(txt, label_x, label_y, align='left')
            i += 1
            y -= spacing

        return img_array

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

    def set_style(self, *, radius=None, ring_thickness=None,
                  tick_length=None, tick_thickness=None, gap=None, color=None,
                  # scale params:
                  scale_spacing=None, scale_major_every=None,
                  scale_minor_length=None, scale_major_length=None,
                  scale_tick_thickness=None,
                  scale_label_font_scale=None, scale_label_thickness=None,
                  scale_label_offset=None, scale_label_show=None,
                  scale_label_units=None):
        """Change visual style and scale parameters live."""
        if radius is not None: self.radius = int(radius)
        if ring_thickness is not None: self.ring_thickness = int(ring_thickness)
        if tick_length is not None: self.tick_length = int(tick_length)
        if tick_thickness is not None:
            self.tick_thickness = int(tick_thickness)
            # keep scale tick thickness sensible
            self.scale_tick_thickness = max(1, int(tick_thickness))
        if gap is not None: self.gap = int(gap)
        if color is not None: self.color = tuple(color)

        # scale params
        if scale_spacing is not None: self.scale_spacing = int(scale_spacing)
        if scale_major_every is not None: self.scale_major_every = max(1, int(scale_major_every))
        if scale_minor_length is not None: self.scale_minor_length = int(scale_minor_length)
        if scale_major_length is not None: self.scale_major_length = int(scale_major_length)
        if scale_tick_thickness is not None: self.scale_tick_thickness = int(scale_tick_thickness)
        if scale_label_font_scale is not None: self.scale_label_font_scale = float(scale_label_font_scale)
        if scale_label_thickness is not None: self.scale_label_thickness = int(scale_label_thickness)
        if scale_label_offset is not None: self.scale_label_offset = int(scale_label_offset)
        if scale_label_show is not None: self.scale_label_show = bool(scale_label_show)
        if scale_label_units is not None: self.scale_label_units = str(scale_label_units)

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
    def __init__(self, layer, font_path, font_size,
                 pos=('left', 'top'),
                 color=(255,255,255,255),
                 offset=20,
                 rec_indicator=True,
                 rec_color=(255, 0, 0, 255),
                 rec_blink=True,
                 rec_blink_interval=0.5):  # seconds
        self.disp = DispmanX(pixel_format="RGBA", buffer_type="numpy", layer=layer)
        self.disp_w, self.disp_h = self.disp.size
        self.font = ImageFont.truetype(font_path, font_size)
        self.color = color
        self.pos = pos
        self.offset = offset

        self.rec_indicator = rec_indicator
        self.rec_color = rec_color
        self.rec_blink = rec_blink
        self.rec_blink_interval = rec_blink_interval

        self._current_text = ""
        self._blink_phase = True
        self._blink_thread = None
        self._blink_stop = threading.Event()
        self._lock = threading.Lock()

    @property
    def last_text(self):
        # thread-safe read for your RecordingManager callback
        with self._lock:
            return self._current_text

    @last_text.setter
    def last_text(self, value):
        # keep compatibility if anything tries to set it
        self.set_text(value)

    def _measure(self, draw, txt, font):
        if hasattr(draw, "textbbox"):
            l, t, r, b = draw.textbbox((0, 0), txt, font=font)
            return (r - l), (b - t)
        if hasattr(font, "getbbox"):
            l, t, r, b = font.getbbox(txt)
            return (r - l), (b - t)
        return font.getsize(txt)

    def _render(self, text, dot_on):
        img = Image.new('RGBA', (self.disp_w, self.disp_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        w, h = self._measure(draw, text, self.font)

        show_rec = self.rec_indicator and text.strip().upper().startswith("REC")
        # dot size & spacing
        dot_radius = max(3, int(h * 0.35)) if show_rec else 0
        dot_diam = dot_radius * 2
        gap = max(4, dot_radius // 2) if show_rec else 0

        total_w = w + (dot_diam + gap if show_rec else 0)

        # group-aligned positions
        x_positions = {
            'left': self.offset,
            'center': (self.disp_w - total_w) // 2,
            'right': self.disp_w - total_w - self.offset
        }
        y_positions = {
            'top': self.offset,
            'center': (self.disp_h - h) // 2,
            'bottom': self.disp_h - h - self.offset
        }

        gx = self.pos[0] + self.offset if isinstance(self.pos[0], int) else x_positions.get(self.pos[0], self.offset)
        gy = self.pos[1] + self.offset if isinstance(self.pos[1], int) else y_positions.get(self.pos[1], self.offset)

        text_x = gx + (dot_diam + gap if show_rec else 0)
        text_y = gy

        # --- draw REC dot vertically centered to the real text box ---
        if show_rec and dot_on:
            try:
                # Get the exact ink box at the position we’ll draw the text
                l, t, r, b = draw.textbbox((text_x, text_y), text, font=self.font)
                cy = (t + b) // 2
            except AttributeError:
                # Fallbacks for older Pillow
                try:
                    ascent, descent = self.font.getmetrics()
                    cy = text_y + (ascent - descent) // 2
                except Exception:
                    cy = text_y + h // 2  # last resort

            cx = gx + dot_radius
            bbox = [cx - dot_radius, cy - dot_radius, cx + dot_radius, cy + dot_radius]
            draw.ellipse(bbox, fill=self.rec_color)

        # Draw the text AFTER the dot so the dot never overlaps letters
        draw.text((text_x, text_y), text, font=self.font, fill=self.color)

        self.disp.buffer[:] = np.array(img, dtype=np.uint8)
        self.disp.update()

    def _start_blink(self):
        if self._blink_thread and self._blink_thread.is_alive():
            return
        self._blink_stop.clear()
        self._blink_thread = threading.Thread(target=self._blink_loop, daemon=True)
        self._blink_thread.start()

    def _stop_blink(self):
        if self._blink_thread and self._blink_thread.is_alive():
            self._blink_stop.set()
            # no join() to keep it non-blocking; thread is daemon

    def _blink_loop(self):
        # Toggle the dot while the text stays "REC..."
        while not self._blink_stop.is_set():
            with self._lock:
                text = self._current_text
                is_rec = text.strip().upper().startswith("REC") and self.rec_indicator
                if not is_rec:
                    break
                self._blink_phase = not self._blink_phase
                self._render(text, dot_on=self._blink_phase)
            # sleep last to render immediately after state change
            self._blink_stop.wait(self.rec_blink_interval)

    def set_text(self, text):
        with self._lock:
            self._current_text = text
            is_rec = text.strip().upper().startswith("REC") and self.rec_indicator

            if is_rec and self.rec_blink:
                # ensure a frame is drawn immediately, then start blinking
                self._blink_phase = True
                self._render(text, dot_on=True)
                self._start_blink()
            else:
                # draw static (no dot or solid dot if blinking disabled)
                self._stop_blink()
                self._render(text, dot_on=is_rec and not self.rec_blink)

    def close(self):
        self._stop_blink()


import numpy as np
from dispmanx import DispmanX

class ContainerOverlay:
    def __init__(self, inner_size=None, bar_width=None, layer=1996, alpha=128,
                 center=True, inner_pos=None):
        """
        inner_size: (W,H) area to keep transparent (preview area). If None, use bar_width.
        bar_width: fixed side-bar width (px). If provided, overrides inner_size for L/R bars.
        alpha: 0..255 (128 ≈ 50%)
        layer: z-order; must be ABOVE preview, BELOW text/reticle
        """
        self.disp = DispmanX(pixel_format="RGBA", buffer_type="numpy", layer=layer)
        self.disp_w, self.disp_h = self.disp.size
        self.alpha = int(max(0, min(255, alpha)))
        self.inner_size = inner_size
        self.bar_width = bar_width
        self.center = center
        self.inner_pos = inner_pos  # (x,y) if not centered

    def _calc_inner_rect(self):
        if self.bar_width is not None:
            x0 = int(self.bar_width)
            x1 = int(self.disp_w - self.bar_width)
            y0, y1 = 0, self.disp_h
        else:
            W, H = self.inner_size
            if self.center:
                x0 = (self.disp_w - W) // 2
                y0 = (self.disp_h - H) // 2
            else:
                x0, y0 = self.inner_pos or (0, 0)
            x1, y1 = x0 + W, y0 + H

        # clamp to screen
        x0 = max(0, min(self.disp_w, x0)); x1 = max(0, min(self.disp_w, x1))
        y0 = max(0, min(self.disp_h, y0)); y1 = max(0, min(self.disp_h, y1))
        return x0, y0, x1, y1

    def show(self):
        # Full-screen 50% black
        buf = self.disp.buffer
        buf[:] = 0
        buf[..., 3] = self.alpha  # black with alpha (premult OK since RGB=0)

        # Carve the inner transparent window
        x0, y0, x1, y1 = self._calc_inner_rect()
        if x1 > x0 and y1 > y0:
            buf[y0:y1, x0:x1, 3] = 0  # alpha=0 -> fully transparent
        self.disp.update()

    def hide(self):
        self.disp.buffer[:] = 0
        self.disp.update()

    def set_inner_size(self, inner_size):
        self.inner_size = inner_size
        self.show()

    def set_bar_width(self, w):
        self.bar_width = int(max(0, w))
        self.show()

