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

class OrdinaryClimateControl(BaseClimateControl):

	async def initialize(self):

		await super().initialize()

		self.settings_ents = [
            "input_number.ordinary_climate_control_variability_threshold",
            "input_number.ordinary_climate_control_temp_warning_threshold_cold",
			"input_number.ordinary_climate_control_temp_warning_threshold_warm",
            "input_number.ordinary_climate_control_repeated_warnings_block_timer",
			"input_boolean.ordinary_climate_disable_control_temp_warnings"
        ]
		self.variability_threshold 			= None
		self.temp_warning_threshold_cold 	= None
		self.temp_warning_threshold_warm 	= None
		self.repeated_warnings_block_timer 	= None
		self.disable_temp_warnings			= None

		await self.init_settings(self.settings_ents, "ordinary")

	async def start(self):

		self.cold_temp_warning_tracker = TempWarningTracker()
		self.warm_temp_warning_tracker = TempWarningTracker()

		# Debug tools
		self.counter = 0
		self.counting_down = False
		self.debug_fake_temps = bool(self.args.get("debug_fake_temps", False))
		
		await super().start()


	async def loop_logic(self):

		self.dev_log("Checking temp...")
		if(self.debug_fake_temps):
			self.dev_log("counter: ", self.counter)

		rooms = [
			TempSensorsLocation.BEDROOM,
			TempSensorsLocation.OFFICE,
			TempSensorsLocation.LIVING_ROOM
		]

		diffs = []
		for room in rooms:
			diffs.append(await self.get_diff_temp_in_room(room))

		highest_diff_index = 0
		for i in range(1, len(diffs)):
			if diffs[i] > diffs[highest_diff_index]:
				highest_diff_index = i

		warmest_room = rooms[highest_diff_index]
		warmest_rooms_diff = diffs[highest_diff_index]
		
		self.dev_log("Warmest room", warmest_room.value)
		self.dev_log("Warmest roms diff", warmest_rooms_diff)

		if(warmest_rooms_diff > self.variability_threshold):
			self.dev_log("Warmest room too hot, turning on cooling.")
			await self.start_cooling()		
		else:
			self.dev_log("Warmest room not hot enough, turning off cooling.")
			await self.stop_cooling()		
	

	async def get_diff_temp_in_room(self, area: TempSensorsLocation):

		target_temp = float(await self.get_state(f"input_number.ordinary_climate_control_target_temp_{area.value}"))
		
		if(self.debug_fake_temps):
			current_temp = float(15 + self.counter)
		else:
			current_temp = await self.get_temp(area)

		diff = current_temp - target_temp
		abs_temp_diff = abs(diff)

		self.dev_log(f"{area.value}: current_temp = {current_temp}, diff = {diff}")

		if(self.debug_fake_temps):
			self.debug_counter()

		# Too warm
		if(diff > 0 and abs_temp_diff > self.temp_warning_threshold_warm):
			await self.send_temp_warning(TempWarningType.WARM, area)
		# Too cold
		elif(diff < 0 and abs_temp_diff > self.temp_warning_threshold_cold):
			await self.send_temp_warning(TempWarningType.COLD, area)
		else:
			cast(TempWarningTrackerArea, getattr(self.warm_temp_warning_tracker,area.value)).temp_normalized_after_last_warning = True
			cast(TempWarningTrackerArea, getattr(self.cold_temp_warning_tracker,area.value)).temp_normalized_after_last_warning = True

		return diff


	async def send_temp_warning(self, type: TempWarningType, area: TempSensorsLocation):

		if(self.disable_temp_warnings):
			self.dev_log("Warnings disabled.")
			return
		
		tracker: TempWarningTrackerArea = getattr(self.warm_temp_warning_tracker, area.value)
		
		if(type == TempWarningType.COLD):
			tracker: TempWarningTrackerArea = getattr(self.cold_temp_warning_tracker, area.value)

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

		if(type == TempWarningType.WARM):
			await self.send_notification(f"WARM WARNING -> {area.value}")
		
		if(type == TempWarningType.COLD):
			await self.send_notification(f"COLD WARNING -> {area.value}")

		tracker.last_warning_sent = timestamp
		tracker.temp_normalized_after_last_warning = False


	def debug_counter(self):

		if(not self.counting_down):
			self.counter += 1
			if(self.counter > 5):
				self.counting_down = True

		else:
			self.counter -= 1
			if(self.counter < 1):
				self.counting_down = False