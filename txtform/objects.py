import datetime

class Login():
    def __init__(self, _id : int, username : str, primary_account_src : str, primary_account_id : int):
        self.__id = _id
        self.username = username
        self.primary_account_src = primary_account_src
        self.primary_account_id = primary_account_id

    @property
    def id(self): return self.__id

class Login_Session():
    def __init__(self, _id : int, user_id : int, session_token : str, validity : datetime.datetime):
        self.__id = _id
        self.user_id = user_id
        self.session_token = session_token
        self.validity = validity.replace(tzinfo=datetime.UTC)

    @property
    def id(self): return self.__id

class Twitch():
    def __init__(self, _id : int, login_id : int, label : str, user_id : int, username : str, display_name : str, is_live : bool, access_token : str, refresh_token : str, scopes : list[str], validity : datetime.datetime):
        self.__id = _id
        self.label = label
        self.login_id = login_id
        self.user_id = user_id
        self.username = username
        self.display_name = display_name
        self.is_live = is_live
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.scopes = scopes
        self.validity = validity.replace(tzinfo=datetime.UTC)

    @property
    def id(self): return self.__id

class Spotify():
    def __init__(self, _id : int, label : str, login_id : int, user_id : str, access_token : str, refresh_token : str, scopes : list[str], validity : datetime.datetime, id_token : str):
        self.__id = _id
        self.label = label
        self.login_id = login_id
        self.user_id = user_id
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.scopes = scopes
        self.validity = validity.replace(tzinfo=datetime.UTC)
        self.id_token = id_token

    @property
    def id(self): return self.__id

class Response:
    def __init__(self, _id : int, label : str, login_id : int):
        self.__id = _id
        self.label = label
        self.login_id = login_id

    @property
    def id(self): return self.__id

class ResponseComponent:
    def __init__(self, _id : int, response_id : int, login_id : int, resp_type : str, variables : dict):
        self.__id = _id
        self.response_id = response_id
        self.login_id = login_id
        self.resp_type = resp_type
        self.variables = variables

    @property
    def id(self): return self.__id

class Flow:
    def __init__(self, _id : int, label : str, login_id : int, enabled : bool):
        self.__id = _id
        self.label = label
        self.login_id = login_id
        self.enabled = enabled

    @property
    def id(self): return self.__id

class FlowState:
    def __init__(self, _id : int, flow_id : int, login_id : int, response_id : int, flow_type : str | None, variables : dict):
        self.__id = _id
        self.flow_id = flow_id
        self.login_id = login_id
        self.response_id = response_id
        self.flow_type = flow_type
        self.variables = variables

    @property
    def id(self): return self.__id

class Token():
    def __init__(self, token_name : str, token_value : str, validity : datetime.datetime):
        self.__token_name = token_name
        self.token_value = token_value
        self.validity = validity.replace(tzinfo=datetime.UTC)

    @property
    def id(self): return self.__token_name

    @property
    def token_name(self): return self.__token_name