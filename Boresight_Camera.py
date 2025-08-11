import threading
from Button_Control import ButtonControl
from Camera_Setup import CameraSetup
from Overlay_Display import OverlayDisplay, StaticPNGOverlay, TextOverlay, ContainerOverlay
from State_Machine import StateMachine, StateMachineEnum
from Alarm import BuzzerControl, LEDControl
import time
from Record_Manager import MetadataRecorder,RecordingManager

# Add global variable to track button press duration
ok_button_press_start_time = None
ok_button_press_duration = 0

button_left_up_pressed = False
button_right_down_pressed = False

arrow_buttons_press_start_time = None
arrow_buttons_press_duration = 0

def buttons_state_update_callback(flag):
    global ok_button_press_duration, ok_button_press_start_time, button_left_up_pressed
    global button_right_down_pressed, arrow_buttons_press_start_time, arrow_buttons_press_duration
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

    elif flag == ButtonControl.RIGHT_DOWN_BUTTON_PRESSED:
        button_right_down_pressed = True

    elif flag == ButtonControl.LEFT_UP_BUTTON_RELEASED:
        button_left_up_pressed = False
        
    elif flag == ButtonControl.RIGHT_DOWN_BUTTON_RELEASED:
        button_right_down_pressed = False

    if button_left_up_pressed and button_right_down_pressed:
        arrow_buttons_press_start_time = time.time()
    else:
        if arrow_buttons_press_start_time:
            arrow_buttons_press_duration = time.time() - arrow_buttons_press_start_time

            arrow_buttons_press_start_time = None






def main():
    led_control = LEDControl(23)
    buzzer_control = BuzzerControl(21)

    # Initialize state machine
    state_machine = StateMachine()
    # --- Initialize Camera Setup ---
    camera = CameraSetup()
    camera.start_preview()  # Start the camera preview

    # Create overlays

    # --- Initialize Overlay Display ---
    overlay_display = OverlayDisplay()
    overlay_display.set_style(radius=20, tick_length=300, ring_thickness=1, tick_thickness=1, gap=-10)
    overlay_display.refresh()

    
    clock_overlay = TextOverlay(layer=2001,
                        font_path="Fonts/digital-7.ttf",
                        font_size=36,
                        pos=('left', 'bottom'),
                        color=(130, 0, 0, 255),
                        offset=20)
    
    state_overlay = TextOverlay(layer=2002,
                        font_path="Fonts/digital-7.ttf",
                        rec_color=(130,0,0,255),
                        font_size=36,
                        pos=('right', 'top'),
                        color=(130, 0, 0, 255),
                        offset=20)
    

    static_png = StaticPNGOverlay("Pictures/Farand_Logo.png", layer=2003,
                              pos=('left','top'),  # or numbers like (50, 30)
                              scale=0.5,
                              offset=20)                # or (width, height)
    static_png.show()  # draws once and done

    side_bars = ContainerOverlay(bar_width=60, layer=2004, alpha=128)
    side_bars.show()


    record_manager = RecordingManager(base_dir="/home/boresight/Saved_Videos")

    # --- Initialize Button Control ---
    button_control = ButtonControl(lambda flag: buttons_state_update_callback(flag))


    def state_machine_thread():
        global ok_button_press_duration, button_left_up_pressed, button_right_down_pressed, arrow_buttons_press_duration
        nonlocal_rec_started = False  # optional guard
        STEP = 1  # pixels per tick; tweak as you like

        while state_machine.running:
            current_state = state_machine.get_state()
            tick = 0.125  # default tick (slower when not adjusting)

            if current_state == StateMachineEnum.START_UP_STATE:
                buzzer_control.start_toggle(0.25, 0.25, 1)
                buzzer_control.start_toggle(0.1, 0.1, 2)
                state_machine.change_state(StateMachineEnum.NORMAL_STATE)
                state_overlay.set_text("LIVE")

            elif current_state == StateMachineEnum.NORMAL_STATE:
                # GOTO Adjustment State
                if ok_button_press_duration >= 3:  # long-press OK to enter H adjust
                    ok_button_press_duration = 0
                    buzzer_control.start_toggle(0.5, 1, 1)
                    state_machine.change_state(StateMachineEnum.HORIZONTAL_ADJUSTMENT)
                    state_overlay.set_text("Horizontal ADJ.")
                    led_control.start_toggle(0.5, 0.5)

                # GOTO RECORDING STATE
                if arrow_buttons_press_duration >= 3:
                    arrow_buttons_press_duration = 0
                    buzzer_control.start_toggle(0.5, 1, 1)
                    state_machine.change_state(StateMachineEnum.RECORD_STATE)
                    state_overlay.set_text("REC.")
                    led_control.start_toggle(0.5, 0.5)

            elif current_state == StateMachineEnum.RECORD_STATE:
                # START recording + metadata on first entry
                if not record_manager.active:
                    record_manager.start(
                        camera=camera.camera,
                        overlay_display=overlay_display,
                        state_text_fn=lambda: (state_overlay.last_text or "")
                    )
                    print("Recording to:", record_manager.video_path)
                    print("Metadata to  :", record_manager.meta_path)


                if ok_button_press_duration > 0:
                    ok_button_press_duration = 0
                    buzzer_control.start_toggle(0.25, 1, 1)
                    led_control.stop()

                    

                    state_overlay.set_text("SAVING...")
                    # STOP recording + metadata
                    record_manager.stop(camera.camera)
                    print("Saved:", record_manager.video_path)
                    print("Sidecar:", record_manager.meta_path)

                    state_machine.change_state(StateMachineEnum.SAVING_VIDEO_STATE)
                    

            elif current_state == StateMachineEnum.HORIZONTAL_ADJUSTMENT:
                # Move vertical line left/right
                if button_left_up_pressed:
                    overlay_display.nudge_vertical(-STEP)   # left
                if button_right_down_pressed:
                    overlay_display.nudge_vertical(+STEP)   # right

                # faster loop in adjust mode
                tick = 0.02

                # short-press OK to switch to vertical adjust
                if ok_button_press_duration > 0:
                    ok_button_press_duration = 0
                    buzzer_control.start_toggle(0.25, 1, 1)
                    state_overlay.set_text("Vertical ADJ.")
                    state_machine.change_state(StateMachineEnum.VERTICAL_ADJUSTMENT)

            elif current_state == StateMachineEnum.VERTICAL_ADJUSTMENT:
                # Move horizontal line up/down
                if button_left_up_pressed:
                    overlay_display.nudge_horizontal(-STEP)  # up
                if button_right_down_pressed:
                    overlay_display.nudge_horizontal(+STEP)  # down

                # faster loop in adjust mode
                tick = 0.02

                # short-press OK to exit to normal
                if ok_button_press_duration > 0:
                    ok_button_press_duration = 0
                    led_control.stop()
                    buzzer_control.start_toggle(0.5, 1, 1)
                    state_overlay.set_text("LIVE")
                    state_machine.change_state(StateMachineEnum.NORMAL_STATE)

            elif current_state == StateMachineEnum.SAVING_VIDEO_STATE:
                if record_manager.active == False:
                    state_machine.change_state(StateMachineEnum.NORMAL_STATE)
                    state_overlay.set_text("LIVE")

            time.sleep(tick)


    # Start the state machine thread
    threading.Thread(target=state_machine_thread, daemon=True).start()

    # replace the infinite main loop with this low-CPU version ---
    last_save_time = time.time()
    last_sec = None
    try:
        while True:
            # Sleep a short time so main loop is responsive but not busy.
            # We keep this loop independent from the state machine thread.
            time.sleep(0.05)

            # Clock updates only when the second changes (once per second)
            now = time.strftime("%H:%M:%S")
            if now != last_sec:
                last_sec = now
                clock_overlay.set_text(now)

            # Periodically save offset every 10 seconds
            if time.time() - last_save_time >= 10:
                overlay_display.save_offset()
                last_save_time = time.time()

    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        overlay_display.save_offset()
        
        camera.stop_preview()

        if record_manager.active:
            record_manager.stop(camera.camera)

        state_machine.stop()

if __name__ == '__main__':
    main()

