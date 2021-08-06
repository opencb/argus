try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup
# To use a consistent encoding
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='dargus',
    version='0.1.0',
    description='A REST client for OpenCGA REST web services',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/opencb/argus',
    packages=['argus'],
    scripts=['argus'],
    license='Apache Software License',
    author='Daniel Perez-Gil',
    author_email='dp529@cam.ac.uk',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Scientific/Engineering :: Bio-Informatics',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3.5.0',
    ],
    keywords='opencb argus bioinformatics rest webservices testing',
    install_requires=[
        'requests >= 2.22',
        'pyyaml >= 3.12'
    ],
    project_urls={
        'Source': 'https://github.com/opencb/argus',
        'Bug Reports': 'https://github.com/opencb/argus/issues',
    }
)
