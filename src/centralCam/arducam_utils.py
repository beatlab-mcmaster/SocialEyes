"""
arducam_utils.py

Adapted from ArduCam's official demo: https://github.com/ArduCAM/ArduCAM_USB_Camera_Shield_Python_Demo/
"""


import ArducamSDK
import arducam_config_parser
import time

ErrorCode_Map = {
    0x0000: "USB_CAMERA_NO_ERROR",
    0xFF01: "USB_CAMERA_USB_CREATE_ERROR",
    0xFF02: "USB_CAMERA_USB_SET_CONTEXT_ERROR",
    0xFF03: "USB_CAMERA_VR_COMMAND_ERROR",
    0xFF04: "USB_CAMERA_USB_VERSION_ERROR",
    0xFF05: "USB_CAMERA_BUFFER_ERROR",
    0xFF06: "USB_CAMERA_NOT_FOUND_DEVICE_ERROR",
    0xFF0B: "USB_CAMERA_I2C_BIT_ERROR",
    0xFF0C: "USB_CAMERA_I2C_NACK_ERROR",
    0xFF0D: "USB_CAMERA_I2C_TIMEOUT",
    0xFF20: "USB_CAMERA_USB_TASK_ERROR",
    0xFF21: "USB_CAMERA_DATA_OVERFLOW_ERROR",
    0xFF22: "USB_CAMERA_DATA_LACK_ERROR",
    0xFF23: "USB_CAMERA_FIFO_FULL_ERROR",
    0xFF24: "USB_CAMERA_DATA_LEN_ERROR",
    0xFF25: "USB_CAMERA_FRAME_INDEX_ERROR",
    0xFF26: "USB_CAMERA_USB_TIMEOUT_ERROR",
    0xFF30: "USB_CAMERA_READ_EMPTY_ERROR",
    0xFF31: "USB_CAMERA_DEL_EMPTY_ERROR",
    0xFF51: "USB_CAMERA_SIZE_EXCEED_ERROR",
    0xFF61: "USB_USERDATA_ADDR_ERROR",
    0xFF62: "USB_USERDATA_LEN_ERROR",
    0xFF71: "USB_BOARD_FW_VERSION_NOT_SUPPORT_ERROR"
}

def GetErrorString(ErrorCode):
    return ErrorCode_Map[ErrorCode]

def configBoard(handle, config):
    ArducamSDK.Py_ArduCam_setboardConfig(handle, config.params[0],
                                         config.params[1], config.params[2], config.params[3],
                                         config.params[4:config.params_length])                                  

def camera_initFromFile(fileName, index):
    # load config file
    config = arducam_config_parser.LoadConfigFile(fileName)

    camera_parameter = config.camera_param.getdict()
    width = camera_parameter["WIDTH"]
    height = camera_parameter["HEIGHT"]

    BitWidth = camera_parameter["BIT_WIDTH"]
    ByteLength = 1
    if BitWidth > 8 and BitWidth <= 16:
        ByteLength = 2
    FmtMode = camera_parameter["FORMAT"][0]
    color_mode = camera_parameter["FORMAT"][1]
    print("color mode", color_mode)

    I2CMode = camera_parameter["I2C_MODE"]
    I2cAddr = camera_parameter["I2C_ADDR"]
    TransLvl = camera_parameter["TRANS_LVL"]
    cfg = {"u32CameraType": 0x00,
           "u32Width": width, "u32Height": height,
           "usbType": 0,
           "u8PixelBytes": ByteLength,
           "u16Vid": 0,
           "u32Size": 0,
           "u8PixelBits": BitWidth,
           "u32I2cAddr": I2cAddr,
           "emI2cMode": I2CMode,
           "emImageFmtMode": FmtMode,
           "u32TransLvl": TransLvl}

    ret, handle, rtn_cfg = ArducamSDK.Py_ArduCam_open(cfg, index)
    # ret, handle, rtn_cfg = ArducamSDK.Py_ArduCam_autoopen(cfg)
    if ret == 0:

        # ArducamSDK.Py_ArduCam_writeReg_8_8(handle,0x46,3,0x00)
        usb_version = rtn_cfg['usbType']
        configs = config.configs
        configs_length = config.configs_length
        for i in range(configs_length):
            type = configs[i].type
            if ((type >> 16) & 0xFF) != 0 and ((type >> 16) & 0xFF) != usb_version:
                continue
            if type & 0xFFFF == arducam_config_parser.CONFIG_TYPE_REG:
                ArducamSDK.Py_ArduCam_writeSensorReg(
                    handle, configs[i].params[0], configs[i].params[1])
            elif type & 0xFFFF == arducam_config_parser.CONFIG_TYPE_DELAY:
                time.sleep(float(configs[i].params[0])/1000)
            elif type & 0xFFFF == arducam_config_parser.CONFIG_TYPE_VRCMD:
                configBoard(handle, configs[i])

        ArducamSDK.Py_ArduCam_registerCtrls(
            handle, config.controls, config.controls_length)

        rtn_val, datas = ArducamSDK.Py_ArduCam_readUserData(
            handle, 0x400-16, 16)
        print("Serial: %c%c%c%c-%c%c%c%c-%c%c%c%c" % (datas[0], datas[1], datas[2], datas[3],
                                                      datas[4], datas[5], datas[6], datas[7],
                                                      datas[8], datas[9], datas[10], datas[11]))

        return (True, handle, rtn_cfg, color_mode)

    print("open fail, Error : {}".format(GetErrorString(ret)))
    return (False, handle, rtn_cfg, color_mode)

def filetime_to_unix_ns(filetime, filetime_to_epoch = 11644473600 * 10**9):
    return int(filetime * (100)) - filetime_to_epoch