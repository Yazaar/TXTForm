#!/bin/sh

export WEB_PORT="80"

export TWITCH_CLIENT_ID=""
export TWITCH_SECRET=""
export TWITCH_SCOPES="bits:read channel:read:subscriptions"
export TWITCH_REDIRECT=""

export TWITCH_WEBHOOK_SECRET=""
export WEBHOOK_HOST=""

export SPOTIFY_CLIENT_ID=""
export SPOTIFY_SECRET=""
export SPOTIFY_SCOPES="user-read-playback-state user-read-currently-playing playlist-read-private user-read-recently-played"
export SPOTIFY_REDIRECT=""

export POSTGRES_CONNECTION_STRING="postgresql://username:password@localhost:5432/database"

scriptDir=$(dirname "$(readlink -f "$0")")
pythonScriptPath="$scriptDir/txtform/txtform.py"
python "$pythonScriptPath"