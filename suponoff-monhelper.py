#! /usr/bin/env python3
"""

A supervisor-like XML-RPC server that offers an interface to retrieve resource
usage and limits of processes, and access to application log files (in addition
to the stdout and stderr access that supervisord already provides).

To use this, copy this file to each server you want to manage, and run it as
root (perhaps from supervisor itself).  It listens on 0.0.0.0:9002, so that the
suponoff web app can connect to it.  It requires the python module `psutil' to
be installed.

"""

import time
import os
import os.path
import logging.handlers
import shlex
import psutil
from datetime import date
from xmlrpc.server import SimpleXMLRPCServer

LOG = logging.getLogger()


def get_application_logfile(argv):
    for argi in range(len(argv)):
        if argi < (len(argv) - 1) and argv[argi] in ["--logfile", "--log-file"]:
            #print(argv[argi + 1])
            return argv[argi + 1]
        if argv[argi:argi+2] == ['bash', '-c']:
            argv1 = shlex.split(argv[argi + 2])
            return get_application_logfile(argv1)


class MonHelperRPCInterface:  # pylint: disable=R0923
    def __init__(self):
        pass

    def getProcessResourceUsage(self, pid_list):
        try:
            results = {}
            for pid in pid_list:
                result = {}
                results[str(pid)] = result
                try:
                    proc = psutil.Process(pid)
                except:
                    LOG.exception("Process %s:", pid)
                    continue
                result["fileno"] = proc.num_fds()
                try:
                    proc.rlimit
                except AttributeError:
                    max_fileno = -1
                    max_vmsize = -1
                else:
                    max_fileno = proc.rlimit(psutil.RLIMIT_NOFILE)[0]
                    max_vmsize = proc.rlimit(psutil.RLIMIT_AS)[0]
                if max_fileno != -1:
                    result["max_fileno"] = max_fileno

                result["numconnections"] = len(proc.connections('all'))
                result["numfiles"] = len(proc.open_files())

                if max_vmsize != -1:
                    result["max_vmsize"] = str(max_vmsize)
                result["vmsize"] = str(proc.memory_info()[1])
                result["numchildren"] = len(proc.children())
                result["numthreads"] = proc.num_threads()
                result["cpu"] = ",".join(str(x) for x in
                                         [time.time()] +
                                         list(proc.cpu_times()))
                result["diskio"] = ",".join(str(x) for x in
                                            [time.time()] +
                                            list(proc.io_counters()))
            return results
        except:
            LOG.exception("Error")
            return {}

    def tailApplicationLog(self, pid, offset, length):
        try:
            cmdline = psutil.Process(pid).cmdline()
            logfile = get_application_logfile(cmdline)

            if logfile is None:
                return ['', 0, False]

            if not os.path.exists(logfile):
                # logbook rotated logfiles have a date even for today
                base, ext = os.path.splitext(logfile)
                logfile2 = "{}-{}{}".format(base,
                                            date.today().strftime("%Y-%m-%d"),
                                            ext)
                if os.path.exists(logfile2):
                    logfile = logfile2

            if not os.path.exists(logfile):
                # rotatelogs rotated logfiles...
                logfile = "{}.{}".format(logfile,
                                         date.today().strftime("%Y-%m-%d"))

            if logfile is None or not os.path.exists(logfile):
                return ['', 0, False]

            return tailFile(logfile, int(offset), int(length))
        except:
            LOG.exception("Error")
            return ['', 0, False]


# copied from supervisor.options
def tailFile(filename, offset, length):
    """
    Read length bytes from the file named by filename starting at
    offset, automatically increasing offset and setting overflow
    flag if log size has grown beyond (offset + length).  If length
    bytes are not available, as many bytes as are available are returned.
    """

    overflow = False
    try:
        f = open(filename, 'rb')
        f.seek(0, 2)
        sz = f.tell()

        if sz > (offset + length):
            overflow = True
            offset = sz - 1

        if (offset + length) > sz:
            if offset > (sz - 1):
                length = 0
            offset = sz - length

        if offset < 0:
            offset = 0
        if length < 0:
            length = 0

        if length == 0:
            data = ''
        else:
            f.seek(offset)
            data = f.read(length)

        offset = sz
        return [data, offset, overflow]

    except (OSError, IOError):
        return ['', offset, False]


# copied from supervisor.options
def split_namespec(namespec):
    names = namespec.split(':', 1)
    if len(names) == 2:
        # group and and process name differ
        group_name, process_name = names
        if not process_name or process_name == '*':
            process_name = None
    else:
        # group name is same as process name
        group_name, process_name = namespec, namespec
    return group_name, process_name


def main():
    logging.basicConfig(format="%(asctime)s %(levelname)s "
                               "%(filename)s:%(lineno)d %(message)s")

    LOG.setLevel(logging.INFO)

    LOG.info("psutil version %s at %s", psutil.__version__, psutil.__file__)

    server = SimpleXMLRPCServer(("0.0.0.0", 9002))
    server.register_introspection_functions()
    server.register_instance(MonHelperRPCInterface())
    server.serve_forever()

if __name__ == '__main__':
    main()
