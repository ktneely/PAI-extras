# PAI-extras
Additional capabilities for the Personal AI assistant

This repository contains copies of stuff I've added to my [PAI-Opencode](https://github.com/Steffen025/pai-opencode) configuration but everything here should work on PAI based on Claude Code or any other harness it's moved over to.

## Installation

I've mirrored the directory structure where these additional components have been added to PAI, so you can simply copy them over, and in the case of a skill, run `GenerateSkillIndex.ts` to provide knowledge of the new skill to your DA.

For the data maintenance tools, configure these and add them to your mechanism for running those tasks periodically.

Alternatively, you should be able to point your agent at this repository and ask it to install one, more, or all of the components and I'm sure it'll figure it out.

## The Extras

### TELOS-related add-ons

The Telos part of PAI is a crucial component for making sure the outputs are aligned with one’s own goals and interests, as well as trying to inject a bit of one’s own personality into outputs and interactions.  However, keeping this up to date can be a real chore.  These scripts help reduce duplicate effort while also keeping it more real-time, rather than me remembering to make some bulk updates once a year or when something is glaringly absent.

#### Books

I use a Bookwyrm server, similar to Good Reads but on the Fediverse so intgrated with other platforms like Mastodon, to keep track of books I'm reading, want to read, or have read and reviewd.  Instead of manually updating `BOOKS.md`, the `bookwyrm_sync.py` script will update from your Bookwyrm account.  Config goes in your `.env` file as outlined at the top of the script, no password required.


#### Movies and Television

Similar to the updating `BOOKS.md` with data from a Bookwyrm server, this one updates both `MOVIES.md` and `TELEVISION.md` with your reviews from [The Movie Database](https://themoviedb.org).  


This requires a free account, and setting `THEMOVIEDB_ACCESS_TOKEN` (not the API key) in your `.env`.

### Substrate

This is my implementation of a [Substrate](https://github.com/danielmiessler/Substrate) skill, though it diverges a bit from Daniel Miessler's original concept, it's pretty close.  This came before the general repo, so it's actually a submodule (nested repository).
