from __future__ import annotations

import cadquery as cq

from features.gear import GearSpec, build_gear


def test_spur_gear():
    print("Testing Spur Gear...")
    spec = GearSpec(
        number_of_teeth=20,
        module=1.0,
        face_width=5.0,
        pressure_angle_deg=20.0,
        helix_angle_deg=0.0,
        bore_diameter=5.0,
    )
    gear = build_gear(spec)
    print("Spur Gear built successfully.")
    return gear


def test_helical_gear():
    print("Testing Helical Gear...")
    spec = GearSpec(
        number_of_teeth=20,
        module=1.0,
        face_width=10.0,
        pressure_angle_deg=20.0,
        helix_angle_deg=15.0,
        bore_diameter=5.0,
        hub_diameter=10.0,
        hub_length=15.0,
    )
    gear = build_gear(spec)
    print("Helical Gear built successfully.")
    return gear


if __name__ == "__main__":
    try:
        test_spur_gear()
        test_helical_gear()
        print("All tests passed.")
    except Exception as e:
        print(f"Test failed with error: {e}")
        exit(1)
