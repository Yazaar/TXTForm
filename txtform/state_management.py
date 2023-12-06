import json, datetime, asyncio
import objects, database, helper

class SmartCache():
    def __init__(self):
        self.__cache = {}

    async def store(self, cache_key, cache_value, timeout_s : int):
        self.__cache[cache_key] = cache_value
        await self.release(cache_key,  timeout_s)

    async def release(self, cache_key, timeout_s : int):
        loop = asyncio.get_event_loop()
        loop.create_task(self.release_blocking(cache_key,  timeout_s))

    async def release_blocking(self, cache_key, timeout_s : int):
        await asyncio.sleep(timeout_s)
        self.release_execute(cache_key)

    def release_execute(self, cache_key):
        if cache_key in self.__cache: del self.__cache[cache_key]

    def get(self, cache_key):
        return self.__cache.get(cache_key, None)

class StateManagement():
    def __init__(self, db : database.Database, spotify_basic : str):
        self.__db = db
        self.__spotify_basic = spotify_basic
        self.__spotify_cache = SmartCache()
        self.__spotify_accounts_cache = SmartCache()

    async def get_first_active_state(self, states : list[objects.FlowState]):
        for state in states:
            if state.flow_type == 'always':
                return state
            if state.flow_type == 'twitchLive':
                is_live = await self.__twitch_is_live(objects.Login(state.login_id, None, None, None), state.variables.get('twitch_id', None))
                if is_live: return state
        return None

    async def get_state_text_response(self, state : objects.FlowState):
        if not state.response_id: return ''
        release_spotify_ids = set()
        text_resp = ''
        response_components = await self.__db.get_response_components(objects.Response(state.response_id, None, state.login_id))
        simulated_login = objects.Login(state.login_id, None, None, None)
        for response_component in  response_components:
            if response_component.resp_type == 'text':
                text_resp += response_component.variables.get('text', '')
            elif response_component.resp_type in 'spotifyCurrentSong':
                spotify_id = response_component.variables.get('spotify_id', None)
                if isinstance(spotify_id, int):
                    current_song = await self.__spotify_current_song(simulated_login, spotify_id)
                    release_spotify_ids.add(spotify_id)
                    if isinstance(current_song, str):
                        text_resp += current_song
            elif response_component.resp_type == 'spotifyCurrentArtist':
                spotify_id = response_component.variables.get('spotify_id', None)
                if isinstance(spotify_id, int):
                    current_artist = await self.__spotify_current_artist(simulated_login, spotify_id)
                    release_spotify_ids.add(spotify_id)
                    if isinstance(current_artist, str):
                        text_resp += current_artist
        for i in release_spotify_ids:
            await self.__spotify_cache.release(i, 5)
        return text_resp

    async def __twitch_is_live(self, login : objects.Login, twitch_id : int | None):
        if not isinstance(twitch_id, int): return False
        twitch_accounts = await self.__db.get_twitch_accounts_by_login(login)
        twitch_account = helper.find_by_key('id', twitch_id, twitch_accounts)
        if not twitch_account: return False
        return twitch_account.is_live

    async def __spotify_current_artist(self, login : objects.Login, spotify_id : int | None):
        current_song, current_artists = await self.__spotify_api_load_song_data(login, spotify_id)
        return helper.linked_string(current_artists, ', ', ' & ') if isinstance(current_artists, list) else ''

    async def __spotify_current_song(self, login : objects.Login, spotify_id : int | None):
        current_song, current_artists = await self.__spotify_api_load_song_data(login, spotify_id)
        return current_song if isinstance(current_song, str) else ''

    async def __spotify_api_load_song_data(self, login : objects.Login, spotify_id : int | None):
        cache_data = self.__spotify_cache.get(spotify_id)
        if isinstance(cache_data, dict) and isinstance(cache_data['current_song'], str) and isinstance(cache_data['current_artists'], list):
            return cache_data['current_song'], cache_data['current_artists']
        spotify_accounts = self.__spotify_accounts_cache.get(login.id)
        if spotify_accounts is None:
            spotify_accounts = await self.__db.get_spotify_accounts_by_login(login)
            await self.__spotify_accounts_cache.store(login.id, spotify_accounts, 10)
        spotify_match = helper.find_by_key('id', spotify_id, spotify_accounts)
        if not isinstance(spotify_match, objects.Spotify): return None, None

        data = await self.__spotify_api_fetch(spotify_match)
        if not isinstance(data, dict): return None, None

        track_info = data.get('item', None)
        if not isinstance(track_info, dict): return None, None
        artists = track_info.get('artists', None)
        parsed_artists = []
        if not isinstance(artists, list): return None, None
        for i in artists:
            if not isinstance(i, dict): return  None, None
            artist_name = i.get('name', None)
            if not isinstance(artist_name, str): return None, None
            parsed_artists.append(artist_name)

        track_name = track_info.get('name', None)
        if not isinstance(track_name, str): return None, None
        await self.__spotify_cache.store(spotify_id, {'current_song': track_name, 'current_artists': parsed_artists}, 60)
        return track_name, parsed_artists

    async def __spotify_api_fetch(self, spotify : objects.Spotify, *, _looped = False):
        try:
            resp = await helper.http_request('get', 'https://api.spotify.com/v1/me/player/currently-playing', headers={
                'Authorization': f'Bearer {spotify.access_token}'
            })
            data = json.loads(resp)

            if 'error' in data and data['error']['status'] == 401:
                # invalid token
                if data['error']['status'] == 401 and not _looped:
                    updated_account = await self.__spotify_api_refresh(spotify)
                    if not updated_account: return None
                    resp = await self.__spotify_api_fetch(updated_account, _looped=True)
                    return resp
                return None
            return data
        except Exception: return None

    async def __spotify_api_refresh(self, spotify : objects.Spotify):
        try:
            resp = await helper.http_request('post', 'https://accounts.spotify.com/api/token',
                headers={
                    'content-type': 'application/x-www-form-urlencoded',
                    'Authorization': f'Basic {self.__spotify_basic}'
                },
                data={
                    'grant_type': 'refresh_token',
                    'refresh_token': spotify.refresh_token
                }
            )
            data = json.loads(resp)
        except Exception: return None

        if not isinstance(data, dict): return None

        access_token = data.get('access_token', None)
        refresh_token = data.get('refresh_token', None)
        scope = data.get('scope', None)
        expires_in = data.get('expires_in', None)

        if not isinstance(access_token, str): return None
        if not isinstance(refresh_token, str): refresh_token = spotify.refresh_token
        if not isinstance(scope, str): return None
        if not isinstance(expires_in, int): return None

        validity = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=expires_in)
        scopes = scope.split(' ')

        updated_account = await self.__db.update_spotify_tokens(spotify, access_token, refresh_token, scopes, validity)
        spotify.access_token = updated_account.access_token
        spotify.refresh_token = updated_account.refresh_token
        spotify.scopes = updated_account.scopes
        spotify.validity = updated_account.validity
        return updated_account
    
    async def test_spotify_tokens(self, spotify : objects.Spotify):
        fetched_data = await self.__spotify_api_fetch(spotify)
        return spotify