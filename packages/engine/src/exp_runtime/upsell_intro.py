"""The store plugs some SHS and Cause of Death episodes open with before their story ("Want to catch up? Grab the
Season 1 Set...", the Story Vote Ticket, the Novel Prelude pack, the Cause of Death plug, CoD's volume bundles and
Facebook page...): the narrator's lines before the title card or the episode's own recap.

The player's `skip_upsell_intros` preference plays those lines headlessly when a new game starts, acknowledging them as
a player would, and stops at the episode's first screen. Which lines are a plug was chosen line by line from every
episode's opening (owner, 2026-10-22; findings "Issue #8: promo intros scan"). The lines are kept as hashes of their
text, in the order they show, so the table carries no story text; an episode whose opening does not match a sequence
whole is left untouched. Only a plug that opens the episode is covered: one after a chapter menu (A New Start Season
2, Set 9, CoD's volume sets) or after a story line (the Novel, A Fallon Family Christmas) waits for line-level
skipping. Cause of Death's openings were added the same way (owner, 2026-11-17).
"""
from hashlib import sha256

from .runtime import Session

STEPS = 40                      # screens the longest plug takes (7), with room for its reveals

SEQUENCES = (
    # 2_1_Howards_Return (5 screens)
    ('8581f6498a1ee326', '295a382fde14c1e7', '3de17d2d8e0c06fc', 'da53abb8520709ac', '3c7d1d3b94328053'),
    # 2_2_Swim_Team_Retreat_1 (1 screen)
    ('3f74d0dcfea47a24',),
    # 2_5_Psych_Project_Subject_Owen (6 screens)
    ('20dcc72a31b11a22', 'b656fe4665acd454', '853cc0442a85ef26', '0fbb162b8bcff6e2', '9a8290d334978d05',
     '3c7d1d3b94328053'),
    # 9_1_Christmas_Break (5 screens)
    ('35f89834ccd7d726', '6ee33d8e20adf34b', 'fcaf95bb0b0d60fa', '5c0d111a3441cfc3', '3c7d1d3b94328053'),
    # 10_4_The_Spartan_Games_Part_2 (7 screens)
    ('aa6a256a6c909cf1', '3aab00510fb6dc53', '890c183ae0829c0f', '2738f42751c0503d', '21f5d521dd6d92c2',
     'c6be5aa3e91aab3b', '3c7d1d3b94328053'),
    # 10_5_The_Spartan_Games_3 (7 screens)
    ('aa6a256a6c909cf1', '3aab00510fb6dc53', '890c183ae0829c0f', '2738f42751c0503d', '64807bde6aa76280',
     'c6be5aa3e91aab3b', '3c7d1d3b94328053'),
    # 10_6_Eyesontheprize (7 screens)
    ('aa6a256a6c909cf1', '3aab00510fb6dc53', '890c183ae0829c0f', 'fbfc176cf7e6eb16', '2ef16df353b0521e',
     'c6be5aa3e91aab3b', '3c7d1d3b94328053'),
    # 10_7_faceplace_zero (7 screens)
    ('aa6a256a6c909cf1', '3aab00510fb6dc53', '890c183ae0829c0f', 'fbfc176cf7e6eb16', '0539c16578996f65',
     'c6be5aa3e91aab3b', '3c7d1d3b94328053'),
    # 10_8_real_life_hero (7 screens)
    ('aa6a256a6c909cf1', '3aab00510fb6dc53', '459016c7a436ac87', '51c3bbf1e253f102', 'ea52b00d5a3249bf',
     '4ea9135c5720ea92', '3c7d1d3b94328053'),
    # 11_0_April_Fools (5 screens)
    ('aa6a256a6c909cf1', '3aab00510fb6dc53', '459016c7a436ac87', '51c3bbf1e253f102', '3c7d1d3b94328053'),
    # 11_5_The_Campaign_Trail (6 screens)
    ('aa6a256a6c909cf1', 'd522f2520826c702', 'bbc3ad2bcd10b83b', '9aa94248e2d982b0', 'deb44940b64d5b7e',
     '3c7d1d3b94328053'),
    # 12_4_Wilson_Strikes_Back, 12_6_The_Island_Party, 12_7_Howards_College_Tour, 12_8_A_Kingston_King,
    # MTX_The_Storm_Part_1 (1 screen)
    ('97f7f8623c770d3e',),
    # 25_Tom_Princes_Carol, 26_New_Years_Kiss, 27_Prank_Wars, 29_Guys_Versus_Wild, 30_Proof, 31_Crosstown_Races_Part_1,
    # 32_Crosstown_Races_Part_2, 33_The_Break_Up, 34_Andy_Cannelloni_PI, 35_Fair_Catch, 36_The_Cheer_Lationship,
    # 38_The_Prince_Plot_Part_2, 40_The_Graduation_List, 41_When_Howard_Met, 42_Spirit_Week (1 screen)
    ('7bfb806078142c3f',),
    # 70_New_Regime (1 screen)
    ('f79e16e35fac0f2d',),
    # 72_Trapped_In_The_Classroom (1 screen)
    ('998d5cb58923a27c',),
    # Cause of Death (owner, 2026-11-17, line by line from reference/promo_review/cod_intro_store_plugs.md): the bundle,
    # Facebook and Claire Hart plugs where they open an episode. Kept: the Halloween special's Ghost Harvest lines,
    # which lead into its choice. Revisit with line-level skipping: Claire Hart's "clairvoyant" line introduces the
    # episode's guest.
    # 14_1_Joint_Forces, 14_4_One_Step_Ahead, 14_Interlude (2 screens)
    ('ea162ff7011c3dff', 'b09d6d542e5ec1e1'),
    # 14_2_Accelerant, 14_3_Catch_and_Release, 14_7_Prodigal_Son, 14_8_New_World_Order_Part_1 (2 screens)
    ('ea162ff7011c3dff', '747a7d85b08a70df'),
    # 14_5_Second_Chances, 14_6_The_Greater_Good, SS09_Greene_Zone_1, SS10_Greene_Zone_2, SS17_Peacemaker_1,
    # SS18_Peacemaker_2 (1 screen)
    ('ea162ff7011c3dff',),
    # 14_9_New_World_Order_Part_2, 16_1_Haunted, 16_2_Metamorphosis, 16_3_Unfinished_Business,
    # 16_5_The_Red_Room, 16_6_True_Faces, 16_7_Sunset, 16_Interlude, SS19_Kai_Hard_Part_1, SS20_Kai_Hard_Part_2,
    # SS21_Seth_Lies_and_Videotape_Part_1, SS22_Seth_Lies_and_Videotape_Part_2, SS23_Forks_in_the_Road_Part_1,
    # SS24_Forks_in_the_Road_Part_2, SS25_City_of_Love_Part_1, SS26_City_of_Love_Part_2 (2 screens)
    ('ea162ff7011c3dff', 'b694a8ea221a5e5b'),
    # SS01_Detective_Kalaba_1, SS02_Detective_Kalaba_2 (1 screen)
    ('73ffa10ee98c6f18',),
    # SS03_Amys_Case_1, SS04_Amys_Case_2 (1 screen)
    ('ec9b1b4d60b6f1d8',),
    # SS05_Fallon_And_Yeong_1, SS06_Fallon_And_Yeong_2 (1 screen)
    ('2c8af3c30355e647',),
    # SS11_In_The_Cards_1 (6 screens)
    ('2c8af3c30355e647', 'ea10313f254a6750', 'edcd62562290de56', 'd4d44402cf64c44b', 'ea6cfa671edd04cf',
     '3c7d1d3b94328053'),
    # SS12_In_The_Cards_2 (5 screens)
    ('2c8af3c30355e647', 'ea10313f254a6750', 'edcd62562290de56', 'd4d44402cf64c44b', 'ea6cfa671edd04cf'),
    # SS16_Far_From_Home_2 (2 screens)
    ('ea162ff7011c3dff', '521b4ccdbb341ead'),
)


def line_digest(text):
    return sha256(text.encode('utf-8')).hexdigest()[:16]


def skip_upsell_intro(session, sequences=SEQUENCES):
    """`session` (a game just started) with its opening store plug acknowledged, or an equal session unchanged when it
    does not open with one of `sequences`."""
    if session.pending is None:
        session.advance()
    start = session.snapshot()
    candidates, shown, last, done = sequences, 0, None, None
    for _ in range(STEPS):
        action = session.pending
        if action is None:
            break
        if session.transitioning:
            session.tick(100)
            continue
        if action.name != 'dialogue':
            break
        if action is not last:
            line = line_digest(action.details.get('text', ''))
            candidates = [lines for lines in candidates if len(lines) > shown and lines[shown] == line]
            if not candidates:
                break
            last, shown = action, shown + 1
        if not session.engine.dialogue_animation.complete:
            session.answer()                     # the first tap finishes the reveal
            session.tick(2000)
        session.answer()
        if any(len(lines) == shown for lines in candidates):
            done = shown, session.snapshot()
    if done is None:
        return Session.from_snapshot(session.resources, start)
    if done[0] == shown:
        return session
    return Session.from_snapshot(session.resources, done[1])
