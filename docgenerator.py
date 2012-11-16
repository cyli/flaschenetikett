"""
Generate documentation based on routes parsed using :mod:`routeparser`
"""

import itertools
from optparse import OptionParser


class DocGenerator(object):
    """
    Formats documentation based on a list of werkzeug routes.

    Subclasses should implement :meth:`formatRule`, :meth:`formatDocstring`,
    and :meth:`formatNode` if necessary.

    If there are extra decorators on the node, they can also be handled by
    implementing `handle_<decorator name>` methods, which take a flattened
    dictionary with the relevant decorator name, args, and kwargs.
    (see :class:`RouteFindingAstVisitor.flattenDecorator`)

    :ivar routes: an iterable of routes as produced by
        :class:`RouteFindingAstVisitor`
    :type routes: ``iterable``
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
        """Results in something like:  GET /blah/blah/blah as a section title
        """
        endpoint = '/'.join(methods) + ' ' + rule
        filehandle.write(endpoint + '\n')
        filehandle.write('=' * len(endpoint) + '\n')

    def formatDocstring(self, filehandle, docstring):
        """Simply writes the docstring without any additional formatting."""
        filehandle.write('\n' + docstring + '\n\n')


def cli(formatters, default=None):
    """Command line script function.

    :param formatters: a mapping of document formats to their corresponding
        :class:`DocGenerator` implementations
    :type formatters: ``dict``

    :param default: the default format in which to produce documentation -
        defaults to the first value returned by calling ``keys()`` on the
        ``formatters`` dictionary
    :type default: ``str``
    """
    parser = OptionParser(usage="Usage: %prog [options] module [module...]")
    parser.add_option("-o", "--output", dest="filename", metavar="FILE",
                      help="File to write documentation to.")
    if len(formatters) > 1:
        choices = formatters.keys()
        default = default or choices[0]
        parser.add_option("-f", "--format", dest="format", metavar="FORMAT",
                          help="Documentation format - default is \"sphinx\"",
                          default=default, choices=choices)
    else:
        parser.format = formatters.keys()[0]

    options, args = parser.parse_args()

    if len(args) < 1:
        parser.error("Need a module to parse")

    import routeparser
    routes = itertools.chain(*[routeparser.routes_from_module(module)
                               for module in args])

    formatter = formatters[parser.format](routes,
                                          getattr(parser, 'filename', None))
    formatter.generate()


if __name__ == "__main__":
    cli({'sphinx': SphinxDocGenerator})
