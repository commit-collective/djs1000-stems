@echo off
rem Starts stemd with the word kept in STEMD_TOKEN (set it once: setx STEMD_TOKEN YOURWORD).
rem Its log goes to this window and to stemd.log in the repository. More options can follow, as for stemd serve.
cd /d "%~dp0.."
".venv\Scripts\stemd.exe" serve --log stemd.log %*
