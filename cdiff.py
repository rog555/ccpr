#!/usr/bin/env python
import argparse
import difflib
from rich.console import Console
from rich.rule import Rule
from rich.style import Style


def print_diff(from_txt, to_txt, name=None):
    console = Console(highlight=False)
    if name is not None:
        console.print('[bold green]%s[/]' % name)
    from_lines = from_txt.splitlines()
    from_lines_stripped = [line.lstrip().rstrip() for line in from_lines]
    to_lines = to_txt.splitlines()
    to_lines_stripped = [line.lstrip().rstrip() for line in to_lines]
    diff = list(difflib._mdiff(
        from_lines_stripped, to_lines_stripped, context=3
    ))

    def leading(line):
        _leading = ''
        for i in range(len(line)):
            if line[i] in ' \t':
                _leading += line[i]
            else:
                break
        return _leading

    def print_line(code, from_lc, to_lc, line):
        colors = {
            '-': 'red',
            '+': 'green',
            ' ': 'white'
        }
        for x in '^+-':
            line = line.replace('\x00' + x, '[bold]')
            line = line.replace('\x01', '[/]')
        console.print(
            '[%s]%4s %4s: %s %s[/]' % (
                colors[code], from_lc, to_lc, code, line
            ),
            highlight=False
        )

    for (_from, _to, changed) in diff:
        if not all([_from, _to]):
            console.print(Rule(style=Style(color='white')))
            continue
        (from_lc, from_line, to_lc, to_line) = (*_from, *_to)
        if str(from_lc) != '':
            from_line = leading(from_lines[from_lc - 1]) + from_line
        if str(to_lc) != '':
            to_line = leading(to_lines[to_lc - 1]) + to_line
        if str(from_lc) == '':
            print_line('+', from_lc, to_lc, to_line)
        elif str(to_lc) == '':
            print_line('-', from_lc, to_lc, from_line)
        elif changed is True:
            print_line('-', from_lc, to_lc, from_line)
            print_line('+', from_lc, to_lc, to_line)
        else:
            print_line(' ', from_lc, to_lc, to_line)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('file1')
    ap.add_argument('file2')
    args = ap.parse_args()
    f1 = open(args.file1, 'r').read()
    f2 = open(args.file2, 'r').read()
    print_diff(f1, f2, args.file2)
