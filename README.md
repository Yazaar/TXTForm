# TXTForm
*Text transformation web service built on top of PostgreSQL and async Python 3.11*

Seamlessly connect various services and provide dynamic data access for external platforms. Developed primarily for use within the Twitch streaming space to give bots such as StreamElements access to an enhanced amount of services with dynamic responses. Includes Spotify integration through the currently playing song and by which artist(s) may be accessed.

When it comes to Twitch able to restrict when information becomes publically available. One response may be returned if the stream is online, with Spotify-related playing information. Another if the stream is offline to keep the information private and secure.

Everything is managed from an easy to use dashboard, where "responses" and "flows" are managed to individually build data access to external services. Each flow has a set of states which determines which response to return. The response is then translated into pure text and returned to the client requesting access.

The service is publically available at [https://txtform.yazaar.xyz](https://txtform.yazaar.xyz).
