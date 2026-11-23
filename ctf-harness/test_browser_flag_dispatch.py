"""Offline test: prove agent flag dispatch uses browser, not JSON grader.
No API key, Docker, network, or live CTF submissions required.
Run from ctf-harness: python test_browser_flag_dispatch.py
"""
from harness.agent import CTFAgent, AgentResult
from harness.platform.base import Challenge

class ForbiddenLocalGrader:
    def submit_flag(self, *_):
        raise AssertionError('FAILED: local JSON/hash grader was called')

class FakeBrowser:
    def __init__(self, status):
        self.status = status
        self.flags = []
    def submit_flag(self, flag):
        self.flags.append(flag)
        return {'status': self.status, 'after_text': 'Simulated website: ' + self.status}
    def read_page(self):
        return 'Visible webpage'
    def click_text(self, text):
        return 'Clicked ' + text

class FakeSandbox:
    def exec(self, command):
        return 0, 'offline analysis output'

ch = Challenge(id='001', name='Base Case', category='crypto', description='')
for status, expected_solved, expected_stop in [('accepted', True, True), ('rejected', False, False), ('unknown', False, False)]:
    browser = FakeBrowser(status)
    agent = CTFAgent(client=None, model='unused', sandbox=FakeSandbox(),
        platform=ForbiddenLocalGrader(), challenge=ch,
        flag_regex=r'FGCU\{.*?\}', max_steps=5, max_wall_seconds=60,
        browser=browser)
    result = AgentResult(ch.id, ch.name, ch.category)
    obs, stop = agent._dispatch('submit_flag', {'flag': 'FGCU{test}'}, result)
    assert result.solved is expected_solved, (status, result)
    assert stop is expected_stop, (status, stop)
    assert browser.flags == ['FGCU{test}']
    assert status.upper() in obs
    print(f'PASS: {status}: browser called, local grader blocked, solved={result.solved}')
print('ALL TESTS PASSED (offline simulation; no real submission was made)')
