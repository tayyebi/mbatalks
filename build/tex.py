"""A tiny LaTeX-subset renderer.

The book only uses a handful of constructs — fractions, sums, upright names,
sub/superscripts — so this replaces KaTeX (a 4MB dependency plus twenty font
files) with plain HTML that the stylesheet lays out. Anything outside the
subset raises, so the build fails loudly rather than shipping a broken formula.
"""

import re
from html import escape

SYMBOLS = {
    'times': '×', 'cdot': '⋅', 'div': '÷', 'pm': '±',
    'sum': '∑', 'prod': '∏', 'leq': '≤', 'geq': '≥',
    'neq': '≠', 'approx': '≈', 'to': '→', 'infty': '∞',
    'alpha': 'α', 'beta': 'β', 'sigma': 'σ', 'mu': 'μ',
}
SPACES = {',': ' ', ';': ' ', 'quad': ' ', 'qquad': '  '}
UPRIGHT = ('mathrm', 'text', 'operatorname')
BIG = ('sum', 'prod')  # take limits above/below when displayed

TOKEN = re.compile(r"\\[A-Za-z]+|\\.|[{}_^]|\s+|[^\\{}_^\s]")


def _tokens(src):
    pos, out = 0, []
    while pos < len(src):
        m = TOKEN.match(src, pos)
        if not m:
            raise ValueError(f'cannot tokenize at {src[pos:pos + 12]!r}')
        out.append(m.group())
        pos = m.end()
    return out


class _Parser:
    def __init__(self, tokens):
        self.t, self.i = tokens, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def group(self):
        """One argument: a braced group, or a single token."""
        tok = self.next()
        if tok is None:
            raise ValueError('formula ends where an argument was expected')
        if tok == '{':
            return self.nodes(stop='}')
        return [self.atom(tok)]

    def nodes(self, stop=None):
        out = []
        while True:
            tok = self.peek()
            if tok is None:
                if stop:
                    raise ValueError('unbalanced {')
                return out
            if tok == stop:
                self.next()
                return out
            self.next()
            if tok in ('_', '^'):
                if not out:
                    raise ValueError(f'{tok} with nothing to attach to')
                key = 'sub' if tok == '_' else 'sup'
                base = out[-1]
                if not isinstance(base, dict):
                    base = out[-1] = {'kind': 'run', 'body': [base]}
                if key in base:
                    raise ValueError(f'two {key}scripts on one base')
                base[key] = self.group()
                continue
            out.append(self.atom(tok))

    def atom(self, tok):
        if tok == '}':
            raise ValueError('unbalanced }')
        if tok == '{':
            return {'kind': 'run', 'body': self.nodes(stop='}')}
        if tok.startswith('\\'):
            name = tok[1:]
            if name == 'frac':
                return {'kind': 'frac', 'num': self.group(), 'den': self.group()}
            if name in UPRIGHT:
                return {'kind': 'upright', 'body': self.group()}
            if name in SPACES:
                return {'kind': 'text', 'text': SPACES[name]}
            if name in SYMBOLS:
                return {'kind': 'op' if name in BIG else 'text', 'text': SYMBOLS[name]}
            if len(name) == 1 and not name.isalpha():
                return {'kind': 'text', 'text': name}  # \% \& \$ …
            raise ValueError(f'unsupported command \\{name}')
        if tok.isspace():
            return {'kind': 'text', 'text': ' '}
        if tok.isalpha():
            return {'kind': 'var', 'text': tok}
        return {'kind': 'text', 'text': tok}


def _html(nodes, upright=False):
    return ''.join(_node(n, upright) for n in nodes)


def _scripts(node, upright):
    sup = f'<sup>{_html(node["sup"], upright)}</sup>' if 'sup' in node else ''
    sub = f'<sub>{_html(node["sub"], upright)}</sub>' if 'sub' in node else ''
    # Both at once stack vertically instead of running side by side.
    if sup and sub:
        return f'<span class="scripts">{sup}{sub}</span>'
    return sup + sub


def _node(node, upright):
    kind = node['kind']
    if kind == 'frac':
        return (f'<span class="frac"><span class="num">{_html(node["num"], upright)}</span>'
                f'<span class="den">{_html(node["den"], upright)}</span></span>'
                + _scripts(node, upright))
    if kind == 'upright':
        return f'<span class="upr">{_html(node["body"], True)}</span>' + _scripts(node, upright)
    if kind == 'run':
        return _html(node['body'], upright) + _scripts(node, upright)
    if kind == 'op':
        # A big operator carries its limits above and below when displayed.
        under = f'<span class="lim">{_html(node["sub"], upright)}</span>' if 'sub' in node else ''
        over = f'<span class="lim">{_html(node["sup"], upright)}</span>' if 'sup' in node else ''
        return (f'<span class="bigop">{over}<span class="op">{escape(node["text"])}</span>{under}</span>')
    text = escape('\u2212' if node['text'] == '-' else node['text'])
    if kind == 'var' and not upright and len(text) == 1:
        text = f'<i>{text}</i>'
    return text + _scripts(node, upright)


def render(src, display=False):
    """LaTeX source -> an HTML span. Raises ValueError on anything unsupported."""
    nodes = _Parser(_tokens(src.strip())).nodes()
    cls = 'math math-display' if display else 'math math-inline'
    return f'<span class="{cls}" dir="ltr">{_html(nodes)}</span>'
