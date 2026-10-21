"""Optional replacement text for the HD pause menu's Help & About pages (`desktop_pause_hd.py`).

The app's own copy for 'airing' and 'demand' describes a service this runtime doesn't offer (paid weekly
episodes, EA's own purchase and restore flow), and 'about' credits EA's own original release rather than this
project. This player's own addition, with no native equivalent to preserve 1:1 against -- a page not listed
here still shows the app's own original string-bank text untouched (see `HdPauseMenu.text_lines()`).

Each entry is `(title, body)`. A bare URL, or `[label](url)` (shown as the label), is a tappable link
(`desktop_pause_hd.link_words`). `body` may still use the native app's own `~276~` version token, substituted the
same way as the original text; write a literal `™` where the native text uses its own trademark control byte,
since that substitution only applies to the original string bank's own encoding.
"""

# Cause of Death's (desktop_cod_pause.CodPauseMenu): the same pages adapted to CoD's library and airdate research
# (docs/COD_RELEASE_DATES.md) and the owner's About page (CoD's credits with this project's). CoD's own version token is
# ~259~ (SHS HD's ~276~); both are substituted.
COD_HELP_TEXT_OVERRIDES = {
    'airing': ('Now Airing', """Use the 'Now Airing' option to sort episodes by their airdate from earliest to latest in an easy-to-navigate list view.

Every chapter was originally released twice: first On Demand, then for free in Now Airing a week or more later. Episodes are listed by their first release, when each chapter first became playable.

Most release dates are exact, taken from the official Cause of Death Facebook page, which announced each release as it happened. The few it never announced are approximated from the weekly release schedule, the Cause of Death Wiki or the App Store listing, and may not be completely accurate."""),
    'demand': ('Episodes On Demand', """Episodes On Demand

Browse every episode in your library, grouped by volume or pack, in an easy-to-navigate classic list view, sorted by the original categories.

Airdates are approximate in a few cases. See the 'Now Airing' section for more info.

Play My Episodes

'Play/Resume' opens the tile grid selector instead, grouped the same way, with a preview thumbnail for each episode. Either screen works the same way: tap an episode to start or continue it."""),
    'about': ('About', """By purchasing and/or using this application, you agree to the terms of the End User License Agreement and EA's Privacy Policy and Terms of Service.

Cause of Death © 2011-2014 Electronic Arts Inc.

This is an unofficial fan preservation project, not affiliated with or endorsed by Electronic Arts or Centerscore Inc.

[shshd-runtime](https://github.com/1timewire1/shshd-runtime) by 1timewire1
Based on the original [exp-runtime](https://github.com/joshrmcdaniel/exp-runtime) by Josh Mcdaniel

Special thanks to zazatree for their code contributions, and the [Cause of Death Discord](https://discord.gg/NdCru4Vz3q) (especially racheletc) for keeping the game preserved & alive! This project wouldn't have been possible without their contributions.

MUSIC
Chromosone Why,  No Hanging Fruit and Euphoric Neurosis  
Written by  Paul Haslinger

Covert Covenant 
Written by  Trevor Morris


Under the Radar
Written by  Rupert Gregson-Williams

Absorption Shock 
Written by  James Hannigan

Jawbreakin 
Written by  Zach Sciacca

Evil Eye
Written by  Jason Graves

Unlucky 13 
Written by  Brad Derrick


Version: ~259~
Upstream EXP Runtime: ~upstream~

Join the Cause of Death Discord: https://discord.gg/NdCru4Vz3q"""),
}

HELP_TEXT_OVERRIDES = {
    'airing': ('Now Airing', """Use the 'Now Airing' option to sort episodes by their airdate from earliest to latest in an easy-to-navigate list view.

Release dates are approximated using these sources in order of priority: @SHSTeam on X (Twitter) > Wikia Episode List > GameFAQs Walkthrough. Some may not be completely accurate.

At the bottom of the 'Now Airing' list are the Homecoming Princesses episode's vote packages, and season bundles that have all individual episodes accounted for."""),
    'demand': ('Episodes On Demand', """Episodes On Demand

Browse every episode in your library, grouped by season or pack, in an easy-to-navigate classic list view, sorted by the original categories.

Airdates are approximate, not exact. See the 'Now Airing' section for more info.

An episode marked 'SD' comes from the Standard (non-HD) release. Its art is automatically upgraded using matching higher-resolution art from the HD release of the same story wherever a match exists; the 'SD' tag only remains when some of its pictures couldn't be upgraded this way.

Play My Episodes

'Play/Resume' opens the HD exclusive tile grid selector instead, grouped the same way, with a preview thumbnail for each episode. Either screen works the same way: tap an episode to start or continue it."""),
    'about': ('About', """Surviving High School © 2011-2014 Electronic Arts Inc. All Rights Reserved. Electronic Arts, EA and the EA logo are trademarks or registered trademarks of Electronic Arts Inc. in the United States and/or other countries. EA™ is an Electronic Arts™ brand.

This is an unofficial fan preservation project, not affiliated with or endorsed by Electronic Arts or Centerscore Inc.

[shshd-runtime](https://github.com/1timewire1/shshd-runtime) by 1timewire1
Based on the original [exp-runtime](https://github.com/joshrmcdaniel/exp-runtime) by Josh Mcdaniel

Special thanks to Alejandro for preserving Surviving High School HD, zazatree for their code contributions, and the [Surviving High School Community Discord](https://discord.gg/reJT83aAeD) in general for keeping the game alive! This project wouldn't have been possible without their contributions.

Credits:
Andrew Shvarts
Bryce Gunkel
Darren Yamaguchi
Henry Shao
Jeremy Biddle
John Cloud
Kara Loo
Late Kan
Max Doty
Monte Lin
Oliver Miao
Phil Ponsaran
Phuong Vo
Rob James
Scott Dods
Winston She

Music Composed by David Lodge

Abhirup Bose
Adam Sussman
Alla Shanker Srinivas
Ankit Kumar
Audrea Topps-Harjo
Autumn Brown
Barry Cottle
Ben Liu
Bernard Kim
Christine Woertink
Dhruv Thukral
Farshid Almassizadeh
Fiona Stevenson
Gary James
Han Hu
Jaime Grieves
Jason Rothman
Jean-Christophe Bornaghi
Jessica Huang
Jimmy Liu
John Krause
Jonathan Correa
Justin Kubiak
Kirsty Sclanders
Leo Deza
Lesley Eastup
Madhava Golkonda
Mel Wallace
Neeraj Mathrani
Nick Rish
Nigel Collinson
Nicolas Stephens
Oliver Winder
Patrick Gunn
Patrick Yin
Rahul Bole
Robert Griffis
Steven Stamstad
Surendar Modugu
Travis Boatman
Wai Mui
Won Sang Jo

Version: ~276~
Upstream EXP Runtime: ~upstream~

Join the Surviving High School Discord: https://discord.gg/reJT83aAeD"""),
}
