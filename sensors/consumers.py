import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer


class FireAlertConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        self.station_id = self.scope["url_route"]["kwargs"]["station_id"]

        # Call the database helper and wait for the result
        is_allowed = await self.check_station_access(user, self.station_id)

        if is_allowed:
            # 1. Join specific station group
            self.group_name = f"station_{self.station_id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            
            # 2. Join the global alerts group (Crucial for Gas Leaks / Warnings!)
            await self.channel_layer.group_add("station_all", self.channel_name)
            
            await self.accept()
            print(f"✅ WebSocket Connected: Station {self.station_id} & Global Channel")
        else:
            print(f"❌ WebSocket Denied: User not authorized for Station {self.station_id}")
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
        # Always discard from the global group upon disconnect
        await self.channel_layer.group_discard("station_all", self.channel_name)

    # Receive message from group (Triggered by Views)
    async def fire_alert(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "fire_alert",
                    # Safely extract variables using .get() to prevent crashes
                    "report_id": event.get("report_id"),
                    "alert_type": event.get("alert_type", "Fire"), # Default to 'Fire' if missing
                    "address": event.get("address", "Unknown Address"),
                    "owner_name": event.get("owner_name", "Unknown Owner"),
                    "owner_phone": event.get("owner_phone", "No Phone"),
                    "lat": event.get("lat", 0.0),
                    "lng": event.get("lng", 0.0),
                    "timestamp": event.get("timestamp", ""),
                }
            )
        )