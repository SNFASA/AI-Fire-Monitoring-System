import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class FireAlertConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        self.station_id = self.scope["url_route"]["kwargs"]["station_id"]

        # Call the database helper and wait for the result
        is_allowed = await self.check_station_access(user, self.station_id)

        if is_allowed:
            self.group_name = f"station_{self.station_id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            print(f"✅ WebSocket Connected: Station {self.station_id}")
        else:
            print(
                f"❌ WebSocket Denied: User not authorized for Station {self.station_id}"
            )
            await self.close()

    # This wrapper allows async consumers to talk to the sync database safely
    @database_sync_to_async
    def check_station_access(self, user, station_id):
        if not user.is_authenticated:
            return False
        try:
            # Inside here, accessing related models like .userprofile is allowed
            return str(user.userprofile.station.id) == str(station_id)
        except Exception:
            return False

    async def disconnect(self, close_code):
        # Only discard if the group_name was successfully created
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # Receive message from group (Triggered by Views)
    async def fire_alert(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "fire_alert",
                    "report_id": event["report_id"],
                    "address": event["address"],
                    "owner_name": event["owner_name"],
                    "owner_phone": event["owner_phone"],
                    "lat": event["lat"],
                    "lng": event["lng"],
                    "timestamp": event["timestamp"],
                }
            )
        )
