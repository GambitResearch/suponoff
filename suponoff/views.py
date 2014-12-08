#!/usr/bin/envpython3
import json
import logging
import re
from collections import defaultdict, OrderedDict

import configparser
import xmlrpc.client

import concurrent.futures
from django.core.context_processors import csrf
from django.http import HttpResponse
from django.shortcuts import redirect, render_to_response
from django.views.decorators.csrf import ensure_csrf_cookie
from django.conf import settings
from pathlib import Path

# from pprint import pformat


LOG = logging.getLogger(__name__)


def _get_supervisor(hostname):
    supervisor = xmlrpc.client.ServerProxy("http://{}:9001".format(hostname),
                                           verbose=False)
    return supervisor


def _get_monhelper(hostname):
    monhelper = xmlrpc.client.ServerProxy(
        "http://{}:9002".format(hostname), verbose=False)
    return monhelper


def _get_server_data(hostname, resource_pids, metadata):
    supervisor = _get_supervisor(hostname)
    monhelper = _get_monhelper(hostname)
    try:
        processes = supervisor.supervisor.getAllProcessInfo()
        server = {}
        pids = []
        for process in processes:
            if process["pid"]:
                pids.append(process["pid"])
            group_name = process['group']
            group = server.setdefault(group_name,
                                      {"processes": [],
                                      "total_processes": 0,
                                      "running_processes": 0})
            process["can_be_stopped"] = process["statename"] in {"RUNNING"}
            process["can_be_restarted"] = process["statename"] in {"RUNNING"}
            process["can_be_started"] = process["statename"] in {"STOPPED", "EXITED"}
            if process["statename"] in {"RUNNING"}:
                group['running_processes'] += 1
            else:
                group['has_not_running_processes'] = True
            group['total_processes'] += 1
            group['processes'].append(process)

            if group['total_processes'] == 1:
                group_tags = set()
                for server_regex, group_regex, tags in metadata:
                    group_match = group_regex.match(group_name)
                    server_match = server_regex.match(hostname)
                    if group_match and server_match:
                        group_tags.update(tags)
                group['tags'] = list(sorted(group_tags))

        if resource_pids:
            try:
                resources_dict = monhelper.getProcessResourceUsage(
                    list(int(x) for x in resource_pids))
            except ConnectionRefusedError:
                LOG.warning("Remote server %s doesn't have the monhelper"
                            " extension", hostname)
            else:
                for pid, resources in resources_dict.items():
                    for process in processes:
                        if str(process['pid']) == pid:
                            process['resources'] = resources
                            break
    finally:
        supervisor("close")()
        monhelper("close")()
    return server


def _get_data(server_pids, metadata):
    # hostname -> group -> process
    services_by_host = OrderedDict()
    servers = sorted(settings.SUPERVISORS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        for hostname in servers:
            server_data = executor.submit(_get_server_data, hostname,
                                          server_pids.get(hostname), metadata)
            services_by_host[hostname] = server_data
        for hostname in servers:
            services_by_host[hostname] = services_by_host[hostname].result()
    return services_by_host


def get_data(request):
    #resource_pids = set(int(x) for x in request.GET.getlist('pid[]'))
    data = json.loads(request.body.decode("ascii"))
    #LOG.debug("data: %r", data)
    data = _get_data(data['server_pids'], [])
    data_json = json.dumps(data)
    return HttpResponse(data_json, content_type='application/json')


@ensure_csrf_cookie
def home(request, template_name="suponoff/index.html"):
    metadata, tags_config, taggroups_dict = _get_metadata_conf()
    services_by_host = _get_data({}, metadata)

    all_tags = set()
    for server_data in services_by_host.values():
        for group in server_data.values():
            all_tags.update(group['tags'])

    tags_by_group = defaultdict(set)
    for tag_name in all_tags:
        tag = tags_config[tag_name]
        tags_by_group[tag.taggroup].add(tag_name)
    taggroups = []
    for name, tags in sorted(tags_by_group.items()):
        taggroups.append((taggroups_dict[name].label, sorted(tags)))

    context = {
        "data": services_by_host,
        "taggroups": taggroups,
        'tags_config': tags_config,
        "SITE_ROOT": settings.SITE_ROOT,
    }

    context.update(csrf(request))

    #LOG.debug("Context: %s", context)
    resp = render_to_response(template_name, context)
    return resp


def action(request):
    server = request.POST['server']
    supervisor = _get_supervisor(server)
    try:
        if 'action_start_all' in request.POST:
            supervisor.supervisor.startAllProcesses()
            return HttpResponse(json.dumps("ok"), content_type='application/json')
        elif 'action_stop_all' in request.POST:
            supervisor.supervisor.stopAllProcesses()
            return HttpResponse(json.dumps("ok"), content_type='application/json')
        program = "{}:{}".format(request.POST['group'], request.POST['program'])
        if 'action_start' in request.POST:
            supervisor.supervisor.startProcess(program)
        elif 'action_stop' in request.POST:
            supervisor.supervisor.stopProcess(program)
        elif 'action_restart' in request.POST:
            supervisor.supervisor.stopProcess(program)
            supervisor.supervisor.startProcess(program)

    finally:
        supervisor("close")()
    return redirect(settings.SITE_ROOT)


def get_program_logs(request):
    logs = "Logs for program {}:{} in server {}".format(
        request.GET['group'], request.GET['program'], request.GET['server'])
    stream = request.GET['stream']
    assert stream in {'stdout', 'stderr', 'applog'}

    if stream == 'stdout':
        supervisor = _get_supervisor(request.GET['server'])
        try:
            logs, _offeset, _overflow = supervisor.supervisor.tailProcessStdoutLog(
                "{}:{}".format(request.GET['group'], request.GET['program']),
                -100000, 100000)
        finally:
            supervisor("close")()
    elif stream == 'stderr':
        supervisor = _get_supervisor(request.GET['server'])
        try:
            logs, _offeset, _overflow = supervisor.supervisor.tailProcessStderrLog(
                "{}:{}".format(request.GET['group'], request.GET['program']),
                -100000, 100000)
        finally:
            supervisor("close")()
    elif stream == 'applog':
        supervisor = _get_monhelper(request.GET['server'])
        try:
            logs, _offeset, _overflow = supervisor.tailApplicationLog(
                int(request.GET['pid']), -100000, 100000)
        finally:
            supervisor("close")()
    else:
        raise AssertionError
    return HttpResponse(logs, content_type='text/plain')


class TagConfig:  # pylint: disable=R0903
    enabled_by_default = True
    taggroup = 'other'


class TagGroup:  # pylint: disable=R0903
    label = ''


def _get_metadata_conf():
    mappings = []
    tags_config = defaultdict(TagConfig)
    taggroups = defaultdict(TagGroup)

    metadata_dir = getattr(settings, "METADATA_DIR", None)
    if not metadata_dir:
        return mappings, tags_config, taggroups

    for fname in Path(metadata_dir).iterdir():
        config = configparser.ConfigParser()
        config.read(str(fname))

        for section in config.sections():

            if section.startswith("meta:"):
                group_regex = re.compile(config[section].get("group", '.*'))
                server_regex = re.compile(config[section].get("server", '.*'))
                tags = config[section].get("tags")
                if tags is None:
                    tags = frozenset()
                else:
                    tags = {tag.strip() for tag in tags.split(',')}
                mappings.append((server_regex, group_regex, tags))

            elif section.startswith("tag:"):
                _, _, tag_name = section.partition("tag:")

                enabled = config[section].getboolean("enabled_by_default", True)
                tags_config[tag_name].enabled_by_default = enabled

                taggroup = config[section].get("taggroup", 'other')
                tags_config[tag_name].taggroup = taggroup

            elif section.startswith("taggroup:"):
                _, _, taggroup_name = section.partition("taggroup:")
                label = config[section].get("label", '')
                taggroups[taggroup_name].label = label

    return mappings, tags_config, taggroups
