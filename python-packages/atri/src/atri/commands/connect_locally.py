import asyncio
from math import inf
import os
import traceback
from typing import Any
import socketio
import subprocess
from ..utils.in_venv import in_virtualenv
from ..utils.is_pkg_installed import is_pipenv_installed
from ..utils.install_package import install_with_pipenv
from shutil import copy
import toml

def print_success(success):
    if success:
        print("Registered as atri-cli with ipc server.")

async def on_connect(sio):
    await sio.emit("registerAs", "atri-cli", callback=print_success)

async def connect_ipc_server(port: str):
    print("Connecting to ipc server...")
    sio = socketio.AsyncClient(
        reconnection=True,
        reconnection_attempts=inf,
        reconnection_delay=1,
        reconnection_delay_max=4,
        handle_sigint=True
        )

    @sio.on('connect')
    async def connect_handler():
        print('Connected to ipc server!')
        await on_connect(sio)

    @sio.event
    def connect_error(data):
        print("Connection to ipc server failed!")

    @sio.event
    def disconnect():
        print("Disconnected from ipc server!")

    while True:
        try:
            await sio.connect("http://localhost:" + port)
            break
        except:
            await asyncio.sleep(1)
    return sio

def handle_ipc_events(sio, paths):
    @sio.on("doComputeInitialState")
    async def doComputeInitialState(route: str, page_state: str):
        try:
            app_dir = paths["app_dir"]
            controllers_dir = os.path.join(app_dir, "controllers")
            child_proc = subprocess.Popen(
                ["python", "-m", "server", "compute", "--route", route, "state", page_state],
                stdout=subprocess.PIPE,
                cwd=controllers_dir
                )
            out = child_proc.stdout.read()
            return out
        except Exception:
            print("except", traceback.print_exc())
    @sio.on("doPythonBuild")
    async def doPythonBuild():
        app_dir = paths["app_dir"]
        controllers_dir = os.path.join(app_dir, "controllers")
        initial_pipfile_path = os.path.join(controllers_dir, "Pipfile")
        final_pipfile_path = os.path.join(app_dir, "Pipfile")
        # check if Pipfile exist in controller directory
        if not os.path.exists(initial_pipfile_path):
            if not in_virtualenv():
                # check if pipenv is installed otherwise ask user to install it
                if is_pipenv_installed():
                    # copy Pipfile to app_dir
                    copy(initial_pipfile_path, final_pipfile_path)
                    # run pipenv install
                    child_proc = install_with_pipenv(app_dir)
                    child_proc.wait()
                    # delete Pipfile from controllers_dir
                    os.remove(initial_pipfile_path)
                else:
                    print("Please install a pipenv or some other virtual environment.")
            else:
                # detect virtual env type
                if is_pipenv_installed():
                    # read Pipfile
                    pipfile_data = toml.load(initial_pipfile_path)
                    pkgs = pipfile_data["packages"]
                    dev_pkgs = pipfile_data["dev-packages"]
                    # run pipenv install <package_name> for each file in Pipfile inside app_dir
                    for pkg in pkgs:
                        version = pkgs[pkg]
                        child_proc = install_with_pipenv(app_dir, pkg, version)
                        child_proc.wait()
                    for pkg in dev_pkgs:
                        version = dev_pkgs[pkg]
                        child_proc = install_with_pipenv(app_dir, pkg, version)
                        child_proc.wait()
                    # delete Pipfile from controllers_dir
                    os.remove(initial_pipfile_path)
                else:
                    print("Failed to detect virtual env type. Currently supported are pipenv")

async def start_ipc_connection(port: str, paths):
    sio = await connect_ipc_server(port)
    handle_ipc_events(sio, paths)
    # Important to call sio.wait if no other task will run
    # If sio.wait is not called, then the python program will crash in ~30 secs
    # with error message 'packet queue is empty, aborting'
    await sio.wait()

def run(u_port, app_dir):
    abs_app_dir = os.path.abspath(app_dir)
    paths = {"app_dir": abs_app_dir}
    asyncio.run(start_ipc_connection(u_port, paths))