from base_climate_control import BaseClimateControl, OnOff, TempSensorsLocation
from datetime import datetime, time, timedelta

class SleepClimateControl(BaseClimateControl):

    next_alarm_time_ent = "sensor.robins_oneplus_13_next_alarm"
    max_alarm_retries = 5
    default_alarm_time = 9 # Default alarm time if not set (hour in 24-hour format)


    async def initialize(self):

        await super().initialize()

        # --------------------------------------------------------------------
        # Mutable state initialization
        # --------------------------------------------------------------------   
        self.alarm_dt: datetime = None

        self.settings_ents = [
            "input_number.sleep_climate_control_target_evening_temp",
            "input_number.sleep_climate_control_target_morning_temp",
            "input_number.sleep_climate_control_warmup_cycles",
            "input_number.sleep_climate_control_variability_threshold",
            "input_datetime.sleep_climate_control_warmup_time"
        ]
        
        # Entity-driven settings (overwritten by init_settings_members)
        self.target_evening_temp 	= None
        self.target_morning_temp 	= None
        self.warmup_cycles 			= None
        self.warmup_time 			= None # time from ha in hh:mm:ss format
        self.variability_threshold	= None

        await self.init_settings_members(self.settings_ents, "sleep_")

        await self.on_init_done()


    async def start(self):

        await self.start_cooling()
        await self.update_alarm_dt()
        await self.call_service("input_boolean/turn_off", entity_id="input_boolean.ordinary_climate_control")
        await self.sleep(1)
        await super().start()


    async def loop_logic(self):
        self.dev_log("loop_logic")

        bedroom_temp = await self.get_temp(TempSensorsLocation.BEDROOM)

        now_time = self.get_datetime_in_local_time().time()
        warmup_time = datetime.strptime(str(self.warmup_time), "%H:%M:%S").time()

        self.dev_log(f"Current time: {now_time}, Warmup time: {warmup_time}")

        if now_time >= time(18, 0) or now_time < warmup_time:
        # Before warmup time
            self.dev_log("Before warmup time, using evening target temp.")
            await self.handle_cooling_or_heating(bedroom_temp, self.target_evening_temp)
            return

        # Warmup time
        self.dev_log("Warmup time started, using morning target temp.")
        await self.handle_cooling_or_heating(bedroom_temp, await self.calculate_warmup_target())


    async def handle_cooling_or_heating(self, current, target):

        diff = current - target
        self.dev_log(f"Temp: {current}, Target: {target}, Diff: {round(diff, 2)}")

        if abs(diff) < self.variability_threshold:
            self.dev_log("Within variability threshold, returning")
            await self.stop_cooling()
            return

        if diff > 0:
            self.dev_log("Higher than target, starting cooling.")
            await self.start_cooling()
        else:
            self.dev_log("Lower than target, starting heating.")
            await self.stop_cooling()
            await self.set_bedroom_heater(OnOff.ON)


    async def calculate_warmup_target(self):

        now_dt = self.get_datetime_in_local_time()

        if now_dt >= self.alarm_dt:
            # If the current time is past the alarm time, return the morning target temperature
            self.dev_log("Current time is past the alarm time, returning morning target temperature.")
            return self.target_morning_temp
        
        # Create a datetime object for the start of the warmup period.
        # Use the date from now and the time from warmup_time (string "HH:MM:SS").
        warmup_time_t = datetime.strptime(self.warmup_time, "%H:%M:%S").time()
        # Use the timezone from now_dt to localize the start_time_dt
        start_time_dt = datetime.combine(now_dt.date(), warmup_time_t).replace(tzinfo=now_dt.tzinfo)

        # Calculate total warmup duration in seconds
        warmup_duration_s = (self.alarm_dt - start_time_dt).total_seconds()

        # Check for warm-up span zero or negative (mis-config)
        if warmup_duration_s <= 0:
            return self.target_morning_temp

        # Calculate elapsed time as a fraction of the warmup duration
        elapsed_time_fraction = (now_dt - start_time_dt).total_seconds() / warmup_duration_s
        # keep it inside [0, 1] 
        elapsed_time_fraction = max(0, min(1, elapsed_time_fraction))

        # Determine which warmup cycle we are currently in
        current_cycle = int(elapsed_time_fraction * self.warmup_cycles)

        # Calculate the total temperature difference to achieve during warmup
        temp_diff = self.target_morning_temp - self.target_evening_temp

        # Calculate the fraction of cycles completed
        cycle_fraction = current_cycle / self.warmup_cycles
        # Ensure cycle_fraction is between 0 and 1
        cycle_fraction = min(1, cycle_fraction)

        # Calculate the temperature increase for the current cycle
        cycle_temp_increase = temp_diff * cycle_fraction

        target_temp = self.target_evening_temp + cycle_temp_increase

        self.dev_log(
            f"Warmup calculation steps:\n"
            f"  alarm_date: {self.alarm_dt}\n"
            f"  start_time_date: {start_time_dt}\n"
            f"  warmup_duration_s: {warmup_duration_s}\n"
            f"  elapsed_time_fraction: {elapsed_time_fraction}\n"
            f"  warmup_cycles: {self.warmup_cycles}\n"
            f"  current_cycle: {current_cycle}\n"
            f"  temp_diff: {temp_diff}\n"
            f"  cycle_fraction: {cycle_fraction}\n"
            f"  cycle_temp_increase: {cycle_temp_increase}\n"
            f"  target_temp: {target_temp}\n"
        )

        return target_temp


    async def update_alarm_dt(self, retries = 0):
        self.dev_log("update_alarm_dt")

        max_retries = SleepClimateControl.max_alarm_retries

        now_dt = self.get_datetime_in_local_time()
        self.dev_log("now_dt", now_dt)

        if retries > max_retries:
            # Using default alarm time after waiting 5 minutes
            self.alarm_dt = datetime.combine(now_dt.date(), time(SleepClimateControl.default_alarm_time)).astimezone()
            self.dev_log(f"Using default alarm time: {self.alarm_dt}")
            return
        
        alarm_string = await self.get_state(self.next_alarm_time_ent)
        self.dev_log("alarm_string", alarm_string)

        if alarm_string == "unavailable":

            if retries == 0:
                await self.send_mobile_notification("Sleep Climate Control", f"No alarm set, retrying {max_retries} times before using default {SleepClimateControl.default_alarm_time}:00")

            if retries < max_retries:
                await self.sleep(5)

            await self.update_alarm_dt(retries=retries + 1)
            return
            
        self.alarm_dt = datetime.fromisoformat(alarm_string).astimezone()
        self.dev_log("alarm_dt", self.alarm_dt)

        alarm_diff = self.alarm_dt - now_dt
        self.dev_log("alarm_diff", alarm_diff)

        if alarm_diff > timedelta(hours=12):

            self.dev_log("Alarm time is more than 12 hours away.")
            if retries == 0:
                await self.send_mobile_notification("Sleep Climate Control", f"Alarm time is more than 12 hours away, retrying {max_retries} times before using default {SleepClimateControl.default_alarm_time}:00")

            if retries < max_retries:
                await self.sleep(5)

            await self.update_alarm_dt(retries=retries + 1)
            return
