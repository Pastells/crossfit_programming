# backup cyle names
import json


def backup_cycles():
    with open("data/pushjerk_cycles.json", "r") as f:
        data = json.load(f)

    names = {d["cycle_id"]: d["name"] for d in data}

    with open("data/pushjerk_cycles_names.json", "w") as f:
        f.write(json.dumps(names, indent=2))


def restore_cycles():
    with open("data/pushjerk_cycles.json", "r") as f:
        data = json.load(f)

    with open("data/pushjerk_cycles_names.json", "r") as f:
        names = json.load(f)

    for d in data:
        cycle_id = str(d["cycle_id"])
        if cycle_id in names:
            d["name"] = names[cycle_id]
        else:
            print(cycle_id, "not found in names")

    with open("data/pushjerk_cycles.json", "w") as f:
        f.write(json.dumps(data, indent=2))
