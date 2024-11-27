import threading

class StateManager:
    STATES = ['WAITING_FOR_POWER', 'WAITING_FOR_DEPENDENCY', 'WAITING_FOR_TICK', 'READY_TO_PROCESS', 'PROCESSING', 'DONE']

    def __init__(self, dependencies=None):
        self.state = 'WAITING_FOR_POWER'
        self.lock = threading.Lock()
        self.power_received = False
        self.dependency_received = False
        self.tick_received = False
        self.dependencies_met = False

    def receive_power(self):
        with self.lock:
            self.power_received = True
            self._update_state()

    def receive_dependency(self):
        with self.lock:
            self.dependency_received = True
            self._update_state()

    def receive_tick(self):
        with self.lock:
            self.tick_received = True
            self._update_state()

    def _update_state(self):
        # Update the container state based on the current conditions
        if self.power_received and self.dependency_received:
            if self.tick_received:
                self.state = 'READY_TO_PROCESS'
            else:
                self.state = 'WAITING_FOR_TICK'
        elif self.power_received:
            self.state = 'WAITING_FOR_DEPENDENCY'
        else:
            self.state = 'WAITING_FOR_POWER'

    def is_ready_to_process(self):
        return self.state == 'READY_TO_PROCESS'

    def start_processing(self):
        with self.lock:
            if self.state == 'READY_TO_PROCESS':
                self.state = 'PROCESSING'
                return True
            return False

    def complete_processing(self):
        with self.lock:
            if self.state == 'PROCESSING':
                self.state = 'DONE'
                self._reset_state_for_next_tick()

    def _reset_state_for_next_tick(self):
        # Reset state for the next tick
        self.state = 'WAITING_FOR_POWER'
        self.power_received = False
        self.dependency_received = False
        self.tick_received = False