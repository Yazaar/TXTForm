import asyncio, json, datetime, time, secrets
import psycopg
import objects, helper

class DB_CONNECT_ERROR(Exception): pass

class Database:
    def __init__(self, connectionStr : str):
        self.__connectionStr = connectionStr
        self.__adb : psycopg.AsyncConnection = None
        self.__tryReconnectLock = asyncio.Lock()

    async def startup(self):
        if self.__adb is None or self.__adb.closed:
            errorMsg = ''
            try: self.__adb = await psycopg.AsyncConnection.connect(self.__connectionStr)
            except Exception as e:
                self.__adb = None
                errorMsg = ' ' + e.args[0]
            if self.__adb is None or self.__adb.closed: raise DB_CONNECT_ERROR('[DB] ERROR' + errorMsg)
            print('[DB] Connected')
            await self.__create_database()

    async def __tryReconnect(self):
        if self.__tryReconnectLock.locked():
            async with self.__tryReconnectLock:
                 if self.__adb is None or self.__adb.closed: raise SystemExit
                 return
        async with self.__tryReconnectLock:
            loop = asyncio.get_event_loop()
            loop.create_task(self.__tryReconnect())
            tries = 1
            while True:
                try:
                    print(f'Reconnect try {tries}')
                    await self.startup()
                    break
                except DB_CONNECT_ERROR as e:
                    print(f'Failed reconnect {tries}: {e.args[0]}')
                    if tries == 7: raise SystemError('[DB] Failed reaching database')
                    tries += 1
                    await asyncio.sleep(10)

    async def __create_database(self):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('''CREATE TABLE IF NOT EXISTS login(
                                id BIGSERIAL PRIMARY KEY,
                                username TEXT NOT NULL,
                                primary_account_src TEXT NOT NULL,
                                primary_account_id BIGINT NOT NULL
                                )''')
                await c.execute('''CREATE TABLE IF NOT EXISTS login_session(
                                id INT,
                                login_id BIGINT NOT NULL,
                                session_token TEXT NOT NULL,
                                validity TIMESTAMP NOT NULL,
                                CONSTRAINT fk_login FOREIGN KEY(login_id) REFERENCES login(id),
                                PRIMARY KEY(login_id, id)
                                )''')
                await c.execute('''CREATE TABLE IF NOT EXISTS twitch_account(
                                id INT,
                                login_id BIGINT NOT NULL,
                                label TEXT NOT NULL,
                                user_id BIGINT NOT NULL,
                                username TEXT NOT NULL,
                                display_name TEXT NOT NULL,
                                is_live BOOLEAN NOT NULL,
                                access_token TEXT NOT NULL,
                                refresh_token TEXT NOT NULL,
                                scopes JSONB NOT NULL,
                                validity TIMESTAMP NOT NULL,
                                CONSTRAINT fk_login FOREIGN KEY(login_id) REFERENCES login(id),
                                PRIMARY KEY(login_id, id)
                                )''')
                await c.execute('''CREATE TABLE IF NOT EXISTS spotify_account(
                                id INT,
                                login_id BIGINT NOT NULL,
                                label TEXT NOT NULL,
                                user_id TEXT NOT NULL,
                                access_token TEXT NOT NULL,
                                refresh_token TEXT NOT NULL,
                                scopes JSONB NOT NULL,
                                validity TIMESTAMP NOT NULL,
                                CONSTRAINT fk_login FOREIGN KEY(login_id) REFERENCES login(id),
                                PRIMARY KEY(login_id, id)
                                )''')
                await c.execute('''CREATE TABLE IF NOT EXISTS response(
                                id INT,
                                label TEXT NOT NULL,
                                login_id BIGINT NOT NULL,
                                CONSTRAINT fk_login FOREIGN KEY(login_id) REFERENCES login(id),
                                PRIMARY KEY(login_id, id)
                                )''')
                await c.execute('''CREATE TABLE IF NOT EXISTS response_component(
                                id INT,
                                response_id INT NOT NULL,
                                login_id BIGINT NOT NULL,
                                resp_type TEXT NOT NULL,
                                variables JSONB NOT NULL,
                                CONSTRAINT fk_login FOREIGN KEY(login_id) REFERENCES login(id),
                                CONSTRAINT fk_response FOREIGN KEY(response_id, login_id) REFERENCES response(id, login_id),
                                PRIMARY KEY(login_id, response_id, id)
                                )''')
                await c.execute('''CREATE TABLE IF NOT EXISTS flow(
                                id INT,
                                label TEXT NOT NULL,
                                login_id BIGINT NOT NULL,
                                enabled BOOLEAN NOT NULL DEFAULT True,
                                CONSTRAINT fk_login FOREIGN KEY(login_id) REFERENCES login(id),
                                PRIMARY KEY(login_id, id)
                                )''')
                await c.execute('''CREATE TABLE IF NOT EXISTS flow_state(
                                id INT,
                                flow_id INT NOT NULL,
                                login_id BIGINT NOT NULL,
                                response_id INT,
                                flow_type TEXT,
                                variables JSONB NOT NULL,
                                CONSTRAINT fk_login FOREIGN KEY(login_id) REFERENCES login(id),
                                CONSTRAINT fk_flow FOREIGN KEY(flow_id, login_id) REFERENCES flow(id, login_id),
                                CONSTRAINT fk_response FOREIGN KEY(response_id, login_id) REFERENCES response(id, login_id),
                                PRIMARY KEY(login_id, flow_id, id)
                                )''')
                await c.execute('''CREATE TABLE IF NOT EXISTS token(
                                token_name TEXT PRIMARY KEY,
                                token_value TEXT NOT NULL,
                                validity TIMESTAMP NOT NULL
                                )''')
                await self.__adb.commit()
                await c.close()
                return
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def get_taken_usernames(self, username : str):
        parsed_username = helper.strip_string(username, helper.BASE_CHARS)
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('SELECT username FROM login WHERE username ~ %s', (f'^{parsed_username}\d*$',))
                data = await c.fetchall()
                await c.close()
                return [i[0] for i in data]
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def register_login(self, username : str, primary_account_src : str, primary_account_id : int):
        account = await self.get_login(primary_account_src, primary_account_id)
        if account: return account

        parsed_username = helper.strip_string(username, helper.BASE_CHARS)
        if len(parsed_username) == 0: parsed_username = helper.generate_string(7)
        taken_usernames = await self.get_taken_usernames(parsed_username)
        unique_username = helper.unique_string(parsed_username, taken_usernames)
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('INSERT INTO login(username, primary_account_src, primary_account_id) VALUES(%s, %s, %s) RETURNING id', (username, primary_account_src, primary_account_id))
                last_id = await c.fetchone()
                await self.__adb.commit()
                await c.close()
                return objects.Login(last_id[0], unique_username, None, None)
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def get_login(self, platform : str, account_id : int):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('SELECT id, username, primary_account_src, primary_account_id FROM login WHERE primary_account_src = %s AND primary_account_id = %s LIMIT 1', (platform, account_id))
                data = await c.fetchone()
                await c.close()
                return None if data is None else objects.Login(data[0], data[1], data[2], data[3])
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def get_login_by_username(self, username : str):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('SELECT id, username, primary_account_src, primary_account_id FROM login WHERE username ILIKE %s LIMIT 1', (username,))
                data = await c.fetchone()
                await c.close()
                return None if data is None else objects.Login(data[0], data[1], data[2], data[3])
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def get_login_by_id(self, _id : int):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('SELECT id, username, primary_account_src, primary_account_id FROM login WHERE id = %s LIMIT 1', (_id,))
                data = await c.fetchone()
                await c.close()
                return None if data is None else objects.Login(data[0], data[1], data[2], data[3])
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def update_username(self, login : objects.Login, username : str):
        parsed_username = helper.strip_string(username, helper.BASE_CHARS)
        taken_usernames = await self.get_taken_usernames(parsed_username)
        unique_username = helper.unique_string(parsed_username, taken_usernames)
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('UPDATE login SET username = %s WHERE id = %s', (unique_username, login.id))
                await self.__adb.commit()
                await c.close()
                return objects.Login(login.id, unique_username, login.primary_account_src, login.primary_account_id)
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def create_login_session(self, login : objects.Login):
        while True:
            try:
                new_session_token = f'{login.id}x{secrets.token_hex(20)}'
                validity = datetime.datetime.utcnow() + datetime.timedelta(days=30)
                c = self.__adb.cursor()
                await c.execute('''INSERT INTO login_session(id, login_id, session_token, validity)
                                SELECT COALESCE(MAX(id)+1, 1), %s, %s, %s FROM login_session WHERE login_id = %s RETURNING id''', (login.id, new_session_token, validity, login.id))
                last_id = await c.fetchone()
                await self.__adb.commit()
                await c.close()
                return objects.Login_Session(last_id[0], login.id, new_session_token, validity)
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def delete_login_session(self, session_token : str):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('DELETE FROM login_session WHERE session_token = %s', (session_token,))
                await self.__adb.commit()
                await c.close()
                return
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def get_login_by_session(self, session_token : str):
        if session_token is None: return None
        while True:
            try:
                c = self.__adb.cursor()
                ts = datetime.datetime.utcnow()
                await c.execute('''SELECT login.id, login.username, login.primary_account_src, login.primary_account_id, login_session.validity, login_session.id FROM login
                                   LEFT JOIN login_session
                                   ON login_session.login_id = login.id
                                   WHERE login_session.session_token = %s AND login_session.validity > %s
                                   LIMIT 1
                                ''', (session_token, ts))
                data = await c.fetchone()
                update_at_time = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
                update_to_time = update_at_time + datetime.timedelta(hours=3)
                if update_at_time > data[4]:
                    await c.execute('UPDATE login_session SET validity = %s WHERE id = %s', (update_to_time, data[5]))
                    await self.__adb.commit()
                await c.close()
                return objects.Login(data[0], data[1], data[2], data[3]) if data is not None else None
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def bind_primary_account(self, login : objects.Login, primary_account_src : str, primary_account_id : int):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('UPDATE login SET primary_account_src = %s, primary_account_id = %s WHERE id = %s', (login.id, primary_account_src, primary_account_id))
                await self.__adb.commit()
                await c.close()
                login.primary_account_src = primary_account_src
                login.primary_account_id = primary_account_id
                return login
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def get_twitch_accounts_by_login(self, login : objects.Login):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('SELECT id, login_id, label, user_id, username, display_name, is_live, access_token, refresh_token, scopes, validity FROM twitch_account WHERE login_id = %s', (login.id, ))
                data = await c.fetchall()
                await c.close()
                return [objects.Twitch(i[0], i[1], i[2], i[3], i[4], i[5], i[6], i[7], i[8], i[9], i[10]) for i in data]
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def get_twitch_accounts_by_user_id(self, user_id : int):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('SELECT id, login_id, label, user_id, username, display_name, is_live, access_token, refresh_token, scopes, validity FROM twitch_account WHERE user_id = %s', (user_id, ))
                data = await c.fetchall()
                await c.close()
                return [objects.Twitch(i[0], i[1], i[2], i[3], i[4], i[5], i[6], i[7], i[8], i[9], i[10]) for i in data]
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def update_twitch_account_live_status_by_uid(self, live_state : bool, user_id : int):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('UPDATE twitch_account SET is_live = %s WHERE user_id = %s', (live_state, user_id))
                await c.close()
                await self.__adb.commit()
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def add_twitch_account(self, login : objects.Login, user_id : int, username : str, display_name : str, is_live : bool, access_token : str, refresh_token : str, scopes : list[str], validity : datetime.datetime):
        accounts = await self.get_twitch_accounts_by_login(login)
        match = helper.find_by_key('user_id', user_id, accounts)
        if match: return match

        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('''INSERT INTO twitch_account(id, login_id, label, user_id, username, display_name, is_live, access_token, refresh_token, scopes, validity)
                                SELECT COALESCE(MAX(id)+1, 1), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s FROM twitch_account WHERE login_id = %s RETURNING id''',
                                (login.id, username, user_id, username, display_name, is_live, access_token, refresh_token, json.dumps(scopes), validity, login.id))
                last_id = await c.fetchone()
                await self.__adb.commit()
                await c.close()
                return objects.Twitch(last_id[0], login.id, username, user_id, username, display_name, is_live, access_token, refresh_token, scopes, validity)
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def get_spotify_accounts_by_login(self, login : objects.Login):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('SELECT id, label, login_id, user_id, access_token, refresh_token, scopes, validity FROM spotify_account WHERE login_id = %s',
                                (login.id,))
                accounts = await c.fetchall()
                await c.close()
                return [objects.Spotify(data[0], data[1], data[2], data[3], data[4], data[5], data[6], data[7]) for data in accounts]
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def add_spotify_account(self, login : objects.Login, label : str | None, user_id : str, access_token : str, refresh_token : str, scopes : list[str], validity : datetime.datetime):
        accounts = await self.get_spotify_accounts_by_login(login)
        match = helper.find_by_key('user_id', user_id, accounts)
        if match: return match

        while True:
            try:
                if label is None: label = str(int(time.time()))
                c = self.__adb.cursor()
                await c.execute('''INSERT INTO spotify_account(id, label, login_id, user_id, access_token, refresh_token, scopes, validity)
                                SELECT COALESCE(MAX(id)+1, 1), %s, %s, %s, %s, %s, %s, %s FROM spotify_account WHERE login_id = %s RETURNING id''',
                                (label, login.id, user_id, access_token, refresh_token, json.dumps(scopes), validity, login.id))
                last_id = await c.fetchone()
                await self.__adb.commit()
                await c.close()
                return objects.Spotify(last_id, label, login.id, user_id, access_token, refresh_token, scopes, validity)
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def update_spotify_tokens(self, spotify_account : objects.Spotify, access_token : str, refresh_token : str, scopes : list[str], validity : datetime.datetime):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('UPDATE spotify_account SET access_token = %s, refresh_token = %s, scopes = %s, validity = %s WHERE login_id = %s AND id = %s', (access_token, refresh_token, json.dumps(scopes), validity, spotify_account.login_id, spotify_account.id))
                await self.__adb.commit()
                await c.close()
                return objects.Spotify(spotify_account.id, spotify_account.label, spotify_account.login_id, spotify_account.user_id, access_token, refresh_token, scopes, validity)
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def remove_spotify_account(self, spotify_account : objects.Spotify):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('DELETE FROM spotify_account WHERE login_id = %s AND id = %s', (spotify_account.login_id, spotify_account.id))
                await self.__adb.commit()
                await c.close()
                return
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def get_all_login_responses(self, login : objects.Login):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('SELECT id, label, login_id FROM response WHERE login_id = %s', (login.id,))
                data = await c.fetchall()
                await c.close()
                return [objects.Response(i[0], i[1], i[2]) for i in data]
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def create_empty_response(self, login : objects.Login, resp_name : str):
        resps = await self.get_all_login_responses(login)
        names = [i.label for i in resps]
        unique_name = helper.unique_string(resp_name, names)
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('''
                                INSERT INTO response(id, label, login_id)
                                SELECT COALESCE(MAX(id)+1, 1), %s, %s FROM response WHERE login_id = %s RETURNING id
                                ''', (unique_name, login.id, login.id))
                last_id = await c.fetchone()
                await self.__adb.commit()
                await c.close()
                return objects.Response(last_id[0], unique_name, login.id)
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def delete_response(self, response : objects.Response):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('UPDATE flow_state SET response_id = NULL WHERE response_id = %s AND login_id = %s', (response.id, response.login_id))
                await c.execute('DELETE FROM response_component WHERE response_id = %s AND login_id = %s', (response.id, response.login_id))
                await c.execute('DELETE FROM response WHERE login_id = %s AND id = %s', (response.login_id, response.id))
                await self.__adb.commit()
                await c.close()
                return
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def update_response_label(self, response : objects.Response, label : str):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('SELECT id FROM response WHERE login_id = %s AND label ILIKE %s LIMIT 1', (response.login_id, label))
                data = await c.fetchone()
                if data is not None: return
                await c.execute('UPDATE response SET label = %s WHERE login_id = %s AND id = %s', (label, response.login_id, response.id))
                await self.__adb.commit()
                await c.close()
                return
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def set_response_components(self, response : objects.Response, components : list):
        while True:
            try:
                c = self.__adb.cursor()
                insert_str = 'INSERT INTO response_component(id, response_id, login_id, resp_type, variables) VALUES (%s, %s, %s, %s, %s)'
                sql_data = [('DELETE FROM response_component WHERE response_id = %s AND login_id = %s', (response.id, response.login_id))]
                for index, i in enumerate(components):
                    sql_data.append((insert_str, (index+1, response.id, response.login_id, i['type'], json.dumps(i['values']))))
                sql_str = self.__mogrify_sql(sql_data)
                await c.execute(sql_str)
                await self.__adb.commit()
                await c.close()
                return
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def get_response_components(self, response : objects.Response):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('SELECT id, response_id, login_id, resp_type, variables FROM response_component WHERE response_id = %s AND login_id = %s',
                                (response.id, response.login_id))
                data = await c.fetchall()
                await c.close()
                return [objects.ResponseComponent(i[0], i[1], i[2], i[3], i[4]) for i in data]
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def get_all_login_flows(self, login : objects.Login):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('SELECT id, label, login_id, enabled FROM flow WHERE login_id = %s', (login.id,))
                data = await c.fetchall()
                await c.close()
                return [objects.Flow(i[0], i[1], i[2], i[3]) for i in data]
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def get_flow_states(self, flow : objects.Flow):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('SELECT id, flow_id, login_id, response_id, flow_type, variables FROM flow_state WHERE flow_id = %s AND login_id = %s', (flow.id, flow.login_id,))
                data = await c.fetchall()
                await c.close()
                return [objects.FlowState(i[0], i[1], i[2], i[3], i[4], i[5]) for i in data]
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def toggle_flow(self, flow : objects.Flow, enabled : bool):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('UPDATE flow SET enabled = %s WHERE id = %s AND login_id = %s', (enabled, flow.id, flow.login_id,))
                await self.__adb.commit()
                await c.close()
                return
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def update_flow_label(self, flow : objects.Flow, label : str):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('UPDATE flow SET label = %s WHERE id = %s AND login_id = %s', (label, flow.id, flow.login_id,))
                await self.__adb.commit()
                await c.close()
                return
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def set_flow_states(self, flow : objects.Flow, states : list):
        while True:
            try:
                c = self.__adb.cursor()
                insert_str = 'INSERT INTO flow_state(id, flow_id, login_id, response_id, flow_type, variables) VALUES (%s, %s, %s, %s, %s, %s)'
                sql_data = [('DELETE FROM flow_state WHERE flow_id = %s AND login_id = %s', (flow.id, flow.login_id))]
                for index, i in enumerate(states):
                    sql_data.append((insert_str, (index+1, flow.id, flow.login_id, i['response_id'], i['condition'], json.dumps(i['values']))))
                sql_str = self.__mogrify_sql(sql_data)
                await c.execute(sql_str)
                await self.__adb.commit()
                await c.close()
                return
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def delete_flow(self, flow : objects.Flow):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('DELETE FROM flow_state WHERE flow_id = %s AND login_id = %s', (flow.id, flow.login_id))
                await c.execute('DELETE FROM flow WHERE login_id = %s AND id = %s', (flow.login_id, flow.id))
                await self.__adb.commit()
                await c.close()
                return
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def create_empty_flow(self, login : objects.Login, resp_name : str):
        resps = await self.get_all_login_flows(login)
        names = [i.label for i in resps]
        unique_name = helper.unique_string(resp_name, names)
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('''
                                INSERT INTO flow(id, label, login_id)
                                SELECT COALESCE(MAX(id)+1, 1), %s, %s FROM flow WHERE login_id = %s RETURNING id
                                ''', (unique_name, login.id, login.id))
                last_id = await c.fetchone()
                await self.__adb.commit()
                await c.close()
                return objects.Flow(last_id[0], unique_name, login.id, True)
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def get_token(self, token_name : str):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('SELECT token_name, token_value, validity FROM token WHERE token_name = %s LIMIT 1', (token_name,))
                data = await c.fetchone()
                await c.close()
                return None if not data else objects.Token(data[0], data[1], data[2])
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def set_token(self, token_name : str, token_value : str, validity : datetime.datetime):
        found_token = await self.get_token(token_name)
        if found_token:
            found_token = await self.edit_token(found_token, token_value, validity)
            return found_token
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('INSERT INTO token(token_name, token_value, validity) VALUES(%s, %s, %s)', (token_name, token_value, validity))
                await c.close()
                return objects.Token(token_name, token_value, validity)
            except psycopg.OperationalError:
                await self.__tryReconnect()

    async def edit_token(self, token_name : str, token_value : str, validity : datetime.datetime):
        while True:
            try:
                c = self.__adb.cursor()
                await c.execute('UPDATE token SET token_value = %s, validity = %s WHERE token_name = %s', (token_value, validity, token_name))
                await c.close()
                return objects.Token(token_name, token_value, validity)
            except psycopg.OperationalError:
                await self.__tryReconnect()

    def __mogrify_sql(self, data : list[tuple[str, tuple]]):
        cc = psycopg.ClientCursor(self.__adb)
        resp = ''
        for i in data: resp += cc.mogrify(i[0], i[1]) + ';'
        cc.close()
        return resp
