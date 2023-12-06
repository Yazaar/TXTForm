import json, datetime
import database, helper

class TwitchWebhookManager():
    def __init__(self, db : database.Database, url : str, hook_secret : str, twitch_client_id : str, twitch_client_secret : str):
        self.__db = db
        self.__url = url
        self.__hook_secret = hook_secret
        self.__twitch_app_token = None
        self.__twitch_client_id = twitch_client_id
        self.__twitch_client_secret = twitch_client_secret

    async def startup(self):
        self.__twitch_app_token = await self.__db.get_token('twitch_app')
        if self.__twitch_app_token is None:
            await self.__new_app_token()

    async def __new_app_token(self):
        try:
            resp = await helper.http_request('post', 'https://id.twitch.tv/oauth2/token', data = {
                'client_id': self.__twitch_client_id,
                'client_secret': self.__twitch_client_secret,
                'grant_type': 'client_credentials'
            })
        except Exception: return None

        try: data = json.loads(resp)
        except Exception: return None

        if (not isinstance(data, dict) or not 'access_token' in data or not 'expires_in' in data
            or not isinstance(data['access_token'], str) or not isinstance(data['expires_in'], int)): return None

        validity = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=data['expires_in'])
        self.__twitch_app_token = await self.__db.set_token('twitch_app', data['access_token'], validity)

    async def listen(self, channel_id : int):
        if not self.__twitch_app_token or not self.__url.startswith('https://'): return False
        channel_id_str = str(channel_id)

        try:
            await helper.http_request('post', 'https://api.twitch.tv/helix/eventsub/subscriptions',
                data = json.dumps({
                    'type': 'stream.online',
                    'version': '1',
                    'condition': {'broadcaster_user_id': channel_id_str},
                    'transport': {
                        'method': 'webhook',
                        'callback': self.__url,
                        'secret': self.__hook_secret
                    }
                }),
                headers={
                    'Client-Id': self.__twitch_client_id,
                    'Authorization': f'Bearer {self.__twitch_app_token.token_value}',
                    'Content-Type': 'application/json'
                }
            )
        except Exception: return False
        try:
            await helper.http_request('post', 'https://api.twitch.tv/helix/eventsub/subscriptions',
                data = json.dumps({
                    'type': 'stream.offline',
                    'version': '1',
                    'condition': {'broadcaster_user_id': channel_id_str},
                    'transport': {
                        'method': 'webhook',
                        'callback': self.__url,
                        'secret': self.__hook_secret
                    }
                }),
                headers={
                    'Client-Id': self.__twitch_client_id,
                    'Authorization': f'Bearer {self.__twitch_app_token.token_value}',
                    'Content-Type': 'application/json'
                }
            )
        except Exception: return False
        return True