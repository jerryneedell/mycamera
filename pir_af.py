# SPDX-FileCopyrightText: 2023 Brent Rubell for Adafruit Industries
#
# An open-source IoT doorbell with the Adafruit MEMENTO camera and Adafruit IO
#
# SPDX-License-Identifier: Unlicense
import os
import time
import ssl
import binascii
import digitalio
import mycamera
import board
import wifi
import socketpool
import adafruit_requests
from adafruit_io.adafruit_io import IO_HTTP, AdafruitIO_RequestError

print("CircuitPython PIR triggered Camera")

pir = digitalio.DigitalInOut(board.TX)

### WiFi ###
# Add settings.toml to your filesystem CIRCUITPY_WIFI_SSID and CIRCUITPY_WIFI_PASSWORD keys
# with your WiFi credentials. DO NOT share that file or commit it into Git or other
# source control.

# Set your Adafruit IO Username, Key and Port in settings.toml
# (visit io.adafruit.com if you need to create an account,
# or if you need your Adafruit IO key.)
aio_username = os.getenv("ADAFRUIT_AIO_USERNAME")
aio_key = os.getenv("ADAFRUIT_AIO_KEY")

print(f"Connecting to {os.getenv('CIRCUITPY_WIFI_SSID')}")
wifi.radio.connect(
    os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD")
)
print(f"Connected to {os.getenv('CIRCUITPY_WIFI_SSID')}!")

pool = socketpool.SocketPool(wifi.radio)
requests = adafruit_requests.Session(pool, ssl.create_default_context())

# Initialize an Adafruit IO HTTP API object
io = IO_HTTP(os.getenv("AIO_USERNAME"), os.getenv("AIO_KEY"), requests)

found_feed = False
# Adafruit IO feed configuration
try:
    # Get the 'camera' feed from Adafruit IO
    feed_camera = io.get_feed("featheresp32s3")
    found_feed = True
except AdafruitIO_RequestError:
    # If no 'camera' feed exists, create one 
    # it neese to be amnually created
    print("Create a feen names featheresp32s3 and turn off history")
# Initialize amera
pycam = mycamera.MyCamera()
pycam.resolution = 3
def capture_send_image():
    """Captures an image and send it to Adafruit IO."""
    # Force autofocus and capture a JPEG image
    pycam.autofocus()
    jpeg = pycam.capture_into_jpeg()
    print("Captured image!")
    if jpeg is not None:
        # Encode JPEG data into base64 for sending to Adafruit IO
        print("Encoding image...")
        encoded_data = binascii.b2a_base64(jpeg).strip()
        # Send encoded_data to Adafruit IO camera feed
        if found_feed:
            print("Sending image to Adafruit IO...")
            io.send_data(feed_camera["key"], encoded_data)
            print("Sent image to IO!")
        else:
            print("Not sending o AIO -Feed not available")
    else:
        print("ERROR: JPEG frame capture failed!")
    print("DONE, waiting for next trigger..")

pir_last_status = False
while True:
    pir_status = pir.value
    if (pir_status is True) and (pir_status != pir_last_status):
        pir_last_status = True
        print("PIR triggered")
        capture_send_image()
        time.sleep(10)
    else:
        pir_last_status = False

