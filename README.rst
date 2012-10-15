Scale Stack is a simple, scalable, multi-master server development
framework written in Python. For more information, check out:

* http://scalestack.org/
* https://github.com/eday/scalestack
* irc://irc.freenode.net/#scalestack

To run the server::

    ./bin/scalestack

To run the test suite::

    python setup.py nosetests

To build the documentation (then browse to doc/_build/html/index.html)::

    python setup.py build_sphinx

If you have python-coverage installed, you can generate both a text and
HTML code coverage report by running::

    rm -rf coverage.html .coverage*
    python-coverage run setup.py nosetests
    python-coverage combine
    python-coverage html -d coverage.html --omit=/usr,test,setup
    python-coverage report --omit=/usr,test,setup

If you have the following tools installed, you can perform sanity checks
on the code by running::

    pylint -iy --rcfile .pylintrc scalestack
    pep8 -r scalestack
    pyflakes scalestack
