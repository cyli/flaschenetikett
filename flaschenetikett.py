"""
Parses routing information from modules containing Bottle/Flask/Klein handlers
"""

from compiler import ast, parseFile, visitor, walk
from inspect import cleandoc
from operator import add, sub
import re
from urlparse import urljoin
import warnings

_seq_types = {
    ast.Tuple: tuple,
    ast.List: list
}

_map_types = {ast.Dict: dict}

_oper_types = {
    ast.Add: add,
    ast.Sub: sub
}

_builtin_consts = {
    "True": True,
    "False": False,
    "None": None,
}

_route_decorator_name = re.compile('(.+\.)?route$')
_fragment_finder = re.compile('^\<(?P<type>\S+):(?P<name>\S+)\>$')
_camel_cased = (re.compile('(.)([A-Z][a-z]+)'),
                re.compile('([a-z0-9])([A-Z])'),
                re.compile('([a-zA-Z])([0-9])'))


class NonGlobalError(Exception):
    """
    Exception raised when trying to look up a variable, but the variable is
    not a global variable.
    """


class OperationException(Exception):
    """
    Exception raised when trying to assemble some type of operation
    """


class AssemblyError(Exception):
    """
    Other exception if attempting to assemble things fails
    """


def flatten_name(name_node):
    """
    Flattens a node into a string, but only if it is a L{`ast.Name`} or
    L{ast.Getattr} or C{str}
    """
    if isinstance(name_node, str):
        return name_node
    elif isinstance(name_node, ast.Name):
        return name_node.name
    elif isinstance(name_node, ast.Getattr):
        return '{0}.{1}'.format(flatten_name(name_node.expr),
                                name_node.attrname)
    else:
        raise Exception(
            "Cannot flatten a node of type {0}".format(name_node.__class__))


class Route(object):
    """
    An object that represents a werkzeug route to be documented.
    """
    def __init__(self, rule, methods, ast_node, werkzeug_kwargs=None,
                 decorators=None):
        self.rule = rule
        self.methods = methods
        self.werkzeug_kwargs = werkzeug_kwargs or {}
        self.decorators = decorators or []

        self._ast_node = ast_node
        self._path = None
        self._path_types = None
        self._docstring = None
        self._title = None

    def _pretty_parse_rule(self):
        """
        Parses the werkzeug rule into a pretty path (instead of
        C{/<string:name>}, C{/{name}}) and a dictionary that maps the
        partial path fragment names with the type

        Only ``int`` and ``string`` types are supported.

        TODO: support other types, support additional type parameters like
            length for strings, min/max for ints, etc.
        """
        self._path_types = {}
        fragments = self.rule.split('/')

        for i in range(len(fragments)):
            match = _fragment_finder.search(fragments[i])
            if match:
                name_then_type = match.groups()[::-1]
                self._path_types.update([name_then_type])
                fragments[i] = "{{{0}}}".format(name_then_type[0])

        self._path = '/'.join(fragments)

    @property
    def path(self):
        """
        A pretty version of the werkzeug rule.  Rather than C{/<string:name>},
        path will contain C{/{name}}
        """
        if self._path is None:
            self._pretty_parse_rule()
        return self._path

    @property
    def path_types(self):
        """
        A dictionary mapping the names of parameters in the path to their types
        (which foor now can only be ints and strings)
        """
        if self._path_types is None:
            self._pretty_parse_rule()
        return self._path_types

    @property
    def docstring(self):
        """
        The docstring for the handler associated with the route
        """
        if self._docstring is None:
            self._docstring = cleandoc(self._ast_node.doc)
            if self._docstring is None:
                self._docstring = ""

        return self._docstring

    @property
    def handler_name(self):
        """
        The name of the handler
        """
        return self._ast_node.name

    @property
    def title(self):
        """
        Pretty-printed name of the handler - the either camel-cased or
        underscored handler name is split into words, with the first word
        capitalized.
        """
        if self._title is None:
            self._title = self._ast_node.name.strip('_')

            # if camel-cased, make it underscored
            if '_' not in self._title:
                for camel_cased in _camel_cased:
                    self._title = camel_cased.sub(r'\1_\2', self._title)

            # replace underscores with spaces and capitalize
            words = self._title.split('_')

            def _maybe_lower(word):
                if word.isupper():
                    return word
                return word.lower()

            def _maybe_capitalize(word):
                if word.islower():
                    return word.capitalize()
                return '{0}{1}'.format(word[0].upper(), word[1:])

            self._title = ' '.join(
                [_maybe_capitalize(words[0])] +
                [_maybe_lower(word) for word in words[1:]])

        return self._title


class _RouteFindingASTVisitor(visitor.ASTVisitor):
    """
    A visitor for a parsed AST which finds Flask/Klein/Bottle routes, which
    are handlers decorated by a C{@route} or C{@app.route} or some sort of
    decorator, containing a URL pattern that is then given to a
    L{werkzeug.routing.Rule}.

    This assumes that the C{@route} handlers are functions on a particular
    module, rather than methods on a class.

    @ivar routes: a list of found routes encapsulated as
        L{flaschenetikett.Route} objects
    @type routes: C{list} of L{flaschenetikett.Route}

    @ivar globals: a list of the module's global variables and imports,
        so that variable used in the decorators can be looked up
    @type globals: C{dict}

    @ivar prepath: the path to append to all the rules/paths
    @type prepath: C{str}
    """

    def __init__(self, routes, module_globals=None, prepath=''):
        visitor.ASTVisitor.__init__(self)
        self.routes = routes
        self.globals = module_globals or {}
        self.prepath = prepath

    def default(self, node):
        """
        By default, ignore the node (no-op)
        """

    def doRecurse(self, node):
        """
        Recurse down to get process child nodes
        """
        for n in node.getChildNodes():
            self.dispatch(n)

    visitStmt = visitModule = doRecurse

    def visitFunction(self, node):
        """
        Handle functions, which could be routes
        """
        if hasattr(node, 'decorators') and node.decorators:
            try:
                decorators = [self.flattenDecorator(decorator) for decorator in
                              node.decorators]
                route_decorator = [flat for flat in decorators if
                                   _route_decorator_name.match(flat['name'])]
                if len(route_decorator) > 0:
                    decorators.remove(route_decorator[0])
                    info = self.analyzeRoute(route_decorator[0])
                    info['ast_node'] = node
                    info['decorators'] = decorators
                    self.routes.append(Route(**info))
            except Exception as e:
                warnings.warn(
                    "Ignoring {0!r} due to exception {1!r}".format(node, e))

    def analyzeRoute(self, route):
        """
        Takes one flattened route decorator and produces dictionary instead
        containing the path/rule, the methods, and any other keyword args
        that get passed to a werkzeug rule.

        @param route: something produced by L{flattenDecorator}
        @type route: C{dict}

        @return: dictionary containing the the rule, the methods, and the other
            keyword arguments
        @rtype: C{dict}
        """
        fragments = route['args'][0].split('/')
        fragments = [part for part in fragments if part.strip()]
        url = urljoin('http://{0}'.format(self.prepath),
                      '/'.join(fragments))[7:]
        if not url.startswith('/'):
            url = '/{0}'.format(url)

        info = {
            'rule': url,
            'methods': route['kwargs'].get('methods', ['GET']),
            'werkzeug_kwargs': route['kwargs']
        }
        if 'methods' in info['werkzeug_kwargs']:
            del info['werkzeug_kwargs']['methods']
        return info

    def flattenDecorator(self, decorator):
        """
        Takes a decorator node and turns it into a flattened dictionary
        containing the name, the arguments to the decorator, and the keyword
        arguments to the decorator, all hopefully eval-ed.

        @param decorator: the decorator AST node
        @type decorator: L{compiler.ast.Node}

        @return: C{dict}
        """
        flattened = {}
        nodes = decorator.getChildren()

        # first child should be the name
        flattened['name'] = flatten_name(nodes[0])
        flattened['args'] = []
        flattened['kwargs'] = {}
        for node in nodes[1:]:
            if isinstance(node, ast.Keyword):
                flattened['kwargs'][node.name] = self.eval(node.expr)
            elif node is not None:
                flattened['args'].append(self.eval(node))
        return flattened

    def eval(self, node):
        """
        Recursively assemble parsed ast node, assuming that the node has
        no function call (although this can probably be supported at some
        point)

        @param node: the AST node
        @type node: L{compiler.ast.Node}

        @return: value that the node evaluates to
        """
        # Constant - return the value
        if node.__class__ == ast.Const:
            return node.value

        # sequences - map the values on to the appropriate python built-in
        elif node.__class__ in _seq_types:
            args = map(self.eval, node.getChildren())
            return _seq_types[node.__class__](args)

        # dictionaries - map the values on to the appropriate python built-in
        elif node.__class__ in _map_types:
            keys, values = zip(*node.items)
            keys = map(self.eval, keys)
            values = map(self.eval, values)
            return _map_types[node.__class__](zip(keys, values))

        # expression that contains operators - evaluate the expression and
        # return the value
        elif node.__class__ in _oper_types:
            left = self.eval(node.left)
            right = self.eval(node.right)
            if isinstance(left, complex) or isinstance(right, complex):
                return _oper_types[node.__class__](left, right)
            else:
                raise OperationException()

        # a variable - look it up and see if it's a python builtin of None or
        # a boolean, or try to look it up in the module's globals
        elif node.__class__ == ast.Name:
            if node.name in _builtin_consts:
                return _builtin_consts[node.name]
            elif node.name in self.globals:
                return self.globals[node.name]
            raise NonGlobalError(node.name)
        else:
            raise AssemblyError("Unknown node type {0!s}".format(
                node.__class__))


def import_module(module_name):
    """
    Import a module and return all its globals as a dictionary

    @param module_name: the module name separated by dots
    @type module_name: C{str}

    @return: the modules globals
    @rtype: C{dict}
    """
    tokens = module_name.split('.')
    module = __import__(module_name)
    for token in tokens[1:]:
        module = getattr(module, token)
    return module


def routes_from_module(module, prepath=''):
    """
    Parse a module that contains werkzeug rules and handlers.  This will
    both import the module (so that symbols can be resolved) and parses the
    file itself (since I do not know how I can extract decorator arguments
    out of a compiled code object)

    @param module_name: the module name separated by dots
    @type module_name: C{str}

    @param prepath: the prepath to use

    @return: the routes contained in the module
    @rtype: C{list} (see L{_RouteFindingASTVisitor})
    """
    # this seems fragile
    filename = re.sub('\.pyc$', '.py', module.__file__)
    tree = parseFile(filename)

    routes = []
    route_visitor = _RouteFindingASTVisitor(routes, vars(module), prepath)
    walk(tree, route_visitor, walker=route_visitor)

    return routes
