import appdaemon.plugins.hass.hassapi as hass
from support import Support
from enum import Enum


class TempSensorsLocation(Enum):
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

class BaseClimateControl(Support):

    async def initialize(self):

        self.log("Base initing..")

        self.error_restart_interval = 10

        self.temp_ent_ending = "_temp_humid_sensor_temperature"

        self.ac_ent             = "select.nedis_ir_controller_ac_mode"
        self.ac_ext_fan_ent     = "switch.smart_socket_4"
        self.bedroom_heater_ent = "switch.smart_socket_1"

        self.disable_compressor_mode_ent    = "input_boolean.climate_control_disable_compressor_mode"
        self.polling_interval_ent           = "input_number.climate_control_polling_interval"

        self.polling_interval = None
        self.latest_start_time = None

        self.debug      = bool(self.args.get("debug", False))
        self.dev_logs   = bool(self.args.get("dev_logs", False))

        self.is_active_ent  = self.args.get("is_active_ent")
        self.is_active = (await self.get_state(self.is_active_ent)) == "on"
        self.listen_state(self.on_is_active_ent_change, self.is_active_ent)
        
        self.dev_log("is_active", self.is_active)

        if(self.is_active):
            self.create_task(self.start())


    def on_is_active_ent_change(self, entity, attribute, old, new, kwargs):

        self.dev_log(f"Is active change from '{old}' to '{new}'")

        if new == "on":
            self.is_active = True
            self.create_task(self.start())
        else:
            self.is_active = False
    

    async def start(self):
        self.dev_log("Starting climate control")

        self.polling_interval = float(await self.get_state(self.polling_interval_ent))

        start_time = self.get_timestamp()
        self.latest_start_time = start_time

        try:
            await self.base_loop(start_time)

        except Exception as e:
            self.log("Error caught\n", level="ERROR", exc_info=True)

            if(not self.debug):
                self.log("Starting again in 5 seconds....")

                await self.sleep(self.error_restart_interval)

                if(self.is_active and start_time == self.latest_start_time):
                    self.create_task(self.start())


    async def base_loop(self, start_time):

        while(self.is_active and start_time == self.latest_start_time):
            await self.loop_logic()
            await self.sleep(self.polling_interval)


    async def loop_logic(self):
        return
    
    async def send_notification(self, msg):
        await self.send_mobile_notification(f"Climate Control", msg)

    async def get_temp(self, sensor: TempSensorsLocation):
        return float(await self.get_state(f"sensor.{sensor.value}{self.temp_ent_ending}"))

    async def set_ac_mode(self, mode: ACModes):
        await self.call_service("select/select_option", entity_id=self.ac_ent, option=mode.value)

    async def set_ac_ext_fan(self, mode: OnOff):
        await self.call_service(f"switch/turn_{mode.value}", entity_id=self.ac_ext_fan_ent)

    async def set_bedroom_heater(self, mode: OnOff):
        await self.call_service(f"switch/turn_{mode.value}", entity_id=self.bedroom_heater_ent)

    async def start_cooling(self):

        outside_temp = await self.get_temp(TempSensorsLocation.OUTSIDE_FOREST_SIDE)
        
        #TODO make the starting and stopping of cooling
        #if(outside_temp):

    async def stop_cooling(self):
        return