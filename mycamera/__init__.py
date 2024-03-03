# SPDX-FileCopyrightText: 2023 Jeff Epler for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""Library for the Adafruit OV5640 with autofocus module"""

import os
import struct
import time

try:
    from typing import Sequence
except ImportError:
    pass

import bitmaptools
import board
import espcamera
from adafruit_bus_device.i2c_device import I2CDevice
from digitalio import DigitalInOut, Pull


from micropython import const

_REG_DLY = const(0xFFFF)

_OV5640_STAT_FIRMWAREBAD = const(0x7F)
_OV5640_STAT_STARTUP = const(0x7E)
_OV5640_STAT_IDLE = const(0x70)
_OV5640_STAT_FOCUSING = const(0x00)
_OV5640_STAT_FOCUSED = const(0x10)

_OV5640_CMD_TRIGGER_AUTOFOCUS = const(0x03)
_OV5640_CMD_AUTO_AUTOFOCUS = const(0x04)
_OV5640_CMD_RELEASE_FOCUS = const(0x08)
_OV5640_CMD_AF_SET_VCM_STEP = const(0x1A)
_OV5640_CMD_AF_GET_VCM_STEP = const(0x1B)

_OV5640_CMD_MAIN = const(0x3022)
_OV5640_CMD_ACK = const(0x3023)
_OV5640_CMD_PARA0 = const(0x3024)
_OV5640_CMD_PARA1 = const(0x3025)
_OV5640_CMD_PARA2 = const(0x3026)
_OV5640_CMD_PARA3 = const(0x3027)
_OV5640_CMD_PARA4 = const(0x3028)
_OV5640_CMD_FW_STATUS = const(0x3029)


class MyCameraBase:  # pylint: disable=too-many-instance-attributes,too-many-public-methods
    """Base class for MyCamera hardware"""

    """Wrapper class for the MyCamera hardware with lots of smarts"""

    _finalize_firmware_load = (
        0x3022,
        0x00,
        0x3023,
        0x00,
        0x3024,
        0x00,
        0x3025,
        0x00,
        0x3026,
        0x00,
        0x3027,
        0x00,
        0x3028,
        0x00,
        0x3029,
        0x7F,
        0x3000,
        0x00,
    )

    resolutions = (
        # "160x120",
        # "176x144",
        # "240x176",
        "240x240",
        "320x240",
        # "400x296",
        # "480x320",
        "640x480",
        "800x600",
        "1024x768",
        "1280x720",
        "1280x1024",
        "1600x1200",
        "1920x1080",
        # "720x1280",
        # "864x1536",
        "2048x1536",
        "2560x1440",
        "2560x1600",
        # "1080x1920",
        "2560x1920",
    )
    resolution_to_frame_size = (
        # espcamera.FrameSize.QQVGA,
        # espcamera.FrameSize.QCIF,
        # espcamera.FrameSize.HQVGA,
        espcamera.FrameSize.R240X240,  # 240x240
        espcamera.FrameSize.QVGA,  # 320x240
        # espcamera.FrameSize.CIF, # 400x296
        # espcamera.FrameSize.HVGA, # 480x320
        espcamera.FrameSize.VGA,  #  640x480
        espcamera.FrameSize.SVGA,  # 800x600
        espcamera.FrameSize.XGA,  # 1024x768
        espcamera.FrameSize.HD,  # 1280x720
        espcamera.FrameSize.SXGA,  # 1280x1024
        espcamera.FrameSize.UXGA,  # 1600x1200
        espcamera.FrameSize.FHD,  # 1920x1080
        # espcamera.FrameSize.P_HD, # 720x1280
        # espcamera.FrameSize.P_3MP, # 864x1536
        espcamera.FrameSize.QXGA,  # 2048x1536
        espcamera.FrameSize.QHD,  # 2560x1440
        espcamera.FrameSize.WQXGA,  # 2560x1600
        # espcamera.FrameSize.P_FHD, # 1080x1920
        espcamera.FrameSize.QSXGA,  # 2560x1920
    )

    def __init__(self) -> None:  # pylint: disable=too-many-statements
        self._i2c = board.I2C()
        self._camera_device = None
        self.camera = None



    def init_camera(self, init_autofocus=True) -> None:
        """Initialize the camera, by default including autofocus"""

        print("Initializing camera")
        self.camera = espcamera.Camera(
            data_pins=[board.D6,board.A5,board.D9,board.A4,board.D10,board.A3,board.D11,board.A2],
            external_clock_pin=board.D12,
            pixel_clock_pin=board.A1,
            vsync_pin=board.A0,
            href_pin=board.D13,
            powerdown_pin=board.D5,
            reset_pin=board.RX,
            pixel_format=espcamera.PixelFormat.RGB565,
            frame_size=espcamera.FrameSize.HQVGA,
            i2c=board.I2C(),
            external_clock_frequency=20_000_000,
            framebuffer_count=2,
        )

        print(
            "Found camera %s (%d x %d) at I2C address %02x"
            % (
                self.camera.sensor_name,
                self.camera.width,
                self.camera.height,
                self.camera.address,
            )
        )

        self._camera_device = I2CDevice(self._i2c, self.camera.address)

        self.camera.hmirror = False
        self.camera.vflip = True

        # self.camera.colorbar = True
        if init_autofocus:
            self.autofocus_init()

        print("init done @")

    def autofocus_init_from_file(self, filename):
        """Initialize the autofocus engine from a .bin file"""
        with open(filename, mode="rb") as file:
            firmware = file.read()
        self.autofocus_init_from_bitstream(firmware)

    def write_camera_register(self, reg: int, value: int) -> None:
        """Write a 1-byte camera register"""
        b = bytearray(3)
        b[0] = reg >> 8
        b[1] = reg & 0xFF
        b[2] = value
        with self._camera_device as i2c:
            i2c.write(b)

    def write_camera_list(self, reg_list: Sequence[int]) -> None:
        """Write a series of 1-byte camera registers"""
        for i in range(0, len(reg_list), 2):
            register = reg_list[i]
            value = reg_list[i + 1]
            if register == _REG_DLY:
                time.sleep(value / 1000)
            else:
                self.write_camera_register(register, value)

    def read_camera_register(self, reg: int) -> int:
        """Read a 1-byte camera register"""
        b = bytearray(2)
        b[0] = reg >> 8
        b[1] = reg & 0xFF
        with self._camera_device as i2c:
            i2c.write(b)
            i2c.readinto(b, end=1)
        return b[0]

    def autofocus_init_from_bitstream(self, firmware: bytes):
        """Initialize the autofocus engine from a bytestring"""
        if self.camera.sensor_name != "OV5640":
            raise RuntimeError(f"Autofocus not supported on {self.camera.sensor_name}")

        self.write_camera_register(0x3000, 0x20)  # reset autofocus coprocessor
        time.sleep(0.01)

        arr = bytearray(256)
        with self._camera_device as i2c:
            for offset in range(0, len(firmware), 254):
                num_firmware_bytes = min(254, len(firmware) - offset)
                reg = offset + 0x8000
                arr[0] = reg >> 8
                arr[1] = reg & 0xFF
                arr[2 : 2 + num_firmware_bytes] = firmware[
                    offset : offset + num_firmware_bytes
                ]
                i2c.write(arr, end=2 + num_firmware_bytes)

        self.write_camera_list(self._finalize_firmware_load)
        for _ in range(100):
            if self.autofocus_status == _OV5640_STAT_IDLE:
                break
            time.sleep(0.01)
        else:
            raise RuntimeError("Timed out after trying to load autofocus firmware")

    def autofocus_init(self):
        """Initialize the autofocus engine from ov5640_autofocus.bin"""
        if "/" in __file__:
            binfile = (
                __file__.rsplit("/", 1)[0].rsplit(".", 1)[0] + "/ov5640_autofocus.bin"
            )
        else:
            binfile = "ov5640_autofocus.bin"
        print(binfile)
        return self.autofocus_init_from_file(binfile)

    @property
    def autofocus_status(self):
        """Read the camera autofocus status register"""
        return self.read_camera_register(_OV5640_CMD_FW_STATUS)

    def _send_autofocus_command(self, command, msg):  # pylint: disable=unused-argument
        self.write_camera_register(_OV5640_CMD_ACK, 0x01)  # clear command ack
        self.write_camera_register(_OV5640_CMD_MAIN, command)  # send command
        for _ in range(100):
            if self.read_camera_register(_OV5640_CMD_ACK) == 0x0:  # command is finished
                return True
            time.sleep(0.01)
        return False

    def autofocus(self) -> list[int]:
        """Perform an autofocus operation.

        If all elements of the list are 0, the autofocus operation failed. Otherwise,
        if at least one element is nonzero, the operation succeeded.

        In principle the elements correspond to 5 autofocus regions, if configured."""
        if not self._send_autofocus_command(_OV5640_CMD_RELEASE_FOCUS, "release focus"):
            return [False] * 5
        if not self._send_autofocus_command(_OV5640_CMD_TRIGGER_AUTOFOCUS, "autofocus"):
            return [False] * 5
        zone_focus = [
            self.read_camera_register(_OV5640_CMD_PARA0 + i) for i in range(5)
        ]
        print(f"zones focused: {zone_focus}")
        return zone_focus

    @property
    def autofocus_vcm_step(self):
        """Get the voice coil motor step location"""
        if not self._send_autofocus_command(
            _OV5640_CMD_AF_GET_VCM_STEP, "get vcm step"
        ):
            return None
        return self.read_camera_register(_OV5640_CMD_PARA4)

    @autofocus_vcm_step.setter
    def autofocus_vcm_step(self, step):
        """Get the voice coil motor step location, from 0 to 255"""
        if not 0 <= step <= 255:
            raise RuntimeError("VCM step must be 0 to 255")
        self.write_camera_register(_OV5640_CMD_PARA3, 0x00)
        self.write_camera_register(_OV5640_CMD_PARA4, step)
        self._send_autofocus_command(_OV5640_CMD_AF_SET_VCM_STEP, "set vcm step")

    @property
    def resolution(self):
        """Get or set the resolution as a numeric constant

        The resolution can also be set as a string such as "240x240"."""
        return self._resolution

    @resolution.setter
    def resolution(self, res):
        if isinstance(res, str):
            if not res in self.resolutions:
                raise RuntimeError("Invalid Resolution")
            res = self.resolutions.index(res)
        if isinstance(res, int):
            res = (res + len(self.resolutions)) % len(self.resolutions)
            self._resolution = res



    def continuous_capture_start(self):
        """Switch the camera to continuous-capture mode"""
        pass  # pylint: disable=unnecessary-pass

    def capture_into_jpeg(self):
        """Captures an image and returns it in JPEG format.

        Returns:
            bytes: The captured image in JPEG format, otherwise None if the capture failed.
        """
        self.camera.reconfigure(
            pixel_format=espcamera.PixelFormat.JPEG,
            frame_size=self.resolution_to_frame_size[self._resolution],
        )
        time.sleep(0.1)
        jpeg = self.camera.take(1)
        if jpeg is not None:
            print(f"Captured {len(jpeg)} bytes of jpeg data")
            print("Resolution %d x %d" % (self.camera.width, self.camera.height))
        else:
            print("JPEG capture failed")
        return jpeg

    def capture_into_bitmap(self, bitmap):
        """Capture an image and blit it into the given bitmap"""
        bitmaptools.blit(bitmap, self.continuous_capture(), 0, 0)

    def continuous_capture(self):
        """Capture an image into an internal buffer.

        The image is valid at least until the next image capture,
        or the camera's capture mode is changed"""
        return self.camera.take(1)


    def get_camera_autosettings(self):
        """Collect all the settings related to exposure and white balance"""
        exposure = (
            (self.read_camera_register(0x3500) << 12)
            + (self.read_camera_register(0x3501) << 4)
            + (self.read_camera_register(0x3502) >> 4)
        )
        white_balance = [
            self.read_camera_register(x)
            for x in (0x3400, 0x3401, 0x3402, 0x3403, 0x3404, 0x3405)
        ]

        settings = {
            "gain": self.read_camera_register(0x350B),
            "exposure": exposure,
            "wb": white_balance,
        }
        return settings

    def set_camera_wb(self, wb_register_values=None):
        """Set the camera white balance.

        The argument of `None` selects auto white balance, while
        a list of 6 numbers sets a specific white balance.

        The numbers can come from the datasheet or from
        ``get_camera_autosettings()["wb"]``."""
        if wb_register_values is None:
            # just set to auto balance
            self.camera.whitebal = True
            return

        if len(wb_register_values) != 6:
            raise RuntimeError("Please pass in 0x3400~0x3405 inclusive!")

        self.write_camera_register(0x3212, 0x03)
        self.write_camera_register(0x3406, 0x01)
        for i, reg_val in enumerate(wb_register_values):
            self.write_camera_register(0x3400 + i, reg_val)
        self.write_camera_register(0x3212, 0x13)
        self.write_camera_register(0x3212, 0xA3)

    def set_camera_exposure(self, new_exposure=None):
        """Set the camera's exposure values

        The argument of `None` selects auto exposure.

        Otherwise, the new exposure data should come from
        ``get_camera_autosettings()["exposure"]``."""
        if new_exposure is None:
            # just set auto expose
            self.camera.exposure_ctrl = True
            return
        self.camera.exposure_ctrl = False

        self.write_camera_register(0x3500, (new_exposure >> 12) & 0xFF)
        self.write_camera_register(0x3501, (new_exposure >> 4) & 0xFF)
        self.write_camera_register(0x3502, (new_exposure << 4) & 0xFF)

    def set_camera_gain(self, new_gain=None):
        """Set the camera's exposure values

        The argument of `None` selects auto gain control.

        Otherwise, the new exposure data should come from
        ``get_camera_autosettings()["gain"]``."""
        if new_gain is None:
            # just set auto expose
            self.camera.gain_ctrl = True
            return

        self.camera.gain_ctrl = False
        self.write_camera_register(0x350B, new_gain)


class MyCamera(MyCameraBase):
    """Wrapper class for the MyCamera hardware"""

    def __init__(self, init_autofocus=True):
        super().__init__()

        self.init_camera(init_autofocus)
