"""No provider calls or real credentials: final-preview feedback regressions."""
from html.parser import HTMLParser
import importlib
from pathlib import Path
import sys
import unittest

WORK = next(p for p in Path(__file__).resolve().parents if (p / 'gpt56_vnext').is_dir())
sys.path[:0] = [str(WORK), str(WORK / 'meow-web')]


class PreviewFeedbackTests(unittest.TestCase):
    def test_both_scoring_notes_link_to_readme_without_replacing_detection(self):
        class Links(HTMLParser):
            def __init__(self):
                super().__init__()
                self.links = []
            def handle_starttag(self, tag, attrs):
                value = dict(attrs)
                if tag == 'a' and value.get('class') == 'score-scale-link':
                    self.links.append(value)
        for path in (WORK / 'gpt56_vnext/web/index.html', WORK / 'meow-web/web/index.html'):
            if not path.exists():
                continue
            parser = Links()
            parser.feed(path.read_text(encoding='utf-8'))
            self.assertEqual(len(parser.links), 1)
            link = parser.links[0]
            self.assertEqual(link['href'], 'https://github.com/chen-006/meow-llm-detector#新旧版分数参考')
            self.assertEqual(link['target'], '_blank')
            self.assertEqual(set(link['rel'].split()), {'noopener', 'noreferrer'})

    def test_non_stream_bodies_are_not_misreported_as_interrupted_streams(self):
        for side in ('gpt56_vnext', 'meow_web'):
            try:
                protocol = importlib.import_module(side + '.protocol')
            except ModuleNotFoundError:
                continue  # Public desktop package does not include the website.
            models = importlib.import_module(side + '.model_list')
            for body in ('<html><title>Not an API endpoint</title></html>',
                         '{"error":{"code":"bad_route","message":"Use /api/v1"}}'):
                for mode in ('gpt', 'claude', 'chat'):
                    with self.subTest(side=side, mode=mode, body=body):
                        with self.assertRaises(protocol.RequestError) as got:
                            protocol.parse_stream(body, mode, protocol.SecretGuard())
                        error = got.exception.public()
                        self.assertEqual(error['code'], 'unexpected_response')
                        self.assertTrue(error['retryable'])
                        self.assertEqual(error['local']['source'], 'protocol')
                        self.assertTrue(error['upstream']['message'])
                with self.assertRaises(protocol.RequestError) as got:
                    models.parse_models(body, protocol.SecretGuard())
                self.assertEqual(got.exception.code, 'model_list_unavailable')
                self.assertTrue(got.exception.public()['upstream']['message'])

    def test_save_connection_is_outside_collapsed_options(self):
        class Layout(HTMLParser):
            depth = 0
            buttons = []
            def handle_starttag(self, tag, attrs):
                if tag == 'details':
                    self.depth += 1
                if dict(attrs).get('id') == 'save-current-connection':
                    self.buttons.append((tag, self.depth, dict(attrs).get('type')))
            def handle_endtag(self, tag):
                if tag == 'details':
                    self.depth -= 1
        parser = Layout()
        parser.feed((WORK / 'gpt56_vnext/web/index.html').read_text(encoding='utf-8'))
        self.assertEqual(parser.buttons, [('button', 0, 'button')])


if __name__ == '__main__':
    unittest.main()
