from enum import Enum
import time
import threading

class StateMachineEnum(Enum):
    START_UP_STATE = 0
    NORMAL_STATE = 1
    RECORD_STATE = 2
    HORIZONTAL_ADJUSTMENT = 3
    VERTICAL_ADJUSTMENT = 4

class StateMachine:
    def __init__(self):
        self.state = StateMachineEnum.START_UP_STATE
        self.running = True
        self.lock = threading.Lock()  # To avoid race conditions when changing states

    def change_state(self, new_state):
        with self.lock:
            self.state = new_state
            print(f"State changed to {self.state.name}")

    def get_state(self):
        return self.state

    def stop(self):
        self.running = False

