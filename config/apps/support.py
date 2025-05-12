from datetime import datetime
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

    def dev_log(self, msg, args=None):
        if self.dev_logs:
            if args is None:
                self.log(f"--> {msg}")
            else:
                self.log(f"--> {msg}: {args}")