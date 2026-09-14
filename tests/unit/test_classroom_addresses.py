from scripts import launcher


def test_classroom_ipv4_keeps_rfc1918_and_drops_tunnels():
    assert launcher._is_classroom_ipv4('192.168.1.20') is True
    assert launcher._is_classroom_ipv4('10.0.0.8') is True
    assert launcher._is_classroom_ipv4('172.16.4.2') is True
    assert launcher._is_classroom_ipv4('127.0.0.1') is False
    assert launcher._is_classroom_ipv4('169.254.1.1') is False
    assert launcher._is_classroom_ipv4('198.18.0.1') is False
    assert launcher._is_classroom_ipv4('100.64.0.1') is False


def test_lan_addresses_prefer_rfc1918_over_warp(monkeypatch):
    monkeypatch.setattr(
        launcher,
        '_interface_ipv4_addresses',
        lambda: ['198.18.0.1', '192.168.10.5', '127.0.0.1'],
    )
    monkeypatch.setattr(launcher, '_virtual_adapter_ipv4_addresses', lambda: [])
    monkeypatch.setattr(launcher, '_default_route_ipv4', lambda: '198.18.0.1')

    assert launcher._lan_addresses() == ['192.168.10.5']


def test_lan_addresses_put_default_route_ahead_of_virtual_nics(monkeypatch):
    monkeypatch.setattr(
        launcher,
        '_interface_ipv4_addresses',
        lambda: ['172.16.0.1', '192.168.10.5', '198.18.0.1'],
    )
    monkeypatch.setattr(launcher, '_virtual_adapter_ipv4_addresses', lambda: ['172.16.0.1'])
    monkeypatch.setattr(launcher, '_default_route_ipv4', lambda: '192.168.10.5')

    assert launcher._lan_addresses() == ['192.168.10.5']


def test_virtual_adapter_names_are_detected():
    assert launcher._is_virtual_adapter('vEthernet (Default Switch)') is True
    assert launcher._is_virtual_adapter('Ethernet') is False
    assert launcher._is_virtual_adapter('WSL') is True
