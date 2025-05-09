import appdaemon.plugins.hass.hassapi as hass
from enum import Enum

class TempSensors(Enum):
    BEDROOM = "bedroom"
    OFFICE = "office"
    LIVING_ROOM = "living_room"
    OUTSIDE_CITY_SIDE = "outside_city_side"
    OUTSIDE_FOREST_SIDE = "outside_forest_side"

class ACModes(Enum):
    OFF = "Off"
    COOL = "Cool"
    FAN = "Fan"

class OnOff(Enum):
    ON = "on"
    OFF = "off"

class BaseClimateControl(hass.Hass):

    async def initialize(self):

        self.polling_interval = 5
        self.error_restart_interval = 5

        self.temp_ent_ending = "_temp_humid_sensor_device_temperature"

        self.ac_ent = "select.nedis_ir_controller_ac_mode"
        self.ac_ext_fan_ent = "switch.smart_socket_4"
        self.bedroom_heater_ent = "switch.smart_socket_1"

        self.debug = bool(self.args.get("debug", True))
        self.is_active_ent  = self.args.get("is_active_ent")

        self.is_active = (await self.get_state(self.is_active_ent)) == "on"
        self.listen_state(self.on_is_active_ent_change, self.is_active_ent)
        
        if(self.is_active): 
            self.create_task(self.start())


    def dev_log(self, msg, args=None):
        if self.debug:
            if args is None:
                self.log(f"--> {msg}")
            else:
                self.log(f"--> {msg}: {args}")


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
    
    async def get_temp(self, sensor: TempSensors):
        return float(await self.get_state(f"sensor.{sensor.value}{self.temp_ent_ending}"))

    async def set_ac_mode(self, mode: ACModes):
        await self.call_service("select/select_option", entity_id=self.ac_ent, option=mode.value)

    async def set_ac_ext_fan(self, mode: OnOff):
        await self.call_service(f"switch/turn_{mode.value}", entity_id=self.ac_ext_fan_ent)

    async def set_bedroom_heater(self, mode: OnOff):
        await self.call_service(f"switch/turn_{mode.value}", entity_id=self.bedroom_heater_ent)

    async def send_notification(self, msg):
        await self.call_service(
            "notify/mobile_app_robins_oneplus_13",
            title="Ordinary Climate Control",
            message=msg,
            data= { "ttl": 0, "priority": "high" }
        )

    