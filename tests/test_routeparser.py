"""
Tests for :mod:`flaschenetikett.routeparser`
"""

from compiler import ast
import mock
from unittest import TestCase

from flaschenetikett.routeparser import flatten_name, Route


class RouteTestCase(TestCase):
    """
    Tests for :mod:`flaschenetikett.routeparser.Route`
    """
    def setUp(self):
        self.ast_node = mock.MagicMock(spec=['doc', 'name'])

    def test_construct_with_dictionary(self):
        """
        Passing a full dictionary to the constructor sets the right variables
        """
        dictionary = {
            'rule': '/',
            'methods': ['GET'],
            'ast_node': self.ast_node,
            'decorators': [1, 2, 3],
            'werkzeug_kwargs': {'what': 'the'}
        }
        r = Route(**dictionary)
        for key, value in dictionary.iteritems():
            if key != 'ast_node':
                self.assertEqual(getattr(r, key), value)

    def test_rule_parsing(self):
        """
        ``/meh/<string:name1>/<int:name2>/something`` parses into a pretty path
        with a dictionary mapping ``name1`` and ``name2`` to their types
        """
        r = Route('/meh/<string(length=2):name1>/<int(min=3):name2>/something',
                  ['GET'], self.ast_node)
        self.assertEqual(r.path, '/meh/{name1}/{name2}/something')
        self.assertEqual(r.path_types,
                         {'name1': 'string(length=2)', 'name2': 'int(min=3)'})

    def test_docstring(self):
        """
        Docstring should be cleaned up so that second line indentations are
        removed and tabs are replaced with spaces
        """
        self.ast_node.doc = """
            indented indented
            \tmore indented
            """
        r = Route('/', ['GET'], self.ast_node)
        self.assertEqual(r.docstring, 'indented indented\n    more indented')

    def test_handler_name(self):
        """
        The handler name property returns the function AST node's name
        """
        self.ast_node.name = 'handler'
        r = Route('/', ['GET'], self.ast_node)
        self.assertEqual(r.handler_name, 'handler')

    def test_title_parses_camel_cased(self):
        """
        Camel cased handler names are split on capital word boundaries, and
        abbreviations are ignored
        """
        name_and_expected = [
            ('getHTTPResponseCode', 'Get HTTP response code'),
            ('handler', 'Handler'),
            ('GoGetStuff', 'Go get stuff'),
            ('Handle92Numbers', 'Handle 92 numbers'),
            ('__ignoreEndUnderscores__', 'Ignore end underscores')
        ]
        for name, expected in name_and_expected:
            self.ast_node.name = name
            r = Route('/', ['GET'], self.ast_node)
            self.assertEqual(r.title, expected)

    def test_title_splits_underscored_names(self):
        """
        Underscored handler names are split on underscores, even if there is
        some camel casing in the middle
        """
        name_and_expected = [
            ('get_HTTP_Response_Code', 'Get HTTP response code'),
            ('mixedCamel_and_underscores', 'MixedCamel and underscores'),
            ('camel_case_InTheMiddle', 'Camel case InTheMiddle'),
            ('__ignore_end_underscores__', 'Ignore end underscores')
        ]
        for name, expected in name_and_expected:
            self.ast_node.name = name
            r = Route('/', ['GET'], self.ast_node)
            self.assertEqual(r.title, expected)


class FlattenNameTestCase(TestCase):
    """
    Tests for :mod:`flaschenetikett.routeparser.flatten_name`
    """
    def test_base_case(self):
        """
        Flattening just a :class:`ast.Name` returns the text
        """
        self.assertEqual(flatten_name(ast.Name('hey')), 'hey')

    def test_flatten_getattr(self):
        """
        Flattening a :class:`ast.Getattr` returns a module.name
        """
        self.assertEqual(flatten_name(ast.Getattr(ast.Name('mod'), 'attr')),
                         'mod.attr')

    def test_flatten_nested_getattr(self):
        """
        Flattening a nested :class:`ast.Getattr` returns a module.module...name
        """
        nested = ast.Getattr(ast.Getattr(ast.Name('mod1'), 'mod2'), 'attr')
        self.assertEqual(flatten_name(nested), 'mod1.mod2.attr')
