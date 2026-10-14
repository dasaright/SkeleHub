"""Static contract checks only; Windows Au3Check and live GW tests are separate."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'Skelefarm.au3').read_text()
API = '\n'.join(p.read_text(encoding='utf-8-sig', errors='replace') for p in (ROOT / 'vendor/GwAu3/API').rglob('*.au3'))


class WorkerContractTests(unittest.TestCase):
    def test_all_gwau3_calls_exist(self):
        functions = {m.lower() for m in re.findall(r'^Func\s+(\w+)\(', API, re.M | re.I)}
        calls = set(re.findall(r'\b((?:Agent|Map|Party|Skill|Item|Game|Chat|Attribute|Core|Ui)_\w+)\(', SOURCE))
        self.assertGreater(len(calls), 30)
        self.assertEqual(sorted(c for c in calls if c.lower() not in functions), [])

    def test_no_removed_includes_or_legacy_calls(self):
        for legacy in ('AccountInfo.au3', '..\\gwApi', 'InvitePlayer(', 'GetIsPartyLeader(', 'TravelTo(', 'UseSkillEx('):
            self.assertNotIn(legacy, SOURCE)

    def test_function_and_block_balance(self):
        self.assertEqual(len(re.findall(r'^Func ', SOURCE, re.M)), len(re.findall(r'^EndFunc', SOURCE, re.M)))
        stack = []
        for line in SOURCE.splitlines():
            line = line.strip()
            if not line or line.startswith(';'):
                continue
            if re.match(r'If .* Then\s*(;.*)?$', line, re.I):
                stack.append('if')
            elif re.match(r'For\s', line, re.I):
                stack.append('for')
            elif re.match(r'While\s', line, re.I):
                stack.append('while')
            elif re.match(r'Switch\s', line, re.I):
                stack.append('switch')
            elif line.lower() in ('endif', 'next', 'wend', 'endswitch'):
                expected = {'endif': 'if', 'next': 'for', 'wend': 'while', 'endswitch': 'switch'}[line.lower()]
                self.assertEqual(stack.pop(), expected, line)
        self.assertEqual(stack, [])

    def test_npc_models_and_build_are_source_backed(self):
        self.assertIn('SkeletonModel1", 2392', SOURCE)
        self.assertIn('GrenthModel", 1995', SOURCE)
        self.assertIn('[1948, 1043, 294, 952, 2358, 2353, 1041, 2136]', SOURCE)
        for skill in (1948, 1043, 294, 952, 2358, 2353, 1041, 2136):
            self.assertRegex(API, rf'\[{skill}, "')


if __name__ == '__main__':
    unittest.main()
