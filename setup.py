import os
from setuptools import setup


def getPackages(base):
    packages = []

    def visit(arg, directory, files):
        if '__init__.py' in files:
            packages.append(directory.replace('/', '.'))

    os.path.walk(base, visit, None)

    return packages


setup(
    name="flaschenetikett",
    version='0.0.1',
    description="Generates docs from bottle/flask/klein apps",
    classifiers=[
        'Programming Language :: Python :: 2.7',
    ],
    maintainer='Ying Li',
    maintainer_email='cyli@twistedmatrix.com',
    license='MIT',
    url='https://github.com/cyli/flaschenetikett/',
    packages=getPackages('flaschenetikett'),
)
