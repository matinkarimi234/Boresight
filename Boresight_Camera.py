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

button_left_up_pressed = False
button_right_down_pressed = False

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


    elif flag == ButtonControl.LEFT_UP_BUTTON_PRESSED:
        button_left_up_pressed = True

    elif flag == ButtonControl.LEFT_UP_BUTTON_RELEASED:
        button_left_up_pressed = False

    elif flag == ButtonControl.RIGHT_DOWN_BUTTON_PRESSED:
        button_right_down_pressed = True
        
    elif flag == ButtonControl.RIGHT_DOWN_BUTTON_RELEASED:
        button_right_down_pressed = False

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


    def state_machine_thread():
        global ok_button_press_duration, button_left_up_pressed, button_right_down_pressed
        nonlocal offset_x, offset_y

        STEP = 10  # pixels per tick; tweak as you like

        # boundaries for overlay movement
        max_x = overlay_display.disp_width  - overlay_res[0]
        max_y = overlay_display.disp_height - overlay_res[1]

        while state_machine.running:
            current_state = state_machine.get_state()
            tick = 0.125  # default tick (slower when not adjusting)

            if current_state == StateMachineEnum.START_UP_STATE:
                buzzer_control.toggle_buzzer(0.25, 0.25, 1)
                buzzer_control.toggle_buzzer(0.1, 0.1, 2)
                state_machine.change_state(StateMachineEnum.NORMAL_STATE)

            elif current_state == StateMachineEnum.NORMAL_STATE:
                if ok_button_press_duration >= 3:  # long-press OK to enter H adjust
                    ok_button_press_duration = 0
                    buzzer_control.toggle_buzzer(0.5, 1, 1)
                    state_machine.change_state(StateMachineEnum.HORIZONTAL_ADJUSTMENT)

            elif current_state == StateMachineEnum.RECORD_STATE:
                pass

            elif current_state == StateMachineEnum.HORIZONTAL_ADJUSTMENT:
                # blink LED to indicate adjust mode (your existing behavior)
                led_control.start_toggle(1, 1)

                moved = False
                # left/up -> move left
                if button_left_up_pressed:
                    new_x = max(0, offset_x - STEP)
                    moved = moved or (new_x != offset_x)
                    offset_x = new_x
                # right/down -> move right
                if button_right_down_pressed:
                    new_x = min(max_x, offset_x + STEP)
                    moved = moved or (new_x != offset_x)
                    offset_x = new_x

                if moved:
                    overlay_display.update_overlay(offset_x, offset_y, overlay_res)

                # faster loop in adjust mode
                tick = 0.02

                # short-press OK to switch to vertical adjust
                if ok_button_press_duration > 0:
                    ok_button_press_duration = 0
                    buzzer_control.toggle_buzzer(0.25, 1, 1)
                    state_machine.change_state(StateMachineEnum.VERTICAL_ADJUSTMENT)

            elif current_state == StateMachineEnum.VERTICAL_ADJUSTMENT:
                moved = False
                # left/up -> move up
                if button_left_up_pressed:
                    new_y = max(0, offset_y - STEP)
                    moved = moved or (new_y != offset_y)
                    offset_y = new_y
                # right/down -> move down
                if button_right_down_pressed:
                    new_y = min(max_y, offset_y + STEP)
                    moved = moved or (new_y != offset_y)
                    offset_y = new_y

                if moved:
                    overlay_display.update_overlay(offset_x, offset_y, overlay_res)

                # faster loop in adjust mode
                tick = 0.02

                # short-press OK to exit to normal
                if ok_button_press_duration > 0:
                    ok_button_press_duration = 0
                    led_control.stop()
                    buzzer_control.toggle_buzzer(0.5, 1, 1)
                    state_machine.change_state(StateMachineEnum.NORMAL_STATE)

            elif current_state == StateMachineEnum.SAVING_VIDEO_STATE:
                pass

            time.sleep(tick)


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

