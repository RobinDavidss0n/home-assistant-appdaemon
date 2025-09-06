from enum import Enum
from base_climate_control import BaseClimateControl, TempSensorsLocation
from dataclasses import dataclass, field
from typing import Optional, cast

class TempWarningType(Enum):
	WARM = 0
	COLD = 1

@dataclass
class TempWarningTrackerArea:
	last_warning_sent: Optional[int] = None #timestamp
	temp_normalized_after_last_warning: bool = True

@dataclass
class TempWarningTracker:
	bedroom: 		TempWarningTrackerArea = field(default_factory=TempWarningTrackerArea)
	office: 		TempWarningTrackerArea = field(default_factory=TempWarningTrackerArea)
	living_room: 	TempWarningTrackerArea = field(default_factory=TempWarningTrackerArea)

def get_tracker_area(tracker: TempWarningTracker, area: TempSensorsLocation):
	return cast(TempWarningTrackerArea, getattr(tracker, area.value))

class OrdinaryClimateControl(BaseClimateControl):

	async def initialize(self):

		await super().initialize()

		# NOTE time input needs to end with _time for the conversions to work
		settings_ents = [
            "input_number.ordinary_climate_control_variability_threshold",
            "input_number.ordinary_climate_control_temp_warning_threshold_cold",
			"input_number.ordinary_climate_control_temp_warning_threshold_warm",
            "input_number.ordinary_climate_control_repeated_warnings_block_timer",
			"input_boolean.ordinary_climate_control_disable_temp_warnings",
			
			# Overrides the base class
            "input_number.ordinary_climate_control_min_time_fan_per_hour",
        ]
		self.variability_threshold 			= None
		self.temp_warning_threshold_cold 	= None
		self.temp_warning_threshold_warm 	= None
		self.repeated_warnings_block_timer 	= None
		self.disable_temp_warnings			= None

		# Overrides base class
		self.min_time_fan_per_hour	= None
	
		self.cold_temp_warning_tracker = TempWarningTracker()
		self.warm_temp_warning_tracker = TempWarningTracker()

		await self.init_settings_members(settings_ents, "ordinary_")

		await self.on_init_done()


	async def start(self):
		await self.call_service("input_boolean/turn_off", entity_id="input_boolean.sleep_climate_control")
		await self.sleep(1)
		await super().start()


	async def loop_logic(self):

		self.dev_log("Checking temp...")

		rooms = [
			TempSensorsLocation.BEDROOM,
			TempSensorsLocation.OFFICE,
			TempSensorsLocation.LIVING_ROOM
		]

		diffs = []
		for room in rooms:

			roomDiff = await self.get_diff_temp_in_room(room)

			if abs(roomDiff) < self.variability_threshold:
				get_tracker_area(self.warm_temp_warning_tracker, room).temp_normalized_after_last_warning = True
				get_tracker_area(self.cold_temp_warning_tracker, room).temp_normalized_after_last_warning = True

			diffs.append(roomDiff)

		highest_diff_index = 0
		for i in range(1, len(diffs)):
			if diffs[i] > diffs[highest_diff_index]:
				highest_diff_index = i

		warmest_room = rooms[highest_diff_index]
		warmest_rooms_diff = diffs[highest_diff_index]

		self.dev_log(f"Warmest room {warmest_room.value} | Diff: {round(warmest_rooms_diff, 2)}")

		if(warmest_rooms_diff > self.variability_threshold):
			self.dev_log("Warmest room too hot, turning on cooling.")
			await self.start_cooling()		
		else:
			self.dev_log("Warmest room not hot enough, turning off cooling.")
			await self.stop_cooling()		
	

	async def get_diff_temp_in_room(self, area: TempSensorsLocation):

		target_temp = await self.get_target_temp(area)
		current_temp = await self.get_temp(area)

		diff = current_temp - target_temp
		abs_temp_diff = abs(diff)

		self.dev_log(f"ROOM = {area.value} | Current temp: {round(current_temp, 2)}\nTarget temp: {round(target_temp, 2)} | Diff: {round(diff, 2)}")

		# Too warm
		if(
			diff > 0 and
			abs_temp_diff > self.temp_warning_threshold_warm
		):
			await self.send_temp_warning(TempWarningType.WARM, area,  target_temp, current_temp)

		# Too cold
		elif(
			diff < 0 and
			abs_temp_diff > self.temp_warning_threshold_cold
		):
			await self.send_temp_warning(TempWarningType.COLD, area, target_temp, current_temp)

		return diff


	async def send_temp_warning(self, type: TempWarningType, area: TempSensorsLocation, target_temp, current_temp):

		if(self.disable_temp_warnings):
			return
		
		coolTracker: TempWarningTrackerArea = getattr(self.cold_temp_warning_tracker, area.value)
		warmTracker: TempWarningTrackerArea = getattr(self.warm_temp_warning_tracker, area.value)

		tracker: TempWarningTrackerArea
		
		if(type == TempWarningType.COLD):
			tracker: TempWarningTrackerArea = coolTracker
			warmTracker.temp_normalized_after_last_warning = True
		else:
			tracker: TempWarningTrackerArea = warmTracker
			coolTracker.temp_normalized_after_last_warning = True

		timestamp = self.get_timestamp_in_seconds()

		seconds_since_last_warning = None
		if(tracker.last_warning_sent != None):
			
			seconds_since_last_warning = timestamp - tracker.last_warning_sent

			if(	seconds_since_last_warning < self.repeated_warnings_block_timer):
				self.dev_log("Not enough time since last warning, time", seconds_since_last_warning)
				return
		
		if(not tracker.temp_normalized_after_last_warning):
			self.dev_log("Temp have not been normalized since last warning")
			return

		temp_info = f"-> {area.value} \n Current: {round(current_temp, 2)} | Target: {round(target_temp, 2)} | Diff: {round((current_temp - target_temp), 2)}"

		if(type == TempWarningType.WARM):
			await self.send_notification(f"WARM WARNING {temp_info}")

		if(type == TempWarningType.COLD):
			await self.send_notification(f"COLD WARNING {temp_info}")

		tracker.last_warning_sent = timestamp
		tracker.temp_normalized_after_last_warning = False
