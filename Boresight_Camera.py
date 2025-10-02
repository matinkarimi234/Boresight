import threading
from Button_Control import ButtonControl
from Camera_Setup import CameraSetup
from Overlay_Display import OverlayDisplay, StaticPNGOverlay, TextOverlay, ContainerOverlay
from State_Machine import StateMachine, StateMachineEnum
from Alarm import BuzzerControl, LEDControl
import time
from Record_Manager import MetadataRecorder,RecordingManager
import os

OVERLAY_COLOR = (180, 0, 0, 255)

# Add global variable to track button press duration
ok_button_press_start_time = None
ok_button_press_duration = 0

button_left_up_pressed = False
button_right_down_pressed = False

button_ok_pressed = False

arrow_buttons_press_start_time = None
arrow_buttons_press_duration = 0

exit_buttons_start_time = None
exit_buttons_press_duration = 0

zoom_Step = 1

def buttons_state_update_callback(flag):
    global ok_button_press_duration, ok_button_press_start_time, button_left_up_pressed
    global button_right_down_pressed, arrow_buttons_press_start_time, arrow_buttons_press_duration
    global button_ok_pressed, exit_buttons_press_duration, exit_buttons_start_time
    """Callback to receive flags from ButtonControl."""
    
    if flag == ButtonControl.OK_PRESSED:
        button_ok_pressed = True;
        # Start a timer when the button is pressed
        ok_button_press_start_time = time.time()
        print("OK button pressed")

    elif flag == ButtonControl.OK_RELEASED:
        button_ok_pressed = False
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


    if button_left_up_pressed and button_ok_pressed:
        exit_buttons_start_time = time.time()

    else:
        if exit_buttons_start_time:
            exit_buttons_press_duration = time.time() - exit_buttons_start_time

            exit_buttons_start_time = None







def main():
    led_control = LEDControl(23)
    buzzer_control = BuzzerControl(12)
    global prezoom_reticle_px

    # --- Initialize Button Control ---
    button_control = ButtonControl(lambda flag: buttons_state_update_callback(flag))

    # Initialize state machine
    state_machine = StateMachine()

    # --- Initialize Camera Setup ---
    camera = CameraSetup()

    # --- Initialize Overlay Display ---
    overlay_display = OverlayDisplay(radius=20, tick_length=300, ring_thickness=1, tick_thickness=1, gap=-10, color=OVERLAY_COLOR)
    overlay_display.set_style(scale_spacing=10, scale_major_every=5, scale_major_length=15, scale_minor_length=5, scale_label_show=False, scale_tick_thickness=1)
    overlay_display.refresh()

    # Tell CameraSetup the REAL display aspect (not just camera.resolution)
    camera.set_display_aspect(overlay_display.disp_width, overlay_display.disp_height)  # 1280x720 → 16:9

    # Put the preview in the exact window to avoid any aspect distortion
    camera.camera.start_preview(fullscreen=False,
                                window=(0, 0, overlay_display.disp_width, overlay_display.disp_height))

    # If left/right feels reversed on your rig, 'inverse' fixes it. Use 'forward' otherwise.
    camera.set_mapping_mode('inverse')

    side_bars = ContainerOverlay(bar_width=150, layer=2001, alpha=150)
    side_bars.show()

    clock_overlay = TextOverlay(layer=2002,
                        font_path="Fonts/digital-7.ttf",
                        font_size=36,
                        pos=('left', 'bottom'),
                        color= OVERLAY_COLOR,
                        offset=20)
    
    state_overlay = TextOverlay(layer=2003,
                        font_path="Fonts/digital-7.ttf",
                        rec_color= OVERLAY_COLOR,
                        font_size=36,
                        pos=('right', 'top'),
                        color= OVERLAY_COLOR,
                        offset=20)
    
    static_png = StaticPNGOverlay("Pictures/Farand_Logo.png", layer=2004,
                              pos=('left','top'),
                              scale=0.35,
                              offset=20)
    static_png.show()

    record_manager = RecordingManager(base_dir="/home/boresight/Saved_Videos")

    # ---- Zoom/reticle behavior state ----
    prezoom_reticle_px = None   # (x_px, y_px) saved when going from 1x -> >1x
    current_zoom = 1

    print("disp:", overlay_display.disp_width, overlay_display.disp_height)
    print("cam :", camera.camera.resolution)


    def center_overlay_reticle():
        overlay_display.center_on_screen(refresh=True)

    def restore_overlay_reticle():
        global prezoom_reticle_px
        if prezoom_reticle_px is not None:
            x_px, y_px = prezoom_reticle_px
            overlay_display.set_center(x_px, y_px, refresh=True)
        prezoom_reticle_px = None

    def state_machine_thread():
        global ok_button_press_duration, button_left_up_pressed, button_right_down_pressed, arrow_buttons_press_duration, exit_buttons_press_duration
        global zoom_Step, button_ok_pressed
        global prezoom_reticle_px
        nonlocal current_zoom

        reticle_STEP = 1  # pixels per tick

        while state_machine.running:
            current_state = state_machine.get_state()
            tick = 0.125  # default tick

            if current_state == StateMachineEnum.START_UP_STATE:
                buzzer_control.start_toggle(0.25, 0.25, 1)
                buzzer_control.start_toggle(0.1, 0.1, 2)
                state_machine.change_state(StateMachineEnum.NORMAL_STATE)
                state_overlay.set_text("LIVE")

            elif current_state == StateMachineEnum.NORMAL_STATE:
                # Enter H adjust
                if ok_button_press_duration >= 3 and exit_buttons_press_duration == 0:
                    ok_button_press_duration = 0
                    buzzer_control.start_toggle(0.5, 1, 1)
                    state_machine.change_state(StateMachineEnum.HORIZONTAL_ADJUSTMENT)
                    state_overlay.set_text("H ADJ.")
                    led_control.start_toggle(0.5, 0.5)

                # ---- Zoom In ----
                if button_left_up_pressed and not button_right_down_pressed and not button_ok_pressed:
                    if current_zoom == 1:
                        prezoom_reticle_px = overlay_display.get_center()

                    current_zoom = min(8, current_zoom + 1)
                    state_overlay.set_text(f"Zoom {current_zoom}x" if current_zoom > 1 else "LIVE")
                    buzzer_control.start_toggle(0.5, 1, 1)

                    # 1) where is the reticle now (display-normalized)?
                    nx0, ny0 = overlay_display.reticle_norm_on_display()

                    # 2) center the ROI on that world point
                    camera.center_zoom_step(current_zoom, reticle_norm_display=(nx0, ny0))

                    # 3) snap overlay reticle to exact screen center (avoid rounding drift)
                    center_overlay_reticle()

                # ---- Zoom Out ----
                if button_right_down_pressed and not button_left_up_pressed and not button_ok_pressed:
                    current_zoom = max(1, current_zoom - 1)
                    state_overlay.set_text(f"Zoom {current_zoom}x" if current_zoom > 1 else "LIVE")
                    buzzer_control.start_toggle(0.5, 1, 1)

                    if current_zoom > 1:
                        # keep centering ROI on the same world point under current reticle
                        nx0, ny0 = overlay_display.reticle_norm_on_display()
                        camera.center_zoom_step(current_zoom, reticle_norm_display=(nx0, ny0))
                        center_overlay_reticle()
                    else:
                        # back to 1x: full frame + restore original reticle position
                        camera.center_zoom_step(1.0, reticle_norm_display=None)
                        restore_overlay_reticle()

                # GOTO RECORDING STATE
                if arrow_buttons_press_duration >= 3:
                    arrow_buttons_press_duration = 0
                    buzzer_control.start_toggle(0.5, 1, 1)
                    state_machine.change_state(StateMachineEnum.RECORD_STATE)
                    state_overlay.set_text("REC.")
                    led_control.start_toggle(0.5, 0.5)

                # Exiting
                if exit_buttons_press_duration >= 3:
                    exit_buttons_press_duration = 0
                    buzzer_control.start_toggle(1, 1, 2)
                    time.sleep(5)
                    os._exit(0)

            elif current_state == StateMachineEnum.RECORD_STATE:
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
                    record_manager.stop(camera.camera)
                    print("Saved:", record_manager.video_path)
                    print("Sidecar:", record_manager.meta_path)

                    state_machine.change_state(StateMachineEnum.SAVING_VIDEO_STATE)

            elif current_state == StateMachineEnum.HORIZONTAL_ADJUSTMENT:
                if button_left_up_pressed:
                    overlay_display.nudge_vertical(-reticle_STEP)   # left
                if button_right_down_pressed:
                    overlay_display.nudge_vertical(+reticle_STEP)   # right
                tick = 0.02
                if ok_button_press_duration > 0:
                    ok_button_press_duration = 0
                    buzzer_control.start_toggle(0.25, 1, 1)
                    state_overlay.set_text("V ADJ.")
                    state_machine.change_state(StateMachineEnum.VERTICAL_ADJUSTMENT)

            elif current_state == StateMachineEnum.VERTICAL_ADJUSTMENT:
                if button_left_up_pressed:
                    overlay_display.nudge_horizontal(-reticle_STEP)  # up
                if button_right_down_pressed:
                    overlay_display.nudge_horizontal(+reticle_STEP)  # down
                tick = 0.02
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

    # Low-CPU main loop
    last_save_time = time.time()
    last_sec = None
    try:
        while True:
            time.sleep(0.05)

            # Clock update once per second
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
        try: 
            side_bars.hide()
        except: 
            pass
        try:
             static_png.hide()
        except:
            pass
        # clear the reticle layer completely
        try:
            overlay_display.disp.buffer[:] = 0
            overlay_display.disp.update()
        except:
            pass
        
        camera.stop_preview()

        state_machine.stop()

if __name__ == '__main__':
    main()

