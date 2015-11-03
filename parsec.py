#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
A univeral Python parser combinator library inspirted by Parsec library of Haskell.
'''

__author__ = 'He Tao, sighingnow@gmail.com'
__version__ = '1.0.0'

import re
from collections import namedtuple

##########################################################################
## Text.Parsec.Error
##########################################################################

class ParseError(RuntimeError):
    '''Parser error.'''
    def __init__(self, expected, text, index):
        super().__init__()
        self.expected = expected
        self.text = text
        self.index = index

    def loc(self):
        '''Locate the error position in the source code text.'''

        def loc_info(text, index):
            '''Location of `index` in source code `text`.'''
            if index > len(text):
                raise ValueError('Invalid index.')
            line, last_ln = text.count('\n', 0, index), text.rfind('\n', 0, index)
            col = index - (last_ln+1)
            return (line, col)

        try:
            return '{}:{}'.format(*loc_info(self.text, self.index))
        except ValueError:
            return '<out of bounds index {!r}>'.format(self.index)

    def __str__(self):
        return 'excepted {} at {}'.format(self.expected, self.loc())

class Value(namedtuple('Value', 'status index value expected')):
    '''Represent the result of the Parser.'''
    @staticmethod
    def success(index, actual):
        '''Create success value.'''
        return Value(True, index, actual, None)

    @staticmethod
    def failure(index, expected):
        '''Create failure value.'''
        return Value(False, index, None, expected)

    def aggregate(self, other=None):
        '''collect the furthest failure from self and other.'''
        if not self.status:
            return self
        if not other:
            return self
        if not other.status:
            return other
        return Value(True, self.index, self.value+other.value, None)

    def __str__(self):
        return 'Value: state: {},  @index: {}, values: {}, expected: {}'.format(
            self.status, self.index, self.value, self.expected)

##########################################################################
## Text.Parsec.Prim
##########################################################################

class Parser(object):
    '''
    A Parser is an object that wraps a function to do the parsing work.
    Arguments of the function should be a string to be parsed and the index on
    which to begin parsing.
    The function should return either Value.success(next_index, value) if
    parsing successfully, or Value.failure(index, expected) on the failure.
    '''
    def __init__(self, fn):
        '''`fn` is the function to wrap.'''
        self.fn = fn

    def __call__(self, text, index):
        '''call wrapped function.'''
        return self.fn(text, index)

    def parse(self, text):
        '''Parser a given string `text`.'''
        return self.parse_partial(text)[0]

    def parse_partial(self, text):
        '''Parse the longest possible prefix of a given string.
        Return a tuple of the result value and the rest of the string.
        If failed, raise a ParseError. '''
        if not isinstance(text, str):
            raise TypeError('Can only parsing string but got {!r}'.format(text))
        res = self(text, 0)
        if res.status:
            return (res.value, text[res.index:])
        else:
            raise ParseError(res.expected, text, res.index)

    def parse_strict(self, text):
        '''Parse the longest possible prefix of the entire given string.
        If the parser worked successfully and NONE text was rested, return the
        result value, else raise a ParseError.
        The difference between `parse` and `parse_strict` is that whether entire
        given text must be used.'''
        return (self << eof()).parse_partial(text)[0]

    def bind(self, fn):
        '''This is the monadic binding operation. Returns a parser which, if
        parser is successful, passes the result to fn, and continues with the
        parser returned from fn.'''
        @Parser
        def bind_parser(text, index):
            res = self(text, index)
            return res if not res.status else fn(res.value)(text, res.index)
        return bind_parser

    def compose(self, other):
        '''(>>) Sequentially compose two actions, discarding any value produced
        by the first.'''
        @Parser
        def compose_parser(text, index):
            res = self(text, index)
            return res if not res.status else other(text, res.index)
        return compose_parser

    def joint(self, other):
        '''(+) Joint two parsers into one. Return the aggregate of two results
        from this two parser.'''
        @Parser
        def joint_parser(text, index):
            fstres = self(text, index)
            if not fstres:
                return fstres
            sndres = other(text, fstres.index)
            if not sndres:
                return sndres
            return fstres.aggregate(sndres)
        return joint_parser

    def choice(self, other):
        '''(|) This combinator implements choice. The parser p | q first applies p.
        If it succeeds, the value of p is returned.
        If p fails **without consuming any input**, parser q is tried.
        NOTICE: without backtrack.'''
        @Parser
        def choice_parser(text, index):
            res = self(text, index)
            return res if res.status or res.index != index else other(text, index)
        return choice_parser

    def try_choice(self, other):
        '''(^) Choice with backtrack. This combinator is used whenever arbitrary
        look ahead is needed. The parser p || q first applies p, if it success,
        the value of p is returned. If p fails, it pretends that it hasn't consumed
        any input, and then parser q is tried.
        '''
        @Parser
        def try_choice_parser(text, index):
            res = self(text, index)
            return res if res.status else other(text, index)
        return try_choice_parser

    def ends_with(self, other):
        '''(<<) Ends with a specified parser, and the end parser hasn't consumed
        any input.'''
        @Parser
        def ends_with_parser(text, index):
            res = self(text, index)
            if not res.status:
                return res
            end = other(text, res.index)
            if end.status:
                return res
            else:
                return Value.failure(end.index, 'ends with {}'.format(end.expected))
        return ends_with_parser

    def parsecmap(self, fn):
        '''Returns a parser that transforms the produced value of parser with `fn`.'''
        return self.bind(lambda res: Parser(lambda _, index: Value.success(index, fn(res))))

    def times(self, mint, maxt=None):
        '''Repeat a parser between `mint` and `maxt` times. DO AS MUCH MATCH AS IT CAN.
        Return a list of values.'''
        maxt = maxt if maxt else mint
        @Parser
        def times_parser(text, index):
            cnt, values, res = 0, Value.success(index, []), None
            while cnt < maxt:
                res = self(text, index)
                if res.status:
                    values = values.aggregate(Value.success(res.index, [res.value]))
                    index, cnt = res.index, cnt+1
                else:
                    if cnt >= mint:
                        break
                    else:
                        return res ## failed, throw exception.
                if cnt >= maxt: ## finish.
                    break
            return values
        return times_parser

    def count(self, n):
        '''`count n p` parses n occurrences of p. If n is smaller or equal to zero,
        the parser equals to return []. Returns a list of n values returned by p.'''
        return self.times(n, n)

    def many(self):
        '''Repeat a parser 0 to infinity times. DO AS MUCH MATCH AS IT CAN.
        Return a list of values.'''
        return self.times(0, float('inf'))

    def many1(self):
        '''Repeat a parser 1 to infinity times. DO AS MUCH MATCH AS IT CAN.
        Return a list of values.'''
        return self.times(1, float('inf'))

    def __or__(self, other):
        '''Implements the `(|)` operator.'''
        return self.choice(other)

    def __xor__(self, other):
        '''Implements the `(^)` operator.'''
        return self.try_choice(other)

    def __add__(self, other):
        '''Implements the `(+)` operator.'''
        return self.joint(other)

    def __rshift__(self, other):
        '''Implements the `(>>)` operator.'''
        return self.compose(other)

    def __irshift__(self, other):
        '''Implements the `(>>=)` operator.'''
        return self.bind(other)

    def __lshift__(self, other):
        '''Implements the `(<<)` operator.'''
        return self.ends_with(other)

def parse(p, text, index):
    '''Parse a string and return the result or raise a ParseError.'''
    return p.parse(text, index)

def bind(p, fn):
    '''Bind two parsers, implements the operator of `(>>=)`.'''
    return p.bind(fn)

def compose(pa, pb):
    '''Compose two parsers, implements the operator of `(>>)`.'''
    return pa.compose(pb)

def joint(pa, pb):
    '''Joint two parsers, implements the operator of `(>>)`.'''
    return pa.joint(pb)

def choice(pa, pb):
    '''Choice one from two parsers, implements the operator of `(|)`.'''
    return pa.choice(pb)

def try_choice(pa, pb):
    '''Choice one from two parsers with backtrack, implements the operator of `(^)`.'''
    return pa.try_choice(pb)

def parsecmap(p, fn):
    '''Returns a parser that transforms the produced value of parser with `fn`.'''
    return p.map(fn)

def times(p, mint, maxt):
    '''Repeat a parser between `mint` and `maxt` times. DO AS MUCH MATCH AS IT CAN.
    Return a list of values.'''
    return p.times(mint, maxt)

def count(p, n):
    '''`count n p` parses n occurrences of p. If n is smaller or equal to zero,
    the parser equals to return []. Returns a list of n values returned by p.'''
    return p.count(n)

def many(p):
    '''Repeat a parser 0 to infinity times. DO AS MUCH MATCH AS IT CAN.
    Return a list of values.'''
    return p.many()

def many1(p):
    '''Repeat a parser 1 to infinity times. DO AS MUCH MATCH AS IT CAN.
    Return a list of values.'''
    return p.many1()

##########################################################################
## Text.Parsec.Char
##########################################################################

def one_of(s):
    '''Parser a char from specified string.'''
    @Parser
    def one_of_parser(text, index=0):
        if index < len(text) and text[index] in s:
            return Value.success(index+1, text[index])
        else:
            return Value.failure(index, 'one of {}'.format(s))
    return one_of_parser

def none_of(s):
    '''Parser a char NOT from specified string.'''
    @Parser
    def none_of_parser(text, index=0):
        if index < len(text) and text[index] not in s:
            return Value.success(index+1, text[index])
        else:
            return Value.failure(index, 'none of {}'.format(s))
    return none_of_parser

def space():
    '''Parser a whitespace character.'''
    @Parser
    def space_parser(text, index=0):
        if index < len(text) and text[index].isspace():
            return Value.success(index+1, text[index])
        else:
            return Value.failure(index, 'one space')
    return space_parser

def spaces():
    '''Parser zero or more whitespace characters.'''
    return many(space)

def letter():
    '''Parse a letter in alphabet.'''
    @Parser
    def letter_parser(text, index=0):
        if index < len(text) and text[index].isalpha():
            return Value.success(index+1, text[index])
        else:
            return Value.failure(index, 'a letter')
    return letter_parser

def digit():
    '''Parse a digit character.'''
    @Parser
    def digit_parser(text, index=0):
        if index < len(text) and text[index].isdigit():
            return Value.success(index+1, text[index])
        else:
            return Value.failure(index, 'a digit')
    return digit_parser

def eof():
    '''Parser EOF flag of a string.'''
    @Parser
    def eof_parser(text, index=0):
        if index >= len(text):
            return Value.success(index, None)
        else:
            return Value.failure(index, 'EOF')
    return eof_parser

def string(s):
    '''Parser a string.'''
    slen = len(s)
    @Parser
    def string_parser(text, index=0):
        if text[index:index+slen] == s:
            return Value.success(index+slen, s)
        else:
            return Value.failure(index, s)
    return string_parser

def regex(exp, flags=0):
    '''Parser according to a regular expression.'''
    if isinstance(exp, str):
        exp = re.compile(exp, flags)
    @Parser
    def regex_parser(text, index):
        match = exp.match(text, index)
        if match:
            return Value.success(match.end(), match.group(0))
        else:
            return Value.failure(index, exp.pattern)
    return regex_parser

