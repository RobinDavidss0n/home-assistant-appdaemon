from enum import Enum
from base_climat_control import BaseClimateControl, TempSensorsLocation
from dataclasses import dataclass, field
from typing import Optional, cast

class TempWarningType(Enum):
	WARM = 0
	COLD = 1

@dataclass
class TempWarningTrackerArea:
	last_warning_sent: Optional[int] = None #timestamp
	temp_normilised_after_last_warning: bool = True

@dataclass
class TempWarningTracker:
	bedroom: 		TempWarningTrackerArea = field(default_factory=TempWarningTrackerArea)
	office: 		TempWarningTrackerArea = field(default_factory=TempWarningTrackerArea)
	living_room: 	TempWarningTrackerArea = field(default_factory=TempWarningTrackerArea)

class OrdinaryClimateControl(BaseClimateControl):

	async def start(self):

		self.dev_log("Ordinary start()")

		self.cold_temp_warning_tracker = TempWarningTracker()
		self.warm_temp_warning_tracker = TempWarningTracker()

		self.counter = 0
		self.counting_down = False

		self.variability 					= float(await self.get_state("input_number.ordinary_climate_control_variability_threshold"))
		self.cold_warning_threshold 		= float(await self.get_state("input_number.ordinary_climate_control_temp_warning_threshold_cold"))
		self.warm_warning_threshold 		= float(await self.get_state("input_number.ordinary_climate_control_temp_warning_threshold_warm"))
		self.repeated_warnings_block_timer 	= float(await self.get_state("input_number.ordinary_climate_control_repeated_warnings_block_timer"))
		
		await super().start()


	async def loop_logic(self):

		self.dev_log("Checking temp...")
		if(self.debug):
			self.dev_log("counter: ", self.counter)

		self.outside_forest_side_temp = float(await self.get_temp(TempSensorsLocation.OUTSIDE_FOREST_SIDE))

		total_temp_diff = 0

		total_temp_diff += await self.get_diff_temp_in_area(TempSensorsLocation.BEDROOM)
		total_temp_diff += await self.get_diff_temp_in_area(TempSensorsLocation.OFFICE)
		total_temp_diff += await self.get_diff_temp_in_area(TempSensorsLocation.LIVING_ROOM)

		if(abs(total_temp_diff) < self.variability):
			self.dev_log("Temp diff not great enough, check done.")
			return
		
		#TODO adjust temp accordeling
	

	async def get_diff_temp_in_area(self, area: TempSensorsLocation):

		self.dev_log(f"Getting temp dif in > {area.value}")

		target_temp = float(await self.get_state(f"input_number.ordinary_climate_control_target_temp_{area.value}"))
		
		if(self.debug):
			current_temp = 15 + self.counter
		else:
			current_temp = await self.get_temp(area)

		diff = current_temp - target_temp
		abs_temp_diff = abs(diff)

		self.dev_log("current_temp =", current_temp)
		self.dev_log("Temp diff =", diff)

		if(self.debug):
			self.debug_conter()

		# Too warm
		if(diff > 0 and abs_temp_diff > self.warm_warning_threshold):
			await self.send_temp_warning(TempWarningType.WARM, area)
		# Too cold
		elif(diff < 0 and abs_temp_diff > self.cold_warning_threshold):
			await self.send_temp_warning(TempWarningType.COLD, area)
		else:
			cast(TempWarningTrackerArea, getattr(self.warm_temp_warning_tracker,area.value)).temp_normilised_after_last_warning = True
			cast(TempWarningTrackerArea, getattr(self.cold_temp_warning_tracker,area.value)).temp_normilised_after_last_warning = True

		return diff


	async def send_temp_warning(self, type: TempWarningType, area: TempSensorsLocation):

		if(await self.get_state("input_boolean.ordinary_climate_control_temp_warnings") == "off"):
			self.dev_log("send_temp_warning: Warnings disabled, returning.")
			return
		
		tracker: TempWarningTrackerArea = getattr(self.warm_temp_warning_tracker, area.value)
		
		if(type == TempWarningType.COLD):
			tracker: TempWarningTrackerArea = getattr(self.cold_temp_warning_tracker, area.value)

		timestamp = self.get_timestamp_in_seconds()

		seconds_since_last_warning = None
		if(tracker.last_warning_sent != None):
			
			seconds_since_last_warning = timestamp - tracker.last_warning_sent

			if(	seconds_since_last_warning != None and
				seconds_since_last_warning < self.repeated_warnings_block_timer
			):
				self.dev_log("Not enough time sinces last warning, sconds sinces last: ", seconds_since_last_warning)
				return
		
		if(not tracker.temp_normilised_after_last_warning):
			self.dev_log("Temp have not been normilised sinces last warning")
			return

		if(type == TempWarningType.WARM):
			await self.send_notification(f"WARM WARNING -> {area.value}")
		
		if(type == TempWarningType.COLD):
			await self.send_notification(f"COLD WARNING -> {area.value}")

		tracker.last_warning_sent = timestamp
		tracker.temp_normilised_after_last_warning = False


	def debug_conter(self):

		if(not self.counting_down):
			self.counter += 1
			if(self.counter > 5):
				self.counting_down = True

		else:
			self.counter -= 1
			if(self.counter < 1):
				self.counting_down = False