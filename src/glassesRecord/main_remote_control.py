"""
main_remote_control.py

Author: Alexander Nguyen
Purpose: A GUI application used to remote control the NEON companion devices (android smartphones). 
This utility is not a part of the main SocialEyes framework but added here for auxiliary use cases like device-specific remote troubleshooting.
"""

from textual.app import App, ComposeResult
from textual.widgets import Input, Button, Static
from textual.containers import Horizontal, VerticalScroll
import subprocess
import time
import re

class InputApp(App):
    #Using hard-coded pixel locations to be complaint with NEON companion smartphones (Motorola 40 Edge Pro). Please adjust for other devices accordingly.  
    app_position             = [0.390, 0.128]
    record_button_position   = [0.514, 0.839]
    save_button_position     = [0.775, 0.927]
    discard_button_position  = [0.261, 0.927]
    center_bottom_button_position  = [0.500, 0.927]
    confirm_discard_position = [0.878, 0.564]
    abort_discard_position   = [0.670, 0.564]

    inputs  = {}
    buttons = {}

    screen_proc = None
    ffplay_proc = None
    last_target = None

    def compose(self) -> ComposeResult:
        """
        Composes the GUI layout of the application.

        This method sets up the input fields and buttons, organizing them into a vertical and horizontal layout.
        """
        self.inputs['ip_addr']                = Input(placeholder="IP address", value="192.168.35.", max_length=15) 

        self.buttons['stream_display']        = Button('Stream Display')
        self.buttons['unlock_phone']          = Button('Unlock phone (incl. pin)')
        self.buttons['lock_phone']            = Button('Lock phone')
        self.buttons['confirm_alert_window']  = Button('Confirm alert window')
        self.buttons['save_recording']        = Button('Save recording')
        self.buttons['discard_recording']     = Button('Discard recording')
        self.buttons['start_recording']       = Button('Start recording')
        self.buttons['key_power']             = Button('Key power (26)')
        self.buttons['key_menu']              = Button('Key menu (82)')
        self.buttons['key_enter']             = Button('Key enter (66)')
        self.buttons['swipe_left']            = Button('Swipe left')
        self.buttons['swipe_right']           = Button('Swipe right')
        self.buttons['swipe_up']              = Button('Swipe up')
        self.buttons['swipe_down']            = Button('Swipe down')
        self.buttons['tap_app']               = Button('Tap at Neon app\'s position')
        self.buttons['tap_alert_left']        = Button('Tap centered alert, left option')
        self.buttons['tap_alert_right']       = Button('Tap centered alert, right option')
        self.buttons['tap_discard_recording'] = Button('Tap discard recording (bottom left)')
        self.buttons['tap_record_tab'] = Button('Tap recording tab (bottom middle)')
        self.buttons['tap_save_recording']    = Button('Tap save recording (bottom right)')


        yield Horizontal(
            VerticalScroll(
                self.inputs['ip_addr'],
                VerticalScroll(
                    self.buttons['stream_display']
                ),
                VerticalScroll(
                    Static("# General functions"),
                    Horizontal(
                        VerticalScroll(
                            Static("## Android"),
                            self.buttons['unlock_phone'],
                            self.buttons['lock_phone'],
                        ),
                        VerticalScroll(
                            Static("## Key events"),
                            self.buttons['key_power'],
                            self.buttons['key_menu'],
                            self.buttons['key_enter'],
                        ),
                        VerticalScroll(
                            Static("## Touch events"),
                            self.buttons['swipe_left'],
                            self.buttons['swipe_right'],
                            self.buttons['swipe_up'],
                            self.buttons['swipe_down'],
                            self.buttons['tap_app'],
                        ),
                    ),
                ),
                VerticalScroll(
                    Static("# Low-level functions"),
                    Horizontal(
                        VerticalScroll(
                            Static("## Crash handling"),                           
                            self.buttons['tap_alert_left'],
                            self.buttons['tap_alert_right'],
                            self.buttons['tap_discard_recording'],
                            self.buttons['tap_save_recording'],
                        ),
                        VerticalScroll(
                            Static("## Other controls"),
                            self.buttons['start_recording'],
                            self.buttons['tap_record_tab'],
                        )
                    ),                    
                ),
            ),
        )

    def action_stream_display(self, target):
        """
        Starts phone screen-capture and displays it using ffplay.

        Args:
            target (str): The target device's IP address.
        """
        if any([p.poll() is None for p in [self.screen_proc, self.ffplay_proc] if p is not None]):
            try:
                self.ffplay_proc.kill()
                self.screen_proc.kill()
            except:
                pass
            finally:
                self.ffplay_proc = None
                self.screen_proc = None
        else:
            screen_on = subprocess.getoutput(f'adb -s {target} shell dumpsys input_method | grep screenOn')
            screen_on = 'true' in screen_on

            if screen_on:
                self._action_key(target, 26)
                time.sleep(0.2)
            self._action_key(target, 26)

            self.screen_proc = subprocess.Popen(f'adb -s {target} exec-out screenrecord --output-format=h264 -'.split(' '), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.ffplay_proc = subprocess.Popen(f'ffplay -fflags nobuffer -flags low_delay -framedrop -probesize 32 -vf setpts=0 -'.split(' '), stdin=self.screen_proc.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def action_unlock_phone(self, target):
        """
        Simulating the unlocking of companion smartphone using the specified sequence of key events and remote key strokes.

        Args:
            target (str): The target device's IP address.
        """
        self._action_key(target, 26)
        time.sleep(0.6)
        self._action_key(target, 26)
        time.sleep(0.4)
        self._action_key(target, 82)
        time.sleep(0.4)
        self._action_key(target, 82)
        time.sleep(0.)
        subprocess.getoutput(f"adb -s {target} shell input text 2023")
        time.sleep(0.3)
        self._action_key(target, 66)

    def action_lock_phone(self, target):
        """
        Locks the phone if the screen is currently on.

        Args:
            target (str): The target device's IP address.
        """
        screen_on = subprocess.getoutput(f'adb -s {target} shell dumpsys input_method | grep screenOn')
        screen_on = 'true' in screen_on

        if screen_on:
            self._action_key(target, 26)
    
    def action_swipe_left(self, target):
        """
        Performs a swipe left gesture on the device.

        Args:
            target (str): The target device's IP address.
        """ 
        res = subprocess.getoutput(f'adb -s {target} shell wm size')
        res = re.search(': (\d+)x(\d+)', res)
        if res is None or len(res.groups()) != 2:
            return
        w, h = [float(s) for s in res.groups()]
        h_2 = h/2
        w_2 = w/2
        subprocess.getoutput(f'adb -s {target} shell input swipe {0.4*w} {h_2} 0 {h_2}')

    def action_swipe_right(self, target):
        """
        Performs a swipe right gesture on the device.

        Args:
            target (str): The target device's IP address.
        """
        res = subprocess.getoutput(f'adb -s {target} shell wm size')
        res = re.search(': (\d+)x(\d+)', res)
        if res is None or len(res.groups()) != 2:
            return
        w, h = [float(s) for s in res.groups()]
        h_2 = h/2
        w_2 = w/2
        subprocess.getoutput(f'adb -s {target} shell input swipe 0 {h_2} {0.4*w} {h_2}')

    def action_swipe_up(self, target):
        """
        Performs a swipe up gesture on the device.

        Args:
            target (str): The target device's IP address.
        """
        res = subprocess.getoutput(f'adb -s {target} shell wm size')
        res = re.search(': (\d+)x(\d+)', res)
        if res is None or len(res.groups()) != 2:
            return
        w, h = [float(s) for s in res.groups()]
        h_2 = h/2
        w_2 = w/2
        subprocess.getoutput(f'adb -s {target} shell input swipe {w_2} {h} {w_2} {h_2}')

    def action_swipe_down(self, target):
        """
        Performs a swipe down gesture on the device.

        Args:
            target (str): The target device's IP address.
        """
        res = subprocess.getoutput(f'adb -s {target} shell wm size')
        res = re.search(': (\d+)x(\d+)', res)
        if res is None or len(res.groups()) != 2:
            return
        w, h = [float(s) for s in res.groups()]
        h_2 = h/2
        w_2 = w/2
        subprocess.getoutput(f'adb -s {target} shell input swipe {w_2} 0 {w_2} {h_2}')

    def _action_tap(self, target, position):
        """
        Simulates a tap action at the specified position on the target device's screen.

        Args:
            target (str): The target device's IP address.
            position (list): A list containing the x and y coordinates as fractions of the screen size.
        """    
        res = subprocess.getoutput(f'adb -s {target} shell wm size')
        res = re.search(': (\d+)x(\d+)', res)
        if res is None or len(res.groups()) != 2:
            return
        w, h = [float(s) for s in res.groups()]
        print('tap ...')
        subprocess.getoutput(f'adb -s {target} shell input tap {position[0]*w} {position[1]*h}')

    def _action_key(self, target, key_code):
        """
        Sends a key event to the target device.

        Args:
            target (str): The target device's IP address.
            key_code (int): The key code of the event to be sent.
        """
        subprocess.getoutput(f'adb -s {target} shell input keyevent {str(key_code)}')
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Handles button press events by invoking the appropriate action based on the button pressed.

        Args:
            event (Button.Pressed): The event triggered by a button press.
        """

        target = self.inputs['ip_addr'].value
        self.last_target = target

        if event.button == self.buttons['stream_display']:
            self.action_stream_display(target)
        elif event.button == self.buttons['unlock_phone']:
            self.action_unlock_phone(target)
        elif event.button == self.buttons['lock_phone']:
            self.action_lock_phone(target)
        elif event.button == self.buttons['confirm_alert_window']:
            self._action_tap(target, self.confirm_discard_position)
        elif event.button == self.buttons['save_recording']:
            self._action_tap(target, self.save_button_position)
        elif event.button == self.buttons['discard_recording']:
            self._action_tap(target, self.discard_button_position)
        elif event.button == self.buttons['key_power']:
            self._action_key(target, 26)
        elif event.button == self.buttons['key_menu']:
            self._action_key(target, 82)
        elif event.button == self.buttons['key_enter']:
            self._action_key(target, 66)
        elif event.button == self.buttons['swipe_left']:
            self.action_swipe_left(target)
        elif event.button == self.buttons['swipe_right']:
            self.action_swipe_right(target)
        elif event.button == self.buttons['swipe_up']:
            self.action_swipe_up(target)
        elif event.button == self.buttons['tap_app']:
            self._action_tap(target, self.app_position)
        elif event.button == self.buttons['tap_alert_left']:
            self._action_tap(target, self.abort_discard_position)
        elif event.button == self.buttons['tap_alert_right']:
            self._action_tap(target, self.confirm_discard_position)
        elif event.button == self.buttons['tap_discard_recording']:
            self._action_tap(target, self.discard_button_position)
        elif event.button == self.buttons['tap_save_recording']:
            self._action_tap(target, self.save_button_position)
        elif event.button == self.buttons['start_recording']:
            self._action_tap(target, self.record_button_position)
        elif event.button == self.buttons['tap_record_tab']:
            self._action_tap(target, self.center_bottom_button_position)
        else:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        """
        Validates the input value and enables/disables buttons based on its validity.

        Args:
            event (Input.Changed): The event triggered when the input value changes.
        """
        actual_value = event.value
        value_valid = re.search('\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', actual_value) is not None
        for b in self.buttons.values():
            b.disabled = value_valid != True

    def teardown(self):
        """
        Cleans up any active processes before shutting down the application.
        """
        try:
            self.ffplay_proc.kill()
            self.screen_proc.kill()
        except:
            pass
        finally:
            self.ffplay_proc = None
            self.screen_proc = None

if __name__ == "__main__":
    try:
        app = InputApp()
        app.run()
    finally:
        app.teardown()