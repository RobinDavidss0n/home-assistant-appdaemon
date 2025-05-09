from config.apps.climat_control.base_climat_control import ACModes, BaseClimateControl, OnOff, TempSensors


class OrdinaryClimateControl(BaseClimateControl):

	async def initialize(self):
		await super.initialize()

		self.last_cold_notification_sent = None

	async def loop_logic(self):

		self.dev_log("Checking temp...")
	
		self.variability = float(await self.get_state("input_number.ordinary_climate_control_variability_threshold"))
		self.cold_threshold = float(await self.get_state("input_number.ordinary_climate_control_temp_warning_threshold_cold"))
		self.warm_threshold = float(await self.get_state("input_number.ordinary_climate_control_temp_warning_threshold_warm"))

		self.outside_forest_side_temp = float(await self.get_temp(TempSensors.OUTSIDE_FOREST_SIDE))

		total_temp_diff = 0

		total_temp_diff + await self.control_temp_in_area(TempSensors.BEDROOM)
		total_temp_diff + await self.control_temp_in_area(TempSensors.OFFICE)
		total_temp_diff + await self.control_temp_in_area(TempSensors.LIVING_ROOM)

		if(abs(total_temp_diff) < self.variability):
			self.dev_log("Temp diff not great enough, check done.")
			return
	

	#TODO finish so the notification are not sent too often
	async def get_diff_temp_in_area(self, area: TempSensors):

		self.dev_log(f"Getting temp dif in > {area.value}")

		target_temp = float(await self.get_state(f"input_number.ordinary_climate_control_target_temp_{area.value}"))
		current_temp = await self.get_temp(area)

		temp_diff = current_temp - target_temp

		self.dev_log("Temp diff =", temp_diff)

		## Too cold
		if(temp_diff < 0 and abs(temp_diff) > self.cold_threshold):
			await self.send_notification(f"{area.value} is abnormally COLD, check vents.")

		## Too warm
		if(temp_diff < 0 and abs(temp_diff) > self.warm_threshold):
			await self.send_notification(f"{area.value} is abnormally WARM, check vents.")

