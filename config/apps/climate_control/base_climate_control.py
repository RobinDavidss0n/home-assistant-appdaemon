import appdaemon.plugins.hass.hassapi as hass
from support import Support
from enum import Enum
import time

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

    temp_ent_ending    = "_temp_humid_sensor_temperature"

    ac_ent             = "select.nedis_ir_controller_ac_mode"
    ac_power_draw_ent  = "sensor.smart_socket_3_power"
    ac_ext_fan_ent     = "switch.smart_socket_4"
    bedroom_heater_ent = "switch.smart_socket_1"

    base_settings_ents = [
        "input_number.climate_control_polling_interval",
        "input_number.climate_control_min_time_fan_per_hour",
        "input_number.climate_control_compressor_outside_temp_cutoff",
        "input_number.climate_control_compressor_low_draw_threshold",
        "input_number.climate_control_compressor_max_low_draw_duration",
        "input_number.climate_control_defrost_cycle_duration",
        "input_boolean.climate_control_disable_ac_compressor",
        "input_boolean.climate_control_disable_external_ac_fan",
        "input_boolean.climate_control_disable_freeze_warnings",
    ]

    error_restart_interval = 60
    compressor_running_draw_threshold  = 200     # CONST - Threshold for when compressor is running, the ac would draw more than this

    async def initialize(self):

        self.debug          = bool(self.args.get("debug", False))
        self.dev_logs       = bool(self.args.get("dev_logs", False))
        
        self.is_active_ent  = self.args.get("is_active_ent")
        self.is_active = (await self.get_state(self.is_active_ent)) == "on"
        self.dev_log("is_active", self.is_active)

        # --------------------------------------------------------------------
        # Mutable state initialization
        # --------------------------------------------------------------------        
        self.latest_start_time                  = None  # Used to make sure we don't have multiple instances running
        self.is_cooling                         = False
        self.is_any_fans_active                 = False
        self.current_hour                       = None 
        self.fan_runtime_mins_current_hour      = None
        self.compressor_low_draw_timer          = 0    # Used to track when compressor low draw started
        self.current_defrosting_timer           = 0    # seconds on the current defrosting timer

        # Entity-driven settings (overwritten by init_settings_members)
        self.polling_interval                   = None
        self.min_time_fan_per_hour              = None
        self.compressor_outside_temp_cutoff     = None
        self.compressor_low_draw_threshold      = None # Threshold for when the compressor is running but drawing low watts the usual, might be freezed over
        self.compressor_max_low_draw_duration   = None # seconds before considering freezed over
        self.defrost_cycle_duration             = None # Minutes after a freezed over to defrost
        self.disable_ac_compressor              = None
        self.disable_external_ac_fan            = None
        self.disable_freeze_warnings            = None

        await self.init_settings_members(BaseClimateControl.base_settings_ents)


    async def on_init_done(self):

        if(self.is_active):
            self.create_task(self.start())

        self.listen_state(self.on_is_active_ent_change, self.is_active_ent)
        self.listen_state(self.on_ac_power_draw_change, BaseClimateControl.ac_power_draw_ent)


    async def init_settings_members(self, settings_ents, sub_class_prefix=""):

        for ent in settings_ents:

            attr = ent.split(sub_class_prefix+"climate_control_")[1]
            val = await self.get_state(ent)

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

    async def on_ac_power_draw_change(self, entity, attribute, old, new, kwargs): 
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
        self.current_defrosting_timer = 0
        self.compressor_low_draw_timer = 0

        self.dev_log("Starting climate control, start_time", start_time)

        try:
            await self.base_loop(start_time)
        except Exception as e:
            self.log("Error caught\n", level="ERROR", exc_info=True)

            if(not self.debug):
                
                self.send_notification(f"An error happened: {e}")
                self.log("Starting again in 5 seconds....")

                await self.sleep(BaseClimateControl.error_restart_interval)

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
        return float(await self.get_state(f"sensor.{sensor.value}{BaseClimateControl.temp_ent_ending}"))

    async def get_target_temp(self, area: TempSensorsLocation):
        return float(await self.get_state(f"input_number.ordinary_climate_control_target_temp_{area.value}"))

    async def set_ac_mode(self, mode: ACModes):
        await self.call_service("select/select_option", entity_id=BaseClimateControl.ac_ent, option=mode.value)

    async def get_ac_current_power_draw(self):
        return float(await self.get_state(BaseClimateControl.ac_power_draw_ent))

    async def set_ac_ext_fan(self, mode: OnOff):
        await self.call_service(f"switch/turn_{mode.value}", entity_id=BaseClimateControl.ac_ext_fan_ent)

    async def set_bedroom_heater(self, mode: OnOff):
        await self.call_service(f"switch/turn_{mode.value}", entity_id=BaseClimateControl.bedroom_heater_ent)

    async def get_too_cold_for_compressor(self):
        outside_temp = await self.get_temp(TempSensorsLocation.OUTSIDE_FOREST_SIDE)
        return outside_temp < self.compressor_outside_temp_cutoff


    async def start_cooling(self):
        self.dev_log("start_cooling")

        self.is_cooling = True
        too_cold_for_compressor = await self.get_too_cold_for_compressor()

        # Set AC mode
        if(not too_cold_for_compressor and not self.disable_ac_compressor):

            # Sets defrosting mode if radiator might have freezed over
            # Returns if radiator freeze is detected
            if await self.check_for_radiator_freeze():
                self.dev_log("Radiator freeze detected, starting fans mode.")
                
                await self.set_ac_mode(ACModes.FAN)
                await self.set_ac_ext_fan(OnOff.ON)
                return

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

        self.dev_log(f"\nFan runtime this hour: {self.fan_runtime_mins_current_hour}\n Minimum fan runtime this hour: {self.min_time_fan_per_hour}")

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

        current_hour = (await self.datetime()).hour

        if current_hour != self.current_hour:
            self.fan_runtime_mins_current_hour = 0
            self.current_hour = current_hour

        if self.is_any_fans_active:
             self.fan_runtime_mins_current_hour += self.polling_interval / 60

    async def handle_ac_ext_fan_operation_during_cooling(self):

        if not self.is_active:
            return
        
        # If currently in defrosting mode, no need to change external fan state
        if self.current_defrosting_timer > 0:
            self.dev_log("Defrosting in progress, do not changing external fan state")
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
        
        if self.disable_ac_compressor:
            self.dev_log("Compressor disabled, setting external fan to ON")
            await self.set_ac_ext_fan(OnOff.ON)
            return

        ac_current_power_draw = await self.get_ac_current_power_draw()
        self.dev_log("AC current power draw", ac_current_power_draw)

        if ac_current_power_draw > BaseClimateControl.compressor_running_draw_threshold:
            self.dev_log("Compressor running, setting external fan to ON")
            await self.set_ac_ext_fan(OnOff.ON)
            return
        
        self.dev_log("Compressor not running, turning OFF external fan")
        await self.set_ac_ext_fan(OnOff.OFF)


    async def check_for_radiator_freeze(self) -> bool:
        self.dev_log("check_for_radiator_freeze")

        # Currently in defrost mode
        if self.current_defrosting_timer > 0:
            self.dev_log("Defrost active, defrosting cycle duration", {self.defrost_cycle_duration * 60})

            self.current_defrosting_timer += self.polling_interval
            self.dev_log(f"Current defrosting timer", self.current_defrosting_timer)

            # Defrosting complete
            if self.current_defrosting_timer > self.defrost_cycle_duration * 60:
                self.dev_log("Defrosting complete")
                self.current_defrosting_timer = 0
                return False
            
            self.dev_log("Defrosting in progress - IS freezed, returning True")
            return True

        else:
            ac_watt = await self.get_ac_current_power_draw()
            self.dev_log("AC current power draw", ac_watt)

            # Compressor running normally
            if ac_watt >= self.compressor_low_draw_threshold:
                self.dev_log("Compressor draw above threshold")
                self.compressor_low_draw_timer = 0
                return False

            # Compressor not running
            if ac_watt <= BaseClimateControl.compressor_running_draw_threshold:
                self.dev_log("Compressor not running")
                self.compressor_low_draw_timer = 0
                return False

            # Compressor low draw detected
            if ac_watt <= self.compressor_low_draw_threshold:
                self.dev_log("Compressor low draw detected, adding to timer")

                self.compressor_low_draw_timer += self.polling_interval
                self.dev_log("Compressor low draw timer", self.compressor_low_draw_timer)

                # Low draw timer exceeded, start defrosting
                if self.compressor_low_draw_timer > self.compressor_max_low_draw_duration:
                    self.dev_log("Low draw duration exceeded, might have freezed over, starting defrost")

                    self.compressor_low_draw_timer = 0
                    self.current_defrosting_timer = 1 # activate defrosting

                    if not self.disable_freeze_warnings:
                        await self.send_notification("Radiator freeze detected, starting defrosting cycle.")
                    return await self.check_for_radiator_freeze()
                
                self.dev_log("Compressor low draw timer not exceeded")
                return False              

        raise Exception(f"check_for_radiator_freeze > unhandled case, ac power draw: {ac_watt}")