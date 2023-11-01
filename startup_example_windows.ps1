$env:WEB_PORT = "80"

$env:TWITCH_CLIENT_ID = ""
$env:TWITCH_SECRET = ""
$env:TWITCH_SCOPES = "bits:read channel:read:subscriptions"
$env:TWITCH_REDIRECT = ""

$env:TWITCH_WEBHOOK_SECRET = ""
$env:WEBHOOK_HOST = ""

$env:SPOTIFY_CLIENT_ID = ""
$env:SPOTIFY_SECRET = ""
$env:SPOTIFY_SCOPES = "user-read-playback-state user-read-currently-playing playlist-read-private user-read-recently-played"
$env:SPOTIFY_REDIRECT = ""

$env:POSTGRES_CONNECTION_STRING = "postgresql://username:password@localhost:5432/database"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$pythonScriptPath = Join-Path -Path $scriptDir -ChildPath "\txtform\txtform.py"
python $pythonScriptPath
