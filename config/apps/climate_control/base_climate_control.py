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

        self.debug          = bool(self.args.get("debug", False))
        self.dev_logs       = bool(self.args.get("dev_logs", False))
        
        self.is_active_ent  = self.args.get("is_active_ent")
        self.is_active = (await self.get_state(self.is_active_ent)) == "on"
        self.dev_log("is_active", self.is_active)

        self.error_restart_interval         = 60
        self.latest_start_time              = None  # Used to make sure we don't have multiple instances running
        self.is_cooling                     = False
        self.is_any_fans_active             = False
        self.current_hour                   = None 
        self.fan_runtime_mins_current_hour  = None

        self.temp_ent_ending    = "_temp_humid_sensor_temperature"

        self.ac_ent             = "select.nedis_ir_controller_ac_mode"
        self.ac_power_draw_ent  = "sensor.smart_socket_3_power"
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
        self.listen_state(self.on_ac_power_draw_change, self.ac_power_draw_ent)


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
            self.create_task(self.set_ac_ext_fan(OnOff.OFF))
            self.create_task(self.set_ac_mode(ACModes.OFF))
            self.is_active = False

    def on_ac_power_draw_change(self, entity, attribute, old, new, kwargs):
        self.dev_log(f"AC power draw change from '{old}' to '{new}'")
        self.create_task(self.handle_ac_ext_fan_operation_during_cooling())

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
        except Exception as e:
            self.log("Error caught\n", level="ERROR", exc_info=True)

            if(not self.debug):
                
                self.send_notification(f"An error happened: {e}")
                self.log("Starting again in 5 seconds....")

                await self.sleep(self.error_restart_interval)

                if(self.is_active and start_time == self.latest_start_time):
                    self.create_task(self.start())


    async def base_loop(self, start_time):

        while(self.is_active and start_time == self.latest_start_time):
            await self.update_fan_runtime()
            await self.loop_logic()
            await self.sleep(self.polling_interval)

    async def loop_logic(self):
        return
    
    
    async def send_notification(self, msg):
        await self.send_mobile_notification("Climate Control", msg)

    async def get_temp(self, sensor: TempSensorsLocation):
        return float(await self.get_state(f"sensor.{sensor.value}{self.temp_ent_ending}"))

    async def get_target_temp(self, area: TempSensorsLocation):
        return float(await self.get_state(f"input_number.ordinary_climate_control_target_temp_{area.value}"))

    async def set_ac_mode(self, mode: ACModes):
        await self.call_service("select/select_option", entity_id=self.ac_ent, option=mode.value)

    async def get_ac_current_power_draw(self):
        return float(await self.get_state(self.ac_power_draw_ent))

    async def set_ac_ext_fan(self, mode: OnOff):
        await self.call_service(f"switch/turn_{mode.value}", entity_id=self.ac_ext_fan_ent)

    async def set_bedroom_heater(self, mode: OnOff):
        await self.call_service(f"switch/turn_{mode.value}", entity_id=self.bedroom_heater_ent)

    async def get_too_cold_for_compressor(self):
        outside_temp = await self.get_temp(TempSensorsLocation.OUTSIDE_FOREST_SIDE)
        return outside_temp < self.compressor_outside_temp_cutoff


    async def start_cooling(self):
        self.dev_log("start_cooling")

        self.is_cooling = True
        too_cold_for_compressor = await self.get_too_cold_for_compressor()

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
        await self.handle_ac_ext_fan_operation_during_cooling()

        # Set bedroom heater to off
        await self.set_bedroom_heater(OnOff.OFF)

        self.is_any_fans_active = True
            

    async def stop_cooling(self):
        self.dev_log("stop_cooling")

        self.dev_log("Fan runtime this hour", self.fan_runtime_mins_current_hour)
        self.dev_log("Minimum fan runtime this hour", self.min_time_fan_per_hour)

        self.is_cooling = False

        if self.min_time_fan_per_hour > self.fan_runtime_mins_current_hour:
            
            self.dev_log("Fan runtime this hour is less than minimum, keeping AC fan on.")
            await self.set_ac_mode(ACModes.FAN)
            self.is_any_fans_active = True

        else:
            await self.set_ac_mode(ACModes.OFF)
            self.is_any_fans_active = False

        await self.set_ac_ext_fan(OnOff.OFF)

    
    async def update_fan_runtime(self):
        self.dev_log("update_fan_runtime")

        current_hour = (await self.datetime()).hour
        self.dev_log("current hour", current_hour)

        if current_hour != self.current_hour:
            self.dev_log("New hour started. Previous hour fan runtime", self.fan_runtime_mins_current_hour)
            self.fan_runtime_mins_current_hour = 0
            self.current_hour = current_hour

        if self.is_any_fans_active:
             self.fan_runtime_mins_current_hour += self.polling_interval / 60

        self.dev_log("Fan mins run current hour", self.fan_runtime_mins_current_hour)

    async def handle_ac_ext_fan_operation_during_cooling(self):
        self.dev_log("handle_ac_ext_fan_operation")

        if not self.is_active:
            self.dev_log("CC not active, returning")
            return

        if not self.is_cooling:
            self.dev_log("Not cooling, setting external fan to OFF")
            await self.set_ac_ext_fan(OnOff.OFF)
            return

        if(self.disable_external_ac_fan):
            self.dev_log("External AC Fan disabled, setting external fan to OFF")
            await self.set_ac_ext_fan(OnOff.OFF)
            return
        
        too_cold_for_compressor = await self.get_too_cold_for_compressor()
        if too_cold_for_compressor:
            self.dev_log("Too cold outside to run compressor, setting external fan to ON")
            await self.set_ac_ext_fan(OnOff.ON)
            return

        ac_current_power_draw = await self.get_ac_current_power_draw()
        self.dev_log("AC current power draw", ac_current_power_draw)

        if ac_current_power_draw > 500:
            self.dev_log("Compressor running, setting external fan to ON")
            await self.set_ac_ext_fan(OnOff.ON)
            return
        
        self.dev_log("Compressor not running, turning OFF external fan")
        await self.set_ac_ext_fan(OnOff.OFF)