suponoff is a web interface to supervisor
=========================================

suponoff (short for Supervisor On/Off) is a Django app to control supervisor and
monitor the programs running under supervisor.

You give the app a list of server hostnames to connect to, and it connects to
port 9001 of each of the servers, where supervisor normally listens.
Optionally, you may run the provided program `suponoff-monhelper.py`, which
listens on port 9002 and provides the following additional functionalities:

1. Reports back the resource limits and usage of the processes, such as
   number of file descriptors, memory, cpu, number of threads and subprocesses;

2. Provides the ability to monitor application log files in some cases: it
   looks at the process command line and parses it, looking for `--logfile` or
   `--log-file` arguments.If it can find and open the indicated log file, then
   you will be able to open this log file from the web interface.


To use this app, create a Django project that includes 'suponoff' in its
applications and includes the URLs from 'suponoff.urls'.  Then you add the
SUPERVISORS setting (a list of hostnames).  The web interface can also add
"tags" to each program, allowing you to filter by tags.  For an example, see the
`demo` project in the source distribution.

Screenshot:
-----------
.. image:: https://raw.githubusercontent.com/GambitResearch/suponoff/master/demo/screenshot.png
