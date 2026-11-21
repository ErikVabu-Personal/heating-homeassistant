"""The pure modules and their tests must never need a network connection."""

import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch, request):
    if request.node.get_closest_marker("integration"):
        return

    def forbidden(*args, **kwargs):
        raise AssertionError("Pure logic must not open sockets")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
