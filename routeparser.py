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

route_decorator_name = re.compile('.*\.?route$')


class NonGlobalError(Exception):
    """Exception raised when trying to look up a variable, but the variable is
    not a global variable.
    """
    pass


class OperationException(Exception):
    """Exception raised when trying to assemble some type of operation"""
    pass


class AssemblyError(Exception):
    """Other exception if attempting to assemble things fails"""
    pass


class RouteFindingASTVisitor(visitor.ASTVisitor):
    """A visitor for a parsed AST which finds Flask/Klein/Bottle routes, which
    are handlers decorated by a ``@route`` or ``@app.route`` decorator,
    containing a URL pattern that is then given to a ``werkzeug.routing.Rule``.

    This assumes that the ``@route`` handlers are functions on a particular
    module, rather than methods on a class.

    :ivar routes: a list of found routes, each route consisting of a dictionary
        containing the following keys and values::

        "rule": the werkzeug rule - e.g. the url/endpoint/path
        "methods": a list of http methods the rule operates on - e.g. 'GET'
        "route_kwargs": other kwargs that get passed to the werkzeug rule
        "docstring": the docstring on the route handler
        "decorators": a list of flattened decorators that are also on the
            node (such as that returned by :func:`flattenDecorator`)
        "_node": the AST node for the route handler - provided just in case

    :type routes: ``list`` of ``dict``

    :ivar globals: a list of the module's global variables and imports,
        so that variable used in the decorators can be looked up
    :type globals: ``dict``

    :ivar prepath: the path to append to all the rules/paths
    :type prepath: ``str``
    """

    def __init__(self, routes, module_globals=None, prepath=''):
        visitor.ASTVisitor.__init__(self)
        self.routes = routes
        self.globals = module_globals or {}
        self.prepath = prepath

    def default(self, node):
        """By default, ignore the node (no-op)"""
        pass

    def doRecurse(self, node):
        """Recurse down to get process child nodes"""
        for n in node.getChildNodes():
            self.dispatch(n)

    visitStmt = visitModule = doRecurse

    def visitFunction(self, node):
        """Handle functions, which could be routes"""
        if hasattr(node, 'decorators') and node.decorators:
            try:
                decorators = [self.flattenDecorator(decorator) for decorator in
                              node.decorators]
                route_decorator = [flat for flat in decorators if
                                   route_decorator_name.match(flat['name'])]
                if len(route_decorator) > 0:
                    decorators.remove(route_decorator[0])
                    info = self.analyzeRoute(route_decorator[0])
                    info['docstring'] = cleandoc(node.doc)
                    info['_node'] = node
                    info['decorators'] = decorators
                    self.routes.append(info)
            except Exception as e:
                warnings.warn(
                    "Ignoring {0!r} due to exception {1!r}".format(node, e))

    def analyzeRoute(self, route):
        """Takes one flattened route decorator and produces dictionary instead
        containing the path/rule, the methods, and any other keyword args
        that get passed to a werkzeug rule.

        :param route: something produced by :meth:`flattenDecorator`
        :type route: ``dict``

        :return: dictionary containing the the rule, the methods, and the other
            keyword arguments
        :rtype: ``dict``
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
            'route_kwargs': route['kwargs']
        }
        del info['route_kwargs']['methods']
        return info

    def flattenDecorator(self, decorator):
        """Takes a decorator node and turns it into a flattened dictionary
        containing the name, the arguments to the decorator, and the keyword
        arguments to the decorator, all hopefully eval-ed.

        :param decorator: the decorator AST node
        :type decorator: :class:`compiler.ast.Node`

        :return
        """
        flattened = {}
        nodes = decorator.getChildren()
        if not isinstance(nodes[0], ast.Name):
            # first child should be the name
            return flattened
        flattened['name'] = nodes[0].name
        flattened['args'] = []
        flattened['kwargs'] = {}
        for node in nodes[1:]:
            if isinstance(node, ast.Keyword):
                flattened['kwargs'][node.name] = self.eval(node.expr)
            elif node is not None:
                flattened['args'].append(self.eval(node))
        return flattened

    def eval(self, node):
        """Recursively assemble parsed ast node, assuming that the node has
        no function call (although this can probably be supported at some
        point)

        :param node: the AST node
        :type node: :class:`compiler.ast.Node`

        :return: value that the node evaluates to
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
            if type(left) == type(1.0j) or type(right) == type(1.0j):
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
    """Import a module and return all its globals as a dictionary

    :param module_name: the module name separated by dots
    :type module_name: ``str``

    :return: the modules globals
    :rtype: ``dict``
    """
    tokens = module_name.split('.')
    module = __import__(module_name)
    for token in tokens[1:]:
        module = getattr(module, token)
    return module


def routes_from_module(module_name, prepath=''):
    """Parse a module that contains werkzeug rules and handlers.  This will
    both import the module (so that symbols can be resolved) and parses the
    file itself (since I do not know how I can extract decorator arguments
    out of a compiled code object)

    :param module_name: the module name separated by dots
    :type module_name: ``str``

    :param prepath: the prepath to use

    :return: the routes contained in the module
    :rtype: ``list`` (see :class:`RouteFindingASTVisitor`)
    """
    module = import_module(module_name)
    # this seems fragile
    filename = re.sub('\.pyc$', '.py', module.__file__)
    tree = parseFile(filename)

    routes = []
    route_visitor = RouteFindingASTVisitor(routes, vars(module), prepath)
    walk(tree, route_visitor, walker=route_visitor)

    return routes
