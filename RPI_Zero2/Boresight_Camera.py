import numpy as np  # Ensure numpy is imported first.
from dispmanx import DispmanX
import time
import json
import os
from picamera import PiCamera
from gpiozero import Button

# Desired overlay resolution (sensor native crop)
DESIRED_OVERLAY_RES = (1920, 1080)  # (width, height)
ov_width, ov_height = DESIRED_OVERLAY_RES

OFFSET_FILE = "overlay_offset.json"

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

def load_offset():
    """Load crosshair offset from file if available; otherwise return center positions."""
    if os.path.exists(OFFSET_FILE):
        try:
            with open(OFFSET_FILE, "r") as f:
                offset_data = json.load(f)
            horizontal_y = offset_data.get("horizontal_y", DESIRED_OVERLAY_RES[1] // 2)
            vertical_x = offset_data.get("vertical_x", DESIRED_OVERLAY_RES[0] // 2)
            print("Loaded saved offset:", horizontal_y, vertical_x)
            return horizontal_y, vertical_x
        except Exception as e:
            print("Error reading offset file, using defaults:", e)
    # Default: center of overlay.
    return DESIRED_OVERLAY_RES[1] // 2, DESIRED_OVERLAY_RES[0] // 2

def save_offset(horizontal_y, vertical_x):
    """Save the current crosshair offset to file."""
    try:
        with open(OFFSET_FILE, "w") as f:
            json.dump({"horizontal_y": horizontal_y, "vertical_x": vertical_x}, f)
        print("Saved offset:", horizontal_y, vertical_x)
    except Exception as e:
        print("Error saving offset:", e)

def main():
    # --- Start PiCamera Preview ---
    camera = PiCamera()
    # Set resolution to match the overlay size.
    camera.resolution = DESIRED_OVERLAY_RES
    # Use sensor_mode 1 for a native 16:9 crop (if lighting permits).
    camera.sensor_mode = 1
    # Set ISO low to reduce noise.
    camera.iso = 100
    # Set a high framerate for low latency.
    camera.framerate = 60
    # Use a fast exposure mode (e.g., 'sports') to reduce motion blur.
    camera.exposure_mode = 'sports'
    # Optionally, fix AWB to a preset (e.g., 'auto') if lighting is constant.
    camera.awb_mode = 'auto'
    # Start preview in fullscreen.
    camera.start_preview(fullscreen=True)
    time.sleep(2)  # Allow the preview to initialize.

    # --- Initialize DispmanX overlay ---
    disp = DispmanX(pixel_format="RGBA", buffer_type="numpy", layer=2000)
    disp_width, disp_height = disp.size  # Full display resolution
    print("Display resolution:", disp_width, disp_height)

    # Calculate the offset to center the overlay region.
    offset_x = (disp_width - DESIRED_OVERLAY_RES[0]) // 2
    offset_y = (disp_height - DESIRED_OVERLAY_RES[1]) // 2

    # Create the overlay image buffer.
    overlay_image = np.zeros((DESIRED_OVERLAY_RES[1], DESIRED_OVERLAY_RES[0], 4), dtype=np.uint8)

    # --- Load initial crosshair positions ---
    horizontal_y, vertical_x = load_offset()

    # Draw the initial overlay image.
    update_overlay_image(overlay_image, horizontal_y, vertical_x)
    # Copy it into the center of the DispmanX buffer.
    disp.buffer[offset_y:offset_y+DESIRED_OVERLAY_RES[1],
                offset_x:offset_x+DESIRED_OVERLAY_RES[0], :] = overlay_image
    disp.update()

    print("Push Button Control:")
    print("  Left:  GPIO 5")
    print("  Down:  GPIO 6")
    print("  Right: GPIO 24")
    print("  Up:    GPIO 23")
    print("Press Ctrl+C to quit.")

    # --- Setup gpiozero Push Buttons ---
    button_left = Button(5)
    button_down = Button(6)
    button_right = Button(24)
    button_up = Button(23)

    # Define movement step size.
    step = 10

    # Define callback functions to update the crosshair.
    def on_left():
        nonlocal vertical_x, horizontal_y, overlay_image
        vertical_x = max(0, vertical_x - step)
        update_overlay_image(overlay_image, horizontal_y, vertical_x)
        disp.buffer[offset_y:offset_y+DESIRED_OVERLAY_RES[1],
                    offset_x:offset_x+DESIRED_OVERLAY_RES[0], :] = overlay_image
        disp.update()

    def on_right():
        nonlocal vertical_x, horizontal_y, overlay_image
        vertical_x = min(DESIRED_OVERLAY_RES[0]-1, vertical_x + step)
        update_overlay_image(overlay_image, horizontal_y, vertical_x)
        disp.buffer[offset_y:offset_y+DESIRED_OVERLAY_RES[1],
                    offset_x:offset_x+DESIRED_OVERLAY_RES[0], :] = overlay_image
        disp.update()

    def on_up():
        nonlocal horizontal_y, vertical_x, overlay_image
        horizontal_y = max(0, horizontal_y - step)
        update_overlay_image(overlay_image, horizontal_y, vertical_x)
        disp.buffer[offset_y:offset_y+DESIRED_OVERLAY_RES[1],
                    offset_x:offset_x+DESIRED_OVERLAY_RES[0], :] = overlay_image
        disp.update()

    def on_down():
        nonlocal horizontal_y, vertical_x, overlay_image
        horizontal_y = min(DESIRED_OVERLAY_RES[1]-1, horizontal_y + step)
        update_overlay_image(overlay_image, horizontal_y, vertical_x)
        disp.buffer[offset_y:offset_y+DESIRED_OVERLAY_RES[1],
                    offset_x:offset_x+DESIRED_OVERLAY_RES[0], :] = overlay_image
        disp.update()

    # Attach callbacks to button press events.
    button_left.when_pressed = on_left
    button_right.when_pressed = on_right
    button_up.when_pressed = on_up
    button_down.when_pressed = on_down

    # Main loop with periodic saving every 10 seconds.
    last_save_time = time.time()
    try:
        while True:
            time.sleep(0.1)
            if time.time() - last_save_time >= 10:
                save_offset(horizontal_y, vertical_x)
                last_save_time = time.time()
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        # Save one last time on exit.
        save_offset(horizontal_y, vertical_x)
        camera.stop_preview()
        camera.close()

if __name__ == '__main__':
    main()
