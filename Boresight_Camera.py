from Button_Control import ButtonControl
from Camera_Setup import CameraSetup
from Overlay_Display import OverlayDisplay
import time

def main():
    # --- Initialize Camera Setup ---
    camera = CameraSetup()
    camera.start_preview()  # Start the camera preview

    # --- Initialize Overlay Display ---
    overlay_display = OverlayDisplay()
    overlay_res = overlay_display.scale_overlay()

    # Calculate the offset to center the overlay region.
    offset_x = (overlay_display.disp_width - overlay_res[0]) // 2
    offset_y = (overlay_display.disp_height - overlay_res[1]) // 2

    # Draw the initial overlay with default offset
    overlay_display.update_overlay(offset_x, offset_y, overlay_res)

    # --- Initialize Button Control ---
    button_control = ButtonControl(overlay_display)
    
    # Main loop with periodic saving every 10 seconds
    last_save_time = time.time()
    try:
        while True:
            time.sleep(0.1)
            if time.time() - last_save_time >= 10:
                button_control.save_offset()
                last_save_time = time.time()
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        # Save offset and stop the camera preview when exiting
        button_control.save_offset()
        camera.stop_preview()

if __name__ == '__main__':
    main()

