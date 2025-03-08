import numpy as np  # Ensure numpy is imported first.
from dispmanx import DispmanX
import time
import curses
from picamera import PiCamera
from gpiozero import Button

# Desired overlay resolution (sensor native crop)
DESIRED_OVERLAY_RES = (1920, 1080)  # (width, height)

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
    # Initialize curses settings.
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.clear()
    stdscr.addstr(0, 0, "Push buttons for crosshair movement:")
    stdscr.addstr(1, 0, "  Left=GPIO5, Down=GPIO6, Right=GPIO24, Up=GPIO23")
    stdscr.addstr(2, 0, "Press 'r' to toggle recording; 'q' to quit.")

    # --- Start PiCamera Preview ---
    camera = PiCamera()
    camera.resolution = DESIRED_OVERLAY_RES
    camera.sensor_mode = 1
    camera.iso = 100
    camera.framerate = 30
    camera.exposure_mode = 'sports'
    camera.awb_mode = 'auto'
    camera.start_preview(fullscreen=True)
    time.sleep(2)  # Allow the preview to initialize.

    # --- Initialize DispmanX overlay ---
    disp = DispmanX(pixel_format="RGBA", buffer_type="numpy", layer=2000)
    disp_width, disp_height = disp.size  # Full display resolution
    offset_x = (disp_width - DESIRED_OVERLAY_RES[0]) // 2
    offset_y = (disp_height - DESIRED_OVERLAY_RES[1]) // 2

    # Create the overlay image buffer.
    overlay_image = np.zeros((DESIRED_OVERLAY_RES[1], DESIRED_OVERLAY_RES[0], 4), dtype=np.uint8)
    horizontal_y = DESIRED_OVERLAY_RES[1] // 2
    vertical_x = DESIRED_OVERLAY_RES[0] // 2
    update_overlay_image(overlay_image, horizontal_y, vertical_x)
    disp.buffer[offset_y:offset_y+DESIRED_OVERLAY_RES[1],
                offset_x:offset_x+DESIRED_OVERLAY_RES[0], :] = overlay_image
    disp.update()

    # --- Setup gpiozero Push Buttons for Crosshair Movement ---
    button_left = Button(5)
    button_down = Button(6)
    button_right = Button(24)
    button_up = Button(23)
    step = 10  # Movement step in pixels

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

    button_left.when_pressed = on_left
    button_right.when_pressed = on_right
    button_up.when_pressed = on_up
    button_down.when_pressed = on_down

    # --- Recording Toggle Setup ---
    recording = False
    video_filename = "video.h264"

    # --- Main Loop: Check for Keyboard Input ---
    try:
        while True:
            key = stdscr.getch()
            if key != -1:
                if key == ord('q'):
                    break
                elif key == ord('r'):
                    if not recording:
                        stdscr.addstr(3, 0, "Recording started...          ")
                        # Note: This records only the camera's feed, not the overlay.
                        camera.start_recording(video_filename)
                        recording = True
                    else:
                        stdscr.addstr(3, 0, "Recording stopped and saved.  ")
                        camera.stop_recording()
                        recording = False
                    # Simple debounce delay
                    time.sleep(0.3)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        if recording:
            camera.stop_recording()
        camera.stop_preview()
        camera.close()

if __name__ == '__main__':
    curses.wrapper(main)
