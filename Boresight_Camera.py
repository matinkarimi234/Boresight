import threading
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
    
    if flag == ButtonControl.OK_PRESSED:
        # Start a timer when the button is pressed
        ok_button_press_start_time = time.time()
        print("OK button pressed")

    elif flag == ButtonControl.OK_RELEASED:
        print("OK button released")
        if ok_button_press_start_time:
            ok_button_press_duration = time.time() - ok_button_press_start_time

            ok_button_press_start_time = None  # Reset the timer after release

def main():
    led_control = LEDControl(23)
    buzzer_control = BuzzerControl(21)

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
        global ok_button_press_duration
        while state_machine.running:
            # Here we can add actions based on the state
            current_state = state_machine.get_state()

            if current_state == StateMachineEnum.START_UP_STATE:
                buzzer_control.toggle_buzzer(0.25,0.25,1)
                buzzer_control.toggle_buzzer(0.1,0.1,2)
                state_machine.change_state(StateMachineEnum.NORMAL_STATE)

            elif current_state == StateMachineEnum.NORMAL_STATE:
                if ok_button_press_duration >= 3: # 3 Seconds Pressed
                        ok_button_press_duration = 0
                        state_machine.change_state(StateMachineEnum.HORIZONTAL_ADJUSTMENT)
                        buzzer_control.toggle_buzzer(0.5,1,1)

            elif current_state == StateMachineEnum.RECORD_STATE:
                pass

            elif current_state == StateMachineEnum.HORIZONTAL_ADJUSTMENT:
                led_control.start_toggle(1, 1)
                if ok_button_press_duration > 0: # ok button just pressed
                    buzzer_control.toggle_buzzer(0.25,1,1)
                    state_machine.change_state(StateMachineEnum.VERTICAL_ADJUSTMENT)

            elif current_state == StateMachineEnum.VERTICAL_ADJUSTMENT:
                if ok_button_press_duration > 0: # ok button just pressed
                    led_control.stop()
                    buzzer_control.toggle_buzzer(0.5,1,1)
                    state_machine.change_state(StateMachineEnum.NORMAL_STATE)

            elif current_state == StateMachineEnum.SAVING_VIDEO_STATE:
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

