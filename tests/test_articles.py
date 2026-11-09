"""shshd-runtime: "a(n)" in the BREW games' formatted lines, made "a" or "an" by the word filled in (engine.choose_articles), and "word(s)" made singular or plural by the number before it (choose_plurals)."""
import unittest

from exp_runtime.engine import choose_articles, choose_plurals
from exp_runtime.runtime import Session
from test_runtime import Resources, host_call, text_words
from test_vm import program


class ArticleTests(unittest.TestCase):
    def test_the_word_after_it_picks_a_or_an(self):
        # M.A.S.H. Pack 1's houses and cars, and Fall '06's grades, said by their letter's name.
        for text, expected in (('in a(n) mansion', 'in a mansion'), ('in a(n) apartment', 'in an apartment'),
                               ('driving a(n) orange hearse', 'driving an orange hearse'),
                               ('a(n) A in Math, a(n) B in Art, a(n) F in French and a(n) C- overall',
                                'an A in Math, a B in Art, an F in French and a C- overall'),
                               ('A(n) hour', 'An hour'), ('a(n) university', 'a university'),
                               ('a(n) "Alone" poster', 'an "Alone" poster')):
            self.assertEqual(choose_articles(text), expected)
        for kept in ('a(n)', 'banana(n) x', 'plain text'):
            self.assertEqual(choose_articles(kept), kept)

    def test_the_number_before_it_picks_singular_or_plural(self):
        # Fall '06's season record after each game (owner, 2026-11-09): "(s)" and "(es)" go when the count is 1.
        for text, expected in (('4 Win(s) and 0 Loss(es). You have 3 more game(s) to go.',
                                '4 Wins and 0 Losses. You have 3 more games to go.'),
                               ('1 Win(s) and 1 Loss(es). You have 1 more game(s) to go.',
                                '1 Win and 1 Loss. You have 1 more game to go.'),
                               ('11 Win(s)', '11 Wins'), ('-1 point(s)', '-1 point')):
            self.assertEqual(choose_plurals(text), expected)
        for kept in ('Win(s)', 'a game(s)', 'plain text'):
            self.assertEqual(choose_plurals(kept), kept)

    def test_a_creator_episodes_placeholders_change_where_it_asks(self):
        # A Creator episode's `{placeholders}` format through service 0; its `word_forms` setting picks the forms there too
        # (owner, 2026-11-09).
        words, (pattern,) = text_words('%d game(s) left')
        for presentation, expected in (({'word_forms': True}, '1 game left'), ({}, '1 game(s) left')):
            with self.subTest(presentation=presentation):
                resources = Resources(program(*host_call(0, pattern, 1), 0x33, words=words))
                resources.record['pack_id'] = 30000
                resources.presentation = presentation
                session = Session(resources)
                session.advance()
                self.assertEqual(session.engine.dynamic_strings[0], expected)

    def test_only_a_brew_packs_formatted_lines_change(self):
        words, (destination, pattern, house) = text_words('                                ', 'You live in a(n) %s.',
                                                            'apartment')
        for pack, expected in ((31100, 'You live in an apartment.'), (5, 'You live in a(n) apartment.')):
            with self.subTest(pack=pack):
                resources = Resources(program(*host_call(22, destination, pattern, house), 0x33, words=words))
                resources.record['pack_id'] = pack
                session = Session(resources)
                session.advance()
                self.assertEqual(session.engine.read_text(session.vm, destination), expected)


if __name__ == '__main__':
    unittest.main()
