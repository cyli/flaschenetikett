"""
Generate documentation based on routes parsed using :mod:`routeparser`
"""


class DocGenerator(object):
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
        pass

    def formatDocstring(self, filehandle, docstring):
        """Adds to the documentation based on the docstring of the rule
        handler"""
        pass

    def formatNode(self, filehandle, node):
        """Adds to the documentation based on the AST node (probably just the
        docstring)"""
        pass

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

                self.formatDocstring(filehandle, route['docstring'])

                self.formatNode(filehandle, route['_node'])


class SphinxDocGenerator(DocGenerator):
    """Generate a Sphinx doc in reST format from parsed routes.

    :ivar routes: a list of routes as produced by
        :class:`routeparser.RouteFindingAstVisitor` or
        :class:`routeparser.routes_from_module`
    :type routes: ``list``
    """
    def formatRule(self, filehandle, rule, methods, **kwargs):
        endpoint = '/'.join(methods) + ' ' + rule
        filehandle.write(endpoint + '\n')
        filehandle.write('=' * len(endpoint) + '\n')

    def formatDocstring(self, filehandle, docstring):
        filehandle.write('\n')
        filehandle.write('**Notes:**\n\n')
        filehandle.write(docstring + '\n\n')
