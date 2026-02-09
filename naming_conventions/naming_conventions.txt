Skip to:
Top Bar
Sidebar
Main Content



Search Confluence, Jira, Slack and other apps

Create

9+



Back to top
Search by title
Updated 12 Dec, 2025
Aleksander Klar
Edit

Share


Assets naming convention



By Adam Stężała

4 min

21

Add a reaction
Introduction
This document outlines the standard naming convention for all game assets. The goal is to ensure consistency, clarity, and efficient organization across the project. This convention was established during meetings held on March 12, 2025, and March 19, 2025. Some changes were applied after that and open for discussion between Frontend and Tech Art teams.

General Principles
All asset names should be in lowercase.

Underscores should be used as separators between words.

The use of ambiguous acronyms (e.g., "FS" for "free spins") is discouraged.

Naming pattern
General pattern
Game mode

Specific asset type

Feature / identifier

Part of asset

Subfunction / type of animation

State

Version/option

Orientation

Size

loading_screen | feature_screen

free_spins | base_game | hold_and_win

pop_up | button | bullet | panel | ambient | bar

reels | symbol | logo

buy_bonus | side bet 

award | summary | retrigger | select | feature

respin_counter | total_win

background | top | bottom | back | front

intro | outro | loop | idle | win

continue | dismiss | confirm

 

active | inactive | disabled

1, 2, 3…

portrait | landscape

small | medium | large

All parts joined with underscore, e.g.: 

button_buy_bonus

free_spins_pop_up_select_1_landscape

free_spins_button_select_1_active,

free_spins_pop_up_retrigger_portrait

hold_and_win_respin_counter

etc.

Game modes
Unified naming for game modes: free_spins, base_game, hold_and_win. 

loading_screen and feature_screen are specific game modes (states) which can be entered into only once per client session i.e. without refreshing the game.

Orientation-Specific Assets
For assets that differ based on screen orientation, append either "_landscape" or "_portrait" as a suffix.

Asset Sizes

When multiple sizes of the same asset exist, use suffixes like "_small", "_medium", or "_large".

Multiple Versions

When there are multiple versions of the same asset, append a number as a suffix (e.g., "_1", "_2").

Specific Asset Types
Buttons

Button asset names must contain “button” keyword and a feature name which it refers to.  

If the asset is game mode related, e.g. free_spins the name should start with game mode name.

Button states should be added as a suffix, e.g. "_active" or "_disabled". No suffix for default state.

Good examples: button_side_bet_active, free_spins_button_award_continue

Bad examples: button, button_plus, buy_bonus_button

Popups 

Popups asset names must contain “pop_up” keyword and a feature name which it refers to. 

If the asset is game mode related, e.g. free_spins the name should start with game mode name.

Good examples: free_spins_pop_up_award, pop_up_buy_bonus_intro

Bad examples: pop_up, pop_up_intro_buy_bonus, buy_bonus_pop_up

Panels 

Popups asset names must contain “panel” keyword and a feature name which it refers to. 

If the asset is game mode related, e.g. free_spins the name should start with game mode name.

Good examples: panel_side_bet_active, hold_and_win_panel_respin_counter

Bad examples: panel, panel_intro, side_bet_panel

Symbols
Popups asset names must start with “symbol_” prefix, followed by symbol index mapped per game and mandatory a state (static | lose | blur | any game specific state name if needed). State should be always in the end of the symbol asset name, e.g. symbol_1_static

Stacked and colossal symbols variants should be named following the pattern WIDTHxHEIGHT: 1x3 1x2 2x2 etc.

Good examples: symbol_9_1x3_blur (symbol with index 9 - according to the map delivered by frontend team e.g. 
SoGVH&W - Symbols mapping
; one column width, three rows height; blur state)

Loading Screen
Loading screen assets should start with “loading_screen_” prefix.

Examples: loading_screen_bar_background, loading_screen_bar_border, loading_screen_bar_fill, loading_screen_logo 

The folder containing should be named “loading_screen”.

Feature Screen
Feature screen assets should start with “feature_screen_” prefix.

The buttons and bullets should follow the general pattern: [game_mode]_[specific_asset_type]_[identifier]_[state]

Examples: feature_screen_button_arrow_static, feature_screen_button_arrow_pressed, feature_screen_bullet_inactive, feature_screen_bullet_active, feature_screen_button_play, feature_screen_button_play_pressed

Feature panels should be numbered from 1: feature_screen_panel_feature_1, feature_screen_panel_feature_2

The folder containing should be named “feature_screen”.

Frame by frame animations
Each frame should have a suffix with number (two digits long) of the frame in order from “_00” to “_99”.

Spine animations
Name parts marked with * are optional. Example: pop_up_buy_bonus has no states or there is only one asset for both orientations.

Background animations (ambient) - ambient.skel
Pattern: [game_mode]_ambient_[orientation]*
Good examples: base_game_ambient_landscape, free_spins_ambient_portrait


Buy bonus - buy_bonus.skel
Pattern:[specific_asset_type]_buy_bonus_[state]*_[orientation]*
Good examples: pop_up_buy_bonus, button_buy_bonus


Jackpot panels - jackpot_panels.skel
Pattern: [specific_asset_type]_jackpot_[option]_[orientation]*
Good examples: panel_jackpot_1, panel_jackpot_1_landscape


Special spin - special_spin.skel
Pattern: special_spin_[part]*_[type_of_animation]*_[orientation]*
Good examples: special_spin, special_spin_portrait, special_spin_back_loop, special_spin_front_intro


Feature screen - feature_screen.skel
Pattern: feature_screen_feature_[feature_index]_[orientation]*
Good examples: feature_screen_feature_1, feature_screen_feature_1_landscape 


Logo - logo.skel
Pattern: logo_[type_of_animation]_[orientation]*
Good examples: logo_idle, logo_win, logo_win_landscape


Game mode popups - pop_ups.skel.
Pattern: [game_mode]_pop_up_[feature]_[feature_index]_[subfunction]_[orientation]*
Good examples: free_spins_pop_up_feature_1_intro_portrait, free_spins_pop_up_retrigger_intro


Anticipation - anticipation.skel
Pattern: reel_anticipation_[anticipation_index]**_[orientation]* and/or tile_anticipation_[anticipation_index]**_[orientation]*
Good examples: reel_anticipation_1, reel_anticipation_2, reel_anticipation_1_portrait, tile_anticipation_1, tile_anticipation_2, tile_anticipation_1_portrait
**anticipation_index is the identifier of the anticipation, for example reel_anticipation_1 is an anticipation for free spins scatter symbol and reel_anticipation_2 is an anticipation for coin scatter symbol for hold and win trigger.
reel_anticipation - anticipation animation for entire reel
tile_anticipation - anticipation animation for single symbol


Side bet - side_bet.skel
Pattern: [specific_asset_type]_side_bet
Good examples: panel_side_bet


Win events - win_events.skel
Pattern: win_event_[win_event_index]**_[type_of_animation]_[orientation]*
Good examples: win_event_1_loop, win_event_2_intro_landscape
**win_event_index is the index of win event ordered by the win threshold


Game intro - game_intro.skel
Pattern: game_intro_[orientation]*
Good examples: game_intro, game_intro_landscape, game_intro_portrait


Game mode transition - game_mode_transition.skel
Pattern: transition_[from_game_mode]*_to_[to_game_mode]
Good examples: transition_base_game_to_free_spins, transition_to_free_spins


Win frame - win_frame.skel
Pattern: win_frame_[orientation]*
Good examples: win_frame, win_frame_landscape, win_frame_portrait


Perceived persistence - persistence.skel
Perceived persistence collect animation can be a logo animation - then respective collect animation should be added to logo.skel.
If there are dedicated elements to show collect animations naming should follow the pattern below. Index of progress might be useful for the animations like for example pot filling gradually with gold. There could be multiple elements collecting different types of symbols (index_of_persistence_element)
Pattern: persistence_[index_of_persistence_element]_[type_of_animation]_[index_of_progress]*
Good examples: persistence_1_collect, persistence_2_collect, persistence_2_collect_1, persistence_2_collect_2

 

Related content


GN - Assets Appendices
Product Games
More like this
UBHW- Assets Appendices
Product Games
More like this
7FOR - Assets Appendices
Product Games
More like this
Phase 4 | Phase B: Create Game Assets Specifications Document
Technical Art
More like this
Currency Signs + Generic Bitmap Fonts
Technical Art
Read with this
GN - Game Design Document
Product Games
More like this





Add a comment

Add labels

Add a reaction