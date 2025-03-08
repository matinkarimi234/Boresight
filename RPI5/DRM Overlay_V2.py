#!/usr/bin/python3
import time
import numpy as np
import curses
from picamera2 import Picamera2, Preview
from picamera2.encoders import H264Encoder
from PIL import Image, ImageDraw, ImageFont

def main(stdscr):
    # Initialize Picamera2 using the default (optimized) preview configuration.
    picam2 = Picamera2()
    config = picam2.create_preview_configuration(raw={"size": (1640, 1232)})  # using the optimal configuration
    picam2.configure(config)
    encoder = H264Encoder(10000000)
    picam2.start_preview(Preview.DRM)
    picam2.start()
    time.sleep(1)  # Allow the camera to settle

    # Get the preview resolution.
    preview_width, preview_height = 1640, 1232

    # Create an RGBA overlay array matching the preview resolution.
    overlay = np.zeros((preview_height, preview_width, 4), dtype=np.uint8)

    # Cross parameters
    thickness = 5                              # Thickness of cross lines in pixels
    cross_color = (255, 255, 255, 128)           # White with 50% transparency
    # Initial cross position (centered)
    cross_x = preview_width // 2
    cross_y = preview_height // 2

    # Load a larger TrueType font.
    # Adjust the font path and size as needed.
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
    except IOError:
        # If the specified TTF font is not available, fall back to the default font.
        font = ImageFont.load_default()

    def draw_overlay(ov, cx, cy, thick, color):
        """
        Clear the overlay, draw a cross at (cx,cy), and add a timestamp
        (formatted as YYYY-MM-DD HH:MM) in the top left corner.
        """
        ov.fill(0)  # Clear overlay to transparent

        # Draw vertical cross line:
        x_start = max(cx - thick // 2, 0)
        x_end   = min(cx + thick // 2 + 1, preview_width)
        ov[:, x_start:x_end] = color

        # Draw horizontal cross line:
        y_start = max(cy - thick // 2, 0)
        y_end   = min(cy + thick // 2 + 1, preview_height)
        ov[y_start:y_end, :] = color

        # --- Draw timestamp ---
        # Define a larger region (a box at the top-left) for the timestamp.
        region_height = 60   # Increased height for bigger text
        region_width = 400   # Increased width for bigger text
        region_height = min(region_height, preview_height)
        region_width = min(region_width, preview_width)

        # Extract the region from the overlay.
        text_region = ov[0:region_height, 0:region_width]
        # Convert the numpy region to a Pillow image.
        img_region = Image.fromarray(text_region, mode="RGBA")
        draw = ImageDraw.Draw(img_region)
        # Format the timestamp (date, hour, minute)
        timestamp = time.strftime("%Y-%m-%d %H:%M")
        # Draw the text in white (fully opaque) with a slight margin.
        draw.text((5, 5), timestamp, font=font, fill=(255, 255, 255, 255))
        # Copy the modified region back into the overlay.
        ov[0:region_height, 0:region_width] = np.array(img_region)

        return ov

    # Draw the initial overlay and apply it.
    draw_overlay(overlay, cross_x, cross_y, thickness, cross_color)
    picam2.set_overlay(overlay)

    # Set up curses for non-blocking input and arrow key support.
    stdscr.nodelay(True)
    stdscr.keypad(True)
    stdscr.clear()
    stdscr.addstr(0, 0, "Arrow keys: move cross | r: start recording | s: stop recording | q: quit")
    stdscr.refresh()

    recording = False

    while True:
        key = stdscr.getch()
        if key == curses.KEY_UP:
            cross_y = max(cross_y - 10, 0)
        elif key == curses.KEY_DOWN:
            cross_y = min(cross_y + 10, preview_height - 1)
        elif key == curses.KEY_LEFT:
            cross_x = max(cross_x - 10, 0)
        elif key == curses.KEY_RIGHT:
            cross_x = min(cross_x + 10, preview_width - 1)
        elif key == ord('r'):
            if not recording:
                recording = True
                picam2.start_recording(encoder, "video.h264")
                stdscr.addstr(1, 0, "Recording started                     ")
        elif key == ord('s'):
            if recording:
                recording = False
                picam2.stop_recording()
                stdscr.addstr(1, 0, "Recording stopped, saved as video.h264")
        elif key == ord('q'):
            break

        # Update the overlay (redraw the cross and the timestamp)
        draw_overlay(overlay, cross_x, cross_y, thickness, cross_color)
        picam2.set_overlay(overlay)

        time.sleep(0.05)  # Short delay for responsiveness

    # Clean up before exit.
    picam2.stop_preview()
    picam2.stop()

if __name__ == '__main__':
    curses.wrapper(main)
