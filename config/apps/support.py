from datetime import datetime
from datetime import timedelta
import appdaemon.plugins.hass.hassapi as hass

class Support(hass.Hass):


    async def send_mobile_notification(self, title, msg):
        await self.call_service(
            "notify/mobile_app_robins_oneplus_13",
            title=title,
            message=msg,
            data= { "ttl": 0, "priority": "high" }
        )
	
    def get_timestamp_in_seconds(self):
        return int(datetime.now().timestamp())
    
    def get_timestamp(self):
        return datetime.now().timestamp()
    
    
    def get_datetime_in_local_time(self):

        # return (datetime.now().astimezone() + timedelta(days=1)).replace(
        #     hour=1+self.counter, minute=0, second=0, microsecond=0)
    
        return datetime.now().astimezone()

    def dev_log(self, msg, args=None):
        if self.dev_logs:

            if args is None:
                self.log(f"-> {msg}")
            else:
                if isinstance(args, float):
                    self.log(f"-> {msg}: {round(args, 2)}")
                else:
                    self.log(f"-> {msg}: {args}")


    def is_weekend(self, dt=None):
        if dt is None:
            dt = self.get_datetime_in_local_time()
        
        return dt.weekday() >= 5

    def get_time_from_ha_time_input(self, time_input):
        return datetime.strptime(str(time_input), "%H:%M:%S").time()
    
    def get_datetime_from_ha_time_input(self, time_input):
        """
        Parses a time string and returns a timezone-aware datetime for today.
        """
        now_dt = datetime.now().astimezone()
        time_obj = self.get_time_from_ha_time_input(time_input)

        return now_dt.replace(
            hour=time_obj.hour,
            minute=time_obj.minute,
            second=time_obj.second,
            microsecond=0
        )