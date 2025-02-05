"""
arducam_central.py

Adapted from ArduCam's official demo: https://github.com/ArduCAM/ArduCAM_USB_Camera_Shield_Python_Demo/
"""

import threading

import ArducamSDK
from arducam_utils import *


class ArducamCamera(object):
    def __init__(self):
        self.isOpened = False
        self.running_ = False
        self.signal_ = threading.Condition()
        pass

    def openCamera(self, fname, index=0):
        self.isOpened, self.handle, self.cameraCfg, self.color_mode = camera_initFromFile(
            fname, index)

        return self.isOpened

    def start(self):
        if not self.isOpened:
            raise RuntimeError("The camera has not been opened.")
        
        self.running_ = True
        ArducamSDK.Py_ArduCam_setMode(self.handle, ArducamSDK.CONTINUOUS_MODE)
        self.capture_thread_ = threading.Thread(target=self.capture_thread)
        self.capture_thread_.daemon = True
        self.capture_thread_.start()

    def read(self, timeout=1500):
        if not self.running_:
            raise RuntimeError("The camera is not running.")

        if ArducamSDK.Py_ArduCam_availableImage(self.handle) <= 0:
            with self.signal_:
                self.signal_.wait(timeout/1000.0)

        if ArducamSDK.Py_ArduCam_availableImage(self.handle) <= 0:
            return (False, None, None)

        ret, data, cfg = ArducamSDK.Py_ArduCam_readImage(self.handle)
        ArducamSDK.Py_ArduCam_del(self.handle)
        size = cfg['u32Size']
        if ret != 0 or size == 0:
            return (False, data, cfg)
    
        return (True, data, cfg)

    def stop(self):
        if not self.running_:
            raise RuntimeError("The camera is not running.")

        self.running_ = False
        self.capture_thread_.join()

    def closeCamera(self):
        if not self.isOpened:
            raise RuntimeError("The camera has not been opened.")

        if (self.running_):
            self.stop()
        self.isOpened = False
        ArducamSDK.Py_ArduCam_close(self.handle)
        self.handle = None


    def capture_thread(self):
        ret = ArducamSDK.Py_ArduCam_beginCaptureImage(self.handle)

        if ret != 0:
            self.running_ = False
            raise RuntimeError("Error beginning capture, Error : {}".format(GetErrorString(ret)))

        print("Capture began, Error : {}".format(GetErrorString(ret)))
        
        while self.running_:
            ret = ArducamSDK.Py_ArduCam_captureImage(self.handle)
            if ret > 255:
                print("Error capture image, Error : {}".format(GetErrorString(ret)))
                if ret == ArducamSDK.USB_CAMERA_USB_TASK_ERROR:
                    break
            elif ret > 0:
                with self.signal_:
                    self.signal_.notify()
            
        self.running_ = False
        ArducamSDK.Py_ArduCam_endCaptureImage(self.handle)

    def setCtrl(self, func_name, val):
        return ArducamSDK.Py_ArduCam_setCtrl(self.handle, func_name, val)

    def dumpDeviceInfo(self):
        USB_CPLD_I2C_ADDRESS=0x46
        cpld_info={}
        ret, version = ArducamSDK.Py_ArduCam_readReg_8_8(
            self.handle, USB_CPLD_I2C_ADDRESS, 0x00)
        ret, year = ArducamSDK.Py_ArduCam_readReg_8_8(
            self.handle, USB_CPLD_I2C_ADDRESS, 0x05)
        ret, mouth = ArducamSDK.Py_ArduCam_readReg_8_8(
            self.handle, USB_CPLD_I2C_ADDRESS, 0x06)
        ret, day = ArducamSDK.Py_ArduCam_readReg_8_8(
            self.handle, USB_CPLD_I2C_ADDRESS, 0x07)

        cpld_info["version"] = "v{}.{}".format(version>>4, version & 0x0F)
        cpld_info["year"] = year
        cpld_info["mouth"] = mouth
        cpld_info["day"] = day

        print(cpld_info)

        ret, data = ArducamSDK.Py_ArduCam_getboardConfig(
            self.handle, 0x80, 0x00, 0x00, 2
        )

        usb_info={}
        usb_info["fw_version"] = "v{}.{}".format((data[0] & 0xFF), (data[1] & 0xFF))
        usb_info["interface"] = 2 if self.cameraCfg["usbType"] == 4 else 3
        usb_info["device"] = 3 if self.cameraCfg["usbType"] == 3 or self.cameraCfg["usbType"] == 4 else 2

        print(usb_info)

    def getCamInformation(self):
        self.version = ArducamSDK.Py_ArduCam_readReg_8_8(self.handle, 0x46, 00)[1]
        self.year = ArducamSDK.Py_ArduCam_readReg_8_8(self.handle, 0x46, 5)[1]
        self.mouth = ArducamSDK.Py_ArduCam_readReg_8_8(self.handle, 0x46, 6)[1]
        self.day = ArducamSDK.Py_ArduCam_readReg_8_8(self.handle, 0x46, 7)[1]
        cpldVersion = "V{:d}.{:d}\t20{:0>2d}/{:0>2d}/{:0>2d}".format(self.version >> 4, self.version & 0x0F, self.year,
                                                                     self.mouth, self.day)
        return cpldVersion

    def getMipiDataInfo(self):
        mipiData = {"mipiDataID": "",
                    "mipiDataRow": "",
                    "mipiDataCol": "",
                    "mipiDataClk": "",
                    "mipiWordCount": "",
                    "mFramerateValue": ""}
        self.getCamInformation()
        cpld_version = self.version & 0xF0
        date = (self.year * 1000 + self.mouth * 100 + self.day)
        if cpld_version not in [0x20, 0x30]:
            return None
        if cpld_version == 0x20 and date < (19 * 1000 + 7 * 100 + 8):
            return None
        elif cpld_version == 0x30 and date < (19 * 1000 + 3 * 100 + 22):
            return None

        mipiDataID = ArducamSDK.Py_ArduCam_readReg_8_8(self.handle, 0x46, 0x1E)[1]
        mipiData["mipiDataID"] = hex(mipiDataID)

        rowMSB = ArducamSDK.Py_ArduCam_readReg_8_8(self.handle, 0x46, 0x21)[1]
        rowLSB = ArducamSDK.Py_ArduCam_readReg_8_8(self.handle, 0x46, 0x22)[1]
        mipiDataRow = ((rowMSB & 0xFF) << 8) | (rowLSB & 0xFF)
        mipiData["mipiDataRow"] = str(mipiDataRow)

        colMSB = ArducamSDK.Py_ArduCam_readReg_8_8(self.handle, 0x46, 0x1F)[1]
        colLSB = ArducamSDK.Py_ArduCam_readReg_8_8(self.handle, 0x46, 0x20)[1]
        mipiDataCol = ((colMSB & 0xFF) << 8) | (colLSB & 0xFF)
        mipiData["mipiDataCol"] = str(mipiDataCol)

        # after 2020/06/22
        if cpld_version == 0x20 and date < (20 * 1000 + 6 * 100 + 22):
            return mipiData
        elif cpld_version == 0x30 and date < (20 * 1000 + 6 * 100 + 22):
            return mipiData

        mipiDataClk = ArducamSDK.Py_ArduCam_readReg_8_8(self.handle, 0x46, 0x27)[1]
        mipiData["mipiDataClk"] = str(mipiDataClk)

        if (cpld_version == 0x30 and date >= (21 * 1000 + 3 * 100 + 1)) or (
                cpld_version == 0x20 and date >= (21 * 1000 + 9 * 100 + 6)):
            wordCountMSB = ArducamSDK.Py_ArduCam_readReg_8_8(self.handle, 0x46, 0x25)[1]
            wordCountLSB = ArducamSDK.Py_ArduCam_readReg_8_8(self.handle, 0x46, 0x26)[1]
            mipiWordCount = ((wordCountMSB & 0xFF) << 8) | (wordCountLSB & 0xFF)
            mipiData["mipiWordCount"] = str(mipiWordCount)

        if date >= (21 * 1000 + 6 * 100 + 22):
            fpsMSB = ArducamSDK.Py_ArduCam_readReg_8_8(self.handle, 0x46, 0x2A)[1]
            fpsLSB = ArducamSDK.Py_ArduCam_readReg_8_8(self.handle, 0x46, 0x2B)[1]
            fps = (fpsMSB << 8 | fpsLSB) / 4.0
            fpsResult = "{:.1f}".format(fps)
            mipiData["mFramerateValue"] = fpsResult
        return mipiData
        