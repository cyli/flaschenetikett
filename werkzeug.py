from compiler import ast, parseFile, visitor, walk
from inspect import cleandoc
import json
from operator import add, sub
import re
import sys
from urlparse import urljoin

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


class RouteFindingAstVisitor(visitor.ASTVisitor):
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
        "node": the AST node for the route handler
        "decorators": a list of flattened decorators that are also on the
            node (such as that returned by :func:`flattenDecorator`)

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
        """Recurse down to get child nodes"""
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
                    info['node'] = node
                    info['decorators'] = decorators
                    self.routes.append(info)
            except Exception as e:
                print "Ignoring {0!r} due to exception {1!r}".format(node, e)

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
        arguments to the decorator, all hopefully eval-ed"""
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
        no function call (although this can probably be supported)

        :return: value that the node evaluates to
        """
        if node.__class__ == ast.Const:
            return node.value
        elif node.__class__ in _seq_types:
            args = map(self.eval, node.getChildren())
            return _seq_types[node.__class__](args)
        elif node.__class__ in _map_types:
            keys, values = zip(*node.items)
            keys = map(self.eval, keys)
            values = map(self.eval, values)
            return _map_types[node.__class__](zip(keys, values))
        elif node.__class__ in _oper_types:
            left = self.eval(node.left)
            right = self.eval(node.right)
            if type(left) == type(1.0j) or type(right) == type(1.0j):
                return _oper_types[node.__class__](left, right)
            else:
                raise OperationException()
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
    tokens = module_name.split('.')
    module = __import__(module_name)
    for token in tokens[1:]:
        module = getattr(module, token)
    return module


class DocFormatter(object):
    """
    Formats documentation based on a list of werkzeug routes

    :ivar routes: a list of routes as produced by
        :class:`RouteFindingAstVisitor`
    :type routes: ``list``
    """

    def __init__(self, routes, dest_filename):
        self.routes = routes
        self.filename = dest_filename

    def formatRule(self, filehandle, rule, methods, **kwargs):
        """Adds to the documentation based on the werkzeug rule, the http
        methods, and other possible kwargs that get passed to the werkzeug
        rule"""
        raise NotImplementedError()

    def formatNode(self, filehandle, node):
        """Adds to the documentation based on the AST node (probably just the
        docstring)"""
        raise NotImplementedError()

    def generate(self):
        """Writes the REST documentation to a file"""
        with open(self.filename, 'wb') as filehandle:
            for route in self.routes:
                self.formatRule(filehandle, route['rule'], route['methods'],
                                **route['route_kwargs'])

                for decorator in route['decorators']:
                    handler_name = 'handle_{0}'.format(decorator['name'])
                    handler = getattr(self, handler_name, None)
                    if handler is not None:
                        handler(filehandle, decorator)

                self.formatNode(filehandle, route['node'])


class SphinxDocFormatter(DocFormatter):
    """Generate Sphinx docs in reST format from parsed routes

    :ivar routes: a list of routes as produced by
        :class:`RouteFindingAstVisitor`
    :type routes: ``list``
    """

    def formatRule(self, filehandle, rule, methods, **kwargs):
        endpoint = '/'.join(methods) + ' ' + rule
        filehandle.write(endpoint + '\n')
        filehandle.write('=' * len(endpoint) + '\n')

    def formatNode(self, filehandle, node):
        filehandle.write('\n')
        filehandle.write('**Notes:**\n\n')
        filehandle.write(cleandoc(node.doc) + '\n\n')


if __name__ == "__main__":
    module = import_module(sys.argv[1])
    # TODO this is fragile
    filename = module.__file__.replace('.pyc', '.py')
    tree = parseFile(filename)

    routes = []
    route_visitor = RouteFindingAstVisitor(routes, vars(module))
    walk(tree, route_visitor, walker=route_visitor)

    formatter = SphinxDocFormatter(routes, sys.argv[2])
    formatter.generate()
