import dataclasses
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
        self._door_driver_thread = None
        self._mqtt_client = mqtt.Client()
        self._mqtt_client.connect_async(mqtt_host)
        self.door_driver = DoorDriver(self._mqtt_client)

    def start(self):
        self._mqtt_client.loop_start()
        self._door_driver_thread = threading.Thread(target=self.door_driver.run_forever)
        self._door_driver_thread.start()
        signal.signal(signal.SIGTERM, self._shutdown)

    def stop(self):
        self.door_driver.stop()
        self._door_driver_thread.join()
        self._mqtt_client.loop_stop()

    def _shutdown(self, signo, sigframe):
        print(f'DoorApp shutting down', file=sys.stderr)
        self.stop()


class DoorOperation(enum.Enum):
    STOP = 1
    LOCK = 2
    UNLOCK = 3
    LOCK_SHUTDOWN = 4


@dataclasses.dataclass
class QueueCommand:
    operation: DoorOperation
    who: str
    force: bool


class DoorDriver:
    BUTTON_SHUTDOWN_LOCK_TIME = 60
    ZERO_MEMBER_PRESENT_SHUTDOWN_TIMEOUT = 15 * 60

    def __init__(self, mqtt_client):
        self._mqtt_client = mqtt_client
        self._is_running = False
        self._shutdown_timer = 0
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
        self._last_command_time = time.monotonic()
        self._zero_member_present_time = 0
        self._mqtt_client.on_connect = self._on_mqtt_connect
        self._mqtt_client.on_message = self._on_mqtt_message

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

    def lock(self, who=None, force=False):
        self._queue_operation(DoorOperation.LOCK, who, force)

    def lock_shutdown(self):
        self._queue_operation(DoorOperation.LOCK_SHUTDOWN, who=None, force=True)

    def unlock(self, who=None, force=False):
        self._queue_operation(DoorOperation.UNLOCK, who, force)

    def stop(self):
        self._queue_operation(DoorOperation.STOP, who=None, force=True)

    def run_forever(self):
        self._is_running = True
        while self._is_running:
            operation_fn = self._process_queue()
            operation_fn()

    def _process_queue(self):
        """ Processes queue entries for door operations

        This function will *NOT* execute commands immediately, but take the
        last command in the queue unless the command is forced. This prevents
        the door executing unnecessary operations for a long time; it does,
        however, not prevent the same command executed twice in the row when
        the queue was empty in between. This behavior is intended.
        :return:
        """
        timeout = 10
        try:
            command = self._command_queue.get(timeout=timeout)
            self._last_command_time = time.monotonic()
        except queue.Empty:
            if self._zero_member_present_time > 0:
                time_passed = time.monotonic() - self._zero_member_present_time
                if time_passed > self.ZERO_MEMBER_PRESENT_SHUTDOWN_TIMEOUT:
                    return self._lock_door_emergency
            return self._nop
        operation_fn = {
            DoorOperation.LOCK: self._lock_door,
            DoorOperation.UNLOCK: self._unlock_door,
            DoorOperation.LOCK_SHUTDOWN: self._lock_door_shutdown,
            DoorOperation.STOP: self._stop
        }[command.operation]
        self._log_command(command)
        if self._command_queue.empty() or command.force:
            return operation_fn
        return self._nop

    def _queue_operation(self, operation, who, force):
        self._command_queue.put(QueueCommand(operation, who, force))

    def _nop(self):
        pass

    def _stop(self):
        self._is_running = False

    def _unlock_door(self):
        self._zero_member_present_time = 0
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

    def _lock_door_shutdown(self):
        time.sleep(3)
        if self.is_closed:
            self._lock_door()

    def _lock_door_emergency(self):
        if not self.is_locked and self.is_closed:
            self._mqtt_client.publish('psa/alarm', 'Notfallabschliessung der Tuer!')
            self._lock_door()
            self._zero_member_present_time = 0

    def _button_pressed(self):
        self._mqtt_client.publish('sensor/door/button', 'pressed')
        if self.is_unlocked:
            self._shutdown_timer = time.monotonic()
        else:
            self.unlock()

    def _button_released(self):
        self._mqtt_client.publish('sensor/door/button', 'released')

    def _door_opened(self):
        self._mqtt_client.publish('sensor/door/frame', 'open')

    def _door_closed(self):
        self._mqtt_client.publish('sensor/door/frame', 'closed')
        if self._shutdown_timer > 0:
            seconds_passed = time.monotonic() - self._shutdown_timer
            self._shutdown_timer = 0
            if seconds_passed <= self.BUTTON_SHUTDOWN_LOCK_TIME:
                self.lock_shutdown()

    def _door_locked(self):
        self._mqtt_client.publish('sensor/door/lock', 'closed')

    def _door_unlocked(self):
        self._mqtt_client.publish('sensor/door/lock', 'open')

    def _log_command(self, command):
        who = command.who
        now = datetime.utcnow()
        print(f'{now}: {command.operation.name} (user: {who})', file=sys.stderr)

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        client.subscribe('sensor/space/member/present', 0)

    def _on_mqtt_message(self, client, userdata, message: mqtt.MQTTMessage):
        try:
            member_count = int(message.payload, 10)
        except ValueError:
            return
        if member_count == 0:
            self._zero_member_present_time = time.monotonic()
        else:
            self._zero_member_present_time = 0


def get_door_app_environ(start=True):
    mqtt_host = os.environ.get('PYDOOR_MQTT_HOST', 'mqtt.core.bckspc.de')
    door_app = DoorApp(mqtt_host)
    if start:
        door_app.start()
    return door_app
