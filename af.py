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

print("CircuitPython Doorbell Camera")

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

# Adafruit IO feed configuration
try:
    # Get the 'camera' feed from Adafruit IO
    feed_camera = io.get_feed("camera")
except AdafruitIO_RequestError:
    # If no 'camera' feed exists, create one
    feed_camera = io.create_new_feed("camera")

# Initialize amera
pycam = mycamera.MyCamera()
pycam.resolution = 3
pycam.autofocus()
#print("AF Status: ",pycam.autofocus_status, pycam.autofocus_vcm_step)
print("AF Status: ",pycam.autofocus_status)
def capture_send_image():
    """Captures an image and send it to Adafruit IO."""
    # Force autofocus and capture a JPEG image
    pycam.autofocus()
    #print("AF Status: ",pycam.autofocus_status, pycam.autofocus_vcm_step)
    #pycam.autofocus_vcm_step=255
    #print("AF Status: ",pycam.autofocus_status, pycam.autofocus_vcm_step)
    jpeg = pycam.capture_into_jpeg()
    print("Captured image!")
    if jpeg is not None:
        # Encode JPEG data into base64 for sending to Adafruit IO
        print("Encoding image...")
        encoded_data = binascii.b2a_base64(jpeg).strip()
        # Send encoded_data to Adafruit IO camera feed
        print("Sending image to Adafruit IO...")
        io.send_data(feed_camera["key"], encoded_data)
        print("Sent image to IO!")
    else:
        print("ERROR: JPEG frame capture failed!")
    print("DONE, waiting for next capture")


while True:
    capture_send_image()
    time.sleep(15)
