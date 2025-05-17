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

        self.debug          = bool(self.args.get("debug", False))
        self.dev_logs       = bool(self.args.get("dev_logs", False))
        
        self.is_active_ent  = self.args.get("is_active_ent")
        self.is_active = (await self.get_state(self.is_active_ent)) == "on"
        self.dev_log("is_active", self.is_active)

        self.error_restart_interval = 10
        self.latest_start_time = None

        self.temp_ent_ending    = "_temp_humid_sensor_temperature"

        self.ac_ent             = "select.nedis_ir_controller_ac_mode"
        self.ac_ext_fan_ent     = "switch.smart_socket_4"
        self.bedroom_heater_ent = "switch.smart_socket_1"

        self.base_settings_ents = [
            "input_number.climate_control_polling_interval",
            "input_number.climate_control_min_time_fan_per_hour",
            "input_number.climate_control_compressor_outside_temp_cutoff",
            "input_boolean.climate_control_disable_ac_compressor",
            "input_boolean.climate_control_disable_external_ac_fan",
        ]
        self.polling_interval               = None
        self.min_time_fan_per_hour          = None
        self.compressor_outside_temp_cutoff = None
        self.disable_ac_compressor          = None
        self.disable_external_ac_fan        = None

        await self.init_settings_members(self.base_settings_ents)


    async def on_init_done(self):

        if(self.is_active):
            self.create_task(self.start())

        self.listen_state(self.on_is_active_ent_change, self.is_active_ent)


    async def init_settings_members(self, settings_ents, sub_class_prefix=""):
        self.dev_log("init_settings")

        for ent in settings_ents:
            self.dev_log("<=======================================================>")
            self.dev_log("ent", ent)

            self.dev_log("split str", sub_class_prefix+"climate_control_")
            attr = ent.split(sub_class_prefix+"climate_control_")[1]
            self.dev_log("attr", attr)

            val = await self.get_state(ent)
            self.dev_log("val", val)

            if attr.startswith("disable_"):
                setattr(self, attr, val == "on")
            else:
                setattr(self, attr, float(val))

            self.listen_state(self.on_setting_change, ent, attr_name=attr)
            self.dev_log(attr, getattr(self, attr))


    def on_is_active_ent_change(self, entity, attribute, old, new, kwargs):

        self.dev_log(f"Is active change from '{old}' to '{new}'")

        if new == "on":
            self.is_active = True
            self.create_task(self.start())
        else:
            self.is_active = False

    def on_setting_change(self, entity, attribute, old, new, kwargs):

        attr = kwargs.get("attr_name")

        if attr:
            if attr.startswith("disable_"):
                value = new == "on"
            else:
                value = float(new)

            setattr(self, attr, value)
            self.dev_log(f"Setting '{attr}' updated to", value)
    

    async def start(self):

        start_time = self.get_timestamp()
        self.latest_start_time = start_time

        self.dev_log("Starting climate control, start_time", start_time)

        try:
            await self.base_loop(start_time)
        except:
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

    async def get_target_temp(self, area: TempSensorsLocation):
        return float(await self.get_state(f"input_number.ordinary_climate_control_target_temp_{area.value}"))

    async def set_ac_mode(self, mode: ACModes):
        await self.call_service("select/select_option", entity_id=self.ac_ent, option=mode.value)

    async def set_ac_ext_fan(self, mode: OnOff):
        await self.call_service(f"switch/turn_{mode.value}", entity_id=self.ac_ext_fan_ent)

    async def set_bedroom_heater(self, mode: OnOff):
        await self.call_service(f"switch/turn_{mode.value}", entity_id=self.bedroom_heater_ent)


    async def start_cooling(self):
        self.dev_log("start_cooling")

        outside_temp = await self.get_temp(TempSensorsLocation.OUTSIDE_FOREST_SIDE)
        too_cold_for_compressor = outside_temp < self.compressor_outside_temp_cutoff

        # Set AC mode
        if(not too_cold_for_compressor and not self.disable_ac_compressor):
            self.dev_log("Setting AC to COOL")
            await self.set_ac_mode(ACModes.COOL)

        else:
            if self.disable_ac_compressor:  self.dev_log("Compressor disabled in settings.")
            if too_cold_for_compressor:     self.dev_log("Too cold outside to run compressor.")

            self.dev_log("Setting AC to FAN")
            await self.set_ac_mode(ACModes.FAN)

        # Set external AC fan
        if(self.disable_external_ac_fan):
            self.dev_log("Setting External AC Fan to OFF")
            await self.set_ac_ext_fan(OnOff.OFF)

        else:
            self.dev_log("Setting External AC Fan to On")
            await self.set_ac_ext_fan(OnOff.ON)

        # Set bedroom heater to off
        await self.set_bedroom_heater(OnOff.OFF)
            

    async def stop_cooling(self):
        self.dev_log("stop_cooling")

        await self.set_ac_mode(ACModes.OFF)
        await self.set_ac_ext_fan(OnOff.OFF)