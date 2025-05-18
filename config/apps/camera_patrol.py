import appdaemon.plugins.hass.hassapi as hass
import time
from enum import IntEnum

class DoorState(IntEnum):
    CLOSED_FROM_INSIDE  = 0
    OPENED_FROM_INSIDE  = 1
    CLOSED_FROM_OUTSIDE = 2
    OPENED_FROM_OUTSIDE = 3

class CameraPatrol(hass.Hass):

    async def initialize(self):
        self.is_patroling_ent = self.args.get("is_patroling_ent")
        self.is_in_privacy_ent = self.args.get("is_in_privacy_ent")
        self.camera_name = self.args.get("camera_name")
        self.motion_alarm_ent = self.args.get("motion_alarm_ent")
        self.switch_privacy_entity = self.args.get("switch_privacy_entity")
        self.move_to_preset_ent = self.args.get("move_to_preset_ent")
        self.presets = self.args.get("presets", [])
        self.movement_timer = int(self.args.get("movement_timer"))

        self.debug = bool(self.args.get("debug", True))

        self.is_sleep_state_ent = "input_boolean.is_sleep_state"
        self.door_sensor_ent = "binary_sensor.bedroom_door_sensor_contact"
        
        self.is_patroling = await self.get_state(self.is_patroling_ent) == "on"
        self.is_in_privacy = await self.get_state(self.is_in_privacy_ent) == "on"
        
        self.loop_counter = 0
        self.last_patrol_start_time = None
        self.door_state = DoorState.CLOSED_FROM_INSIDE
        self.privacy_set_by_door_state = False

        self.listen_state(self.on_is_patroling_ent_change, self.is_patroling_ent)
        self.listen_state(self.on_is_in_privacy_ent_change, self.is_in_privacy_ent)
        self.listen_state(self.on_door_sensor_ent_change, self.door_sensor_ent)

        self.dev_log("is_patroling", self.is_patroling)
        self.dev_log("is_in_privacy", self.is_in_privacy)
        self.dev_log("door_state", self.door_state)

        if(self.is_in_privacy):
            self.create_task(self.turn_on_privacy())
        else:
            if(self.is_patroling):
                self.start_patrol()
            else:
                self.stop_patrol()



    def on_is_patroling_ent_change(self, entity, attribute, old, new, kwargs):
        self.dev_log(f"{entity} changed from {old} to {new}")
        
        if new == "on":
            self.start_patrol()
        else:
            self.stop_patrol()


    def on_is_in_privacy_ent_change(self, entity, attribute, old, new, kwargs):
        self.dev_log(f"{entity} changed from {old} to {new}")
        
        if new == "on":
            self.create_task(self.turn_on_privacy())
        else:
            self.create_task(self.turn_off_privacy())


    def on_door_sensor_ent_change(self, entity, attribute, old, new, kwargs):
        self.dev_log(f"{entity} changed from {old} to {new}")

        self.create_task(self.handle_door_sensor_change())
    

    def start_patrol(self, request = None, kwargs = None):
        
        self.dev_log("Camera patrol started")

        self.is_patroling = True
        self.is_in_privacy = False
        self.last_patrol_start_time = time.time()

        self.create_task(self.camera_patrol(self))


    def stop_patrol(self, request = None, kwargs = None):
        
        self.dev_log("Camera patrol stopped")
        self.is_patroling = False
    
    

    async def camera_patrol(self, kwargs):
        self.dev_log("Starting camera patrol")

        try:
            self.dev_log("sleep state: ", await self.get_state(self.is_sleep_state_ent))
            self.dev_log("door_sensor_ent: ", await self.get_state(self.door_sensor_ent))
            if await self.get_state(self.is_sleep_state_ent) == "on":
                
                if await self.get_state(self.door_sensor_ent) == "off": # off == contact...
                    self.door_state = DoorState.CLOSED_FROM_INSIDE
                    self.dev_log("door_state set to", self.door_state)
                else:
                    self.dev_log("Bedroom door not closed.")
                    await self.call_service("input_boolean/turn_off", entity_id=self.is_patroling_ent)

                    if(self.camera_name == "camera-1"):
                        await self.call_service(
                            "notify/mobile_app_robins_oneplus_13",
                            title="Camera patrol",
                            message="Sleep state - Door not closed, stopping.",
                            data= { "ttl": 0, "priority": "high" }
                        )
                    return

            # turn off privacy bool entity
            await self.call_service("input_boolean/turn_off", entity_id=self.is_in_privacy_ent)

            await self.call_service("python_script/set_state", entity_id=self.motion_alarm_ent, state="off")
            await self.call_service("switch/turn_off", entity_id=self.switch_privacy_entity)
            await self.sleep(1)

            # Outer infinite loop (repeat: while True)
            while self.is_patroling:
                self.dev_log("Going trough preset list")
                
                # For each preset in the list
                for preset in self.presets:
                    if not self.is_patroling:
                        break

                    self.dev_log(f"Moving to preset: {preset}")
                    # Move the camera by selecting the preset
                    await self.call_service("select/select_option", entity_id=self.move_to_preset_ent, option=preset)
                    
                    self.loop_counter = 0
                    while (self.loop_counter <= int(self.movement_timer)) and self.is_patroling:
                        # self.dev_log("Looping: ", self.loop_counter)
                        # self.dev_log("motion alarm state: ", await self.get_state(self.motion_alarm_ent))

                        # Wait a second between each check
                        await self.sleep(1)

                        # Update the counter based on the motion alarm state
                        if await self.get_state(self.motion_alarm_ent) == "off":
                            self.loop_counter += 1
                        else:
                            self.loop_counter = 0
                            
        except Exception as e:
            self.log("camera_patrol -> Error caught", e)
            
            await self.sleep(5)
            await self.camera_patrol(self)


    
    async def turn_on_privacy(self):
        self.dev_log("Turning on privacy mode.")

        try:
            self.is_in_privacy = True
            self.is_patroling = False
            await self.call_service("input_boolean/turn_off", entity_id=self.is_patroling_ent)
            
            await self.call_service("switch/turn_off", entity_id=self.switch_privacy_entity)
            await self.sleep(1)

            if(not self.is_in_privacy): 
                self.dev_log("Set privacy aborted, not in privacy anymore.")
                return
            
            await self.move_to_privacy_mode()
            await self.sleep(9)            

            if(not self.is_in_privacy): 
                self.dev_log("Set privacy aborted, not in privacy anymore.")
                return
            
            await self.call_service("switch/turn_on", entity_id=self.switch_privacy_entity)

            # Reset the alarm and detection states
            await self.call_service("python_script/set_state", entity_id=self.motion_alarm_ent, state="off")

        except Exception as e:
            self.log("turn_on_privacy -> Error caught", e)

            await self.sleep(1)
            self.create_task(self.turn_on_privacy())

    async def move_to_privacy_mode(self):
        await self.call_service("select/select_option", entity_id=self.move_to_preset_ent, option="Privacy")
    
    
    # NOTE will not set the privacy ent, that would create a infinite loop
    async def turn_off_privacy(self):
        self.dev_log("Turning off privacy mode.")

        try:
            self.is_in_privacy = False
            
            await self.call_service("switch/turn_off", entity_id=self.switch_privacy_entity)
            
            # Reset the alarm and detection states
            await self.call_service("python_script/set_state", entity_id=self.motion_alarm_ent, state="off")

        except Exception as e:
            self.log("turn_off_privacy -> Error caught", e)

            await self.sleep(1)
            self.create_task(self.turn_on_privacy())


    async def handle_door_sensor_change(self, restartFromError = False):

        try: 
            self.dev_log("Handling door sensor change.")
            
            if(await self.get_state(self.is_sleep_state_ent) == "off"):
                self.dev_log("Sleep state is off, returning.")
                return
            
            if(self.is_patroling and not self.privacy_set_by_door_state):
                self.dev_log("Currently patrolling, setting privacy.")
                self.privacy_set_by_door_state = True

            if(not self.privacy_set_by_door_state):
                self.dev_log("Not patrolling and privacy not set by door state, returning.")
                return
            
            if(not restartFromError):
                self.door_state = (self.door_state + 1) % 4
                
            self.dev_log("door_state: ", self.door_state)

            # Going out from bedroom, entering privacy mode
            if self.door_state == DoorState.OPENED_FROM_INSIDE:
                await self.move_to_privacy_mode()
                await self.call_service("input_boolean/turn_on", entity_id=self.is_in_privacy_ent)

            # Going in to bedroom, entering patrol mode
            elif self.door_state == DoorState.CLOSED_FROM_INSIDE:
                await self.call_service("input_boolean/turn_on", entity_id=self.is_patroling_ent)
                self.privacy_set_by_door_state = False

        except Exception as e:
            self.log("handle_door_sensor_change -> Error caught", e)

            await self.sleep(1)
            self.create_task(self.handle_door_sensor_change(True))



    def dev_log(self, msg, args=None):
        if self.debug:
            if args is None:
                self.log(f"--> {msg}")
            else:
                self.log(f"--> {msg}: {args}")