"""How the server is configured: its secret key and where it listens."""

import gfg_main

OLD_PUBLIC_KEY = "hPqPfz!y=moJ!MVO{*tqQO$_Itoo:"


# ---------------------------------------------------------------- secret key

def test_the_signing_key_is_not_the_one_published_in_the_repository():
    """A constant in a public repository lets anyone forge session and CSRF tokens"""
    assert gfg_main.app.config["SECRET_KEY"] != OLD_PUBLIC_KEY


def test_the_key_can_be_fixed_from_the_environment():
    assert gfg_main.secret_key({"GFG_SECRET_KEY": "from-the-environment"}) == "from-the-environment"


def test_without_one_a_strong_random_key_is_made_each_time():
    first, second = gfg_main.secret_key({}), gfg_main.secret_key({})

    assert first != second
    assert len(first) >= 64  # 32 random bytes, hex-encoded


def test_an_empty_key_setting_is_ignored_rather_than_used():
    assert len(gfg_main.secret_key({"GFG_SECRET_KEY": ""})) >= 64


# ---------------------------------------------------------------- where it listens

def test_production_defaults():
    assert gfg_main.server_settings({}) == ("0.0.0.0", 5000, False)


def test_the_debug_server_listens_on_this_machine_only_by_default():
    """Its interactive debugger can run code on the machine"""
    host, port, debug = gfg_main.server_settings({"FLASK_DEBUG": "True"})

    assert (host, debug) == ("127.0.0.1", True)


def test_the_listening_address_can_be_chosen():
    assert gfg_main.server_settings({"GFG_BIND": "192.168.1.10"})[0] == "192.168.1.10"
    assert gfg_main.server_settings({"FLASK_DEBUG": "True", "GFG_BIND": "0.0.0.0"})[0] == "0.0.0.0"
    assert gfg_main.server_settings({"GFG_BIND": ""})[0] == "0.0.0.0"  # empty means "use the default"


def test_ports_behave_as_before():
    assert gfg_main.server_settings({"FLASK_PORT": "8080"})[1] == 8080
    # PORT only ever applied to the debug server
    assert gfg_main.server_settings({"PORT": "9000"})[1] == 5000
    assert gfg_main.server_settings({"FLASK_DEBUG": "True", "PORT": "9000", "FLASK_PORT": "8080"})[1] == 9000
    assert gfg_main.server_settings({"FLASK_DEBUG": "True", "FLASK_PORT": "8080"})[1] == 8080


def test_only_the_exact_value_true_enables_debug():
    for value in ("true", "1", "yes", "False", ""):
        assert gfg_main.server_settings({"FLASK_DEBUG": value})[2] is False
