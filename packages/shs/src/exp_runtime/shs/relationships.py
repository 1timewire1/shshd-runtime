"""SHS relationship feedback sounds, FUN_000a916c."""


def sound(change):
    """FUN_000a916c chooses from both the old and new icon/count."""
    if not change.changed or change.previous_asset not in (3010, 3011, 3012) or change.asset_id < 0:
        return None
    if change.previous_asset == change.asset_id:
        return 8008 if change.count < change.previous_count else 8006 if change.asset_id == 3011 else 8009
    if change.asset_id == 3011:
        return 8006
    if change.asset_id == 3010:
        return 8015
    return 8016 if change.previous_asset == 3010 else 8009
