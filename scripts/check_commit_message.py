#!/usr/bin/env python3
"""Check a commit message or PR title against the git-commit-helper skill.

The approved gitmoji/type pairs are read from the table in
.claude/skills/git-commit-helper/SKILL.md, so the skill and this check
cannot drift apart. The emoji must match the table exactly, including the
variation selector U+FE0F that some of them carry.

Usage:
  check_commit_message.py --file <commit-msg-file>   (githook)
  check_commit_message.py --title "<pr title>"       (CI)
"""
import argparse
import pathlib
import re
import sys

SKILL = pathlib.Path(__file__).resolve().parent.parent / '.claude/skills/git-commit-helper/SKILL.md'
ROW = re.compile(r'^\|\s*(\S+)\s*\|\s*`([a-z]+)`\s*\|')
SUBJECT = re.compile(r'^(?P<emoji>\S+) (?P<type>[a-z]+)\((?P<domain>[a-z0-9]+(?:[-/][a-z0-9]+)*)\): (?P<title>[a-z].*)$')
SESSION = re.compile(r'(Claude-Session:|claude\.ai/code/session|/sessions?/[0-9a-f-]{8,})', re.I)
ASSISTANT_TRAILER = re.compile(
    r'^(Co-authored-by|Generated-by|Assisted-by):.*(claude|anthropic|copilot|codex|openai|gpt|gemini|cursor|kiro|\[bot\]|noreply@)',
    re.I | re.M,
)


def load_pairs(skill=SKILL):
    pairs = {}
    for line in skill.read_text(encoding='utf-8').splitlines():
        m = ROW.match(line)
        if m:
            pairs[m.group(2)] = m.group(1)
    if not pairs:
        raise SystemExit(f'No emoji/type table found in {skill}')
    return pairs


def check_subject(subject, pairs):
    errors = []
    m = SUBJECT.match(subject)
    if not m:
        return ['Subject must look like "<gitmoji> <type>(<domain>): <title>" '
                '(lowercase kebab-case domain, title starts with a lowercase letter)']
    t = m.group('type')
    if t not in pairs:
        errors.append(f'Unknown type "{t}". Approved: {", ".join(sorted(pairs))}')
    elif m.group('emoji') != pairs[t]:
        got, want = m.group('emoji'), pairs[t]
        hint = ''
        if got.replace('\ufe0f', '') == want.replace('\ufe0f', ''):
            hint = ' (same symbol, but the variation selector U+FE0F differs; copy the emoji from the table)'
        errors.append(f'Type "{t}" must use {want}, not {got}{hint}')
    return errors


def check_message(text, pairs):
    lines = [l for l in text.splitlines() if not l.startswith('#')]
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return ['Empty commit message']
    subject = lines[0]
    if subject.startswith('Merge ') or subject.startswith('Revert "'):
        return []
    errors = check_subject(subject, pairs)
    if len(lines) > 1 and lines[1].strip():
        errors.append('Leave a blank line between the subject and the description')
    body = '\n'.join(lines)
    if SESSION.search(body):
        errors.append('Remove session metadata or session links; this repository is public')
    if ASSISTANT_TRAILER.search(body):
        errors.append('Remove assistant co-author or generated-by trailers')
    return errors


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--file')
    g.add_argument('--title')
    args = ap.parse_args()
    pairs = load_pairs()
    if args.file:
        text = pathlib.Path(args.file).read_text(encoding='utf-8')
    else:
        text = args.title
    errors = check_message(text, pairs)
    if errors:
        print('Commit message rejected:', file=sys.stderr)
        for e in errors:
            print(f'  - {e}', file=sys.stderr)
        print('See .claude/skills/git-commit-helper/SKILL.md', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
