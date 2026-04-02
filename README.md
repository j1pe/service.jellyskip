Jellyskip (Binge-Watching Edition)
A modified and enhanced version of the service.jellyskip Kodi add-on.

This fork introduces a complete Netflix-style Binge-Watching experience for Jellyfin media segments (Intros & Outros) directly within Kodi. It seamlessly integrates with the default Estuary skin using native visual components.

✨ New Features in this Fork
1. Smart Outro Handling (Next Episode / Quit)
Instead of just offering to "Skip Outro" like the original add-on, reaching the end credits now prompts a split-button menu:

Next Episode: Skips the remaining credits and immediately plays the next file.

Quit: Stops playback and returns to the Kodi interface.

2. Netflix-Style Auto-Play (Binge-Watching)
If no action is taken during the Outro prompt, a dynamic countdown (default: 10s) will start. Once the countdown reaches zero:

The add-on automatically jumps to the Next Episode.

A Binge Counter keeps track of consecutive auto-played episodes.

If the limit (default: 3 episodes) is reached, the playback automatically stops to prevent endless streaming if you fall asleep.

Any manual interaction (pressing a button or navigating) instantly resets the binge counter.

3. Fully Customizable via GUI
You no longer need to edit the Python code to change the behavior. A new settings menu allows you to adjust:

Intro Display Time: How long the "Skip Intro" button stays on screen.

Outro Timeout: The countdown duration before auto-playing the next episode.

Binge Limit: The maximum number of consecutive episodes played without user interaction before playback halts.

4. Estuary Skin Integration
The dialogue menu has been completely rewritten in XML to match Kodi's default Estuary theme:

The "Next Episode" and "Quit" buttons are perfectly aligned and glued together in a clean, translucent pill shape.

The blue focus texture wraps the text properly without cropping or deformation.

🚀 Installation
1. Go to the [Releases page](../../releases/latest) of this repository.
2. Download the latest `service.jellyskip-x.x.x.zip` file from the Assets section.
3. In Kodi, go to **Add-ons** > **Install from zip file** and select the downloaded archive.