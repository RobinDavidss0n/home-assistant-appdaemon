import appdaemon.plugins.hass.hassapi as hass
from enum import Enum

class ACModes(Enum):
    OFF = "Off"
    COOL = "Cool"
    FAN = "Fan"

class BaseClimateController(hass.Hass):
    def initialize(self):

        self.polling_interval = 5
        self.error_restart_interval = 5

        self.bedroom_temp_ent = "sensor.bedroom_temp_humid_sensor_device_temperature"
        self.office_temp_ent = "sensor.office_temp_humid_sensor_device_temperature"
        self.living_room_temp_ent = "sensor.living_room_temp_humid_sensor_device_temperature"

        self.ac_ent = "select.nedis_ir_controller_ac_mode"
        self.ac_ext_fan_ent = "sensor.smart_socket_4_power"
        self.bedroom_heater_ent = "sensor.smart_socket_1_power"

        self.debug = bool(self.args.get("debug", True))
        self.is_active_ent  = self.args.get("is_active_ent")
        self.is_active = self.get_state(self.is_active_ent) == "on"
        
        self.listen_state(self.on_is_active_ent_change, self.is_active_ent)
        
        if(self.is_active): 
            self.create_task(self.start())


    def on_is_active_ent_change(self, entity, attribute, old, new, kwargs):

        if new == "on":
            self.is_active = True
            self.create_task(self.start())
        else:
            self.is_active = False
    

    async def start(self):
        self.dev_log("(base class) > Turning on climate controller")

        try:
            await self.base_loop()
        except Exception as e:
            self.log("(base class) > ClimateController -> Error caught\n", level="ERROR", exc_info=True)
            self.log("(base class) > Starting again in 5 seconds....")

            await self.sleep(self.error_restart_interval)
            self.create_task(self.start())


    async def base_loop(self):

        while(self.is_active):
            await self.loop_logic()
            await self.sleep(self.polling_interval)


    async def loop_logic(self):
        return



    def dev_log(self, msg, args=None):
        if self.debug:
            if args is None:
                self.log(f"--> {msg}")
            else:
                self.log(f"--> {msg}: {args}")