import threading
from soupsieve import match
from Button_Control import ButtonControl
from Camera_Setup import CameraSetup
from Overlay_Display import OverlayDisplay
from State_Machine import StateMachine, StateMachineEnum
from Alarm import BuzzerControl, LEDControl
import time

# Add global variable to track button press duration
ok_button_press_start_time = None
ok_button_press_duration = 0

def buttons_state_update_callback(flag):
    global ok_button_press_duration, ok_button_press_start_time
    """Callback to receive flags from ButtonControl."""
    match flag:
        case ButtonControl.OK_PRESSED:
            # Start a timer when the button is pressed
            ok_button_press_start_time = time.time()
            print("OK button pressed")
        case ButtonControl.OK_RELEASED:
            print("OK button released")
            if ok_button_press_start_time:
                ok_button_press_duration = time.time() - ok_button_press_start_time

                ok_button_press_start_time = None  # Reset the timer after release

def main():
    global ok_button_press_duration
    led_control = LEDControl(23)
    buzzer_control = BuzzerControl(40)

    # Initialize state machine
    state_machine = StateMachine()
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
    button_control = ButtonControl(lambda flag: buttons_state_update_callback(flag))


    # Create a thread for running the state machine
    def state_machine_thread():
        while state_machine.running:
            # Here we can add actions based on the state
            current_state = state_machine.get_state()

            match current_state:
                case StateMachineEnum.START_UP_STATE:
                    pass

                case StateMachineEnum.NORMAL_STATE:
                    if ok_button_press_duration >= 3: # 3 Seconds Pressed
                        ok_button_press_duration = 0
                        state_machine.change_state(StateMachineEnum.HORIZONTAL_ADJUSTMENT)
                        buzzer_control.toggle_buzzer(2,1,1)

                case StateMachineEnum.RECORD_STATE:
                    pass

                case StateMachineEnum.HORIZONTAL_ADJUSTMENT:
                    led_control.start_toggle(1, 1)
                    print("Adjusting horizontally...")
                    
                case StateMachineEnum.VERTICAL_ADJUSTMENT:
                    pass
                case StateMachineEnum.SAVING_VIDEO_STATE:
                    pass
            time.sleep(0.125)

    # Start the state machine thread
    threading.Thread(target=state_machine_thread, daemon=True).start()

    # Main loop with periodic saving every 10 seconds
    last_save_time = time.time()
    try:
        while True:
            time.sleep(0.125)
            if time.time() - last_save_time >= 10:
                overlay_display.save_offset()
                last_save_time = time.time()
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        # Save offset and stop the camera preview when exiting
        overlay_display.save_offset()
        camera.stop_preview()
        state_machine.stop()

if __name__ == '__main__':
    main()

