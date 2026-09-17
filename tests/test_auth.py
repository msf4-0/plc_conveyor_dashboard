from app.auth import SESSION_MAX_AGE_S, sign_session, verify_session


def test_round_trip():
    token = sign_session("pw", now=1000)
    assert verify_session(token, "pw", now=1000 + SESSION_MAX_AGE_S - 1)


def test_expired_token_rejected():
    token = sign_session("pw", now=0)
    assert not verify_session(token, "pw", now=SESSION_MAX_AGE_S)
    assert verify_session(token, "pw", now=SESSION_MAX_AGE_S - 1)


def test_tampered_signature_rejected():
    token = sign_session("pw", now=1000)
    expiry, _, sig = token.partition(".")
    bad_sig = ("0" if sig[0] != "0" else "1") + sig[1:]
    assert not verify_session(f"{expiry}.{bad_sig}", "pw", now=1001)


def test_cross_password_rejected():
    token = sign_session("pw1", now=1000)
    assert not verify_session(token, "pw2", now=1001)


def test_garbage_cookie_rejected():
    for bad in ("", "garbage", "1000", "1000.", ".abcdef", "abc.def", "12.5.9"):
        assert not verify_session(bad, "pw", now=1001)
