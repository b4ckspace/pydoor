# pydoor

Automated door lock system based on Raspberry Pi

## Requirements

### Hardware

- Raspberry Pi (tested on Raspberry Pi 3)

### Operating System

- Raspberry Pi OS (formerly knows as Raspbian)

### Software

- Python 3 (uses system's Python 3 distribution)
- `python3-venv`
- `python3-rpi.gpio` (Note: also required outside of venv?)
- `nginx`

For specific Python dependencies see `requirements.txt`.

### Installation

1. Clone this repository: `git clone https://github.com/b4ckspace/pydoor.git`
2. Create Python virtual environment, e.g.: `python3 -m venv venv`
3. Activate venv: `. venv/bin/activate`
4. In venv install dependencies: `pip install -r requirements.txt`
5. Copy systemd service file: `cp extras/systemd/pydoor.service /etc/systemd/system/`
6. Copy systemd service environment file: `cp extras/systemd/pydoor.env /etc/default/`
7. Adjust systemd serice enviroment file `/etc/default/pydoor.env`
8. Enable systemd service: `systemd enable pydoor.service`
9. Install and adjust nginx configuration: `cp extras/nginx/default /etc/nginx/conf.d/default`
10. Reload nginx: `systemd reload nginx.service`

Important: Make sure that the logging output of the service (`sudo journalctl -u pydoor.service -f`) does not contain warnings like "PinFactoryFallback: Falling back from rpigpio: No module named 'RPi'" or "NativePinFactoryFallback: Falling back to the experimental pin factory NativeFactory because no other pin factory could be loaded. For best results, install RPi.GPIO or pigpio. See https://gpiozero.readthedocs.io/en/stable/api_pins.html for more information." – this means a pin driver library like `RPi.GPIO` is missing (see [gpiozero FAQ](https://gpiozero.readthedocs.io/en/stable/faq.html#why-do-i-get-pinfactoryfallback-warnings-when-i-import-gpiozero)).
