import json
from channels.generic.websocket import AsyncWebsocketConsumer

class FireAlertConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.station_id = self.scope['url_route']['kwargs']['station_id']
        self.group_name = f'station_{self.station_id}'

        # Join station group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    # Receive message from group (Triggered by Views)
    async def fire_alert(self, event):
        await self.send(text_data=json.dumps({
            'type': 'fire_alert',
            'report_id': event['report_id'],
            'address': event['address'],
            'owner_name': event['owner_name'],
            'owner_phone': event['owner_phone'],
            'lat': event['lat'],
            'lng': event['lng'],
            'timestamp': event['timestamp']
        }))