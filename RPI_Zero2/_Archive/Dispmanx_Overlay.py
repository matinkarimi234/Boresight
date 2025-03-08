import numpy  # Ensure numpy is imported first.
import numpy as np
from dispmanx import DispmanX
import time
import curses
from picamera import PiCamera

# Desired overlay resolution (sensor native crop)
DESIRED_OVERLAY_RES = (1920, 1080)  # (width, height)
ov_width, ov_height = DESIRED_OVERLAY_RES

def update_overlay_image(buf, horizontal_y, vertical_x, thickness=2):
    """
    Update the overlay buffer (of shape DESIRED_OVERLAY_RES) in place:
      - Clear the buffer (transparent background)
      - Draw a horizontal red line at y and a vertical red line at x.
    """
    buf.fill(0)
    height, width, _ = buf.shape
    # Clamp positions within the overlay image dimensions.
    horizontal_y = max(0, min(height - thickness, horizontal_y))
    vertical_x = max(0, min(width - thickness, vertical_x))
    # Draw horizontal line.
    buf[horizontal_y:horizontal_y+thickness, :, :] = [255, 0, 0, 255]
    # Draw vertical line.
    buf[:, vertical_x:vertical_x+thickness, :] = [255, 0, 0, 255]

def main(stdscr):
    # --- Start PiCamera Preview ---
    camera = PiCamera()
        # Set resolution to 1280x720.
    camera.resolution = DESIRED_OVERLAY_RES
        # Use sensor_mode 1 for a native 16:9 crop (if lighting permits).
    camera.sensor_mode = 1
        # Set ISO low to reduce noise.
    camera.iso = 100
        # Set a high framerate for low latency.
    camera.framerate = 60
    # Use a fast exposure mode (e.g., 'sports') to reduce motion blur.
    camera.exposure_mode = 'sports'
    # Optionally, fix AWB to a preset (e.g., 'sunlight') if lighting is constant.
    camera.awb_mode = 'auto'
    # Set the camera's resolution as desired (or leave default).
    # Here we start fullscreen so the HDMI output resolution is used.
    camera.start_preview(fullscreen=True)
    time.sleep(2)  # Allow the preview to initialize.

    # --- Initialize DispmanX overlay ---
    # The DispmanX object provides a full-screen buffer based on the current HDMI resolution.
    disp = DispmanX(pixel_format="RGBA", buffer_type="numpy", layer=2000)
    disp_width, disp_height = disp.size  # full display resolution
    print("Display resolution:", disp_width, disp_height)

    # Calculate the offset to center the desired overlay region.
    offset_x = (disp_width - DESIRED_OVERLAY_RES[0]) // 2
    offset_y = (disp_height - DESIRED_OVERLAY_RES[1]) // 2

    # Create a separate overlay image buffer (the desired 1640×1232 region).
    overlay_image = np.zeros((DESIRED_OVERLAY_RES[1], DESIRED_OVERLAY_RES[0], 4), dtype=np.uint8)

    # Initial crosshair positions relative to the overlay image.
    horizontal_y = DESIRED_OVERLAY_RES[1] // 2
    vertical_x = DESIRED_OVERLAY_RES[0] // 2

    # Draw the initial overlay image.
    update_overlay_image(overlay_image, horizontal_y, vertical_x)
    # Copy it into the center of the DispmanX buffer.
    disp.buffer[offset_y:offset_y+DESIRED_OVERLAY_RES[1],
                offset_x:offset_x+DESIRED_OVERLAY_RES[0], :] = overlay_image
    disp.update()

    # --- Setup Curses for Keyboard Input ---
    stdscr.nodelay(True)
    stdscr.clear()
    stdscr.addstr(0, 0, "Arrow keys to move crosshair; 'q' to quit.")

    try:
        while True:
            key = stdscr.getch()
            if key != -1:
                if key == curses.KEY_UP:
                    horizontal_y = max(0, horizontal_y - 10)
                elif key == curses.KEY_DOWN:
                    horizontal_y = min(DESIRED_OVERLAY_RES[1], horizontal_y + 10)
                elif key == curses.KEY_LEFT:
                    vertical_x = max(0, vertical_x - 10)
                elif key == curses.KEY_RIGHT:
                    vertical_x = min(DESIRED_OVERLAY_RES[0], vertical_x + 10)
                elif key == ord('q'):
                    break

                update_overlay_image(overlay_image, horizontal_y, vertical_x)
                # Copy updated overlay image into the centered region of the DispmanX buffer.
                disp.buffer[offset_y:offset_y+DESIRED_OVERLAY_RES[1],
                            offset_x:offset_x+DESIRED_OVERLAY_RES[0], :] = overlay_image
                disp.update()
            time.sleep(0.05)
    finally:
        camera.stop_preview()
        camera.close()

if __name__ == '__main__':
    curses.wrapper(main)
