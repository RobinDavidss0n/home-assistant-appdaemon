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

        self.polling_interval_ent               = "input_number.climate_control_polling_interval"
        self.min_time_fan_per_hour_ent          = "input_number.climate_control_min_time_fan_per_hour"
        self.compressor_outside_temp_cutoff_ent = "input_number.climate_control_compressor_outside_temp_cutoff"
        self.disable_ac_compressor_ent          = "input_boolean.climate_control_disable_compressor_mode"
        self.disable_external_ac_fan_ent        = "input_boolean.climate_control_disable_external_ac_fan"
        
        self.polling_interval               = None
        self.compressor_outside_temp_cutoff = None
        self.disable_ac_compressor          = None
        self.disable_external_ac_fan        = None


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
    
    # TODO restart upon changes on settings
    async def start(self):

        self.polling_interval               = float(await self.get_state(self.polling_interval_ent))
        self.min_time_fan_per_hour          = float(await self.get_state(self.min_time_fan_per_hour_ent))
        self.compressor_outside_temp_cutoff = float(await self.get_state(self.compressor_outside_temp_cutoff_ent))
        self.disable_ac_compressor          = await self.get_state(self.disable_ac_compressor_ent) == "on"
        self.disable_external_ac_fan        = await self.get_state(self.disable_external_ac_fan_ent) == "on"

        self.dev_log("polling_interval", self.polling_interval)
        self.dev_log("min_time_fan_per_hour", self.min_time_fan_per_hour)
        self.dev_log("compressor_outside_temp_cutoff", self.compressor_outside_temp_cutoff)
        self.dev_log("disable_ac_compressor", self.disable_ac_compressor)
        self.dev_log("disable_external_ac_fan", self.disable_external_ac_fan)

        start_time = self.get_timestamp()
        self.latest_start_time = start_time

        self.dev_log("Starting climate control, start_time", start_time)

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
        self.dev_log("start_cooling")

        outside_temp = await self.get_temp(TempSensorsLocation.OUTSIDE_FOREST_SIDE)
        
        if(
            outside_temp > self.compressor_outside_temp_cutoff and
            not self.disable_ac_compressor
        ):
            self.dev_log("Setting AC to COOL")
            await self.set_ac_mode(ACModes.COOL)
        else:
            self.dev_log("Setting AC to FAN")
            await self.set_ac_mode(ACModes.FAN)

        if(self.disable_external_ac_fan):
            self.dev_log("Setting External AC Fan to OFF")
            await self.set_ac_ext_fan(OnOff.OFF)
        else:
            self.dev_log("Setting External AC Fan to On")
            await self.set_ac_ext_fan(OnOff.ON)
            

    async def stop_cooling(self):
        self.dev_log("stop_cooling")

        await self.set_ac_mode(ACModes.OFF)
        await self.set_ac_ext_fan(OnOff.OFF)