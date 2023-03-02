import pytest

from dataSources import DataSource_socket


def test_socket_connection_fails():
    sock = DataSource_socket.Input(ip_address_port="test_missing_lookup:1",
                                   data_type="16tbe",
                                   sample_rate=1.0, centre_frequency=1.0, input_bw=1.0)
    # fails to due address lookup
    with pytest.raises(ValueError):
        sock.open()


def test_socket_connection_no_server():
    sock = DataSource_socket.Input(ip_address_port="127.0.0.1:1",
                                   data_type="16tle",
                                   sample_rate=1.0, centre_frequency=1.0, input_bw=1.0)
    # but no connection as no server to connect to
    with pytest.raises(ValueError):
        sock.open()


def test_socket_too_few_parts():
    sock = DataSource_socket.Input(ip_address_port="127.0.0.1",
                                   data_type="16tle",
                                   sample_rate=1.0, centre_frequency=1.0, input_bw=1.0)
    with pytest.raises(Exception):
        sock.open()


def test_socket_bad_port_number():
    sock = DataSource_socket.Input(ip_address_port="127.0.0.1:abc",
                                   data_type="16tle",
                                   sample_rate=1.0, centre_frequency=1.0, input_bw=1.0)
    with pytest.raises(Exception):
        sock.open()


def test_socket_negative_port_number():
    sock = DataSource_socket.Input(ip_address_port="127.0.0.1:-1",
                                   data_type="16tle",
                                   sample_rate=1.0, centre_frequency=1.0, input_bw=1.0)
    with pytest.raises(Exception):
        sock.open()


@pytest.mark.skip(reason="Can't test without a someone connecting to the server we create")
def test_socket_is_a_server():
    server = DataSource_socket.Input(ip_address_port=":123",
                                     data_type="16tle",
                                     sample_rate=1.0, centre_frequency=1.0, input_bw=1.0)
    server.open()
    assert server.is_server()


@pytest.mark.skip(reason="Can't test without a server to connect to")
def test_read_cplx_samples():
    """Test requires listening socket and for it to provide at least 4 bytes """
    sock = DataSource_socket.Input(ip_address_port="192.168.0.12:5555",
                                   data_type="16tr",
                                   sample_rate=1.0, centre_frequency=1.0, input_bw=1.0)
    sock.open()
    num_cplx_samples = 1024
    samples, time = sock.read_cplx_samples(num_cplx_samples)
    assert samples.size == num_cplx_samples


def test_unpack_16tle():
    # test data 0.5,-0.25 = 16384,8192 => 0x4000,0xe000 => 0x00,0x40,0x00,0xe0
    data = bytes([0x00, 0x40, 0x00, 0xe0])
    sock = DataSource_socket.Input(ip_address_port="127.0.0.1:1",
                                   data_type="16tle",
                                   sample_rate=1.0, centre_frequency=1.0, input_bw=1.0)
    assert sock.unpack_data(data) == pytest.approx([0.5000076 - 0.2500038j])


def test_unpack_16tbe():
    # test data 0.5,-0.25 = 16384,8192 => 0x4000,0xe000 => 0x40,0x00,0xe0,0x00
    data = bytes([0x40, 0x00, 0xe0, 0x00])
    sock = DataSource_socket.Input(ip_address_port="127.0.0.1:1",
                                   data_type="16tbe",
                                   sample_rate=1.0, centre_frequency=1.0, input_bw=1.0)
    assert sock.unpack_data(data) == pytest.approx([0.5000076 - 0.2500038j])


def test_unpack_8t():
    # test data 0.5,-0.25 = 64,-32 => 0x40,0xe0
    data = bytes([0x40, 0xe0])
    sock = DataSource_socket.Input(ip_address_port="127.0.0.1:1",
                                   data_type="8t",
                                   sample_rate=1.0, centre_frequency=1.0, input_bw=1.0)
    assert sock.unpack_data(data) == pytest.approx([0.5019608 - 0.2509804j])


def test_unpack_8o():
    # test data 0.5,-0.25 = 192,96 => 0xc0,0x60
    data = bytes([0xc0, 0x60])
    sock = DataSource_socket.Input(ip_address_port="127.0.0.1@1",
                                   data_type="8o",
                                   sample_rate=1.0, centre_frequency=1.0, input_bw=1.0)
    assert sock.unpack_data(data) == pytest.approx([0.5019608 - 0.2509804j])
