import enum
import logging
import os
import queue
import signal
import sys
import threading
import time
from datetime import datetime

from gpiozero import DigitalOutputDevice, Button
import paho.mqtt.client as mqtt


logger = logging.getLogger(__name__)


class DoorApp:
    def __init__(self, mqtt_host):
        self._door_state_thread = None
        self._mqtt_client = mqtt.Client()
        self._mqtt_client.connect_async(mqtt_host)
        self.door_state = DoorState(self._mqtt_client)
        self._door_state_thread = threading.Thread(target=self.door_state.run_forever)

    def start(self):
        self._mqtt_client.loop_start()
        self._door_state_thread.start()
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signo, sigframe):
        self.door_state.stop()
        self._door_state_thread.join()
        self._mqtt_client.loop_stop()


class DoorOperations(enum.Enum):
    STOP = 1
    LOCK = 2
    UNLOCK = 3
    LOCK_SHUTDOWN = 4


class QueueCommand:
    def __init__(self, operation, args=None):
        if args is None:
            args = {}
        self.operation = operation
        self.args = args

    def __repr__(self):
        return repr(self.__dict__)


class DoorState:
    def __init__(self, mqtt_client):
        self._mqtt_client = mqtt_client
        self._is_running = False
        self._next_door_close_shutdown = False
        self._gpio_unlock = DigitalOutputDevice(23, active_high=False, initial_value=False)
        self._gpio_lock = DigitalOutputDevice(24, active_high=False, initial_value=False)
        self._buzzer = DigitalOutputDevice(25, active_high=True, initial_value=False)
        self._button = Button(17, pull_up=None, active_state=False, bounce_time=0.01)
        self._door_frame = Button(22, pull_up=None, active_state=False, bounce_time=0.01)
        self._door_bolt = Button(27, pull_up=None, active_state=False, bounce_time=0.01)
        self._command_queue = queue.SimpleQueue()
        self._button.when_pressed = self._button_pressed
        self._button.when_released = self._button_released
        self._door_frame.when_pressed = self._door_closed
        self._door_frame.when_released = self._door_opened
        self._door_bolt.when_pressed = self._door_locked
        self._door_bolt.when_released = self._door_unlocked

    @property
    def is_open(self):
        return not self._door_frame.is_pressed

    @property
    def is_closed(self):
        return self._door_frame.is_pressed

    @property
    def is_locked(self):
        return self._door_bolt.is_pressed

    @property
    def is_unlocked(self):
        return not self._door_bolt.is_pressed

    def run_forever(self):
        self._is_running = True
        next_operation = None
        while self._is_running:
            command = self._command_queue.get()
            if command.operation == DoorOperations.STOP:
                self._is_running = False
            elif command.operation in (DoorOperations.LOCK, DoorOperations.UNLOCK):
                self._log_command(command)
                next_operation = command.operation
            elif command.operation == DoorOperations.LOCK_SHUTDOWN:
                self._log_command(command)
                self._lock_shutdown()
            else:
                logger.warning(f'PROGRAMMING ERROR: Invalid command: {command}')
            if self._command_queue.empty() and next_operation is not None:
                self._apply_operation(next_operation)
                next_operation = None

    def _apply_operation(self, next_state):
        if next_state == DoorOperations.UNLOCK:
            self._unlock_door()
        elif next_state == DoorOperations.LOCK:
            self._lock_door()

    def lock(self, who=None):
        self._command_queue.put(QueueCommand(DoorOperations.LOCK, {
            'who': who
        }))

    def lock_shutdown(self):
        self._command_queue.put(QueueCommand(DoorOperations.LOCK_SHUTDOWN))

    def unlock(self, who=None):
        self._command_queue.put(QueueCommand(DoorOperations.UNLOCK, {
            'who': who
        }))

    def stop(self):
        self._command_queue.put(QueueCommand(DoorOperations.STOP, {}))

    def _unlock_door(self):
        self._buzzer.on()
        self._gpio_unlock.on()
        time.sleep(0.2)
        self._gpio_unlock.off()
        time.sleep(5)
        self._buzzer.off()

    def _lock_door(self):
        if self.is_open:
            return
        self._gpio_lock.on()
        time.sleep(0.2)
        self._gpio_lock.off()

    def _lock_shutdown(self):
        time.sleep(3)
        if self.is_closed:
            self._lock_door()

    def _button_pressed(self):
        print('Button was pressed', file=sys.stderr)
        self._mqtt_client.publish('sensor/door/button', 'pressed')
        if self.is_unlocked:
            self._next_door_close_shutdown = True
        else:
            self.unlock()

    def _button_released(self):
        print('Button was released', file=sys.stderr)
        self._mqtt_client.publish('sensor/door/button', 'released')

    def _door_opened(self):
        print('Door opened', file=sys.stderr)
        self._next_door_close_shutdown = False
        self._mqtt_client.publish('sensor/door/frame', 'open')

    def _door_closed(self):
        print('Door closed', file=sys.stderr)
        self._mqtt_client.publish('sensor/door/frame', 'closed')
        if self._next_door_close_shutdown:
            self._next_door_close_shutdown = False
            self.lock_shutdown()

    def _door_locked(self):
        print('Door locked', file=sys.stderr)
        self._mqtt_client.publish('sensor/door/lock', 'closed')

    def _door_unlocked(self):
        print('Door unlocked', file=sys.stderr)
        self._mqtt_client.publish('sensor/door/lock', 'open')

    def _log_command(self, command):
        who = command.args.get('who')
        now = datetime.utcnow()
        print(f'{now}: {command.operation.name} (user: {who})', file=sys.stderr)


def get_door_app_environ(start=True):
    mqtt_host = os.environ.get('PYDOOR_MQTT_HOST', 'mqtt.core.bckspc.de')
    door_app = DoorApp(mqtt_host)
    if start:
        door_app.start()
    return door_app
