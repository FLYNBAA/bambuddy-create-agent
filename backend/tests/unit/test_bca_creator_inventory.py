from backend.app.services.creator_inventory import _hex_srgb


def test_creator_inventory_normalizes_rgba_and_rejects_invalid_values():
    assert _hex_srgb("ff0011aa") == "#FF0011"
    assert _hex_srgb("#abcdef") == "#ABCDEF"
    assert _hex_srgb(None) is None
    assert _hex_srgb("not-a-colour") is None
