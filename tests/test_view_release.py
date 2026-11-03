"""An episode's view lets go when the next starts (episode_thumbnails.release_episode_caches)."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'packages'


class StackedCacheTests(unittest.TestCase):
    def test_no_method_has_two_lru_caches(self):
        # cache_clear reaches only the outer one, so the inner keeps its `self` and every view it saw: note_image's two
        # kept each episode's whole view alive (about 115 MB an episode, on a phone), while the method its first
        # decorator had been written for, frame_native, went uncached.
        stacked = []
        for path in ROOT.rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    caches = [d for d in node.decorator_list if 'lru_cache' in ast.unparse(d) or ast.unparse(d) == 'cache'
                              or ast.unparse(d).startswith('cache(')]
                    if len(caches) > 1:
                        stacked.append(f'{path.name}:{node.lineno} {node.name}')
        self.assertEqual(stacked, [])

    def test_the_frames_are_cached_once(self):
        from exp_runtime.desktop_dialogue import DialogueRenderer
        self.assertTrue(callable(getattr(DialogueRenderer.frame_native, 'cache_clear', None)))
        self.assertFalse(hasattr(DialogueRenderer.note_image.__wrapped__, 'cache_clear'))


if __name__ == '__main__':
    unittest.main()
