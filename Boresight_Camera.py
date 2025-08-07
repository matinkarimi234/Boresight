from Button_Control import ButtonControl
from Camera_Setup import CameraSetup
from Overlay_Display import OverlayDisplay
import time

def main():
    overlay_display = OverlayDisplay()
    overlay_res = overlay_display.scale_overlay()

    offset_x = (overlay_display.disp_width - overlay_res[0]) // 2
    offset_y = (overlay_display.disp_height - overlay_res[1]) // 2

    overlay_display.update_overlay(offset_x, offset_y, overlay_res)

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
        button_control.save_offset()

if __name__ == '__main__':
    main()
