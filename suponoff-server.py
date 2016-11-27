#! /usr/bin/env python3
"""

Serves the Suponoff Django App using the production-ready CherryPy HTTP server.
Launch with '--help' for a list of options.

It requires the python module `cherrypy' to be installed.

"""


import django
from django.conf import settings
from django.conf.urls import include, url
from django.utils.crypto import get_random_string


import suponoff


def configure(site_path, supervisors, debug):
    settings.configure(
        DEBUG=debug,
        ALLOWED_HOSTS = ['*'],
        SECRET_KEY=get_random_string(50),
        ROOT_URLCONF=__name__,
        MIDDLEWARE_CLASSES=(
            'django.middleware.common.CommonMiddleware',
            'django.middleware.csrf.CsrfViewMiddleware',
            'django.middleware.clickjacking.XFrameOptionsMiddleware',
        ),
        INSTALLED_APPS=(
            'django.contrib.contenttypes',
            'django.contrib.staticfiles',
            'suponoff',
        ),
        SUPERVISORS=supervisors,
        STATIC_URL='/'+site_path+'static/',
        SITE_ROOT='/'+site_path,
        # django<=1.8
        TEMPLATE_CONTEXT_PROCESSORS=['django.core.context_processors.request'],
        TEMPLATE_LOADERS=[
            'django.template.loaders.filesystem.Loader',
            'django.template.loaders.app_directories.Loader',
        ],
        # django>=1.8
        TEMPLATES = [
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'APP_DIRS': True,
            },
        ]
    )


def main(args=None):

    import cherrypy
    from django.core.handlers.wsgi import WSGIHandler
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--debug', '-d', action='store_true', help='run the '
                        'django framework in debug mode (insecure).')
    parser.add_argument('--site-path', '-s', default='/', help='site path '
                        'where the app should be served (e.g., "suponoff/" '
                        'for http://a.b.c.d/suponoff/, default: "").')
    parser.add_argument('--address', '-a', default='127.0.0.1', help='the '
                        'address on which the server is listening (e.g., '
                        '"0.0.0.0", default "127.0.0.1").')
    parser.add_argument('--port', '-p', type=int, default=8000, help='the port'
                        ' on which the server is listening (default "8000").')
    parser.add_argument('host', nargs='*', help='one or more hosts to monitor '
                        '(if omitted, "localhost" is implied); the server will'
                        ' expect a supervisor listening at http://host:9001 '
                        'and a monhelper at http://host:9002; if this is not '
                        'the case, host can be a string like "any_name,'
                        'http://hostname:sup_port,http://hostname:mon_port".')
    args = parser.parse_args(args)
    
    # Build dict of supervisors
    supervisors = {}
    for s in args.host or ['localhost']:
        s = s.split(',')
        if len(s) > 1:
            supervisors[s[0]] = s[1:]
        else:
            supervisors[s[0]] = ['http://{}:{}'.format(s[0], p)
                                 for p in (9001, 9002)]
    cherrypy.log('Supervisors: {}'.format(supervisors))

    # Configure django
    site_path = (args.site_path.rstrip('/') + '/').lstrip('/')
    configure(site_path, supervisors, args.debug)
    django.setup()
    global urlpatterns
    urlpatterns = [url('^' + site_path, include('suponoff.urls')),]
    cherrypy.log('Serving on http://{}:{}/{}'
                 .format(args.address, args.port, site_path))

    # Configure cherrypy
    cherrypy.config.update({
        'server.socket_host': args.address,
        'server.socket_port': args.port,
        'engine.autoreload.on': False,
        'log.screen': True
    })

    # Serve static content
    config = {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': suponoff.__path__[0] + '/static/',
            'tools.caching.on': True,
            'tools.caching.delay': 86400
        }
    cherrypy.tree.mount(None, '/' + site_path + 'static', {'/': config})

    # Start WSGI server
    cherrypy.tree.graft(WSGIHandler())
    cherrypy.engine.start()
    cherrypy.engine.block()


if __name__ == "__main__":
    main()

