import asyncio, base64, json, os, sys, datetime, re, hmac, hashlib
import jinja2
from pathlib import Path
from aiohttp import web
import helper, database, state_management, twitch_webhooks, objects
from vendor.StructGuard import StructGuard

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

APP_FOLDER = Path(__file__).parent
ACCOUNTS_DIR = APP_FOLDER / 'accounts'
WEB_FOLDER = APP_FOLDER / 'web'
STATIC_FOLDER = (WEB_FOLDER / 'static').resolve()

SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', None)
SPOTIFY_SECRET = os.environ.get('SPOTIFY_SECRET', None)
SPOTIFY_SCOPES = os.environ.get('SPOTIFY_SCOPES', None)
SPOTIFY_REDIRECT = os.environ.get('SPOTIFY_REDIRECT', None)

TWITCH_CLIENT_ID = os.environ.get('TWITCH_CLIENT_ID', None)
TWITCH_SECRET = os.environ.get('TWITCH_SECRET', None)
TWITCH_SCOPES = os.environ.get('TWITCH_SCOPES', None)
TWITCH_REDIRECT = os.environ.get('TWITCH_REDIRECT', None)

POSTGRES_CONNECTION_STRING = os.environ.get('POSTGRES_CONNECTION_STRING', None)

TWITCH_WEBHOOK_SECRET = os.environ.get('TWITCH_WEBHOOK_SECRET', None)
WEBHOOK_HOST = os.environ.get('WEBHOOK_HOST', None)

try: WEB_PORT = int(os.environ.get('WEB_PORT', None))
except Exception: WEB_PORT = None

if (SPOTIFY_CLIENT_ID is None or SPOTIFY_SECRET is None or SPOTIFY_SCOPES is None or SPOTIFY_REDIRECT is None or
    TWITCH_CLIENT_ID is None or TWITCH_SECRET is None or TWITCH_REDIRECT is None or TWITCH_SCOPES is None or
    POSTGRES_CONNECTION_STRING is None or WEB_PORT is None or TWITCH_WEBHOOK_SECRET is None or WEBHOOK_HOST is None):
    raise SystemError('Please add the required environment variables')

SPOTIFY_SCOPES_ENCODED = helper.url_encode(SPOTIFY_SCOPES)
SPOTIFY_REDIRECT_ENCODED = helper.url_encode(SPOTIFY_REDIRECT)
SPOTIFY_SECRET_BASE64 = base64.b64encode((SPOTIFY_CLIENT_ID + ':' + SPOTIFY_SECRET).encode('utf-8')).decode()
TWITCH_REDIRECT_ENCODED = helper.url_encode(TWITCH_REDIRECT)
TWITCH_SCOPES_ENCODED = helper.url_encode(TWITCH_SCOPES)
TWITCH_WEBHOOK_SECRET_ENCODED = TWITCH_WEBHOOK_SECRET.encode('utf-8')

j2 = jinja2.Environment(loader=jinja2.FileSystemLoader(WEB_FOLDER / 'templates'))

db = database.Database(POSTGRES_CONNECTION_STRING)
sm = state_management.StateManagement(db, SPOTIFY_SECRET_BASE64)
twh = twitch_webhooks.TwitchWebhookManager(db, WEBHOOK_HOST + '/webhook/twitch_live', TWITCH_WEBHOOK_SECRET, TWITCH_CLIENT_ID, TWITCH_SECRET)

app = web.Application()
routes = web.RouteTableDef()

async def get_component_by_name(name : str):
    component_name = 'components/' + name + '.html'
    file_path = WEB_FOLDER / ('templates/' + component_name)
    if not file_path.is_file(): return None
    return j2.get_template(component_name)

@routes.get('/')
async def app_root(request : web.Request):
    t = j2.get_template('index.html')
    login = await db.get_login_by_session(request.cookies.get('session', None))
    return web.Response(text=t.render(login=login), content_type='text/html')

@routes.get('/dashboard')
async def app_root(request : web.Request):
    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text='no session', status=302, headers={'location': '/?loginError=no%20session'})
    login = await db.get_login_by_session(session_key)
    if not login: return web.Response(text='invalid session', status=302, headers={'location': '/?loginError=invalid%20session'})
    spotify_accounts = await db.get_spotify_accounts_by_login(login)
    twitch_accounts = await db.get_twitch_accounts_by_login(login)
    responses = await db.get_all_login_responses(login)
    flows = await db.get_all_login_flows(login)

    t = j2.get_template('dashboard.html')
    return web.Response(text=t.render(login=login, spotify_accounts=spotify_accounts, twitch_accounts=twitch_accounts, responses=responses, flows=flows), content_type='text/html')

@routes.post('/myaccount/save')
async def app_post_responses_verify(request : web.Request):
    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text=json.dumps({'success': False, 'message': 'No session, please sign in'}))
    login = await db.get_login_by_session(session_key)
    if not login: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid session, please sign in'}))

    try: data = await request.read()
    except Exception: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid data'}))

    try: data = json.loads(data.decode('utf-8'))
    except Exception: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid format'}))
    if not isinstance(data, dict): return web.Response(text=json.dumps({'success': False, 'message': 'Invalid type'}))

    new_username = data.get('username', None)
    if not isinstance(new_username, str) or len(new_username) == 0: return web.Response(text=json.dumps({'success': False, 'message': 'No passed username'}))
    resp_name_lower = new_username.lower()
    if not re.search(r'^[a-z0-9]+$', resp_name_lower): return web.Response(text=json.dumps({'success': False, 'message': 'Allowed: a-z, A-Z, 0-9'}))
    taken_usernames = await db.get_taken_usernames(new_username)
    for i in taken_usernames:
        if i.lower() == resp_name_lower: return web.Response(text=json.dumps({'success': False, 'message': 'Username is already taken'}))

    await db.update_username(login, new_username)
    return web.Response(text=json.dumps({'success': True}))

@routes.post('/responses/verify')
async def app_post_responses_verify(request : web.Request):
    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text=json.dumps({'success': False, 'message': 'No session, please sign in'}))
    login = await db.get_login_by_session(session_key)
    if not login: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid session, please sign in'}))
    resp_name = request.query.get('name', None)
    if not isinstance(resp_name, str) or len(resp_name) == 0: return web.Response(text=json.dumps({'success': False, 'message': 'No passed name'}))
    resp_name_lower = resp_name.lower()
    if not re.search(r'^[a-z0-9]+$', resp_name_lower): return web.Response(text=json.dumps({'success': False, 'message': 'Allowed in name: a-z, A-Z, 0-9'}))
    responses = await db.get_all_login_responses(login)
    for i in responses:
        if i.label.lower() == resp_name_lower: return web.Response(text=json.dumps({'success': False, 'message': 'Response name is already taken'}))
    return web.Response(text=json.dumps({'success': True}))

@routes.post('/responses/new')
async def app_post_responses_new(request : web.Request):
    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text='no session', status=302, headers={'location': '/?newResponseError=no%20session'})
    login = await db.get_login_by_session(session_key)
    if not login: return web.Response(text='invalid session', status=302, headers={'location': '/?newResponseError=invalid%20session'})
    try: data = await request.post()
    except Exception: return web.Response(text='invalid post', status=302, headers={'location': '/?newResponseError=invalid%20post'})
    resp_name = data.get('name', None)
    if not isinstance(resp_name, str) or len(resp_name) == 0: return web.Response(text='no name', status=302, headers={'location': '/?newResponseError=no%20name'})
    if not re.search(r'^[a-zA-Z0-9]+$', resp_name): return web.Response(text=json.dumps({'success': False, 'message': 'Allowed in name: a-z, A-Z, 0-9'}))
    resp_obj = await db.create_empty_response(login, resp_name)
    return web.Response(text='created', status=302, headers={'location': f'/dashboard?showResponse={resp_obj.id}'})

@routes.post('/responses/save')
async def app_post_responses_save(request : web.Request):
    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text=json.dumps({'success': False, 'message': 'No session'}))
    login = await db.get_login_by_session(session_key)
    if not login: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid session'}))
    if not request.can_read_body: return web.Response(text=json.dumps({'success': False, 'message': 'No data'}))
    try: data = await request.read()
    except Exception: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid data'}))

    try: data = json.loads(data.decode('utf-8'))
    except Exception: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid format'}))
    if not isinstance(data, dict): return web.Response(text=json.dumps({'success': False, 'message': 'Invalid type'}))

    try: resp_id = int(data['respID'])
    except Exception: return web.Response(text=json.dumps({'success': False, 'message': 'No response'}))

    resp_label = data.get('label', None)
    if not isinstance(resp_label, str) or len(resp_label) == 0:  return web.Response(text=json.dumps({'success': False, 'message': 'No name'}))

    if not 'components' in data or not isinstance(data['components'], list): return web.Response(text=json.dumps({'success': False, 'message': 'Invalid components format'}))

    components = data['components']

    if StructGuard.INVALID == StructGuard.verifyListStructure(components, [{ 'type': str, 'values': dict }], rebuild=False)[0]:
        return web.Response(text=json.dumps({'success': False, 'message': 'Invalid components data'}))

    type_formats = {
        'text': {'text': str},
        'spotifyCurrentArtist': {'spotify_id': str},
        'spotifyCurrentSong': {'spotify_id': str}
    }

    spotify_ids = None

    for i in components:
        match_format = type_formats.get(i['type'], None)
        if match_format is None: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid type'}))
        if StructGuard.INVALID == StructGuard.verifyDictStructure(i['values'], match_format, rebuild=False)[0]:
            return web.Response(text=json.dumps({'success': False, 'message': 'Invalid state format'}))
        elif i['type'] in ['spotifyCurrentArtist', 'spotifyCurrentSong']:
            try: i['values']['spotify_id'] = int(i['values']['spotify_id'])
            except Exception: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid Twitch'}))
            if spotify_ids is None: spotify_ids = [i.id for i in (await db.get_spotify_accounts_by_login(login))]
            if not i['values']['spotify_id'] in spotify_ids: return web.Response(text=json.dumps({'success': False, 'message': 'Spotify not found'}))

    responses = await db.get_all_login_responses(login)
    response = helper.find_by_key('id', resp_id, responses)
    if not response: return web.Response(text=json.dumps({'success': False, 'message': 'Response not found'}))

    label_lower = resp_label.lower()
    update_label = response.label.lower() != label_lower
    if update_label:
        for i in responses:
            if i.label.lower() == label_lower:
                return web.Response(text=json.dumps({'success': False, 'message': 'Response name taken'}))

    if update_label: await db.update_response_label(response, resp_label)
    await db.set_response_components(response, components)
    return web.Response(text=json.dumps({'success': True}))

@routes.post('/responses/delete')
async def app_post_responses_new(request : web.Request):
    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text='no session', status=302, headers={'location': '/?deleteResponseError=no%20session'})
    login = await db.get_login_by_session(session_key)
    if not login: return web.Response(text='invalid session', status=302, headers={'location': '/?deleteResponseError=invalid%20session'})
    try: data = await request.post()
    except Exception: return web.Response(text='no data', status=302, headers={'location': '/dashboard?deleteResponseError=no%20data'})
    try: resp_id = int(data.get('respID', None))
    except Exception: return web.Response(text='invalid or no response', status=302, headers={'location': '/dashboard?deleteResponseError=invalid%20or%20no%20response'})
    responses = await db.get_all_login_responses(login)
    response = helper.find_by_key('id', resp_id, responses)
    if response is None: return web.Response(text='response not found', status=302, headers={'location': '/dashboard?deleteResponseError=response%20not%20found'})
    await db.delete_response(response)
    return web.Response(text='deleted', status=302, headers={'location': '/dashboard'})

@routes.post('/flows/verify')
async def app_post_flows_verify(request : web.Request):
    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text=json.dumps({'success': False, 'message': 'No session, please sign in'}))
    login = await db.get_login_by_session(session_key)
    if not login: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid session, please sign in'}))
    resp_name = request.query.get('name', None)
    if not isinstance(resp_name, str) or len(resp_name) == 0: return web.Response(text=json.dumps({'success': False, 'message': 'No passed name'}))
    resp_name_lower = resp_name.lower()
    if not re.search(r'^[a-z0-9]+$', resp_name_lower): return web.Response(text=json.dumps({'success': False, 'message': 'Allowed in name: a-z, A-Z, 0-9'}))
    responses = await db.get_all_login_flows(login)
    for i in responses:
        if i.label.lower() == resp_name_lower: return web.Response(text=json.dumps({'success': False, 'message': 'Flow name is already taken'}))
    return web.Response(text=json.dumps({'success': True}))

@routes.post('/flows/new')
async def app_post_responses_new(request : web.Request):
    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text='no session', status=302, headers={'location': '/?newFlowError=no%20session'})
    login = await db.get_login_by_session(session_key)
    if not login: return web.Response(text='invalid session', status=302, headers={'location': '/?newFlowError=invalid%20session'})
    try: data = await request.post()
    except Exception: return web.Response(text='invalid post', status=302, headers={'location': '/?newFlowError=invalid%20post'})
    resp_name = data.get('name', None)
    if not isinstance(resp_name, str) or len(resp_name) == 0: return web.Response(text='no name', status=302, headers={'location': '/?newFlowError=no%20name'})
    if not re.search(r'^[a-zA-Z0-9]+$', resp_name): return web.Response(text='illegal name', status=302, headers={'location': '/?newFlowError=illegal%20name'})
    resp_obj = await db.create_empty_flow(login, resp_name)
    return web.Response(text='created', status=302, headers={'location': f'/dashboard?showFlow={resp_obj.id}'})

@routes.post('/flows/toggle')
async def app_flows_toggle(request : web.Request):
    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text=json.dumps({'success': False, 'message': 'No session'}))
    login = await db.get_login_by_session(session_key)
    if not login: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid session'}))
    if not request.can_read_body: return web.Response(text=json.dumps({'success': False, 'message': 'No data'}))
    try: data = await request.read()
    except Exception: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid data'}))
    try: data = json.loads(data.decode('utf-8'))
    except Exception: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid format'}))
    if not isinstance(data, dict): return web.Response(text=json.dumps({'success': False, 'message': 'Invalid type'}))
    try:
        flow_id = int(data.get('flowID', None))
        enabled  = data.get('enabled', False)
    except Exception: return web.Response(text=json.dumps({'success': False, 'message': 'No flow'}))
    flows = await db.get_all_login_flows(login)
    flow = helper.find_by_key('id', flow_id, flows)
    if flow is None: return web.Response(text=json.dumps({'success': False, 'message': 'Flow not found'}))

    await db.toggle_flow(flow, bool(enabled))
    return web.Response(text=json.dumps({'success': True}))

@routes.post('/flows/delete')
async def app_post_responses_new(request : web.Request):
    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text='no session', status=302, headers={'location': '/?deleteFlowError=no%20session'})
    login = await db.get_login_by_session(session_key)
    if not login: return web.Response(text='invalid session', status=302, headers={'location': '/?deleteFlowError=invalid%20session'})
    try: data = await request.post()
    except Exception: return web.Response(text='no data', status=302, headers={'location': '/dashboard?deleteFlowError=no%20data'})
    try: flow_id = int(data.get('flowID', None))
    except Exception: return web.Response(text='invalid or no flow', status=302, headers={'location': '/dashboard?deleteFlowError=invalid%20or%20no%20flow'})
    flows = await db.get_all_login_flows(login)
    flow = helper.find_by_key('id', flow_id, flows)
    if flow is None: return web.Response(text='flow not found', status=302, headers={'location': '/dashboard?deleteFlowError=flow%20not%20found'})
    await db.delete_flow(flow)
    return web.Response(text='deleted', status=302, headers={'location': '/dashboard'})

@routes.post('/flows/save')
async def app_post_flows_save(request : web.Request):
    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text=json.dumps({'success': False, 'message': 'No session'}))
    login = await db.get_login_by_session(session_key)
    if not login: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid session'}))
    if not request.can_read_body: return web.Response(text=json.dumps({'success': False, 'message': 'No data'}))
    try: data = await request.read()
    except Exception: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid data'}))

    try: data = json.loads(data.decode('utf-8'))
    except Exception: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid format'}))
    if not isinstance(data, dict): return web.Response(text=json.dumps({'success': False, 'message': 'Invalid type'}))

    try: flow_id = int(data['flowID'])
    except Exception: return web.Response(text=json.dumps({'success': False, 'message': 'No flow'}))

    resp_label = data.get('label', None)
    if not isinstance(resp_label, str) or len(resp_label) == 0:  return web.Response(text=json.dumps({'success': False, 'message': 'No name'}))

    if not 'states' in data or not isinstance(data['states'], list): return web.Response(text=json.dumps({'success': False, 'message': 'Invalid states format'}))

    states = data['states']

    if StructGuard.INVALID == StructGuard.verifyListStructure(states, [{ 'condition': str, 'response_id': str, 'values': dict }], rebuild=False)[0]:
        return web.Response(text=json.dumps({'success': False, 'message': 'Invalid states data'}))

    type_formats = {
        'twitchLive': {'twitch_id': str},
        'never': {},
        'always': {}
    }

    twitch_ids = None

    for i in states:
        match_format = type_formats.get(i['condition'], None)
        if match_format is None: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid condition'}))
        if StructGuard.INVALID == StructGuard.verifyDictStructure(i['values'], match_format, rebuild=False)[0]:
            return web.Response(text=json.dumps({'success': False, 'message': 'Invalid state format'}))
        elif i['condition'] in ['twitchLive']:
            try: i['values']['twitch_id'] = int(i['values']['twitch_id'])
            except Exception: return web.Response(text=json.dumps({'success': False, 'message': 'Invalid Twitch'}))
            if twitch_ids is None: twitch_ids = [i.id for i in (await db.get_twitch_accounts_by_login(login))]
            if not i['values']['twitch_id'] in twitch_ids: return web.Response(text=json.dumps({'success': False, 'message': 'Twitch not found'}))

    flows = await db.get_all_login_flows(login)
    flow = helper.find_by_key('id', flow_id, flows)
    if not flow: return web.Response(text=json.dumps({'success': False, 'message': 'Flow not found'}))

    label_lower = resp_label.lower()
    update_label = flow.label.lower() != label_lower
    if update_label:
        for i in flows:
            if i.label.lower() == label_lower:
                return web.Response(text=json.dumps({'success': False, 'message': 'Flow name taken'}))

    if update_label: await db.update_flow_label(flow, resp_label)
    await db.set_flow_states(flow, states)
    return web.Response(text=json.dumps({'success': True}))

@routes.get('/render/component/component_options')
async def app_render_component(request : web.Request):
    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text='no session', status=302, headers={'location': '/?loginError=no%20session'})
    login = await db.get_login_by_session(session_key)
    if not login: return web.Response(text='invalid session', status=302, headers={'location': '/?loginError=invalid%20session'})
    t = await get_component_by_name('component_options')
    if not t: return web.Response(status=404)
    spotify_accounts = await db.get_spotify_accounts_by_login(login)
    spotify_connected = bool(spotify_accounts)
    return web.Response(text=t.render(spotify_connected=spotify_connected), content_type='text/html')

@routes.get('/render/component/text')
async def app_render_component(request : web.Request):
    text = request.query.get('text', '')
    t = await get_component_by_name('text')
    if not t: return web.Response(status=404)
    return web.Response(text=t.render(text=text), content_type='text/html')

@routes.get('/render/component/spotifyCurrentArtist')
async def app_render_component(request : web.Request):
    t = await get_component_by_name('spotifyCurrentArtist')
    if not t: return web.Response(status=404)

    try: account_id = int(request.query.get('spotify_id', None))
    except Exception: return web.Response(text='no account id', status=404)

    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text='no session', status=401)
    login = await db.get_login_by_session(session_key)
    if not login: return web.Response(text='invalid session', status=401)

    accounts = await db.get_spotify_accounts_by_login(login)
    match_account = helper.find_by_key('id', account_id, accounts)
    if not match_account: return web.Response(text='account not found', status=404)

    return web.Response(text=t.render(spotify_id=match_account.id, spotify_label=match_account.label), content_type='text/html')

@routes.get('/render/component/spotifyCurrentSong')
async def app_render_component(request : web.Request):
    t = await get_component_by_name('spotifyCurrentSong')
    if not t: return web.Response(status=404)

    try: account_id = int(request.query.get('spotify_id', None))
    except Exception: return web.Response(text='no account id', status=404)

    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text='no session', status=401)
    login = await db.get_login_by_session(session_key)
    if not login: return web.Response(text='invalid session', status=401)

    accounts = await db.get_spotify_accounts_by_login(login)
    match_account = helper.find_by_key('id', account_id, accounts)
    if not match_account: return web.Response(text='account not found', status=404)

    return web.Response(text=t.render(spotify_id=match_account.id, spotify_label=match_account.label), content_type='text/html')

@routes.get(r'/render/components/{respID:\d+}')
async def app_render_components(request : web.Request):
    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text='')
    login = await db.get_login_by_session(session_key)
    if not login: return web.Response(text='')

    resp = ''
    cache = {}

    resp_id = int(request.match_info['respID'])
    responses = await db.get_all_login_responses(login)
    response = helper.find_by_key('id', resp_id, responses)
    if not response: return web.Response(text='')
    components = await db.get_response_components(response)

    spotify_accounts = None

    for i in components:
        if i.resp_type in ['spotifyCurrentArtist', 'spotifyCurrentSong']:
            if spotify_accounts is None: spotify_accounts = await db.get_spotify_accounts_by_login(login)
            spotify_acc = helper.find_by_key('id', i.variables['spotify_id'], spotify_accounts)
            if not spotify_acc: continue
            i.variables['spotify_label'] = spotify_acc.label

        if not i.resp_type in cache: cache[i.resp_type] = await get_component_by_name(i.resp_type)
        t = cache[i.resp_type]
        if not isinstance(t, jinja2.Template): continue
        resp += t.render(i.variables)

    return web.Response(text=resp)

@routes.get('/render/flow/state')
async def app_render_flows(request : web.Request):
    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text='')
    login = await db.get_login_by_session(session_key)
    if not login: return web.Response(text='')

    responses = await db.get_all_login_responses(login)
    twitch_accounts = await db.get_twitch_accounts_by_login(login)

    t = j2.get_template('flows/flow_state.html')
    return web.Response(text=t.render(responses=responses, twitch_accounts=twitch_accounts))

@routes.get(r'/render/flows/{flowID:\d+}')
async def app_render_flows(request : web.Request):
    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text='')
    login = await db.get_login_by_session(session_key)
    if not login: return web.Response(text='')

    flow_id = int(request.match_info['flowID'])

    responses = await db.get_all_login_responses(login)
    twitch_accounts = await db.get_twitch_accounts_by_login(login)
    flows = await db.get_all_login_flows(login)
    flow = helper.find_by_key('id', flow_id, flows)
    if flow is None: return web.Response(text='')
    flow_states = await db.get_flow_states(flow)

    t = j2.get_template('flows/flow.html')
    return web.Response(text=t.render(flow=flow, flow_states=flow_states, responses=responses, twitch_accounts=twitch_accounts))


@routes.get('/logout')
async def app_logout(request : web.Request):
    session_token = request.cookies.get('session', None)
    resp = web.Response(text='signed out', status=302, headers={'location': '/'})
    if not session_token: return resp
    await db.delete_login_session(session_token)
    resp.del_cookie('session')
    return resp

@routes.get('/apis/spotify/connect')
async def app_spotifyConnect(request : web.Request):
    session_key = request.cookies.get('session', None)
    if not session_key: return web.Response(text='no session', status=302, headers={'location': '/?spotifyConnectError=no%20session'})
    login = await db.get_login_by_session(session_key)
    if not login: web.Response(text='invalid session', status=302, headers={'location': '/?spotifyConnectError=invalid%20session'})
    location = f'https://accounts.spotify.com/authorize?response_type=code&client_id={SPOTIFY_CLIENT_ID}&scope={SPOTIFY_SCOPES_ENCODED}&redirect_uri={SPOTIFY_REDIRECT_ENCODED}&show_dialog=true'
    return web.Response(text='hi', status=302, headers={'location': location})

@routes.get('/apis/spotify/callback')
async def app_spotifyConnectCallback(request : web.Request):
    code = request.query.get('code', None)
    if code is None: return web.Response(text='no code', status=302, headers={'location': f'/dashboard?spotifyConnectError=no%20code'})
    session_token = request.cookies.get('session')
    if session_token is None: return web.Response(text='no session', status=302, headers={'location': f'/?spotifyConnectError=no%20session'})
    login = await db.get_login_by_session(session_token)
    if login is None: return web.Response(text='invalid or expired session', status=302, headers={'location': f'/?spotifyConnectError=invalid%20or%20expired%20session'})

    try:
        resp = await helper.http_request(method='post',
                    url='https://accounts.spotify.com/api/token',
                    data={'grant_type': 'authorization_code', 'code': code, 'redirect_uri': SPOTIFY_REDIRECT},
                    headers={'Authorization': f'Basic {SPOTIFY_SECRET_BASE64}'})
    except Exception:
        return web.Response(text='Invalid authentication request', status=302, headers={'location': f'/dashboard?spotifyConnectError=invalid%20authentication%20request'})

    try: resp = json.loads(resp)
    except Exception: return web.Response(text='Invalid authentication format', status=302, headers={'location': f'/dashboard?spotifyConnectError=invalid%authentication%20format'})

    if not isinstance(resp, dict):
        return web.Response(text='Invalid authentication response', status=302, headers={'location': f'/dashboard?spotifyConnectError=invalid%20authentication%20response'})

    access_token = resp.get('access_token', None)
    expires_in = resp.get('expires_in', None)
    expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=expires_in)
    refresh_token = resp.get('refresh_token', None)
    scope = resp.get('scope', None)

    if not isinstance(access_token, str) or not isinstance(expires_in, int) or not isinstance(refresh_token, str) or not isinstance(scope, str):
        return web.Response(text='Invalid authentication data', status=302, headers={'location': f'/dashboard?spotifyConnectError=invalid%20authentication%20data'})

    scopes = scope.split(' ')

    requested_scopes = SPOTIFY_SCOPES.split(' ')
    for i in requested_scopes:
        if not i in scopes:
            return web.Response(text='Missing authentication scopes', status=302, headers={'location': f'/dashboard?spotifyConnectError=missing%20authentication%20scopes'})

    try:
        user_data = await helper.http_request(method='GET', url='https://api.spotify.com/v1/me', headers={
            'Authorization': f'Bearer {access_token}'
        })
    except Exception:
        return web.Response(text='Invalid user request', status=302, headers={'location': f'/dashboard?spotifyConnectError=invalid%20user%20request'})

    try:
        user_data = json.loads(user_data)
    except Exception:
        return web.Response(text='Invalid user request format', status=302, headers={'location': f'/dashboard?spotifyConnectError=invalid%20user%20request%format'})

    if not isinstance(user_data, dict): return web.Response(text='Invalid user response', status=302, headers={'location': f'/dashboard?spotifyConnectError=invalid%20user%20response'})

    if not 'id' in user_data: return web.Response(text='Invalid user data', status=302, headers={'location': f'/dashboard?spotifyConnectError=invalid%20user%20data'})

    await db.add_spotify_account(login, user_data.get('display_name', None), user_data['id'], access_token, refresh_token, scope, expires_at)

    return web.Response(text='Connected', status=302, headers={'location': f'/dashboard'})

@routes.get(r'/apis/spotify/disconnect/{accountID:\d+}')
async def app_apis_spotify_disconnect(request : web.Request):
    account_id = int(request.match_info['accountID'])
    session_token = request.cookies.get('session')
    if session_token is None: return web.Response(text='no session', status=302, headers={'location': f'/dashboard?spotifyDisconnectError=no%20session'})
    login = await db.get_login_by_session(session_token)
    if login is None: return web.Response(text='invalid or expired session', status=302, headers={'location': f'/dashboard?spotifyDisconnectError=invalid%20or%20expired%20session'})
    accounts = await db.get_spotify_accounts_by_login(login)
    match_account = helper.find_by_key('id', account_id, accounts)
    if not match_account: return web.Response(text='account not found', status=302, headers={'location': f'/dashboard?spotifyDisconnectError=account%20not%20found'})
    await db.remove_spotify_account(match_account)
    return web.Response(text='Account deleted', status=302, headers={'location': f'/dashboard'})

@routes.get('/login/twitch')
async def app_twitchLogin(request : web.Request):
    location = f'https://id.twitch.tv/oauth2/authorize?response_type=code&client_id={TWITCH_CLIENT_ID}&redirect_uri={TWITCH_REDIRECT_ENCODED}&scope={TWITCH_SCOPES_ENCODED}'
    return web.Response(text='hi', status=302, headers={'location': location})

@routes.get('/login/twitch/callback')
async def app_twitchLoginCallback(request : web.Request):
    code = request.query.get('code', None)
    if code is None: return web.Response(text='no code')

    try:
        resp = await helper.http_request(method='post',
                    url='https://id.twitch.tv/oauth2/token',
                    data={
                            'grant_type': 'authorization_code',
                            'code': code,
                            'redirect_uri': TWITCH_REDIRECT,
                            'client_id': TWITCH_CLIENT_ID,
                            'client_secret': TWITCH_SECRET
                        }
                    )
    except Exception: return web.Response(text='Failed authentication request', status=302, headers={'location': '/?loginError=failed%20authentication%20request'})

    try: resp = json.loads(resp)
    except Exception: return web.Response(text='Invalid authentication format', status=302, headers={'location': '/?loginError=invalid%20authentication%20format'})

    if not isinstance(resp, dict) or 'status' in resp and resp['status'] == 400:
        return web.Response(text='Authentication error', status=302, headers={'location': f'/?loginError=authentication%20error'})

    if not 'access_token' in resp or not 'expires_in' in resp or not 'refresh_token' in resp:
        return web.Response(text='Invalid response keys', status=302, headers={'location': '/?loginError=invalid%20response%20keys'})

    access_token = resp['access_token']
    expires_in = resp['expires_in']
    validity = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=expires_in)
    refresh_token = resp['refresh_token']
    scopes = resp.get('scope', list())

    try:
        twitch_data_resp = await helper.http_request(method='GET', url='https://api.twitch.tv/helix/users', headers={
            'Client-Id': TWITCH_CLIENT_ID,
            'Authorization': f'Bearer {access_token}'
        })
    except Exception: return web.Response(text='Invalid Twitch user response', status=302, headers={'location': '/?loginError=invalid%20twitch%20user%20request'})

    try: twitch_user = json.loads(twitch_data_resp)
    except Exception: return web.Response(text='Invalid Twitch user format', status=302, headers={'location': '/?loginError=invalid%20twitch%20user%20format'})

    if (not 'data' in twitch_user or not isinstance(twitch_user['data'], list) or
        not 'id' in twitch_user['data'][0] or not 'login' in twitch_user['data'][0] or not 'display_name' in twitch_user['data'][0]):
        return web.Response(text='Invalid Twitch user data', status=302, headers={'location': f'/?loginError=invalid%20twitch%20user%20data'})

    username = twitch_user['data'][0]['login']
    display_name = twitch_user['data'][0]['display_name']
    try: user_id = int(twitch_user['data'][0]['id'])
    except Exception: return web.Response(text='Invalid Twitch user id', status=302, headers={'location': '/?loginError=invalid%20twitch%20user%20id'})

    try:
        live_resp = await helper.http_request(method='GET', url='https://api.twitch.tv/helix/streams?user_id=' + str(user_id), headers={
            'Client-Id': TWITCH_CLIENT_ID,
            'Authorization': f'Bearer {access_token}'
        })
    except Exception: return web.Response(text='Invalid Twitch live response', status=302, headers={'location': '/?loginError=invalid%20twitch%20live%20request'})

    try: live_data = json.loads(live_resp)
    except Exception: return web.Response(text='Invalid Twitch live format', status=302, headers={'location': '/?loginError=invalid%20twitch%20live%20format'})

    if not isinstance(live_data, dict):
        return web.Response(text='Invalid Twitch live type', status=302, headers={'location': '/?loginError=invalid%20twitch%20live%20type'})

    live_data = live_data.get('data', None)
    if not isinstance(live_data, list):
        return web.Response(text='Invalid Twitch live data', status=302, headers={'location': '/?loginError=invalid%20twitch%20live%20data'})

    is_live = len(live_data) != 0

    login = await db.register_login(username, 'Twitch', user_id)
    await db.add_twitch_account(login, user_id, username, display_name, is_live, access_token, refresh_token, scopes, validity)
    await twh.listen(user_id)

    login_session = await db.create_login_session(login)
    expire_date = login_session.validity + datetime.timedelta(days=1)

    resp = web.Response(text='Signed in', status=302, headers={'location': '/dashboard'})
    resp.set_cookie('session', login_session.session_token, expires=expire_date.strftime('%a, %d %b %Y %H:%M:%S UTC'))
    return resp

@routes.get('/u/{username:[a-zA-Z0-9]+}/flow/{flowname:[a-zA-Z0-9]+}/text')
async def app_u_username_flow_flowname_text(request : web.Request):
    username = request.match_info['username'].lower()
    flowname = request.match_info['flowname'].lower()
    login = await db.get_login_by_username(username)
    if not login: return web.Response(text='')
    flows = await db.get_all_login_flows(login)
    flow = helper.find_by_key('label', flowname, flows, match_lowercase=True)
    if not flow or not flow.enabled: return web.Response(text='')
    flow_states = await db.get_flow_states(flow)
    active_state = await sm.get_first_active_state(flow_states)
    if active_state is None: return web.Response(text='')
    state_text_response = await sm.get_state_text_response(active_state)
    if not isinstance(state_text_response, str): return web.Response(text='')
    return web.Response(text=state_text_response)

@routes.get('/api/account/{accountType:[a-z]+}/{accountId:[0-9]+}/accountSecret')
async def app_api_account_accountType_accountId_accountSecret(request : web.Request):
    accountType = request.match_info['accountType'].lower()
    accountId = int(request.match_info['accountId'])
    session_token = request.cookies.get('session')
    if session_token is None: return web.Response(text=json.dumps({'success': False, 'message': 'no session please login'}))
    login = await db.get_login_by_session(session_token)
    if login is None: return web.Response(text=json.dumps({'success': False, 'message': 'invalid session please login'}))

    if accountType == 'spotify':
        spotify_accounts = await db.get_spotify_accounts_by_login(login)
        spotify_account = helper.find_by_key('id', accountId, spotify_accounts)
        if spotify_account: return web.Response(text=json.dumps({'success': True, 'id_token': spotify_account.id_token}))
        return web.Response(text=json.dumps({'success': False, 'message': 'spotify account not found'}))
    return web.Response(text=json.dumps({'success': False, 'message': 'invalid account type'}))

@routes.get('/api/spotify/{accountSecret:[a-zA-Z0-9]+}/accessToken')
async def app_api_spotify_accountSecret_accessToken(request : web.Request):
    accountSecret = request.match_info['accountSecret']
    spotify_account = await db.get_spotify_account_by_id_token(accountSecret)
    spotify_account = await sm.test_spotify_tokens(spotify_account)
    return web.Response(text=json.dumps({'success': True, 'access_token': spotify_account.access_token, 'validity': helper.datetime_string(spotify_account.validity)}))

@routes.post('/webhook/twitch_live')
async def app_webhook_twitch_live(request : web.Request):
    msg_id = request.headers.get('twitch-eventsub-message-id', None)
    msg_ts = request.headers.get('twitch-eventsub-message-timestamp', None)
    msg_signature = request.headers.get('twitch-eventsub-message-signature', None)
    msg_type = request.headers.get('twitch-eventsub-message-type', None)
    if not isinstance(msg_id, str) or not isinstance(msg_ts, str) or not isinstance(msg_signature, str) or not isinstance(msg_type, str):
        return web.Response(text='Invalid headers', status=400)
    if not request.can_read_body: return web.Response(text='Require body', status=400)
    try:
        msg_body = await request.read()
        msg_body = msg_body.decode('utf-8')
    except Exception: return web.Response(text='Bad body', status=400)
    msg_hmac = (msg_id + msg_ts + msg_body).encode('utf-8')
    hmac_digest = hmac.new(TWITCH_WEBHOOK_SECRET_ENCODED, msg_hmac, hashlib.sha256).hexdigest()
    full_hmac = 'sha256=' +  hmac_digest
    try: body_data = json.loads(msg_body)
    except Exception: return web.Response(text='Bad body type', status=400)
    if not hmac.compare_digest(full_hmac, msg_signature): return web.Response(text='Invalid signature', status=401)
    if not isinstance(body_data, dict): return web.Response(text='Body no object', status=400)
    if msg_type == 'notification':
        return await app_webhook_twitch_live_handle_event(request, body_data)
    elif msg_type == 'webhook_callback_verification':
        challenge = body_data.get('challenge', None)
        if not isinstance(challenge, str): return web.Response(text='Bad challenge', status=400)
        return web.Response(text=challenge, status=200, headers={'Content-Type': 'text/plain'})
    elif msg_type == 'revocation':
        return web.Response(status=204)
    return web.Response(text='Invalid type', status=400)

async def app_webhook_twitch_live_handle_event(request : web.Request, body_data : dict):
    req_type = body_data.get('type', None)
    if not req_type in ['stream.online', 'stream.offline']: return web.Response(text='Invalid type', status=400)
    cond = body_data.get('condition',  None)
    if not isinstance(cond, dict): return web.Response(text='No condition', status=400)
    try: req_cond_broadcaster_uid = int(cond.get('broadcaster_user_id'))
    except Exception: return web.Response(text='Invalid condition broadcaster_user_id', status=400)
    twitch_accounts = await db.get_twitch_accounts_by_user_id(req_cond_broadcaster_uid)
    if not twitch_accounts: return web.Response(text='Twitch account not tracked', status=404)
    await db.update_twitch_account_live_status_by_uid(req_type == 'stream.online', req_cond_broadcaster_uid)
    return web.Response(status=200)

@routes.get('/static/{path:.+}')
async def app_statics(request : web.Request):
    contentRawPath = request.match_info['path']

    try: contentPath = (STATIC_FOLDER / contentRawPath).resolve()
    except Exception: return web.Response(text='invalid resource path', status=403)
    if not contentPath.is_relative_to(STATIC_FOLDER): return web.Response(text='illegal static resource path', status=403)

    if not contentPath.is_file(): return web.Response(text='the target resource does not exist', status=404)

    return web.FileResponse(contentPath)

app.add_routes(routes=routes)

async def start_site():
    runner = web.AppRunner(app)
    print(f'running at http://localhost:{WEB_PORT}')
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=WEB_PORT)
    await site.start()

async def main():
    await db.startup()
    await twh.startup()
    await start_site()
    while True: await asyncio.sleep(10)

if __name__ == '__main__':
    asyncio.run(main())
