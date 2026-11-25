def country_history(state, item_id):
    return state.setdefault("histories", {}).setdefault(item_id, [])
