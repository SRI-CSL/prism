#  Copyright (c) 2019-2023 SRI International.

import subprocess

import trio
from .log_line import LogLine
from .reader import Reader


class Buffer:
    def __init__(self):
        self.buffer = []

    def has_line(self):
        return len(self.buffer) > 0

    def add_to_last(self, s: str):
        if len(self.buffer) > 0:
            self.buffer[-1] = self.buffer[-1] + s
        else:
            self.buffer.append(s)

    def get_next_line(self):
        return self.buffer[0]

    def delete_next_line(self):
        del self.buffer[0]

    def add_lines(self, str_arr):
        self.buffer = str_arr + self.buffer


KUBERNETES_TAGS = {"kubernetes": {"file_type": "log", "format": "json"}}


class KubectlReader(Reader):
    def __init__(self):
        super().__init__()

    def is_multiple_objs(self, json_str):
        if json_str.count("{") > 1 or json_str.count("}") > 1:
            return True
        return False

    def is_complete_obj(self, json_str):
        if "{" not in json_str or "}" not in json_str:
            return False
        return True

    def make_pod_dict(self, pods_string):
        pods_list = pods_string.split("\n")
        del pods_list[0]
        pod_dict = {}
        for pod in pods_list:
            pod_attrs = self.delete_spaces(pod.split(" "))
            if self.collect_pod(pod_attrs):
                pod_dict[pod_attrs[0]] = self.get_attrs_dict(pod_attrs[0], pod_attrs[2])
        return pod_dict

    def get_attrs_dict(self, name_, status_):
        return {"status": status_, "node_type": self.get_node_type(name_)}

    def get_node_type(self, pod_name):
        if pod_name.find("mpc") != -1:
            return "mpc"
        if pod_name.find("dropbox") != -1:
            return "dropbox"
        elif pod_name.find("emix") != -1:
            return "emix"
        elif pod_name.find("bebo") != -1:
            return "bebo"
        elif pod_name.find("obdbx") != -1:
            return "peer"

    def collect_pod(self, pod_attrs):
        if len(pod_attrs) <= 2:
            return False
        if self.get_node_type(pod_attrs[0]) == "mpc":
            return False
        if (
            self.get_node_type(pod_attrs[0]) != "emix"
            and self.get_node_type(pod_attrs[0]) != "dropbox"
            and self.get_node_type(pod_attrs[0]) != "peer"
        ):
            return False
        return True

    def delete_spaces(self, array_with_spaces):
        array_with_no_spaces = []
        for el in array_with_spaces:
            if el != "":
                array_with_no_spaces.append(el)
        return array_with_no_spaces

    async def get_pods(self):
        process = await trio.run_process(["kubectl", "get", "pods"], capture_stdout=True, cwd="../../k8s/demo-nov20")
        stdout = process.stdout.decode("utf-8")
        pod_dict = self.make_pod_dict(stdout)
        return pod_dict

    async def pods_ready(self):
        pods = await self.get_pods()
        if pods == {}:
            return False
        for pod, attrs in pods.items():
            if attrs["status"] != "Running":
                return False
        return True

    async def read_logs(self, line_in: trio.MemorySendChannel, pod_name: str, tags):
        from ...cli.repo import REPO_ROOT
        async with await trio.open_process(
            [
                "kubectl",
                "exec",
                "--stdin",
                "--tty",
                "-c",
                "prism-server",
                pod_name,
                "--",
                "tail",
                "-F",
                "/tmp/prism-server.monitor.log",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=REPO_ROOT / "tools" / "k8s" / "demo-nov20",
        ) as process:

            buffer = Buffer()
            async for line in process.stdout:
                line = line.decode("utf-8")
                buffer.add_to_last(line)
                while buffer.has_line():
                    next_line = buffer.get_next_line()
                    if self.is_complete_obj(next_line) and not self.is_multiple_objs(next_line):
                        log_line = LogLine(next_line, tags)
                        buffer.delete_next_line()
                        self.stats.lines_read += 1
                        await line_in.send(log_line)
                    elif self.is_multiple_objs(next_line):
                        json_array = next_line.split("\n")
                        buffer.delete_next_line()
                        buffer.add_lines(json_array)
                    elif not self.is_complete_obj(next_line):
                        if next_line.find("{") == -1 and next_line.find("}") == -1:
                            buffer.delete_next_line()
                        break

    def init_pods(self, pod_obj):
        event_obj = {}
        for name in pod_obj:
            event_obj[name] = "init"
        return event_obj

    def kubernetes_nicknames(self, name, emix_count):
        str_ = name.split("-")
        if name.find("emix") != -1:
            server_nickname = str_[0] + "-" + str_[1] + "-" + str(emix_count)
        else:
            server_nickname = str_[0] + "-" + str_[1] + "-" + str_[2] + "-" + str_[3]
        return server_nickname

    async def run(self, line_in: trio.MemorySendChannel):
        async with trio.open_nursery() as nursery:
            files_to_read = KUBERNETES_TAGS.copy()
            event_obj = {}
            while True:
                curr_pod_obj = await self.get_pods()
                emix_count = 0
                for name, attrs in curr_pod_obj.items():
                    if name.find("emix") != -1:
                        emix_count = emix_count + 1
                    if name not in event_obj:
                        event_obj[name] = "init"
                    if attrs["status"] == "Running" and event_obj[name] == "init":
                        event_obj[name] = "ready"
                    if attrs["status"] != "Running" and event_obj[name] == "running":
                        event_obj[name] = "init"
                    for filename, tags in files_to_read.items():
                        file_tags = {
                            **tags,
                            "node": self.kubernetes_nicknames(name, emix_count),
                            "node_type": "server",
                            "file_name": filename,  # kubernetes
                        }
                    if event_obj[name] == "ready":
                        nursery.start_soon(self.read_logs, line_in.clone(), name, file_tags)
                        event_obj[name] = "running"
